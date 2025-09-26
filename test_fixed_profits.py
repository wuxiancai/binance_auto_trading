#!/usr/bin/env python3
"""
测试修复后的盈利统计显示功能
"""

import sqlite3
from db import get_conn, init_db
from webapp import get_daily_profits
import json

def test_fixed_profits():
    """测试修复后的盈利统计功能"""
    print("=== 测试修复后的盈利统计功能 ===\n")
    
    # 初始化数据库
    init_db()
    
    # 1. 直接查询数据库验证数据
    print("1. 数据库直接查询结果:")
    conn = get_conn()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT date, trade_count, profit_count, loss_count, profit, profit_rate, total_fees, initial_balance
        FROM daily_profits 
        ORDER BY date DESC 
        LIMIT 3
    """)
    
    results = cur.fetchall()
    for row in results:
        print(f"日期: {row['date']}")
        print(f"  交易次数: {row['trade_count']}")
        print(f"  盈利次数: {row['profit_count']}")
        print(f"  亏损次数: {row['loss_count']}")
        print(f"  净盈利: {row['profit']:.4f}")
        print(f"  利润率: {row['profit_rate']:.2f}%")
        print(f"  总手续费: {row['total_fees']:.4f}")
        print(f"  初始余额: {row['initial_balance']:.4f}")
        print()
    
    conn.close()
    
    # 2. 测试API接口
    print("2. API接口测试结果:")
    try:
        api_result = get_daily_profits()
        if api_result:
            data = json.loads(api_result)
            for item in data[:3]:  # 只显示前3条
                print(f"日期: {item['date']}")
                print(f"  交易次数: {item['trade_count']}")
                print(f"  盈利次数: {item['profit_count']}")
                print(f"  亏损次数: {item['loss_count']}")
                print(f"  净盈利: {item['profit']:.4f}")
                print(f"  利润率: {item['profit_rate']:.2f}%")
                print(f"  总手续费: {item['total_fees']:.4f}")
                if 'initial_balance' in item:
                    print(f"  初始余额: {item['initial_balance']:.4f}")
                print()
        else:
            print("API返回空结果")
    except Exception as e:
        print(f"API测试失败: {e}")
    
    # 3. 验证盈利亏损统计逻辑
    print("3. 验证盈利亏损统计逻辑:")
    conn = get_conn()
    cur = conn.cursor()
    
    # 查看最近的交易记录
    cur.execute("""
        SELECT date(datetime(ts/1000, 'unixepoch')) as trade_date, pnl, fee
        FROM trades 
        WHERE date(datetime(ts/1000, 'unixepoch')) >= '2025-09-25'
        ORDER BY ts DESC
        LIMIT 10
    """)
    
    trades = cur.fetchall()
    print("最近的交易记录:")
    for trade in trades:
        pnl_status = "盈利" if trade['pnl'] > 0 else "亏损" if trade['pnl'] < 0 else "平"
        print(f"  日期: {trade['trade_date']}, 盈亏: {trade['pnl']:.4f} ({pnl_status}), 手续费: {trade['fee']:.4f}")
    
    conn.close()
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_fixed_profits()