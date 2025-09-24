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
if [ ! -d "$VENV" ]; then
    echo "正在创建虚拟环境..."
    if ! $PY -m venv "$VENV" 2>/dev/null; then
        echo "虚拟环境创建失败，尝试安装依赖..."
        install_venv_deps
        echo "重新创建虚拟环境..."
        $PY -m venv "$VENV"
    fi
fi
source "$VENV/bin/activate"

pip install -U pip
pip install -r requirements.txt

echo "部署完成。可运行:"
echo "source $VENV/bin/activate && (\n  nohup python engine.py >/dev/null 2>&1 &\n  nohup python webapp.py >/dev/null 2>&1 &\n)"
chmod +x setup_service.sh
bash setup_service.sh