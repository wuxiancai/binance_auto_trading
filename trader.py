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

    async def place_order(self, side: str, qty: float, price: Optional[float] = None):
        ts = int(time.time() * 1000)
        symbol = config.SYMBOL

        # 模拟模式
        if config.SIMULATE or self.client is None:
            # 直接记录交易与仓位
            mark_price = price if price is not None else 0.0
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

    async def close_all(self):
        pos = get_position(config.SYMBOL)
        if not pos:
            return
        side = pos["side"]
        qty = pos["qty"]
        ts = int(time.time() * 1000)
        # 模拟平仓
        add_trade(ts, config.SYMBOL, f"CLOSE_{side}", qty, 0.0, simulate=True)
        close_position(config.SYMBOL)
        log("INFO", "SIM CLOSE POSITION")