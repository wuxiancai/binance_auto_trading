#!/usr/bin/env bash
set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取应用目录
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

VENV="$APP_DIR/.venv"
PY=${PY:-python3}
SERVICE_NAME="binance-auto-trading"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
USER=$(whoami)

log_info "开始部署币安自动交易系统..."
log_info "应用目录: $APP_DIR"
log_info "当前用户: $USER"

# 检查是否为root用户或有sudo权限
if [[ $EUID -eq 0 ]]; then
    log_warning "检测到root用户，建议使用普通用户运行"
elif ! sudo -n true 2>/dev/null; then
    log_error "需要sudo权限来配置systemd服务"
    log_info "请确保当前用户有sudo权限，或者手动运行: sudo $0"
    exit 1
fi

# 1. 创建虚拟环境和安装依赖
log_info "步骤 1/5: 设置Python虚拟环境..."
if [ ! -d "$VENV" ]; then
    log_info "创建虚拟环境..."
    $PY -m venv "$VENV"
else
    log_info "虚拟环境已存在"
fi

source "$VENV/bin/activate"
log_info "安装/更新依赖..."
pip install -U pip
pip install -r requirements.txt
log_success "Python环境配置完成"

# 2. 创建systemd服务文件
log_info "步骤 2/5: 创建systemd服务文件..."

# 停止现有服务（如果存在）
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    log_info "停止现有服务..."
    sudo systemctl stop "$SERVICE_NAME"
fi

# 创建服务文件
sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Binance Auto Trading System
After=network.target
Wants=network-online.target

[Service]
Type=forking
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
Environment=PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$APP_DIR/start_services.sh
ExecStop=$APP_DIR/stop_services.sh
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

# 安全设置
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

log_success "服务文件创建完成: $SERVICE_FILE"

# 3. 创建启动脚本
log_info "步骤 3/5: 创建服务管理脚本..."

# 创建启动脚本
cat > "$APP_DIR/start_services.sh" << 'EOF'
#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# 激活虚拟环境
source "$APP_DIR/.venv/bin/activate"

# 创建日志目录
mkdir -p "$APP_DIR/logs"

# 启动engine.py
nohup python engine.py > "$APP_DIR/logs/engine.log" 2>&1 &
ENGINE_PID=$!
echo $ENGINE_PID > "$APP_DIR/engine.pid"

# 启动webapp.py
nohup python webapp.py > "$APP_DIR/logs/webapp.log" 2>&1 &
WEBAPP_PID=$!
echo $WEBAPP_PID > "$APP_DIR/webapp.pid"

echo "服务已启动:"
echo "  Engine PID: $ENGINE_PID"
echo "  WebApp PID: $WEBAPP_PID"
echo "  日志目录: $APP_DIR/logs/"
EOF

# 创建停止脚本
cat > "$APP_DIR/stop_services.sh" << 'EOF'
#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

# 停止engine.py
if [ -f "$APP_DIR/engine.pid" ]; then
    ENGINE_PID=$(cat "$APP_DIR/engine.pid")
    if kill -0 "$ENGINE_PID" 2>/dev/null; then
        kill "$ENGINE_PID"
        echo "已停止 Engine (PID: $ENGINE_PID)"
    fi
    rm -f "$APP_DIR/engine.pid"
fi

# 停止webapp.py
if [ -f "$APP_DIR/webapp.pid" ]; then
    WEBAPP_PID=$(cat "$APP_DIR/webapp.pid")
    if kill -0 "$WEBAPP_PID" 2>/dev/null; then
        kill "$WEBAPP_PID"
        echo "已停止 WebApp (PID: $WEBAPP_PID)"
    fi
    rm -f "$APP_DIR/webapp.pid"
fi

echo "所有服务已停止"
EOF

# 设置脚本权限
chmod +x "$APP_DIR/start_services.sh"
chmod +x "$APP_DIR/stop_services.sh"

log_success "服务管理脚本创建完成"

# 4. 重载systemd并启用服务
log_info "步骤 4/5: 配置systemd服务..."
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
log_success "服务已启用，将在系统启动时自动运行"

# 5. 启动服务
log_info "步骤 5/5: 启动服务..."
sudo systemctl start "$SERVICE_NAME"

# 等待服务启动
sleep 3

# 检查服务状态
if systemctl is-active --quiet "$SERVICE_NAME"; then
    log_success "服务启动成功！"
    log_info "服务状态:"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
else
    log_error "服务启动失败！"
    log_info "查看服务状态:"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
    exit 1
fi

echo ""
log_success "🎉 部署完成！"
echo ""
log_info "服务管理命令:"
echo "  启动服务: sudo systemctl start $SERVICE_NAME"
echo "  停止服务: sudo systemctl stop $SERVICE_NAME"
echo "  重启服务: sudo systemctl restart $SERVICE_NAME"
echo "  查看状态: sudo systemctl status $SERVICE_NAME"
echo "  查看日志: sudo journalctl -u $SERVICE_NAME -f"
echo ""
log_info "应用日志位置:"
echo "  Engine日志: $APP_DIR/logs/engine.log"
echo "  WebApp日志: $APP_DIR/logs/webapp.log"
echo ""
log_info "Web界面访问: http://localhost:5000"