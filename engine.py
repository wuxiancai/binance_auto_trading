import asyncio
import json
import time
from typing import Deque, Dict, Any, List, Tuple
from collections import deque

import pandas as pd
import websockets

from config import config
from db import init_db, latest_kline_time, insert_kline, fetch_klines, log
from indicators import bollinger_bands
from trader import Trader

KLINE_WS_URL = "wss://fstream.binance.com/ws"  # futures stream

try:
    from binance.um_futures import UMFutures  # type: ignore
except Exception:  # pragma: no cover
    UMFutures = None  # type: ignore


class Engine:
    def __init__(self):
        init_db()
        self.trader = Trader()
        self.state = "idle"  # idle / breakout_up / breakdown_dn / long / short
        self.prices: Deque[float] = deque(maxlen=1000)
        self.last_price: float = 0.0

    async def bootstrap(self):
        # 如果数据库没有足够K线，使用REST补齐 INITIAL_KLINES（按 SYMBOL+INTERVAL）
        try:
            rows = fetch_klines(config.SYMBOL, limit=config.INITIAL_KLINES)
            if len(rows) >= config.INITIAL_KLINES:
                return
            if UMFutures is None:
                return
            client = UMFutures()  # 公共端点无需密钥
            data = await asyncio.to_thread(
                client.klines, config.SYMBOL, config.INTERVAL, None, None, config.INITIAL_KLINES
            )
            last_time = latest_kline_time(config.SYMBOL, config.INTERVAL) or -1
            inserts: List[Tuple] = []
            for k in data:
                ot, o, h, l, c, v, ct = int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]), int(k[6])
                if ot <= last_time:
                    continue  # 去重
                inserts.append((config.SYMBOL, config.INTERVAL, ot, o, h, l, c, v, ct))
            if inserts:
                insert_kline(inserts)
                log("INFO", f"bootstrap 插入历史K线 {len(inserts)} 条: {config.SYMBOL} {config.INTERVAL}")
            else:
                log("INFO", "bootstrap 无需插入K线（已最新）")
        except Exception as e:  # pragma: no cover
            log("ERROR", f"bootstrap失败: {e}")

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
        mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD, ddof=0)
        last_mid = float(mid.iloc[-1])
        last_up = float(up.iloc[-1])
        last_dn = float(dn.iloc[-1])
        price = float(df["close"].iloc[-1]) if self.last_price == 0 else self.last_price

        # 状态机
        if price > last_up and self.state != "breakout_up":
            self.state = "breakout_up"
            log("INFO", f"突破UP，等待回落到UP：{last_up}")
            return
        if price < last_dn and self.state != "breakdown_dn":
            self.state = "breakdown_dn"
            log("INFO", f"跌破DN，等待反弹到DN：{last_dn}")
            return

        # 回落至UP -> 做空
        if self.state == "breakout_up" and price <= last_up:
            await self.trader.place_order("SELL", config.QUANTITY, price)
            self.state = "short"
            log("INFO", f"回落至UP做空 @ {price}")
            return

        # 反弹至DN -> 做多
        if self.state == "breakdown_dn" and price >= last_dn:
            await self.trader.place_order("BUY", config.QUANTITY, price)
            self.state = "long"
            log("INFO", f"反弹至DN做多 @ {price}")
            return

        # 多仓止损/止盈切空：再次触及UP
        if self.state == "long" and price >= last_up:
            await self.trader.place_order("SELL", config.QUANTITY, price)
            self.state = "short"
            log("INFO", f"多->空（触及UP） @ {price}")
            return

        # 空仓止损/止盈切多：再次触及DN
        if self.state == "short" and price <= last_dn:
            await self.trader.place_order("BUY", config.QUANTITY, price)
            self.state = "long"
            log("INFO", f"空->多（触及DN） @ {price}")
            return


async def main():
    eng = Engine()
    await eng.run_ws()


if __name__ == "__main__":
    asyncio.run(main())