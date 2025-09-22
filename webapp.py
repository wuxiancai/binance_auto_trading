import threading
import time
import psutil
import os
import socket
import asyncio
from flask import Flask, render_template_string, jsonify
import logging

from config import config
from db import get_conn, init_db, latest_kline_time, get_position, get_daily_profits
from engine import Engine
from indicators import bollinger_bands
import pandas as pd
from db import fetch_klines

init_db()

app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# 工具：UTC+8 时间格式（月-日 时:分）
def fmt_ts_utc8(ts_ms: int) -> str:
    return time.strftime('%m-%d %H:%M', time.gmtime(ts_ms / 1000 + 8 * 3600))

TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>自动交易监控</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500;600&display=swap" rel="stylesheet">

  <style>
    :root {
      /* 中国水墨山水色彩 */
      --ink-black: #2c3e50;        /* 墨黑 */
      --ink-gray: #34495e;         /* 墨灰 */
      --mist-gray: #95a5a6;        /* 雾灰 */
      --cloud-white: #ecf0f1;      /* 云白 */
      --mountain-blue: #7fb3d3;    /* 山青 */
      --water-blue: #a8d8ea;       /* 水蓝 */
      --bamboo-green: #52c41a;     /* 竹绿 */
      --sunset-red: #ff7875;       /* 夕红 */
      --paper-bg: #fafbfc;         /* 宣纸背景 */
      --card-bg: rgba(255, 255, 255, 0.85); /* 半透明卡片 */
    }

    * {
      font-family: 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    body {
      background: linear-gradient(135deg, var(--paper-bg) 0%, var(--cloud-white) 100%);
      padding: 16px;
      font-size: 13px;
      color: var(--ink-black);
      min-height: 100vh;
    }

    .container {
      max-width: 1400px;
    }

    h3 {
      color: var(--ink-black);
      font-weight: 500;
      font-size: 1.4rem;
      letter-spacing: 0.5px;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid rgba(151, 165, 166, 0.2);
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(44, 62, 80, 0.08);
      backdrop-filter: blur(10px);
      transition: all 0.3s ease;
    }

    .card:hover {
      box-shadow: 0 4px 16px rgba(44, 62, 80, 0.12);
      transform: translateY(-1px);
    }

    .card-header {
      background: linear-gradient(90deg, var(--mountain-blue), var(--water-blue));
      color: white;
      border-bottom: none;
      font-weight: 500;
      font-size: 13px;
      padding: 10px 16px;
      border-radius: 8px 8px 0 0 !important;
    }

    .card-body {
      padding: 14px 16px;
      font-size: 12px;
      line-height: 1.6;
    }

    .card-body > div {
      margin-bottom: 6px;
      color: var(--ink-gray);
    }

    .card-body > div:last-child {
      margin-bottom: 0;
    }

    .row {
      --bs-gutter-x: 12px;
      --bs-gutter-y: 12px;
    }

    .metric {
      font-size: 1rem;
      font-weight: 500;
    }

    .log {
      white-space: pre-wrap;
      max-height: 280px;
      overflow: auto;
      background: var(--paper-bg);
      border: 1px solid rgba(151, 165, 166, 0.15);
      border-radius: 6px;
      padding: 10px;
      font-family: 'Courier New', monospace;
      font-size: 11px;
      color: var(--ink-gray);
      line-height: 1.4;
    }

    .table-sm {
      font-size: 11px;
    }

    .table-sm td, .table-sm th {
      padding: 6px 8px;
      border-color: rgba(151, 165, 166, 0.15);
      color: var(--ink-gray);
    }

    .table-sm th {
      background: var(--cloud-white);
      font-weight: 500;
      color: var(--ink-black);
    }

    .list-group-item {
      background: transparent;
      border: none;
      border-bottom: 1px solid rgba(151, 165, 166, 0.1);
      padding: 8px 0;
      font-size: 11px;
      color: var(--ink-gray);
      line-height: 1.5;
    }

    .list-group-item:last-child {
      border-bottom: none;
    }

    .text-success {
      color: var(--bamboo-green) !important;
      font-weight: 500;
    }

    .text-danger {
      color: var(--sunset-red) !important;
      font-weight: 500;
    }

    .text-muted {
      color: var(--mist-gray) !important;
    }

    /* 系统信息在标题行内单行展示 */
    #sysline {
      font-size: clamp(9px, 1.6vw, 12px);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: var(--mist-gray);
      font-weight: 300;
    }

    /* 响应式优化 */
    @media (max-width: 768px) {
      body {
        padding: 12px;
        font-size: 12px;
      }
      
      h3 {
        font-size: 1.2rem;
      }
      
      .card-body {
        padding: 12px;
        font-size: 11px;
      }
      
      .log {
        max-height: 200px;
        font-size: 10px;
      }
    }

    /* 滚动条美化 */
    ::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }

    ::-webkit-scrollbar-track {
      background: var(--cloud-white);
      border-radius: 3px;
    }

    ::-webkit-scrollbar-thumb {
      background: var(--mist-gray);
      border-radius: 3px;
    }

    ::-webkit-scrollbar-thumb:hover {
      background: var(--ink-gray);
    }

    /* 数值高亮 */
    #balance {
      color: var(--bamboo-green);
      font-weight: 500;
    }

    /* 卡片内容间距优化 */
    .my-3 {
      margin-top: 12px !important;
      margin-bottom: 12px !important;
    }

    .mt-2 {
      margin-top: 8px !important;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="d-flex flex-wrap justify-content-between align-items-center my-3 gap-2">
      <h3 class="mb-0">币安合约自动交易 - 监控</h3>
      <div id="sysline" class="text-muted"></div>
    </div>
    <div class="row g-3">
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">配置</div>
          <div class="card-body">
            <div>交易币对: {{ cfg.SYMBOL }}</div>
            <div>K 线周期: {{ cfg.INTERVAL }}</div>
            <div>BOLL: P={{ cfg.BOLL_PERIOD }} STD={{ cfg.BOLL_STD }}</div>
            <div>保证金余额: <span id="balance">加载中...</span> USDT</div>
            <div>默认买入仓位: {{ cfg.TRADE_PERCENT * 100 }}% 杠杆: {{ cfg.LEVERAGE }}X</div>
            <div>模拟: {{ cfg.SIMULATE }}</div>
            <div>自动重启: {{ cfg.AUTO_RESTART }}</div>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">持仓</div>
          <div class="card-body" id="pos">加载中...</div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">实时币价和实时 BOLL</div>
          <div class="card-body" id="price_boll">加载中...</div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">盈利</div>
          <div class="card-body">
            <table class="table table-sm">
              <thead>
                <tr><th>日期</th><th>交易次数</th><th>盈利</th><th>利润率</th></tr>
              </thead>
              <tbody id="profits"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <div class="row g-3 mt-2">
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">交易记录</div>
          <div class="card-body">
            <ul id="trades" class="list-group list-group-flush"></ul>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">系统日志</div>
          <div class="card-body"><div id="logs" class="log">加载中...</div></div>
        </div>
      </div>
    </div>
  </div>
<script>
async function fetchJSON(url){ const r = await fetch(url); return r.json(); }
function fmt2(v){ return Number(v).toFixed(2); }

let current_price = 0;
let current_boll = {boll_up: 0, boll_mid: 0, boll_dn: 0};

function updatePriceBoll() {
  const pbDiv = document.getElementById('price_boll');
  if (current_price) {
    pbDiv.innerHTML = `
      <div>实时币价: ${fmt2(current_price)}</div>
      <div>BOLL 上轨: ${fmt2(current_boll.boll_up)}</div>
      <div>BOLL 中轨: ${fmt2(current_boll.boll_mid)}</div>
      <div>BOLL 下轨: ${fmt2(current_boll.boll_dn)}</div>
    `;
  } else {
    pbDiv.innerText = '加载中...';
  }
}

// 定期获取价格和BOLL数据
async function updatePriceAndBoll() {
  try {
    const data = await fetchJSON('/api/price_and_boll');
    if (data.price) {
      current_price = data.price;
      current_boll = {
        boll_up: data.boll_up,
        boll_mid: data.boll_mid,
        boll_dn: data.boll_dn
      };
      updatePriceBoll();
    }
  } catch (e) {
    console.error('获取价格数据失败:', e);
  }
}

async function refresh(){
  // 系统信息 - 标题行一行展示
  const sys = await fetchJSON('/api/system');
  const sysLine = `CPU ${sys.cpu}% | 核 ${sys.cpu_cores} | 内存 ${sys.mem}% (总 ${sys.mem_total_mb}M/剩余 ${sys.mem_available_mb}M) | 磁盘 ${sys.disk}% (总 ${sys.disk_total_gb}G/剩余 ${sys.disk_free_gb}G)`;
  const sysEl = document.getElementById('sysline');
  if (sysEl) sysEl.innerText = sysLine;

  // 获取实时余额
  const balanceData = await fetchJSON('/api/balance');
  const balanceEl = document.getElementById('balance');
  if (balanceEl) balanceEl.innerText = fmt2(balanceData.balance);

  // positions (multi-symbol)
  const posData = await fetchJSON('/api/positions');
  const posDiv = document.getElementById('pos');
  if (!posData.items || posData.items.length === 0){ posDiv.innerText = '无持仓'; }
  else {
    let parts = [];
    for (const p of posData.items){
      parts.push(
        `<div class="mb-2">
          <div>开仓时间:${p.open_time}</div>
          <div>交易币对: ${p.symbol}</div>
          <div>方向:${p.side}</div>
          <div>金额:${fmt2(p.open_amount)} USDT</div>
          <div>价格:${fmt2(p.entry_price)}</div>
          <div>已实现盈亏: ${fmt2(p.realized_pnl)}</div>
          <div>数量: ${fmt2(p.qty)}</div>
        </div>`
      );
    }
    posDiv.innerHTML = parts.join('<hr class="my-2">');
  }

  const trades = await fetchJSON('/api/trades');
  const ul = document.getElementById('trades'); ul.innerHTML='';
  trades.forEach(t=>{ const li = document.createElement('li'); li.className='list-group-item';
    li.textContent = t.text; ul.appendChild(li); });

  const logs = await fetch('/api/logs');
  document.getElementById('logs').innerText = await logs.text();

  const profits = await fetchJSON('/api/profits');
  const profitsBody = document.getElementById('profits');
  profitsBody.innerHTML = '';
  profits.forEach(p => {
    const tr = document.createElement('tr');
    const dateTd = document.createElement('td'); dateTd.textContent = p.date; tr.appendChild(dateTd);
    const countTd = document.createElement('td'); countTd.textContent = p.trade_count; tr.appendChild(countTd);
    const profitTd = document.createElement('td'); profitTd.textContent = fmt2(p.profit);
    profitTd.className = p.profit >= 0 ? 'text-success' : 'text-danger'; tr.appendChild(profitTd);
    const rateTd = document.createElement('td'); rateTd.textContent = fmt2(p.profit_rate) + '%'; tr.appendChild(rateTd);
    profitsBody.appendChild(tr);
  });
  
  // 更新价格和BOLL数据
  await updatePriceAndBoll();
}
setInterval(refresh, 2000); refresh();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(TEMPLATE, cfg=config)


@app.get("/api/system")
def api_system():
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return jsonify({
        "cpu": psutil.cpu_percent(interval=None),
        "cpu_cores": psutil.cpu_count(logical=True),
        "mem": vm.percent,
        "mem_total_mb": int(vm.total / (1024 * 1024)),
        "mem_available_mb": int(vm.available / (1024 * 1024)),
        "disk": du.percent,
        "disk_total_gb": round(du.total / (1024 * 1024 * 1024), 1),
        "disk_free_gb": round(du.free / (1024 * 1024 * 1024), 1),
    })


# 兼容旧接口（单一文本）
@app.get("/api/position")
def api_position_compat():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol, side, qty, entry_price, ts FROM positions LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"text": "无持仓"})
    side = row["side"].lower()
    side_text = "long" if side == "long" else ("short" if side == "short" else side)
    open_time = fmt_ts_utc8(row['ts'])
    text = f"{row['symbol']} {side_text} | 开仓时间: {open_time} | 金额: {row['qty']:.2f} | 价格: {row['entry_price']:.2f}"
    return jsonify({"text": text})


# 多交易币对持仓列表
@app.get("/api/positions")
def api_positions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT symbol, side, qty, entry_price, ts FROM positions ORDER BY symbol ASC")
    rows = [dict(r) for r in cur.fetchall()]
    # 预取各symbol最新价格
    latest = {}
    for r in rows:
        cur.execute("SELECT close FROM klines WHERE symbol=? AND interval=? ORDER BY open_time DESC LIMIT 1", (r['symbol'], config.INTERVAL))
        k = cur.fetchone()
        latest[r['symbol']] = float(k['close']) if k else r['entry_price']
    # 计算
    items = []
    for r in rows:
        side_raw = (r['side'] or '').lower()
        side = 'long' if side_raw == 'long' else ('short' if side_raw == 'short' else side_raw)
        last_price = latest.get(r['symbol'], r['entry_price'])
        qty = float(r['qty'])
        entry = float(r['entry_price'])
        # 未实现盈亏
        if side == 'long':
            unrealized = (last_price - entry) * qty
        elif side == 'short':
            unrealized = (entry - last_price) * qty
        else:
            unrealized = 0.0
        # 已实现盈亏（基于trades.pnl汇总，若未维护则为0）
        cur.execute("SELECT COALESCE(SUM(pnl),0) AS s FROM trades WHERE symbol=?", (r['symbol'],))
        realized = float(cur.fetchone()['s'])
        items.append({
            'symbol': r['symbol'],
            'side': side,
            'qty': qty,
            'entry_price': entry,
            'open_amount': qty * entry,
            'open_time': fmt_ts_utc8(r['ts']),
            'unrealized_pnl': unrealized,
            'realized_pnl': realized,
        })
    conn.close()
    return jsonify({'items': items})


@app.route('/api/profits')
def api_profits():
    profits = get_daily_profits()
    return jsonify(profits)

@app.route('/api/engine_status')
def api_engine_status():
    """获取 Engine 实例的实时状态"""
    try:
        if hasattr(app, 'engine_instance') and app.engine_instance:
            eng = app.engine_instance
            return jsonify({
                'connected': True,
                'last_price': eng.last_price,
                'state': eng.state,
                'prices_count': len(eng.prices),
                'recent_prices': list(eng.prices)[-5:] if eng.prices else []
            })
        else:
            return jsonify({
                'connected': False,
                'last_price': 0,
                'state': 'unknown',
                'prices_count': 0,
                'recent_prices': []
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/price_and_boll')
def api_price_and_boll():
    try:
        # 优先使用 Engine 实例的实时数据
        if hasattr(app, 'engine_instance') and app.engine_instance:
            eng = app.engine_instance
            
            # 使用实时价格
            current_price = eng.last_price if eng.last_price > 0 else 0
            
            # 获取最新的 K 线数据并加入实时价格计算 BOLL
            rows = fetch_klines(config.SYMBOL, limit=config.BOLL_PERIOD)
            if len(rows) >= config.BOLL_PERIOD and current_price > 0:
                # 创建包含实时价格的数据框
                df = pd.DataFrame(rows)
                
                # 如果有实时价格，用实时价格替换最后一条记录的收盘价
                if len(df) > 0:
                    df.loc[df.index[-1], 'close'] = current_price
                    df.loc[df.index[-1], 'high'] = max(df.iloc[-1]['high'], current_price)
                    df.loc[df.index[-1], 'low'] = min(df.iloc[-1]['low'], current_price)
                
                # 计算实时 BOLL 指标
                mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD)
                
                return jsonify({
                    'price': current_price,
                    'boll_up': float(up.iloc[-1]),
                    'boll_mid': float(mid.iloc[-1]),
                    'boll_dn': float(dn.iloc[-1])
                })
        
        # 回退到数据库数据
        rows = fetch_klines(config.SYMBOL, limit=config.BOLL_PERIOD + 1)
        if len(rows) < config.BOLL_PERIOD:
            return jsonify({
                'price': 0,
                'boll_up': 0,
                'boll_mid': 0,
                'boll_dn': 0
            })
        
        # 计算 BOLL 指标
        df = pd.DataFrame(rows)
        mid, up, dn = bollinger_bands(df, config.BOLL_PERIOD, config.BOLL_STD)
        price = float(df['close'].iloc[-1])
        
        return jsonify({
            'price': price,
            'boll_up': float(up.iloc[-1]),
            'boll_mid': float(mid.iloc[-1]),
            'boll_dn': float(dn.iloc[-1])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.get("/api/trades")
def api_trades():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ts, side, qty, price, simulate FROM trades ORDER BY ts DESC LIMIT 50")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    def fmt(r):
        ts_str = fmt_ts_utc8(int(r['ts']))
        side = r['side']
        if side in ("BUY", "SELL"):
            action = "开仓"
            direction = "long" if side == "BUY" else "short"
        elif isinstance(side, str) and side.startswith("CLOSE"):
            action = "平仓"
            direction = side.split("_", 1)[-1].lower() if "_" in side else "-"
        else:
            action = side
            direction = "-"
        qty = float(r['qty'])
        price = float(r['price'])
        amount = qty * price
        return {"text": f"{ts_str} {action} 金额: {amount:.2f} 方向: {direction} 价格: {price:.2f}"}

    items = list(map(fmt, rows))
    return jsonify(items)


@app.get("/api/logs")
def api_logs():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ts, level, message FROM logs ORDER BY ts DESC LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    return "\n".join(
        [f"{fmt_ts_utc8(row['ts'])} [{row['level']}] {row['message']}" for row in rows]
    )



@app.get("/api/balance")
def api_balance():
    """获取当前余额（模拟模式下返回模拟余额）"""
    try:
        # 获取 Engine 实例中的 trader 余额
        if hasattr(app, 'engine_instance') and app.engine_instance:
            balance = app.engine_instance.trader.get_balance()
        else:
            # 如果没有 engine 实例，返回默认值
            balance = config.DEFAULT_MARGIN if config.SIMULATE else 0.0
        return jsonify({"balance": balance})
    except Exception as e:
        return jsonify({"balance": config.DEFAULT_MARGIN if config.SIMULATE else 0.0, "error": str(e)})


def _ensure_port_free(port: int):
    """如果端口被占用，立即杀掉占用进程，并等待端口释放。"""
    try:
        victims = set()
        for c in psutil.net_connections(kind='inet'):
            try:
                if c.laddr and getattr(c.laddr, 'port', None) == port and c.pid and c.pid != os.getpid():
                    victims.add(c.pid)
            except Exception:
                continue
        for pid in victims:
            try:
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(2)
                except psutil.TimeoutExpired:
                    p.kill()
            except Exception:
                continue
        # 等待端口释放
        def _in_use(p: int) -> bool:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                return s.connect_ex(('127.0.0.1', p)) == 0
        for _ in range(15):
            if not _in_use(port):
                break
            time.sleep(0.2)
    except Exception:
        # 忽略清理过程中的权限或平台差异错误
        pass


def run_web():
    print("启动检查开始...")

    eng = Engine()
    asyncio.run(eng.bootstrap())
    
    # 将 engine 实例存储到 app 对象中，供 API 接口使用
    app.engine_instance = eng

    print("启动 WebSocket API 订阅实时币价...")
    def run_engine_ws():
        asyncio.run(eng.run_ws())
    thread = threading.Thread(target=run_engine_ws, daemon=True)
    thread.start()
    print("WebSocket 订阅已启动。")

    # 检查数据库 K 线数据（更新后）
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM klines WHERE symbol=? AND interval=?", (config.SYMBOL, config.INTERVAL))
    kline_count = cur.fetchone()['c']
    latest_time = latest_kline_time(config.SYMBOL, config.INTERVAL) or 0
    print(f"数据库中有 {kline_count} 条 {config.SYMBOL} {config.INTERVAL} 的 K 线数据，最新 open_time: {fmt_ts_utc8(latest_time)}。")

    # 检查持仓
    pos = get_position(config.SYMBOL)
    if pos:
        print(f"检测到持仓: {pos['side']} 数量 {pos['qty']} 入场价 {pos['entry_price']}。")
    else:
        print("无当前持仓。")

    # 端口检查
    print("检查端口可用性...")
    _ensure_port_free(int(config.WEB_PORT))
    print(f"端口 {config.WEB_PORT} 已可用。")

    print("启动检查完成。")
    app.run(host=config.WEB_HOST, port=int(config.WEB_PORT), debug=False)


if __name__ == "__main__":
    run_web()