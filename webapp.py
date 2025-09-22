import threading
import time
import psutil
from flask import Flask, render_template_string, jsonify

from config import config
from db import get_conn, init_db

init_db()

app = Flask(__name__)

# 工具：UTC+8 时间格式（月-日 时:分）
def fmt_ts_utc8(ts_ms: int) -> str:
    return time.strftime('%m-%d %H:%M', time.gmtime(ts_ms / 1000 + 8 * 3600))

TEMPLATE = """
<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>自动交易监控</title>
  <link rel=\"stylesheet\" href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css\">
  <style>
    body{padding:20px}
    .metric{font-size:1.1rem}
    .log{white-space: pre-wrap; max-height:300px; overflow:auto}
    .table-sm td, .table-sm th{ padding:.25rem .5rem; }
  </style>
</head>
<body>
  <div class=\"container\">
    <h3 class=\"my-3\">币安合约自动交易 - 监控</h3>
    <div class=\"row g-3\">
      <div class=\"col-md-4\">
        <div class=\"card\">
          <div class=\"card-header\">配置</div>
          <div class=\"card-body\">
            <div>交易对: {{ cfg.SYMBOL }}</div>
            <div>K线周期: {{ cfg.INTERVAL }}</div>
            <div>BOLL: P={{ cfg.BOLL_PERIOD }} STD={{ cfg.BOLL_STD }}</div>
            <div>数量: {{ cfg.QUANTITY }} 杠杆: {{ cfg.LEVERAGE }}</div>
            <div>模拟: {{ cfg.SIMULATE }}</div>
            <div>自动重启: {{ cfg.AUTO_RESTART }}</div>
          </div>
        </div>
      </div>
      <div class=\"col-md-4\">
        <div class=\"card\">
          <div class=\"card-header\">系统</div>
          <div class=\"card-body metric\">
            <div>CPU: <span id=\"cpu\">-</span>%</div>
            <div>CPU核: <span id=\"cpu_cores\">-</span></div>
            <div>内存: <span id=\"mem\">-</span>%</div>
            <div class=\"small text-muted\">内存明细: 总 <span id=\"mem_total\">-</span> M / 剩余 <span id=\"mem_free\">-</span> M</div>
            <div>磁盘: <span id=\"disk\">-</span>%</div>
            <div class=\"small text-muted\">磁盘明细: 总 <span id=\"disk_total\">-</span> G / 剩余 <span id=\"disk_free\">-</span> G</div>
          </div>
        </div>
      </div>
      <div class=\"col-md-4\">
        <div class=\"card\">
          <div class=\"card-header\">持仓</div>
          <div class=\"card-body\" id=\"pos\">加载中...</div>
        </div>
      </div>
    </div>

    <div class=\"row g-3 mt-2\">
      <div class=\"col-md-6\">
        <div class=\"card\">
          <div class=\"card-header\">交易记录（最近50条）</div>
          <div class=\"card-body\">
            <ul id=\"trades\" class=\"list-group list-group-flush\"></ul>
          </div>
        </div>
      </div>
      <div class=\"col-md-6\">
        <div class=\"card\">
          <div class=\"card-header\">日志（最近200条）</div>
          <div class=\"card-body\"><div id=\"logs\" class=\"log\">加载中...</div></div>
        </div>
      </div>
    </div>
  </div>
<script>
async function fetchJSON(url){ const r = await fetch(url); return r.json(); }
function fmt2(v){ return Number(v).toFixed(2); }
async function refresh(){
  const sys = await fetchJSON('/api/system');
  document.getElementById('cpu').innerText = sys.cpu;
  document.getElementById('cpu_cores').innerText = sys.cpu_cores;
  document.getElementById('mem').innerText = sys.mem;
  document.getElementById('mem_total').innerText = sys.mem_total_mb;
  document.getElementById('mem_free').innerText = sys.mem_available_mb;
  document.getElementById('disk').innerText = sys.disk;
  document.getElementById('disk_total').innerText = sys.disk_total_gb;
  document.getElementById('disk_free').innerText = sys.disk_free_gb;

  // positions (multi-symbol)
  const posData = await fetchJSON('/api/positions');
  const posDiv = document.getElementById('pos');
  if (!posData.items || posData.items.length === 0){ posDiv.innerText = '无持仓'; }
  else {
    let html = '<div class="table-responsive"><table class="table table-sm"><thead><tr><th>交易对</th><th>方向</th><th>数量</th><th>价格</th><th>金额</th><th>开仓时间</th><th>未实现盈亏</th><th>已实现盈亏</th></tr></thead><tbody>';
    for (const p of posData.items){
      html += `<tr><td>${p.symbol}</td><td>${p.side}</td><td>${fmt2(p.qty)}</td><td>${fmt2(p.entry_price)}</td><td>${fmt2(p.open_amount)}</td><td>${p.open_time}</td><td>${fmt2(p.unrealized_pnl)}</td><td>${fmt2(p.realized_pnl)}</td></tr>`;
    }
    html += '</tbody></table></div>';
    posDiv.innerHTML = html;
  }

  const trades = await fetchJSON('/api/trades');
  const ul = document.getElementById('trades'); ul.innerHTML='';
  trades.forEach(t=>{ const li = document.createElement('li'); li.className='list-group-item';
    li.textContent = t.text; ul.appendChild(li); });

  const logs = await fetch('/api/logs');
  document.getElementById('logs').innerText = await logs.text();
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


# 多交易对持仓列表
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
            'open_time': fmt_ts_utc8(int(r['ts'])),
            'unrealized_pnl': unrealized,
            'realized_pnl': realized,
        })
    conn.close()
    return jsonify({"items": items})


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
        simulate = bool(r.get('simulate', 1))
        tag = '[SIM]' if simulate else '[REAL]'
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
        return {"text": f"{ts_str} {action} 金额: {amount:.2f} 方向: {direction} 价格: {price:.2f} {tag}"}

    items = list(map(fmt, reversed(rows)))
    return jsonify(items)


@app.get("/api/logs")
def api_logs():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ts, level, message FROM logs ORDER BY ts DESC LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    lines = [f"{fmt_ts_utc8(r['ts'])} [{r['level']}] {r['message']}" for r in rows]
    return "\n".join(reversed(lines))


def run_web():
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False)


if __name__ == "__main__":
    run_web()