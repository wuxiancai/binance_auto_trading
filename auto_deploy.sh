#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

VENV="$APP_DIR/.venv"
PY=${PY:-python3}

# 显示部署帮助信息
show_deployment_help() {
    echo ""
    echo "🔧 部署故障排除指南："
    echo ""
    echo "1. 网络问题："
    echo "   - 检查网络连接：ping pypi.org"
    echo "   - 使用国内镜像：pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/"
    echo ""
    echo "2. 权限问题："
    echo "   - 确保当前用户有写入权限"
    echo "   - 检查磁盘空间：df -h"
    echo ""
    echo "3. Python环境问题："
    echo "   - 检查Python版本：python3 --version"
    echo "   - 确保Python版本 >= 3.8"
    echo ""
    echo "4. 手动安装步骤："
    echo "   source $VENV/bin/activate"
    echo "   pip install --upgrade pip"
    echo "   pip install python-binance pandas flask numpy websockets psutil"
    echo ""
    echo "5. 如果问题持续存在："
    echo "   - 删除虚拟环境：rm -rf $VENV"
    echo "   - 重新运行部署脚本：bash auto_deploy.sh"
    echo ""
}

# 检查系统环境
check_system_requirements() {
    echo "🔍 检查系统环境..."
    
    # 检查Python版本
    if ! command -v "$PY" >/dev/null 2>&1; then
        echo "❌ 错误: 未找到 $PY"
        echo "请安装 Python 3.8 或更高版本"
        exit 1
    fi
    
    local python_version=$($PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "✅ Python 版本: $python_version"
    
    # 检查磁盘空间
    local available_space=$(df . | tail -1 | awk '{print $4}')
    if [ "$available_space" -lt 1048576 ]; then  # 1GB in KB
        echo "⚠️  警告: 可用磁盘空间不足 1GB，可能影响安装"
    fi
    
    # 检查网络连接
    if ! ping -c 1 pypi.org >/dev/null 2>&1; then
        echo "⚠️  警告: 无法连接到 pypi.org，建议使用国内镜像源"
    fi
}

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

# 执行系统环境检查
check_system_requirements

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

# 带重试机制的依赖安装函数
install_dependencies() {
    local max_retries=2
    local retry_count=0
    
    echo "正在升级 pip..."
    while [ $retry_count -le $max_retries ]; do
        if pip install -U pip; then
            echo "✅ pip 升级成功"
            break
        else
            retry_count=$((retry_count + 1))
            if [ $retry_count -le $max_retries ]; then
                echo "⚠️  pip 升级失败，第 $retry_count 次重试..."
                sleep 2
            else
                echo "❌ pip 升级失败，已重试 $max_retries 次"
                echo "请手动运行以下命令："
                echo "  source $VENV/bin/activate"
                echo "  pip install -U pip"
                return 1
            fi
        fi
    done
    
    echo "正在安装项目依赖..."
    retry_count=0
    while [ $retry_count -le $max_retries ]; do
        if pip install -r requirements.txt; then
            echo "✅ 依赖安装成功"
            return 0
        else
            retry_count=$((retry_count + 1))
            if [ $retry_count -le $max_retries ]; then
                echo "⚠️  依赖安装失败，第 $retry_count 次重试..."
                sleep 3
            else
                echo "❌ 依赖安装失败，已重试 $max_retries 次"
                echo ""
                echo "可能的解决方案："
                echo "1. 检查网络连接是否正常"
                echo "2. 手动安装依赖："
                echo "   source $VENV/bin/activate"
                echo "   pip install -r requirements.txt"
                echo "3. 如果某个包安装失败，可以单独安装："
                echo "   pip install python-binance"
                echo "   pip install pandas"
                echo "   pip install flask"
                echo "4. 使用国内镜像源："
                echo "   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/"
                echo ""
                return 1
            fi
        fi
    done
}

# 执行依赖安装
if ! install_dependencies; then
    echo "错误: 依赖安装失败，部署中止"
    show_deployment_help
    exit 1
fi

echo "部署完成。可运行:"
echo "source $VENV/bin/activate && (\n  nohup python engine.py >/dev/null 2>&1 &\n  nohup python webapp.py >/dev/null 2>&1 &\n)"
chmod +x setup_service.sh
bash setup_service.sh