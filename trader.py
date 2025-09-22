import asyncio
import time
from typing import Optional, Dict, Any

from config import config
from db import add_trade, set_position, get_position, close_position, log

try:
    from binance.um_futures import UMFutures  # type: ignore
except Exception:  # pragma: no cover
    UMFutures = None


class Trader:
    def __init__(self):
        self.client = None
        if not config.SIMULATE and UMFutures is not None and config.API_KEY:
            base_url = "https://testnet.binancefuture.com" if config.USE_TESTNET else None
            self.client = UMFutures(key=config.API_KEY, secret=config.API_SECRET, base_url=base_url)
        self.sim_balance = config.DEFAULT_MARGIN if config.SIMULATE else 0.0

    async def place_order(self, side: str, qty: float, price: Optional[float] = None):
        ts = int(time.time() * 1000)
        symbol = config.SYMBOL

        # 模拟模式
        if config.SIMULATE or self.client is None:
            # 直接记录交易与仓位
            mark_price = price if price is not None else 0.0
            margin = (qty * mark_price) / config.LEVERAGE
            self.sim_balance -= margin
            add_trade(ts, symbol, side, qty, mark_price, simulate=True)
            # 更新仓位
            if side == "BUY":
                set_position(symbol, "long", qty, mark_price, ts)
            elif side == "SELL":
                set_position(symbol, "short", qty, mark_price, ts)
            log("INFO", f"SIM ORDER {side} {qty} @ {mark_price}")
            return {"simulate": True, "side": side, "qty": qty, "price": mark_price}

        # 实盘
        try:
            params: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": qty,
            }
            res = self.client.new_order(**params)
            avg_price = float(res.get("avgPrice", 0)) if isinstance(res, dict) else 0.0
            add_trade(ts, symbol, side, qty, avg_price, simulate=False)
            if side == "BUY":
                set_position(symbol, "long", qty, avg_price, ts)
            else:
                set_position(symbol, "short", qty, avg_price, ts)
            log("INFO", f"REAL ORDER {side} {qty} @ {avg_price}")
            return res
        except Exception as e:  # pragma: no cover
            log("ERROR", f"order failed: {e}")
            return {"error": str(e)}

    async def close_all(self, current_price: Optional[float] = None) -> float:
        pos = get_position(config.SYMBOL)
        if not pos:
            return 0.0
        side = pos["side"]
        qty = pos["qty"]
        ts = int(time.time() * 1000)
        symbol = config.SYMBOL
        close_side = "SELL" if side == "long" else "BUY"

        # 模拟平仓
        if config.SIMULATE or self.client is None:
            exit_price = current_price if current_price is not None else 0.0
            pnl = (exit_price - pos["entry_price"]) * qty if side == "long" else (pos["entry_price"] - exit_price) * qty
            margin = (qty * pos["entry_price"]) / config.LEVERAGE
            self.sim_balance += margin + pnl
            add_trade(ts, symbol, f"CLOSE_{side.upper()}", qty, exit_price, simulate=True)
            close_position(symbol)
            log("INFO", f"SIM CLOSE {side} {qty} @ {exit_price}")
            return exit_price

        # 实盘平仓
        try:
            params = {
                "symbol": symbol,
                "side": close_side,
                "type": "MARKET",
                "quantity": qty,
                "reduceOnly": True,
            }
            res = self.client.new_order(**params)
            exit_price = float(res.get("avgPrice", 0))
            add_trade(ts, symbol, f"CLOSE_{side.upper()}", qty, exit_price, simulate=False)
            close_position(symbol)
            log("INFO", f"REAL CLOSE {side} {qty} @ {exit_price}")
            return exit_price
        except Exception as e:  # pragma: no cover
            log("ERROR", f"close failed: {e}")
            return 0.0

    def get_balance(self) -> float:
        if config.SIMULATE or self.client is None:
            return self.sim_balance  # 模拟初始余额
        try:
            acc = self.client.account()
            return float(acc['availableBalance'])
        except Exception as e:
            log("ERROR", f"Failed to get balance: {e}")
            return 0.0