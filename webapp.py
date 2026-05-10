from __future__ import annotations

import json
import os
import threading
import time
import datetime as dt
from decimal import Decimal
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import anyio
from flask import Flask, Response, request
import mysql.connector
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.routing import Mount, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
import uvicorn

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
        "job_jp": os.environ.get(
            "JOB_CMD_JP",
            os.environ.get("JOB_CMD_JP2", f"python dataset_jp.py && {jp_predict}"),
        ),
        "job_kr": os.environ.get(
            "JOB_CMD_KR",
            os.environ.get("JOB_CMD_KR2", f"python dataset_kr.py && {kr_predict}"),
        ),
    }


def _db_config(market: str) -> dict:
    if market == "JP":
        return static.db_config_jp
    if market == "KR":
        return static.db_config_kr
    raise ValueError("unknown market")


def _data_table(market: str) -> str:
    return "STOCK_DATA_JP" if market == "JP" else "STOCK_DATA_KR"


def _list_table(market: str) -> str:
    return "STOCK_LIST_JP" if market == "JP" else "STOCK_LIST_KR"


def _json_default(obj: object):
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def _normalize_value(value: object) -> object:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%Y-%m-%d")
    return value


def _normalize_row(row: Dict[str, object]) -> Dict[str, object]:
    return {key: _normalize_value(val) for key, val in row.items()}


def _fetch_stock_list(market: str) -> List[Dict[str, object]]:
    table = _list_table(market)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT code, name
                FROM {table}
                ORDER BY name, code
                """
            )
            return [
                {"code": row[0], "name": row[1]}
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def _fetch_stock_data(
    market: str,
    code: str,
    limit: int = 2000,
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[Dict[str, object]]:
    table = _data_table(market)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor(dictionary=True) as cur:
            clauses = ["code = %s"]
            params: List[object] = [code]
            if start_date:
                clauses.append("date >= %s")
                params.append(start_date)
            if end_date:
                clauses.append("date <= %s")
                params.append(end_date)
            where_sql = " AND ".join(clauses)
            limit_sql = "" if limit is None or limit <= 0 else " LIMIT %s"
            if limit_sql:
                params.append(limit)
            cur.execute(
                f"""
                SELECT *
                FROM {table}
                WHERE {where_sql}
                ORDER BY date DESC
                {limit_sql}
                """,
                tuple(params),
            )
            rows = cur.fetchall()
            return [_normalize_row(row) for row in rows]
    finally:
        conn.close()


app = Flask(__name__)
mcp = FastMCP("stocksearcher-mcp", streamable_http_path="/", host=os.environ.get("MCP_HOST", os.environ.get("WEB_HOST", "0.0.0.0")))


@mcp.tool()
def list_stocks(market: str = "KR") -> List[Dict[str, object]]:
    """List stocks for a market (KR or JP)."""
    market = market.upper()
    if market not in ("KR", "JP"):
        raise ValueError("market must be KR or JP")
    return _fetch_stock_list(market)


@mcp.tool()
def stock_data(
    market: str,
    code: str,
    limit: int = 2000,
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[Dict[str, object]]:
    """Return stock_data rows for a code, ordered by date DESC."""
    market = market.upper()
    if market not in ("KR", "JP"):
        raise ValueError("market must be KR or JP")
    if not code:
        raise ValueError("code is required")
    return _fetch_stock_data(market, code, limit=limit, start_date=start_date, end_date=end_date)


# ── Batch API ─────────────────────────────────────────────────────────────────

@app.post("/api/run")
def api_run() -> Response:
    data = request.get_json(silent=True) or {}
    task = str(data.get("task", "")).strip()
    cmds = _job_cmds()
    if task not in cmds:
        payload = json.dumps({"error": f"unknown task", "valid_tasks": list(cmds.keys())})
        return Response(payload, status=400, mimetype="application/json")
    try:
        state = _start_task(task, cmds[task])
    except RuntimeError as exc:
        payload = json.dumps({"error": str(exc)})
        return Response(payload, status=409, mimetype="application/json")
    payload = json.dumps({
        "task": state.name,
        "log_name": state.log_name,
        "status": "started",
        "started_at": state.started_at,
    })
    return Response(payload, status=202, mimetype="application/json")


@app.get("/api/tasks")
def api_tasks() -> Response:
    with TASK_LOCK:
        states = list(TASKS.values())
    result = []
    for s in sorted(states, key=lambda x: x.started_at, reverse=True):
        result.append(_task_dict(s))
    return Response(json.dumps({"tasks": result}), mimetype="application/json")


@app.get("/api/tasks/<name>")
def api_task_status(name: str) -> Response:
    with TASK_LOCK:
        state = TASKS.get(name)
    if state is None:
        return Response(json.dumps({"error": "not found"}), status=404, mimetype="application/json")
    return Response(json.dumps(_task_dict(state)), mimetype="application/json")


def _task_dict(s: TaskState) -> Dict[str, object]:
    if s.finished_at is None:
        status = "running"
    elif s.exit_code == 0:
        status = "success"
    else:
        status = f"failed (exit={s.exit_code})"
    return {
        "name": s.name,
        "log_name": s.log_name,
        "started_at": s.started_at,
        "finished_at": s.finished_at,
        "exit_code": s.exit_code,
        "status": status,
    }


# ── WebSocket log tail ─────────────────────────────────────────────────────────

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
            text = text[nl + 1:]
    return text, size


def _read_new_bytes(path: Path, pos: int) -> Tuple[str, int]:
    try:
        with path.open("rb") as handle:
            handle.seek(pos)
            data = handle.read()
            new_pos = handle.tell()
    except FileNotFoundError:
        return "", pos
    if data:
        return data.decode("utf-8", errors="replace"), new_pos
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return "", pos
    if size < pos:
        return "", 0
    return "", pos


async def ws_log(websocket: WebSocket) -> None:
    await websocket.accept()
    name = websocket.path_params.get("name", "")
    path = _safe_log_path(name)
    if path is None:
        await websocket.send_text("[error] not found\n")
        await websocket.close()
        return
    try:
        text, pos = await anyio.to_thread.run_sync(_tail_bytes, path)
        if text:
            await websocket.send_text(text)
        while True:
            await anyio.sleep(0.5)
            chunk, pos = await anyio.to_thread.run_sync(_read_new_bytes, path, pos)
            if chunk:
                await websocket.send_text(chunk)
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close()
        return


def create_asgi_app() -> Starlette:
    mcp_app = mcp.streamable_http_app()
    lifespan = getattr(mcp_app, "lifespan", None)
    if lifespan is None and hasattr(mcp_app, "router"):
        lifespan = mcp_app.router.lifespan_context
    return Starlette(
        routes=[
            Mount("/mcp", app=mcp_app),
            WebSocketRoute("/ws/logs/{name}", ws_log),
            Mount("/", app=WSGIMiddleware(app)),
        ],
        lifespan=lifespan,
    )


ASGI_APP = create_asgi_app()


def main() -> None:
    host = os.environ.get("WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEB_PORT", "9999"))
    uvicorn.run(ASGI_APP, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
