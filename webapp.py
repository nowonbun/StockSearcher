from __future__ import annotations

import html
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from flask import Flask, Response, redirect, request, url_for
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


app = Flask(__name__)


@app.get("/")
def index() -> Response:
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

    body = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>StockSearcher Control</title>
    <style>
      body {{
        font-family: Arial, sans-serif;
        margin: 24px;
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
    </style>
  </head>
  <body>
    <h1>StockSearcher Control</h1>
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
    state = _start_task(task, cmds[task])
    return redirect(url_for("view_log", name=state.log_name))


@app.get("/logs/<name>")
def view_log(name: str) -> Response:
    path = _safe_log_path(name)
    if path is None:
        return Response("not found", status=404)
    content = path.read_text(encoding="utf-8", errors="replace")
    body = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>{html.escape(name)}</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 24px; }}
      pre {{ background: #111; color: #f5f5f5; padding: 12px; overflow-x: auto; }}
      a {{ color: #1a73e8; }}
    </style>
  </head>
  <body>
    <a href="{url_for('index')}">Back</a>
    <h2>{html.escape(name)}</h2>
    <pre>{html.escape(content)}</pre>
  </body>
</html>
"""
    return Response(body, mimetype="text/html")


def main() -> None:
    host = os.environ.get("WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEB_PORT", "9999"))
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
