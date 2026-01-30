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


def _list_table(market: str) -> str:
    return "STOCK_LIST_JP" if market == "JP" else "STOCK_LIST_KR"


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
    list_table = _list_table(market)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  p.as_of,
                  p.code,
                  l.name,
                  p.probability,
                  d.Open,
                  d.Close,
                  d.Low,
                  d.High,
                  d.Volume
                FROM {predict_table} p
                JOIN {list_table} l
                  ON l.code = p.code
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
                        "name": row[2],
                        "probability": row[3],
                        "open": row[4],
                        "close": row[5],
                        "low": row[6],
                        "high": row[7],
                        "volume": row[8],
                    }
                )
            return rows
    finally:
        conn.close()


def _json_default(obj: object):
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def _fetch_series(market: str, code: str, as_of: str, limit: int = 240) -> List[Dict[str, object]]:
    data_table = _data_table(market)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  date,
                  Open,
                  High,
                  Low,
                  Close,
                  Volume,
                  `5MvAvg`,
                  `20MvAvg`,
                  `60MvAvg`,
                  `120MvAvg`,
                  `240MvAvg`,
                  UpperBand60_1,
                  LowerBand60_1,
                  LowerBand60_3,
                  DI_plus,
                  DI_minus,
                  ADX
                FROM {data_table}
                WHERE code = %s AND date <= %s
                ORDER BY date DESC
                LIMIT %s
                """,
                (code, as_of, limit),
            )
            rows = cur.fetchall()
            rows.reverse()
            series = []
            for row in rows:
                series.append(
                    {
                        "date": row[0].strftime("%Y-%m-%d"),
                        "open": row[1],
                        "high": row[2],
                        "low": row[3],
                        "close": row[4],
                        "volume": row[5],
                        "ma5": row[6],
                        "ma20": row[7],
                        "ma60": row[8],
                        "ma120": row[9],
                        "ma240": row[10],
                        "bb_upper": row[11],
                        "bb_lower": row[12],
                        "bb_lower3": row[13],
                        "di_plus": row[14],
                        "di_minus": row[15],
                        "adx": row[16],
                    }
                )
            return series
    finally:
        conn.close()


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
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css">
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.8/css/jquery.dataTables.min.css">
    <style>
      body {{
        font-family: "Roboto", sans-serif;
        background: #f5f7fb;
      }}
      .page {{
        max-width: 1680px;
        margin: 32px auto;
        padding: 0 16px;
      }}
      .card-panel {{
        border-radius: 12px;
        background: transparent;
        box-shadow: none;
      }}
      .tabs {{
        display: flex;
        gap: 6px;
        border-bottom: none;
        margin-bottom: 12px;
      }}
      .tab-btn {{
        border: none;
        background: transparent;
        padding: 10px 16px;
        border-radius: 8px 8px 0 0;
        cursor: pointer;
        font-weight: 500;
      }}
      .tab-btn.active {{
        background: #e8f5e9;
        color: #1b5e20;
        border: 1px solid #c8e6c9;
        border-bottom: 1px solid #e8f5e9;
      }}
      .tab-panel {{
        display: none;
        background: #e8f5e9;
        padding: 16px;
        border-radius: 12px;
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
        border: none;
        padding: 0;
        border-radius: 10px;
        background: transparent;
        box-shadow: none;
      }}
      button {{
        width: 100%;
        padding: 10px;
        font-size: 14px;
      }}
      .action-btn {{
        width: 100%;
      }}
      .section {{
        margin-top: 24px;
      }}
      .batch-title {{
        font-size: 12pt;
      }}
      ul {{
        padding-left: 18px;
      }}
      .search-bar {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        align-items: end;
        margin-bottom: 6px;
      }}
      .search-bar select {{
        height: 2.2rem;
        font-size: 13px;
      }}
      .filter-bar {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
        gap: 12px;
        margin: 4px 0 8px;
      }}
      .form-legend {{
        font-size: 12px;
        color: #666;
        margin: 2px 0;
        text-transform: uppercase;
        letter-spacing: 0.06em;
      }}
      .legend-wrap {{
        background: #e3f2fd;
        padding: 6px 8px;
        border-radius: 8px;
        margin-bottom: 6px;
      }}
      .input-field {{
        margin: 0;
      }}
      .input-field input[type="number"] {{
        margin: 0 0 4px 0;
      }}
      .input-field select {{
        margin: 0 0 4px 0;
      }}
      .input-field input[type="number"] {{
        height: 2.2rem;
        font-size: 13px;
      }}
      .input-field label {{
        font-size: 12px;
      }}
      .filter-actions {{
        display: flex;
        gap: 8px;
        align-items: center;
      }}
      table.dataTable tbody tr td {{
        vertical-align: middle;
      }}
      #predict-table tbody td:nth-child(2) {{
        cursor: pointer;
      }}
      #predict-table tbody td:nth-child(2):hover {{
        background: #1e88e5;
        color: #fff;
      }}
      #predict-table tbody tr.selected {{
        background: #e8f5e9;
      }}
      .dataTables_wrapper .dataTables_filter input {{
        border-bottom: 1px solid #90caf9;
        font-size: 8px;
        height: 1.2rem;
      }}
    </style>
  </head>
  <body>
    <div class="page">
      <div class="card-panel">
        <h4 style="margin-top:0">StockSearcher Control</h4>
        {msg_html}
        <div class="tabs">
          <button class="tab-btn active" data-tab="batch">Batch</button>
          <button class="tab-btn" data-tab="search">Predict Search</button>
        </div>

        <div class="tab-panel active" id="tab-batch">
          <div class="section">
      <h2 class="batch-title">JP</h2>
      <div class="grid">
        {action_form("dataset_jp", "Run dataset_jp.py")}
        {action_form("predict_jp", "Run predict_jp.py")}
        {action_form("job_jp", "Run JP job (dataset + predict)")}
      </div>
      </div>

          <div class="section">
      <h2 class="batch-title">KR</h2>
      <div class="grid">
        {action_form("dataset_kr", "Run dataset_kr.py")}
        {action_form("predict_kr", "Run predict_kr.py")}
        {action_form("job_kr", "Run KR job (dataset + predict)")}
      </div>
      </div>

          <div class="section">
      <h2 class="batch-title">Active/Recent Tasks</h2>
      <ul>
        {''.join(html_tasks) if html_tasks else '<li>None</li>'}
      </ul>
      </div>

          <div class="section">
      <h2 class="batch-title">Recent Logs</h2>
      <ul>
        {''.join(html_logs) if html_logs else '<li>No logs found</li>'}
      </ul>
      </div>
        </div>

        <div class="tab-panel" id="tab-search">
          <div class="section">
        <h2>Predict Search</h2>
        <div class="legend-wrap">
          <div class="form-legend">Search</div>
          <div class="search-bar">
          <div class="input-field">
            <select id="market">
              <option value="KR">KR</option>
              <option value="JP">JP</option>
            </select>
            <label>Market</label>
          </div>
          <div class="input-field">
            <select id="asof"></select>
            <label>As-of Date</label>
          </div>
          <div class="filter-actions">
            <a class="btn waves-effect waves-light blue" id="search-btn">Search</a>
          </div>
        </div>
        </div>
        <div class="legend-wrap">
          <div class="form-legend">Filters (Open / Close)</div>
          <div class="filter-bar">
          <div class="input-field">
            <input id="open-min" type="number" step="0.0001">
            <label for="open-min">Open min</label>
          </div>
          <div class="input-field">
            <input id="open-max" type="number" step="0.0001">
            <label for="open-max">Open max</label>
          </div>
          <div class="input-field">
            <input id="close-min" type="number" step="0.0001">
            <label for="close-min">Close min</label>
          </div>
          <div class="input-field">
            <input id="close-max" type="number" step="0.0001">
            <label for="close-max">Close max</label>
          </div>
          <div class="filter-actions">
            <a class="btn-flat" id="clear-filters">Clear</a>
          </div>
        </div>
        </div>
        <table id="predict-table" class="display" style="width:100%">
          <thead>
            <tr>
              <th>as-of</th>
              <th>code</th>
              <th>name</th>
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
        <div class="section">
          <h5>Chart</h5>
          <div id="chart" style="height: 2160px;"></div>
        </div>
      </div>
        </div>
      </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/js/materialize.min.js"></script>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>
    <script>
      document.addEventListener("DOMContentLoaded", () => {{
        const selects = document.querySelectorAll("select");
        M.FormSelect.init(selects);
      }});

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
      function formatNumber(value) {{
        if (value === null || value === undefined || value === "") return "";
        const num = Number(value);
        if (Number.isNaN(num)) return value;
        return num.toLocaleString("en-US", {{ maximumFractionDigits: 4 }});
      }}

      function parseFilterValue(id) {{
        const val = document.getElementById(id).value.trim();
        if (!val) return null;
        const num = Number(val);
        return Number.isNaN(num) ? null : num;
      }}

      function registerFilters() {{
        $.fn.dataTable.ext.search.push((settings, data) => {{
          const openVal = Number(data[4].replace(/,/g, ""));
          const closeVal = Number(data[5].replace(/,/g, ""));
          const openMin = parseFilterValue("open-min");
          const openMax = parseFilterValue("open-max");
          const closeMin = parseFilterValue("close-min");
          const closeMax = parseFilterValue("close-max");

          if (openMin !== null && openVal < openMin) return false;
          if (openMax !== null && openVal > openMax) return false;
          if (closeMin !== null && closeVal < closeMin) return false;
          if (closeMax !== null && closeVal > closeMax) return false;
          return true;
        }});
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
        M.FormSelect.init(select);
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
          r.name,
          formatNumber(r.probability),
          formatNumber(r.open),
          formatNumber(r.close),
          formatNumber(r.low),
          formatNumber(r.high),
          formatNumber(r.volume),
        ]);
        if (!table) {{
          registerFilters();
          table = new DataTable("#predict-table", {{
            data: rows,
            pageLength: 50,
            order: [[3, "desc"]],
          }});
          $("#predict-table tbody").on("click", "td:nth-child(2)", async function () {{
            const rowEl = $(this).closest("tr");
            $("#predict-table tbody tr").removeClass("selected");
            rowEl.addClass("selected");
            const row = table.row(rowEl).data();
            if (!row) return;
            const code = row[1];
            const asof = row[0];
            await loadChart(code, asof);
            const chartEl = document.getElementById("chart");
            if (chartEl) {{
              chartEl.scrollIntoView({{ behavior: "smooth", block: "start" }});
            }}
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
      ["open-min", "open-max", "close-min", "close-max"].forEach((id) => {{
        document.getElementById(id).addEventListener("input", () => {{
          if (table) table.draw();
        }});
      }});
      document.getElementById("clear-filters").addEventListener("click", () => {{
        ["open-min", "open-max", "close-min", "close-max"].forEach((id) => {{
          const el = document.getElementById(id);
          el.value = "";
        }});
        M.updateTextFields();
        if (table) table.draw();
      }});

      loadDates(true);

      async function loadChart(code, asof) {{
        const market = document.getElementById("market").value;
        const res = await fetch(`/api/series?market=${{encodeURIComponent(market)}}&code=${{encodeURIComponent(code)}}&as_of=${{encodeURIComponent(asof)}}`);
        const data = await res.json();
        const series = data.series;
        if (!series || !series.length) {{
          Plotly.purge("chart");
          return;
        }}
        const dates = series.map((d) => d.date);
        const traceCandle = {{
          x: dates,
          open: series.map((d) => d.open),
          high: series.map((d) => d.high),
          low: series.map((d) => d.low),
          close: series.map((d) => d.close),
          type: "candlestick",
          name: "Price",
          xaxis: "x",
          yaxis: "y",
        }};
        const maTrace = (key, name, color) => ({{
          x: dates,
          y: series.map((d) => d[key]),
          type: "scatter",
          mode: "lines",
          name,
          line: {{ color, width: 1 }},
          xaxis: "x",
          yaxis: "y",
        }});
        const bbTrace = (key, name, color) => ({{
          x: dates,
          y: series.map((d) => d[key]),
          type: "scatter",
          mode: "lines",
          name,
          line: {{ color, width: 1, dash: "dot" }},
          xaxis: "x",
          yaxis: "y",
        }});
        const volumeTrace = {{
          x: dates,
          y: series.map((d) => d.volume),
          type: "bar",
          name: "Volume",
          xaxis: "x2",
          yaxis: "y2",
          marker: {{ color: "#90caf9" }},
        }};
        const dmiTrace = (key, name, color) => ({{
          x: dates,
          y: series.map((d) => d[key]),
          type: "scatter",
          mode: "lines",
          name,
          line: {{ color, width: 1 }},
          xaxis: "x3",
          yaxis: "y3",
        }});
        const layout = {{
          grid: {{
            rows: 3,
            columns: 1,
            pattern: "independent",
            roworder: "top to bottom",
          }},
          height: 2160,
          margin: {{ t: 30, r: 20, b: 30, l: 50 }},
          xaxis: {{ rangeslider: {{ visible: false }}, domain: [0, 1] }},
          xaxis2: {{ matches: "x", showticklabels: false, domain: [0, 1] }},
          xaxis3: {{ matches: "x", domain: [0, 1] }},
          yaxis: {{ title: "Price", domain: [0.22, 1.0] }},
          yaxis2: {{ title: "Volume", domain: [0.12, 0.19] }},
          yaxis3: {{ title: "DMI", domain: [0.0, 0.08] }},
          legend: {{ orientation: "h" }},
        }};
        Plotly.newPlot(
          "chart",
          [
            traceCandle,
            maTrace("ma5", "MA5", "#1e88e5"),
            maTrace("ma20", "MA20", "#43a047"),
            maTrace("ma60", "MA60", "#fb8c00"),
            maTrace("ma120", "MA120", "#8e24aa"),
            maTrace("ma240", "MA240", "#6d4c41"),
            bbTrace("bb_upper", "BB Upper", "#ef5350"),
            bbTrace("bb_lower", "BB Lower", "#ef5350"),
            bbTrace("bb_lower3", "BB Lower3", "#c62828"),
            volumeTrace,
            dmiTrace("di_plus", "DI+", "#26a69a"),
            dmiTrace("di_minus", "DI-", "#ef5350"),
            dmiTrace("adx", "ADX", "#5c6bc0"),
          ],
          layout,
          {{ responsive: true, displayModeBar: false }}
        );
      }}
    </script>
  </body>
</html>
"""
    return Response(body, mimetype="text/html")


def action_form(action: str, label: str) -> str:
    return f"""
<form method="post" action="{url_for('run_task')}">
  <input type="hidden" name="task" value="{html.escape(action)}" />
  <button type="submit" class="btn waves-effect waves-light green action-btn">{html.escape(label)}</button>
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


@app.get("/api/series")
def api_series() -> Response:
    market = request.args.get("market", "KR").upper()
    code = request.args.get("code", "")
    as_of = request.args.get("as_of", "")
    if market not in ("KR", "JP"):
        return Response("invalid market", status=400)
    if not code or not as_of:
        return Response("missing code/as_of", status=400)
    series = _fetch_series(market, code, as_of, limit=240)
    payload = json.dumps({"series": series}, default=_json_default)
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
