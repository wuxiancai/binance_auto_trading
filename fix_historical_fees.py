#!/usr/bin/env python3
"""
修复历史手续费数据脚本
重新计算所有历史交易的手续费并更新数据库
"""

import sqlite3
import os
import sys
from datetime import datetime

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import config
    FEE_RATE = config.config.FEE_RATE
    print(f"使用手续费率: {FEE_RATE} ({FEE_RATE * 100:.3f}%)")
except Exception as e:
    print(f"无法加载配置，使用默认手续费率 0.0005: {e}")
    FEE_RATE = 0.0005

def fix_historical_fees():
    """修复历史手续费数据"""
    print("=== 开始修复历史手续费数据 ===")
    
    try:
        conn = sqlite3.connect('data/trading.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. 获取所有交易记录
        print("\n1. 获取所有交易记录...")
        cursor.execute("SELECT id, symbol, side, qty, price, fee FROM trades ORDER BY ts")
        all_trades = cursor.fetchall()
        print(f"找到 {len(all_trades)} 条交易记录")
        
        # 2. 重新计算每笔交易的手续费
        print("\n2. 重新计算手续费...")
        updated_count = 0
        total_fees_calculated = 0
        
        for trade in all_trades:
            trade_id = trade['id']
            qty = float(trade['qty'])
            price = float(trade['price'])
            current_fee = trade['fee'] if trade['fee'] is not None else 0
            
            # 计算手续费：交易金额 * 手续费率
            trade_amount = qty * price
            calculated_fee = trade_amount * FEE_RATE
            total_fees_calculated += calculated_fee
            
            # 更新数据库中的手续费
            cursor.execute("UPDATE trades SET fee = ? WHERE id = ?", (calculated_fee, trade_id))
            updated_count += 1
            
            if updated_count <= 5:  # 显示前5条作为示例
                print(f"  交易ID {trade_id}: 数量={qty}, 价格={price}, "
                      f"交易金额={trade_amount:.2f}, 手续费={calculated_fee:.6f}")
        
        print(f"已更新 {updated_count} 条交易记录的手续费")
        print(f"计算出的总手续费: {total_fees_calculated:.6f}")
        
        # 3. 重新计算每日盈利统计中的手续费
        print("\n3. 重新计算每日盈利统计...")
        
        # 获取所有有交易的日期
        cursor.execute("""
            SELECT date(datetime(ts, 'unixepoch')) as trade_date, 
                   COUNT(*) as trade_count,
                   SUM(fee) as daily_fees
            FROM trades 
            GROUP BY trade_date 
            ORDER BY trade_date
        """)
        
        daily_stats = cursor.fetchall()
        print(f"找到 {len(daily_stats)} 个交易日")
        
        # 更新daily_profits表中的total_fees
        for day_stat in daily_stats:
            trade_date = day_stat['trade_date']
            daily_fees = day_stat['daily_fees']
            
            # 检查daily_profits表中是否有该日期的记录
            cursor.execute("SELECT id FROM daily_profits WHERE date = ?", (trade_date,))
            existing_record = cursor.fetchone()
            
            if existing_record:
                # 更新现有记录的total_fees
                cursor.execute("UPDATE daily_profits SET total_fees = ? WHERE date = ?", 
                             (daily_fees, trade_date))
                print(f"  更新 {trade_date}: 手续费 {daily_fees:.6f}")
            else:
                # 如果没有记录，创建一个基本记录
                cursor.execute("""
                    INSERT INTO daily_profits (date, trade_count, profit, profit_rate, loss_count, profit_count, total_fees)
                    VALUES (?, ?, 0, 0, 0, 0, ?)
                """, (trade_date, day_stat['trade_count'], daily_fees))
                print(f"  创建 {trade_date}: 交易数 {day_stat['trade_count']}, 手续费 {daily_fees:.6f}")
        
        # 4. 提交所有更改
        conn.commit()
        print("\n4. 所有更改已提交到数据库")
        
        # 5. 验证修复结果
        print("\n5. 验证修复结果...")
        
        # 检查trades表
        cursor.execute("SELECT COUNT(*) as total, COUNT(fee) as with_fee, SUM(fee) as total_fees FROM trades")
        trade_stats = cursor.fetchone()
        print(f"  交易记录统计: 总数={trade_stats['total']}, 有手续费={trade_stats['with_fee']}, 总手续费={trade_stats['total_fees']:.6f}")
        
        # 检查daily_profits表
        cursor.execute("SELECT COUNT(*) as total, SUM(total_fees) as total_fees FROM daily_profits WHERE total_fees IS NOT NULL")
        profit_stats = cursor.fetchone()
        print(f"  盈利记录统计: 有手续费记录数={profit_stats['total']}, 总手续费={profit_stats['total_fees']:.6f}")
        
        # 检查今日数据
        today = datetime.now().date().isoformat()
        cursor.execute("SELECT trade_count, total_fees FROM daily_profits WHERE date = ?", (today,))
        today_data = cursor.fetchone()
        if today_data:
            print(f"  今日数据: 交易数={today_data['trade_count']}, 手续费={today_data['total_fees']:.6f}")
        else:
            print("  今日暂无盈利记录")
        
        conn.close()
        
        print("\n=== 修复完成 ===")
        print("请重启Web服务以查看更新后的手续费显示")
        
    except Exception as e:
        print(f"修复过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_historical_fees()