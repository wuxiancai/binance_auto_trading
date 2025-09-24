#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

VENV="$APP_DIR/.venv"
PY=${PY:-python3}

# 检测系统类型并安装必要的依赖
install_venv_deps() {
    echo "检测到需要安装 python3-venv 包..."
    
    # 检测是否为 Debian/Ubuntu 系统
    if command -v apt >/dev/null 2>&1; then
        echo "检测到 Debian/Ubuntu 系统，正在安装 python3-venv..."
        
        # 获取 Python 版本
        PYTHON_VERSION=$($PY --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        VENV_PACKAGE="python${PYTHON_VERSION}-venv"
        
        # 尝试安装 python3-venv 包
        if sudo apt update && sudo apt install -y "$VENV_PACKAGE"; then
            echo "成功安装 $VENV_PACKAGE"
        elif sudo apt install -y python3-venv; then
            echo "成功安装 python3-venv"
        else
            echo "错误: 无法安装 python3-venv 包"
            echo "请手动运行: sudo apt install python3-venv"
            exit 1
        fi
    # 检测是否为 CentOS/RHEL/Fedora 系统
    elif command -v yum >/dev/null 2>&1; then
        echo "检测到 CentOS/RHEL 系统，正在安装 python3-venv..."
        if sudo yum install -y python3-venv; then
            echo "成功安装 python3-venv"
        else
            echo "错误: 无法安装 python3-venv 包"
            echo "请手动运行: sudo yum install python3-venv"
            exit 1
        fi
    elif command -v dnf >/dev/null 2>&1; then
        echo "检测到 Fedora 系统，正在安装 python3-venv..."
        if sudo dnf install -y python3-venv; then
            echo "成功安装 python3-venv"
        else
            echo "错误: 无法安装 python3-venv 包"
            echo "请手动运行: sudo dnf install python3-venv"
            exit 1
        fi
    else
        echo "错误: 无法识别的系统类型，请手动安装 python3-venv 包"
        exit 1
    fi
}

# 创建虚拟环境，如果失败则尝试安装依赖
create_venv() {
    echo "正在创建虚拟环境..."
    echo "使用 Python: $($PY --version)"
    echo "虚拟环境路径: $VENV"
    
    if $PY -m venv "$VENV" 2>&1; then
        echo "虚拟环境创建成功"
        return 0
    else
        echo "虚拟环境创建失败，尝试安装依赖..."
        install_venv_deps
        echo "重新创建虚拟环境..."
        if $PY -m venv "$VENV" 2>&1; then
            echo "虚拟环境创建成功"
            return 0
        else
            echo "错误: 虚拟环境创建失败"
            echo "请检查:"
            echo "1. Python 版本是否支持 venv 模块"
            echo "2. 是否有足够的磁盘空间"
            echo "3. 是否有写入权限"
            return 1
        fi
    fi
}

if [ ! -d "$VENV" ]; then
    if ! create_venv; then
        echo "错误: 无法创建虚拟环境，部署失败"
        exit 1
    fi
fi

# 验证虚拟环境是否正确创建
if [ ! -f "$VENV/bin/activate" ]; then
    echo "错误: 虚拟环境激活脚本不存在，重新创建..."
    rm -rf "$VENV"
    if ! create_venv; then
        echo "错误: 无法创建虚拟环境，部署失败"
        exit 1
    fi
fi

echo "激活虚拟环境..."
source "$VENV/bin/activate"

pip install -U pip
pip install -r requirements.txt

echo "部署完成。可运行:"
echo "source $VENV/bin/activate && (\n  nohup python engine.py >/dev/null 2>&1 &\n  nohup python webapp.py >/dev/null 2>&1 &\n)"
chmod +x setup_service.sh
bash setup_service.sh