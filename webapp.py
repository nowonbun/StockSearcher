from __future__ import annotations

import html
import json
import os
import threading
import time
from decimal import Decimal
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Flask, Response, redirect, request, url_for
from flask_sock import Sock
import mysql.connector

import function.static as static
import subprocess


APP_ROOT = Path(__file__).resolve().parent
DEFAULT_LOG_DIR = Path(os.environ.get("CRON_LOG_DIR", "/data/log"))


def _log_dir() -> Path:
    cron_log_path = os.environ.get("CRON_LOG_PATH")
    if cron_log_path:
        return Path(cron_log_path).expanduser().resolve().parent
    return DEFAULT_LOG_DIR


def _safe_log_path(name: str) -> Path | None:
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    path = _log_dir() / name
    if not path.exists():
        return None
    return path


def _list_logs(limit: int = 50) -> List[Tuple[str, float]]:
    log_dir = _log_dir()
    if not log_dir.exists():
        return []
    items = []
    for path in log_dir.glob("*.log"):
        try:
            items.append((path.name, path.stat().st_mtime))
        except FileNotFoundError:
            continue
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:limit]


def _now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


@dataclass
class TaskState:
    name: str
    log_name: str
    started_at: float
    finished_at: float | None = None
    exit_code: int | None = None


TASKS: Dict[str, TaskState] = {}
TASK_LOCK = threading.Lock()


def _run_task(name: str, cmd: str, log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write(f"[start] {time.strftime('%F %T')} cmd={cmd}\n")
        logf.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=str(APP_ROOT),
            shell=True,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        code = proc.wait()
        logf.write(f"[done] {time.strftime('%F %T')} exit={code}\n")

    with TASK_LOCK:
        state = TASKS.get(name)
        if state:
            state.finished_at = time.time()
            state.exit_code = code


def _start_task(name: str, cmd: str) -> TaskState:
    with TASK_LOCK:
        existing = TASKS.get(name)
        if existing and existing.finished_at is None:
            raise RuntimeError(f"task '{name}' is already running")
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_name = f"manual-{name}-{_now_stamp()}.log"
    log_path = log_dir / log_name
    state = TaskState(name=name, log_name=log_name, started_at=time.time())
    with TASK_LOCK:
        TASKS[name] = state
    thread = threading.Thread(target=_run_task, args=(name, cmd, log_path), daemon=True)
    thread.start()
    return state


def _job_cmds() -> Dict[str, str]:
    jp_model = os.environ.get("PREDICT_JP_MODEL", "/models/model_jp.pt")
    kr_model = os.environ.get("PREDICT_KR_MODEL", "/models/model_kr.pt")
    jp_predict = f"python predict_jp.py --model {jp_model} --save-db"
    kr_predict = f"python predict_kr.py --model {kr_model} --save-db"
    return {
        "dataset_jp": "python dataset_jp.py",
        "predict_jp": jp_predict,
        "dataset_kr": "python dataset_kr.py",
        "predict_kr": kr_predict,
        "job_jp": os.environ.get("JOB_CMD_JP", "python dataset_jp.py && python predict_jp.py"),
        "job_kr": os.environ.get("JOB_CMD_KR", "python dataset_kr.py && python predict_kr.py"),
    }


def _db_config(market: str) -> dict:
    if market == "JP":
        return static.db_config_jp
    if market == "KR":
        return static.db_config_kr
    raise ValueError("unknown market")


def _predict_table(market: str) -> str:
    return "STOCK_PREDICT_JP" if market == "JP" else "STOCK_PREDICT_KR"


def _data_table(market: str) -> str:
    return "STOCK_DATA_JP" if market == "JP" else "STOCK_DATA_KR"


def _fetch_predict_dates(market: str, limit: int = 120) -> List[str]:
    table = _predict_table(market)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT as_of FROM {table} ORDER BY as_of DESC LIMIT %s",
                (limit,),
            )
            return [row[0].strftime("%Y-%m-%d") for row in cur.fetchall()]
    finally:
        conn.close()


def _fetch_predictions(market: str, as_of: str) -> List[Dict[str, object]]:
    predict_table = _predict_table(market)
    data_table = _data_table(market)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  p.as_of,
                  p.code,
                  p.probability,
                  d.Open,
                  d.Close,
                  d.Low,
                  d.High,
                  d.Volume
                FROM {predict_table} p
                JOIN {data_table} d
                  ON d.code = p.code AND d.date = p.as_of
                WHERE p.as_of = %s
                ORDER BY p.probability DESC
                """,
                (as_of,),
            )
            rows = []
            for row in cur.fetchall():
                rows.append(
                    {
                        "as_of": row[0].strftime("%Y-%m-%d"),
                        "code": row[1],
                        "probability": row[2],
                        "open": row[3],
                        "close": row[4],
                        "low": row[5],
                        "high": row[6],
                        "volume": row[7],
                    }
                )
            return rows
    finally:
        conn.close()


def _json_default(obj: object):
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


app = Flask(__name__)
sock = Sock(app)


@app.get("/")
def index() -> Response:
    message = request.args.get("msg")
    tasks = []
    with TASK_LOCK:
        for state in TASKS.values():
            tasks.append(state)
    logs = _list_logs()
    html_tasks = []
    for state in sorted(tasks, key=lambda s: s.started_at, reverse=True):
        status = "running" if state.finished_at is None else f"exit={state.exit_code}"
        html_tasks.append(
            f"<li>{html.escape(state.name)} - {status} - "
            f"<a href='{url_for('view_log', name=state.log_name)}'>{html.escape(state.log_name)}</a></li>"
        )

    html_logs = []
    for name, mtime in logs:
        ts = time.strftime("%F %T", time.localtime(mtime))
        html_logs.append(
            f"<li><a href='{url_for('view_log', name=name)}'>{html.escape(name)}</a> "
            f"<span style='color:#666'>({ts})</span></li>"
        )

    msg_html = f"<p style='color:#b00020'>{html.escape(message)}</p>" if message else ""
    body = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>StockSearcher Control</title>
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.8/css/jquery.dataTables.min.css">
    <style>
      body {{
        font-family: Arial, sans-serif;
        margin: 24px;
      }}
      .tabs {{
        display: flex;
        gap: 8px;
        border-bottom: 1px solid #ddd;
        margin-bottom: 16px;
      }}
      .tab-btn {{
        border: none;
        background: #f1f1f1;
        padding: 8px 14px;
        border-radius: 6px 6px 0 0;
        cursor: pointer;
      }}
      .tab-btn.active {{
        background: #fff;
        border: 1px solid #ddd;
        border-bottom: 1px solid #fff;
      }}
      .tab-panel {{
        display: none;
      }}
      .tab-panel.active {{
        display: block;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 12px;
      }}
      form {{
        border: 1px solid #ddd;
        padding: 12px;
        border-radius: 6px;
        background: #fafafa;
      }}
      button {{
        width: 100%;
        padding: 10px;
        font-size: 14px;
      }}
      .section {{
        margin-top: 24px;
      }}
      ul {{
        padding-left: 18px;
      }}
      .search-bar {{
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        align-items: center;
        margin-bottom: 16px;
      }}
      .search-bar label {{
        font-size: 14px;
      }}
      .search-bar select {{
        padding: 6px;
        font-size: 14px;
      }}
      .search-bar button {{
        padding: 8px 14px;
        font-size: 14px;
      }}
      table.dataTable tbody tr td {{
        vertical-align: middle;
      }}
    </style>
  </head>
  <body>
    <h1>StockSearcher Control</h1>
    {msg_html}
    <div class="tabs">
      <button class="tab-btn active" data-tab="batch">Batch</button>
      <button class="tab-btn" data-tab="search">Predict Search</button>
    </div>

    <div class="tab-panel active" id="tab-batch">
      <div class="section">
      <h2>JP</h2>
      <div class="grid">
        {action_form("dataset_jp", "Run dataset_jp.py")}
        {action_form("predict_jp", "Run predict_jp.py")}
        {action_form("job_jp", "Run JP job (dataset + predict)")}
      </div>
      </div>

      <div class="section">
      <h2>KR</h2>
      <div class="grid">
        {action_form("dataset_kr", "Run dataset_kr.py")}
        {action_form("predict_kr", "Run predict_kr.py")}
        {action_form("job_kr", "Run KR job (dataset + predict)")}
      </div>
      </div>

      <div class="section">
      <h2>Active/Recent Tasks</h2>
      <ul>
        {''.join(html_tasks) if html_tasks else '<li>None</li>'}
      </ul>
      </div>

      <div class="section">
      <h2>Recent Logs</h2>
      <ul>
        {''.join(html_logs) if html_logs else '<li>No logs found</li>'}
      </ul>
      </div>
    </div>

    <div class="tab-panel" id="tab-search">
      <div class="section">
        <h2>Predict Search</h2>
        <div class="search-bar">
          <label>
            Market
            <select id="market">
              <option value="KR">KR</option>
              <option value="JP">JP</option>
            </select>
          </label>
          <label>
            As-of Date
            <select id="asof"></select>
          </label>
          <button id="search-btn">Search</button>
        </div>
        <table id="predict-table" class="display" style="width:100%">
          <thead>
            <tr>
              <th>as-of</th>
              <th>code</th>
              <th>probability</th>
              <th>open</th>
              <th>close</th>
              <th>low</th>
              <th>high</th>
              <th>volume</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>
    <script>
      const tabs = document.querySelectorAll(".tab-btn");
      tabs.forEach((btn) => {{
        btn.addEventListener("click", () => {{
          tabs.forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          const target = btn.dataset.tab;
          document.querySelectorAll(".tab-panel").forEach((panel) => {{
            panel.classList.toggle("active", panel.id === "tab-" + target);
          }});
        }});
      }});

      let table = null;
      function formatCell(value) {{
        if (value === null || value === undefined) return "";
        return value;
      }}

      async function loadDates(autoSearch = false) {{
        const market = document.getElementById("market").value;
        const res = await fetch(`/api/predict-dates?market=${{encodeURIComponent(market)}}`);
        const data = await res.json();
        const select = document.getElementById("asof");
        select.innerHTML = "";
        data.dates.forEach((d) => {{
          const opt = document.createElement("option");
          opt.value = d;
          opt.textContent = d;
          select.appendChild(opt);
        }});
        if (autoSearch && data.dates.length) {{
          select.value = data.dates[0];
          await searchPredicts();
        }}
      }}

      async function searchPredicts() {{
        const market = document.getElementById("market").value;
        const asof = document.getElementById("asof").value;
        if (!asof) return;
        const res = await fetch(`/api/predict?market=${{encodeURIComponent(market)}}&as_of=${{encodeURIComponent(asof)}}`);
        const data = await res.json();
        const rows = data.rows.map((r) => [
          r.as_of,
          r.code,
          r.probability,
          formatCell(r.open),
          formatCell(r.close),
          formatCell(r.low),
          formatCell(r.high),
          formatCell(r.volume),
        ]);
        if (!table) {{
          table = new DataTable("#predict-table", {{
            data: rows,
            pageLength: 50,
            order: [[2, "desc"]],
          }});
        }} else {{
          table.clear();
          table.rows.add(rows);
          table.draw();
        }}
      }}

      document.getElementById("market").addEventListener("change", async () => {{
        await loadDates(true);
      }});
      document.getElementById("search-btn").addEventListener("click", searchPredicts);

      loadDates(true);
    </script>
  </body>
</html>
"""
    return Response(body, mimetype="text/html")


def action_form(action: str, label: str) -> str:
    return f"""
<form method="post" action="{url_for('run_task')}">
  <input type="hidden" name="task" value="{html.escape(action)}" />
  <button type="submit">{html.escape(label)}</button>
</form>
"""


@app.post("/run")
def run_task() -> Response:
    task = request.form.get("task", "")
    cmds = _job_cmds()
    if task not in cmds:
        return Response("unknown task", status=400)
    try:
        state = _start_task(task, cmds[task])
    except RuntimeError as exc:
        return redirect(url_for("index", msg=str(exc)))
    return redirect(url_for("view_log", name=state.log_name))


@app.get("/logs/<name>")
def view_log(name: str) -> Response:
    path = _safe_log_path(name)
    if path is None:
        return Response("not found", status=404)
    log_name_json = json.dumps(name)
    body = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>{html.escape(name)}</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 24px; }}
      pre {{ background: #111; color: #f5f5f5; padding: 12px; overflow-x: auto; height: 70vh; }}
      a {{ color: #1a73e8; }}
      .status {{ color: #666; margin-left: 8px; }}
    </style>
  </head>
  <body>
    <a href="{url_for('index')}">Back</a>
    <span class="status" id="status">Connecting...</span>
    <h2>{html.escape(name)}</h2>
    <pre id="log"></pre>
    <script>
      const logName = {log_name_json};
      const logEl = document.getElementById("log");
      const statusEl = document.getElementById("status");
      function wsUrl() {{
        const protocol = location.protocol === "https:" ? "wss://" : "ws://";
        return protocol + location.host + "/ws/logs/" + encodeURIComponent(logName);
      }}
      function connect() {{
        const ws = new WebSocket(wsUrl());
        statusEl.textContent = "Connected";
        ws.onmessage = (evt) => {{
          logEl.textContent += evt.data;
          logEl.scrollTop = logEl.scrollHeight;
        }};
        ws.onclose = () => {{
          statusEl.textContent = "Disconnected - reconnecting...";
          setTimeout(connect, 1000);
        }};
        ws.onerror = () => {{
          ws.close();
        }};
      }}
      connect();
    </script>
  </body>
</html>
"""
    return Response(body, mimetype="text/html")


@app.get("/api/predict-dates")
def api_predict_dates() -> Response:
    market = request.args.get("market", "KR").upper()
    if market not in ("KR", "JP"):
        return Response("invalid market", status=400)
    dates = _fetch_predict_dates(market)
    payload = json.dumps({"dates": dates})
    return Response(payload, mimetype="application/json")


@app.get("/api/predict")
def api_predict() -> Response:
    market = request.args.get("market", "KR").upper()
    as_of = request.args.get("as_of", "")
    if market not in ("KR", "JP"):
        return Response("invalid market", status=400)
    if not as_of:
        return Response("missing as_of", status=400)
    rows = _fetch_predictions(market, as_of)
    payload = json.dumps({"rows": rows}, default=_json_default)
    return Response(payload, mimetype="application/json")


def _tail_bytes(path: Path, max_bytes: int = 20000) -> Tuple[str, int]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = max(0, size - max_bytes)
        handle.seek(start)
        data = handle.read()
    text = data.decode("utf-8", errors="replace")
    if start > 0:
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
    return text, size


@sock.route("/ws/logs/<name>")
def stream_log(ws, name: str) -> None:
    path = _safe_log_path(name)
    if path is None:
        ws.send("[error] not found\n")
        return
    try:
        text, pos = _tail_bytes(path)
        if text:
            ws.send(text)
        with path.open("rb") as handle:
            handle.seek(pos)
            while True:
                chunk = handle.read()
                if chunk:
                    ws.send(chunk.decode("utf-8", errors="replace"))
                    pos = handle.tell()
                    continue
                time.sleep(0.5)
                try:
                    size = path.stat().st_size
                except FileNotFoundError:
                    continue
                if size < pos:
                    handle.seek(0)
                    pos = 0
    except Exception:
        return


def main() -> None:
    host = os.environ.get("WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEB_PORT", "9999"))
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
