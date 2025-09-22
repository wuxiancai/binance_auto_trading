#!/usr/bin/env python3
"""
更新历史交易记录的盈亏数据
"""
import sqlite3
from db import get_conn

def update_historical_pnl():
    conn = get_conn()
    cur = conn.cursor()
    
    # 先清空之前的pnl数据
    cur.execute('UPDATE trades SET pnl = 0.0 WHERE side LIKE "CLOSE_%"')
    
    # 获取所有交易记录，按时间排序
    cur.execute('SELECT id, ts, side, qty, price FROM trades ORDER BY ts')
    trades = cur.fetchall()
    
    # 用于跟踪持仓
    positions = {}  # symbol -> {side, qty, entry_price, entry_ts}
    
    for trade in trades:
        trade_id, ts, side, qty, price = trade
        symbol = 'BTCUSDT'  # 假设都是BTCUSDT
        
        if side in ['BUY', 'SELL']:
            # 开仓
            direction = 'long' if side == 'BUY' else 'short'
            positions[symbol] = {
                'side': direction,
                'qty': qty,
                'entry_price': price,
                'entry_ts': ts
            }
            print(f'开仓: {direction} {qty:.6f} @ {price}')
            
        elif side.startswith('CLOSE_'):
            # 平仓
            if symbol in positions:
                pos = positions[symbol]
                direction = side.split('_')[1].lower()
                
                # 计算盈亏
                if direction == 'short':
                    pnl = (pos['entry_price'] - price) * qty
                else:  # long
                    pnl = (price - pos['entry_price']) * qty
                
                # 更新数据库
                cur.execute('UPDATE trades SET pnl = ? WHERE id = ?', (pnl, trade_id))
                print(f'平仓: {direction} {qty:.6f} @ {price}, 开仓价: {pos["entry_price"]}, 盈亏: {pnl:.2f}')
                
                # 清除持仓
                del positions[symbol]
    
    conn.commit()
    conn.close()
    print('历史盈亏数据更新完成')

if __name__ == '__main__':
    update_historical_pnl()