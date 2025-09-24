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
        if UMFutures is not None and config.API_KEY:
            if config.USE_TESTNET:
                # 对于测试网，需要使用不同的初始化方式
                self.client = UMFutures(key=config.API_KEY, secret=config.API_SECRET, base_url="https://testnet.binancefuture.com")
            else:
                # 对于主网，使用默认初始化
                self.client = UMFutures(key=config.API_KEY, secret=config.API_SECRET)

    async def place_order(self, side: str, qty: float, price: Optional[float] = None):
        ts = int(time.time() * 1000)
        symbol = config.SYMBOL

        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return {"error": "Binance client not initialized"}

        # 处理数量精度，BTCUSDT通常是3位小数
        qty = round(qty, 3)
        
        # 确保数量大于最小值
        if qty < 0.001:
            log("WARNING", f"Order quantity {qty} is too small, minimum is 0.001")
            return {"error": "Quantity too small"}

        # 真实交易
        try:
            # 根据交易方向设置持仓方向
            position_side = "LONG" if side == "BUY" else "SHORT"
            
            params: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": qty,
                "positionSide": position_side,
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

        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return 0.0

        # 处理数量精度，BTCUSDT通常是3位小数
        qty = round(qty, 3)
        
        # 确保数量大于最小值
        if qty < 0.001:
            log("WARNING", f"Close quantity {qty} is too small, minimum is 0.001")
            return 0.0

        # 真实平仓
        try:
            # 根据持仓方向设置positionSide
            position_side = "LONG" if side == "long" else "SHORT"
            
            params = {
                "symbol": symbol,
                "side": close_side,
                "type": "MARKET",
                "quantity": qty,
                "positionSide": position_side,
                "reduceOnly": True,
            }
            res = self.client.new_order(**params)
            exit_price = float(res.get("avgPrice", 0))
            pnl = (exit_price - pos["entry_price"]) * qty if side == "long" else (pos["entry_price"] - exit_price) * qty
            add_trade(ts, symbol, f"CLOSE_{side.upper()}", qty, exit_price, pnl, simulate=False)
            close_position(symbol)
            log("INFO", f"REAL CLOSE {side} {qty} @ {exit_price}")
            return exit_price
        except Exception as e:  # pragma: no cover
            log("ERROR", f"close failed: {e}")
            return 0.0

    def get_balance(self) -> float:
        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return 0.0
        try:
            # 使用balance()方法获取余额信息
            balance_info = self.client.balance()
            if balance_info is None:
                log("ERROR", "Failed to get balance: balance() returned None")
                return 0.0
            
            # 查找USDT余额
            usdt_balance = None
            for item in balance_info:
                if item.get('asset') == 'USDT':
                    usdt_balance = float(item.get('balance', 0))
                    break
            
            if usdt_balance is None:
                log("ERROR", "Failed to get USDT balance from balance info")
                return 0.0
            
            return usdt_balance
        except Exception as e:
            log("ERROR", f"Failed to get balance: {str(e)}")
            return 0.0

    def get_positions(self):
        """获取实际持仓信息"""
        if self.client is None:
            log("ERROR", "Binance client not initialized")
            return []
        
        try:
            positions = self.client.get_position_risk()
            if positions is None:
                log("ERROR", "Failed to get positions: get_position_risk() returned None")
                return []
            
            # 只返回有持仓的交易对
            active_positions = []
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    active_positions.append(pos)
            return active_positions
        except Exception as e:
            log("ERROR", f"Failed to get positions: {str(e)}")
            return []