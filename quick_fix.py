#!/usr/bin/env python3
"""
快速修复脚本 - 解决常见的"加载中..."问题
"""

import subprocess
import sys
import os
import time

def run_command(cmd, description):
    """运行命令并显示结果"""
    print(f"\n🔧 {description}")
    print(f"执行: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ 成功")
            if result.stdout:
                print(f"输出: {result.stdout.strip()}")
        else:
            print(f"❌ 失败")
            if result.stderr:
                print(f"错误: {result.stderr.strip()}")
        return result.returncode == 0
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        return False

def main():
    print("🚀 开始快速修复...")
    
    # 1. 停止现有进程
    run_command("pkill -f webapp.py", "停止现有webapp进程")
    time.sleep(2)
    
    # 2. 检查并安装依赖
    if not run_command("python3 -c 'import binance'", "检查binance库"):
        print("📦 安装python-binance库...")
        run_command("pip3 install python-binance", "安装python-binance")
    
    # 3. 检查其他依赖
    required_packages = ['websockets', 'pandas', 'numpy', 'flask', 'psutil']
    for package in required_packages:
        if not run_command(f"python3 -c 'import {package}'", f"检查{package}库"):
            run_command(f"pip3 install {package}", f"安装{package}")
    
    # 4. 检查网络连接
    if not run_command("curl -s --connect-timeout 5 https://api.binance.com/api/v3/ping", "测试币安API连接"):
        print("⚠️  网络连接可能有问题，请检查防火墙和网络设置")
    
    # 5. 清理临时文件
    run_command("rm -f webapp.pid debug_output.txt", "清理临时文件")
    
    # 6. 重启webapp
    print("\n🔄 重启webapp...")
    if os.path.exists("webapp.py"):
        # 后台启动webapp
        subprocess.Popen([
            "nohup", "python3", "webapp.py"
        ], stdout=open("webapp.log", "w"), stderr=subprocess.STDOUT)
        
        # 等待启动
        time.sleep(5)
        
        # 检查是否启动成功
        if run_command("curl -s http://localhost:5000/api/system", "测试webapp响应"):
            print("✅ webapp启动成功！")
        else:
            print("❌ webapp启动失败，请检查日志")
    else:
        print("❌ webapp.py文件不存在")
    
    print("\n🎉 快速修复完成！")
    print("如果问题仍然存在，请运行: python3 diagnose_server.py")

if __name__ == "__main__":
    main()