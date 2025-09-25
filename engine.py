import asyncio
import json
import time
from typing import Deque, Dict, Any, List, Tuple
from collections import deque

import pandas as pd
import websockets

from config import config
from db import init_db, latest_kline_time, insert_kline, fetch_klines, log, get_position, get_daily_profit, update_daily_profit
from indicators import bollinger_bands
from trader import Trader
from datetime import datetime

KLINE_WS_URL = "wss://fstream.binance.com/ws"  # futures stream

try:
    from binance.client import Client as UMFutures  # type: ignore
except ImportError:
    try:
        from binance.um_futures import UMFutures  # type: ignore
    except ImportError:  # pragma: no cover
        UMFutures = None  # type: ignore


class Engine:
    def __init__(self):
        init_db()
        self.trader = Trader()
        self.initial_balance = self.trader.get_balance()
        pos = get_position(config.SYMBOL)
        self.initial_capital = self.initial_balance
        self.state = "idle"  # idle / breakout_up / breakdown_dn / long / short
        self.prices: Deque[float] = deque(maxlen=1000)
        self.last_price: float = 0.0
        # 评估频率节流（用于未收盘K线内的即时评估）
        self._last_eval_ts: float = 0.0
        self.socketio = None
        self.last_trade_time = 0  # 上次交易时间戳
        self.trade_cooldown = 60000  # 交易冷却时间60秒(毫秒)
        self.last_action_price = 0  # 上次动作价格
        self.price_threshold = 0.001  # 价格变化阈值(0.1%)

        if pos and (pos.get("side") in ("long", "short")):
            self.state = pos["side"]
            log("INFO", f"恢复状态为 {self.state}（检测到已有持仓）")

    async def bootstrap(self):
        try:
            if UMFutures is None:
                print("UMFutures 未导入，无法获取历史 K 线。")
                return
        
            client = UMFutures()  # 公共端点无需密钥
        
            def get_interval_ms(itv: str) -> int:
                num = int(itv[:-1])
                unit = itv[-1]
                if unit == 'm':
                    return num * 60000
                elif unit == 'h':
                    return num * 3600000
                elif unit == 'd':
                    return num * 86400000
                else:
                    raise ValueError(f"Unsupported interval: {itv}")
        
            interval_ms = get_interval_ms(config.INTERVAL)
            last_time = latest_kline_time(config.SYMBOL, config.INTERVAL) or 0
            current_time = int(time.time() * 1000)
        
            if last_time >= current_time - interval_ms:
                print("K 线数据已是最新，无需补齐。")
                return
        
            # 如果数据库为空，先获取初始 K 线
            all_inserts: List[Tuple] = []
            if last_time == 0:
                data = await asyncio.to_thread(
                    client.futures_klines, symbol=config.SYMBOL, interval=config.INTERVAL, limit=config.INITIAL_KLINES
                )
                print(f"从 API 获取到 {len(data)} 条初始 K 线数据。")
                for k in data:
                    ot = int(k[0])
                    o, h, l, c, v, ct = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]), int(k[6])
                    all_inserts.append((config.SYMBOL, config.INTERVAL, ot, o, h, l, c, v, ct))
                if data:
                    last_time = max(int(d[0]) for d in data)
        
            # 补齐缺失 K 线
            start_time = last_time + 1
            while start_time < current_time - interval_ms:  # 只补齐到上一个已收盘 K 线
                data = await asyncio.to_thread(
                    client.futures_klines, symbol=config.SYMBOL, interval=config.INTERVAL, startTime=start_time, limit=500
                )
                if not data:
                    break
                print(f"从 API 获取到 {len(data)} 条补齐 K 线数据（从 {start_time} 开始）。")
                for k in data:
                    ot = int(k[0])
                    if ot <= last_time:
                        continue
                    o, h, l, c, v, ct = float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]), int(k[6])
                    all_inserts.append((config.SYMBOL, config.INTERVAL, ot, o, h, l, c, v, ct))
                    last_time = ot
                start_time = last_time + 1
                if len(data) < 500:
                    break
        
            if all_inserts:
                insert_kline(all_inserts)
                log("INFO", f"bootstrap 插入/补齐 {len(all_inserts)} 条 K 线: {config.SYMBOL} {config.INTERVAL}")
                print(f"插入/补齐 {len(all_inserts)} 条 K 线。")
            else:
                log("INFO", "bootstrap 无需插入K线（已最新）")
                print("无需插入 K 线。")
        except Exception as e:  # pragma: no cover
            log("ERROR", f"bootstrap失败: {e}")
            print(f"bootstrap 失败: {e}")

    async def run_ws(self):
        await self.bootstrap()
        stream = f"{config.SYMBOL.lower()}@kline_{config.INTERVAL}"
        url = f"{KLINE_WS_URL}/{stream}"
        while True:
            try:
                async with websockets.connect(url, ping_interval=15, ping_timeout=15, max_queue=1000) as ws:
                    await self._consume(ws)
            except Exception as e:  # pragma: no cover
                log("ERROR", f"ws error: {e}")
                await asyncio.sleep(3)
                continue

    async def _consume(self, ws):
        async for msg in ws:
            data = json.loads(msg)
            k = data.get("k", {})
            is_closed = k.get("x", False)
            price = float(k.get("c", 0))
            open_time = int(k.get("t", 0))
            close = float(k.get("c", 0))
            high = float(k.get("h", 0))
            low = float(k.get("l", 0))
            open_ = float(k.get("o", 0))
            volume = float(k.get("v", 0))

            self.last_price = price
            self.prices.append(price)
            if self.socketio:
                self.socketio.emit('price_update', {'price': price})

            # 在未收盘期间也进行节流评估，以便尽早产生“突破/跌破”信号
            now = time.time()
            if now - self._last_eval_ts >= 1.0:  # 每秒最多一次
                self._last_eval_ts = now
                await self.evaluate()

            if is_closed:
                insert_kline([
                    (
                        config.SYMBOL,
                        config.INTERVAL,
                        open_time,
                        open_,
                        high,
                        low,
                        close,
                        volume,
                        open_time + 1,
                    )
                ])
                await self.evaluate()

    async def evaluate(self):
        rows = fetch_klines(config.SYMBOL, limit=max(60, config.BOLL_PERIOD + 5))
        if len(rows) < config.BOLL_PERIOD:
            return
        df = pd.DataFrame(rows)
        # 计算基于闭合 K 线的 BOLL，以匹配 Binance 显示
        mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=0)
        last_mid = float(mid.iloc[-1])
        last_up = float(up.iloc[-1])
        last_dn = float(dn.iloc[-1])
        
        # 使用K线收盘价而不是实时价格进行比较
        close_price = float(df["close"].iloc[-1])
        current_price = float(self.last_price) if self.last_price != 0 else close_price
        
        if self.socketio:
            self.socketio.emit('boll_update', {
                'boll_up': last_up, 
                'boll_mid': last_mid, 
                'boll_dn': last_dn,
                'close_price': close_price,
                'current_price': current_price
            })

        # 先处理"持仓期间"的止盈/止损，避免在已有持仓时再次开仓
        # 多仓：收盘价跌破DN -> 先平多，然后进入"跌破DN"状态等待反弹确认
        if self.state == "long" and close_price < last_dn:
            close_success = await self.close_and_update_profit(current_price)
            if close_success:
                self.state = "breakdown_dn"
                log("INFO", f"多仓止损，收盘价跌破DN({last_dn:.2f}) -> 等待反弹至DN")
            else:
                log("ERROR", f"多仓止损失败，保持long状态")
            return

        # 多仓止盈：收盘价再次触及UP时先平仓，进入等待回落确认开空
        if self.state == "long" and close_price >= last_up:
            close_success = await self.close_and_update_profit(current_price)
            if close_success:
                self.state = "breakout_up"  # 进入等待回落确认开空的状态
                log("INFO", f"多仓止盈（收盘价触及UP {last_up:.2f}），已平仓，等待回落至UP再考虑开空")
            else:
                log("ERROR", f"多仓止盈失败，保持long状态")
            return

        # 空仓：收盘价突破UP -> 先平空，然后进入"突破UP"状态等待回落确认确认
        if self.state == "short" and close_price > last_up:
            close_success = await self.close_and_update_profit(current_price)
            if close_success:
                self.state = "breakout_up"
                log("INFO", f"空仓止损，收盘价突破UP({last_up:.2f}) -> 等待回落至UP")
            else:
                log("ERROR", f"空仓止损失败，保持short状态")
            return

        # 空仓止盈：收盘价再次触及DN时先平仓，进入等待反弹确认开多
        if self.state == "short" and close_price <= last_dn:
            close_success = await self.close_and_update_profit(current_price)
            if close_success:
                self.state = "breakdown_dn"  # 进入等待反弹确认开多的状态
                log("INFO", f"空仓止盈（收盘价触及DN {last_dn:.2f}），已平仓，等待反弹至DN再考虑开多")
            else:
                log("ERROR", f"空仓止盈失败，保持short状态")
            return

        # 状态机（允许在当前K线内完成"确认"）
        if close_price > last_up and self.state != "breakout_up":
            # 检查价格变化是否足够大
            if self.last_action_price > 0 and abs(close_price - self.last_action_price) / self.last_action_price < self.price_threshold:
                return
            self.last_action_price = close_price
            self.state = "breakout_up"
            log("INFO", f"收盘价突破UP，等待回落到UP：{last_up}")
            return
        if close_price < last_dn and self.state != "breakdown_dn":
            # 检查价格变化是否足够大
            if self.last_action_price > 0 and abs(close_price - self.last_action_price) / self.last_action_price < self.price_threshold:
                return
            self.last_action_price = close_price
            self.state = "breakdown_dn"
            log("INFO", f"收盘价跌破DN，等待反弹到DN：{last_dn}")
            return

        # 回落至UP -> 做空
        if self.state == "breakout_up" and close_price <= last_up:
            current_time = int(time.time() * 1000)
            if current_time - self.last_trade_time < self.trade_cooldown:
                log("INFO", f"交易冷却中，距离上次交易{(current_time - self.last_trade_time)/1000:.1f}秒")
                return
            balance = self.trader.get_balance()
            if balance <= 0 or current_price <= 0 or config.LEVERAGE <= 0:
                log("WARNING", "Insufficient balance, invalid price, or invalid leverage for order")
                return
            margin = balance * config.TRADE_PERCENT
            qty = margin * config.LEVERAGE / current_price
            await self.trader.place_order("SELL", qty, current_price)
            self.last_trade_time = current_time
            self.state = "short"
            log("INFO", f"收盘价回落至UP开空 {qty} @ {current_price}")
            return

        # 反弹至DN -> 做多
        if self.state == "breakdown_dn" and close_price >= last_dn:
            current_time = int(time.time() * 1000)
            if current_time - self.last_trade_time < self.trade_cooldown:
                log("INFO", f"交易冷却中，距离上次交易{(current_time - self.last_trade_time)/1000:.1f}秒")
                return
            balance = self.trader.get_balance()
            if balance <= 0 or current_price <= 0 or config.LEVERAGE <= 0:
                log("WARNING", "Insufficient balance, invalid price, or invalid leverage for order")
                return
            margin = balance * config.TRADE_PERCENT
            qty = margin * config.LEVERAGE / current_price
            await self.trader.place_order("BUY", qty, current_price)
            self.last_trade_time = current_time
            self.state = "long"
            log("INFO", f"收盘价反弹至DN开多 {qty} @ {current_price}")
            return



    async def close_and_update_profit(self, price: float):
        pos = get_position(config.SYMBOL)
        if not pos:
            return True  # 没有持仓，认为是成功的
        side = pos['side']
        entry_price = pos['entry_price']
        qty = pos['qty']
        exit_price = await self.trader.close_all(price)
        if exit_price <= 0:
            log("ERROR", f"平仓失败，exit_price={exit_price}")
            return False  # 平仓失败
        this_profit = (exit_price - entry_price) * qty if side == 'long' else (entry_price - exit_price) * qty
        date = datetime.now().date().isoformat()
        daily = get_daily_profit(date)
        if daily is None:
            daily = {'trade_count': 0, 'profit': 0.0, 'profit_rate': 0.0, 'loss_count': 0, 'profit_count': 0}
        
        # 更新交易次数和总盈利
        daily['trade_count'] += 1
        daily['profit'] += this_profit
        
        # 计算当日手续费总和
        from db import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT SUM(fee) FROM trades WHERE date(datetime(ts, 'unixepoch')) = ?", (date,))
        total_fees_result = cur.fetchone()
        total_fees = total_fees_result[0] if total_fees_result and total_fees_result[0] else 0.0
        conn.close()
        
        # 计算净利润（扣除手续费后的利润）
        net_profit = daily['profit'] - total_fees
        
        # 统计盈利和亏损次数（基于净利润）
        if net_profit > 0:
            daily['profit_count'] = daily.get('profit_count', 0) + 1
        elif net_profit < 0:
            daily['loss_count'] = daily.get('loss_count', 0) + 1
        
        current_balance = self.trader.get_balance()
        if self.initial_capital > 0:
            daily['profit_rate'] = ((current_balance - self.initial_balance) / self.initial_capital) * 100
        else:
            daily['profit_rate'] = 0.0
        
        update_daily_profit(date, daily['trade_count'], net_profit, daily['profit_rate'], 
                          daily.get('loss_count', 0), daily.get('profit_count', 0), total_fees)
        
        log("INFO", f"平仓成功，使用收盘价策略无需冷却期")
        
        return True  # 平仓成功


async def main():
    eng = Engine()
    await eng.run_ws()


if __name__ == "__main__":
    asyncio.run(main())