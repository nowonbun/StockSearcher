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


def _week_data_table(market: str) -> str:
    return "STOCK_DATA_WEEK_JP" if market == "JP" else "STOCK_DATA_WEEK_KR"


def _list_table(market: str) -> str:
    return "STOCK_LIST_JP" if market == "JP" else "STOCK_LIST_KR"


def _predict_table(market: str, weekly: bool = False) -> str:
    suffix = "_WEEK" if weekly else ""
    return f"STOCK_PREDICT{suffix}_JP" if market == "JP" else f"STOCK_PREDICT{suffix}_KR"


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


def _fetch_previous_trading_date(market: str) -> str | None:
    table = _data_table(market)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT date
                FROM {table}
                WHERE date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                ORDER BY date DESC
                LIMIT 30
                """
            )
            rows = cur.fetchall()
            if len(rows) >= 2:
                return rows[1][0].strftime("%Y-%m-%d")
            if rows:
                return rows[0][0].strftime("%Y-%m-%d")
            return None
    finally:
        conn.close()


def _scanner_defaults(market: str) -> Dict[str, object]:
    market = market.upper()
    if market == "JP":
        return {
            "date": _fetch_previous_trading_date(market),
            "close_max": 1000,
            "trans_amnt_min": 500000000,
        }
    return {
        "date": _fetch_previous_trading_date(market),
        "close_max": 100000,
        "trans_amnt_min": 1000000000,
    }


def _fetch_upperband_breakouts(
    market: str,
    scan_date: str,
    trans_amnt_min: int | float,
    close_max: int | float,
    weekly: bool = False,
) -> List[Dict[str, object]]:
    data_table = _week_data_table(market) if weekly else _data_table(market)
    list_table = _list_table(market)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  sd.date,
                  sd.code,
                  sl.name,
                  sd.Close,
                  sd.UpperBand60_1,
                  sd.transAmnt,
                  (sd.Close / NULLIF(sd.UpperBand60_1, 0)) AS upperband_ratio
                FROM {data_table} sd
                JOIN {list_table} sl
                  ON sl.code = sd.code
                WHERE sd.date = %s
                  AND sd.Close > sd.UpperBand60_1
                  AND sd.Close < sd.UpperBand60_1 * 1.2
                  AND sd.transAmnt > %s
                  AND sd.Close < %s
                ORDER BY sd.transAmnt DESC
                LIMIT 20
                """,
                (scan_date, trans_amnt_min, close_max),
            )
            rows = []
            for row in cur.fetchall():
                rows.append(
                    {
                        "date": row[0].strftime("%Y-%m-%d"),
                        "code": row[1],
                        "name": row[2],
                        "close": row[3],
                        "upperband60_1": row[4],
                        "transAmnt": row[5],
                        "upperband_ratio": row[6],
                    }
                )
            return rows
    finally:
        conn.close()


app = Flask(__name__)
mcp = FastMCP("stocksearcher-mcp", streamable_http_path="/", host=os.environ.get("MCP_HOST", os.environ.get("WEB_HOST", "0.0.0.0")))


@mcp.tool(
    name="list_stocks",
    description=(
        "지정한 시장의 전체 종목 목록을 반환합니다.\n"
        "\n"
        "파라미터:\n"
        "  market (str): 시장 코드. 'KR'(한국) 또는 'JP'(일본). 기본값 'KR'.\n"
        "\n"
        "반환값 (List[Dict]):\n"
        "  - code (str): 종목 코드 (KR 예: '005930', JP 예: '7203')\n"
        "  - name (str): 종목명\n"
        "\n"
        "사용 예시:\n"
        "  list_stocks(market='KR')  # 한국 전체 종목\n"
        "  list_stocks(market='JP')  # 일본 전체 종목\n"
        "\n"
        "활용 팁: 종목 코드를 모를 때 이 도구로 먼저 목록을 조회한 뒤 "
        "stock_data 또는 stock_data_week로 상세 데이터를 조회하세요."
    ),
)
def list_stocks(market: str = "KR") -> List[Dict[str, object]]:
    """List stocks for a market (KR or JP)."""
    market = market.upper()
    if market not in ("KR", "JP"):
        raise ValueError("market must be KR or JP")
    return _fetch_stock_list(market)


@mcp.tool(
    name="stock_data",
    description=(
        "특정 종목의 일봉(일별) OHLCV 및 기술적 지표 데이터를 반환합니다. 날짜 내림차순 정렬.\n"
        "\n"
        "파라미터:\n"
        "  market     (str): 'KR' 또는 'JP' (필수)\n"
        "  code       (str): 종목 코드 (필수). 예: KR='005930', JP='7203'\n"
        "  limit      (int): 최대 반환 행 수. 기본값 2000. 0 이하이면 전체 반환.\n"
        "  start_date (str): 조회 시작일 'YYYY-MM-DD' (선택)\n"
        "  end_date   (str): 조회 종료일 'YYYY-MM-DD' (선택)\n"
        "\n"
        "반환값 컬럼 (일봉 테이블: STOCK_DATA_KR / STOCK_DATA_JP):\n"
        "  - code, date, open, high, low, close, volume\n"
        "  - 이동평균: MvAvg5, MvAvg20, MvAvg50, MvAvg60, MvAvg120 (JP는 MvAvg240 추가)\n"
        "  - 볼린저밴드: UpperBand60_1, UpperBand60_2, LowerBand60_1, LowerBand60_2\n"
        "  - DMI 지표: DI_plus, DI_minus, ADX\n"
        "\n"
        "사용 예시:\n"
        "  stock_data(market='KR', code='005930', limit=60)              # 삼성전자 최근 60일\n"
        "  stock_data(market='JP', code='7203', start_date='2024-01-01') # 토요타 2024년~"
    ),
)
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


@mcp.tool(
    name="stock_data_week",
    description=(
        "특정 종목의 주봉(주별) OHLCV 및 기술적 지표 데이터를 반환합니다. 날짜 내림차순 정렬.\n"
        "일봉 대비 더 긴 추세 파악에 적합하며, 데이터 포인트 수가 적어 빠르게 조회됩니다.\n"
        "\n"
        "파라미터:\n"
        "  market     (str): 'KR' 또는 'JP' (필수)\n"
        "  code       (str): 종목 코드 (필수). 예: KR='005930', JP='7203'\n"
        "  limit      (int): 최대 반환 행 수. 기본값 500 (약 10년치). 0 이하이면 전체 반환.\n"
        "  start_date (str): 조회 시작일 'YYYY-MM-DD' (선택)\n"
        "  end_date   (str): 조회 종료일 'YYYY-MM-DD' (선택)\n"
        "\n"
        "반환값 컬럼 (주봉 테이블: STOCK_DATA_WEEK_KR / STOCK_DATA_WEEK_JP):\n"
        "  - code, date (해당 주 시작일), open, high, low, close, volume\n"
        "  - 이동평균: MvAvg5, MvAvg20, MvAvg50, MvAvg60, MvAvg120 (JP는 MvAvg240 추가)\n"
        "  - 볼린저밴드: UpperBand60_1, UpperBand60_2, LowerBand60_1, LowerBand60_2\n"
        "  - DMI 지표: DI_plus, DI_minus, ADX\n"
        "\n"
        "사용 예시:\n"
        "  stock_data_week(market='KR', code='005930', limit=52)              # 삼성전자 최근 1년 주봉\n"
        "  stock_data_week(market='JP', code='7203', start_date='2023-01-01') # 토요타 2023년~ 주봉\n"
        "\n"
        "활용 팁: 단기 매매 신호는 일봉(stock_data), 중장기 추세 분석은 주봉(stock_data_week)을 사용하세요."
    ),
)
def stock_data_week(
    market: str,
    code: str,
    limit: int = 500,
    start_date: str | None = None,
    end_date: str | None = None,
) -> List[Dict[str, object]]:
    """Return weekly stock_data rows for a code, ordered by date DESC."""
    market = market.upper()
    if market not in ("KR", "JP"):
        raise ValueError("market must be KR or JP")
    if not code:
        raise ValueError("code is required")
    table = _week_data_table(market)
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


@mcp.tool(
    name="list_predict_dates",
    description=(
        "예측 결과가 존재하는 기준일(data_cutoff) 목록을 최신순으로 반환합니다.\n"
        "\n"
        "파라미터:\n"
        "  market (str): 'KR' 또는 'JP' (필수)\n"
        "  limit  (int): 최대 반환 건수. 기본값 120. 0 이하이면 전체 반환.\n"
        "  weekly (bool): True이면 주봉 예측 테이블(STOCK_PREDICT_WEEK_*) 사용. 기본값 False.\n"
        "\n"
        "반환값 (List[str]): 'YYYY-MM-DD' 형식의 날짜 문자열 목록 (최신순)\n"
        "\n"
        "사용 예시:\n"
        "  list_predict_dates(market='KR')              # 한국 일봉 예측 기준일 목록\n"
        "  list_predict_dates(market='JP', limit=10)    # 일본 최근 10개 기준일\n"
        "  list_predict_dates(market='KR', weekly=True) # 한국 주봉 예측 기준일\n"
        "\n"
        "활용 팁: 이 목록에서 as_of 값을 골라 predict_rows로 실제 예측 결과를 조회하세요."
    ),
)
def list_predict_dates(
    market: str,
    limit: int = 120,
    weekly: bool = False,
) -> List[str]:
    """Return distinct data_cutoff dates from the predict table, newest first."""
    market = market.upper()
    if market not in ("KR", "JP"):
        raise ValueError("market must be KR or JP")
    table = _predict_table(market, weekly=weekly)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor() as cur:
            limit_sql = "" if limit is None or limit <= 0 else f" LIMIT {int(limit)}"
            cur.execute(
                f"SELECT DISTINCT data_cutoff FROM {table} ORDER BY data_cutoff DESC{limit_sql}"
            )
            return [row[0].strftime("%Y-%m-%d") if hasattr(row[0], "strftime") else str(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()


@mcp.tool(
    name="predict_rows",
    description=(
        "특정 기준일(as_of)의 예측 결과 전체를 확률 내림차순으로 반환합니다.\n"
        "\n"
        "파라미터:\n"
        "  market (str): 'KR' 또는 'JP' (필수)\n"
        "  as_of  (str): 예측 기준일 'YYYY-MM-DD' (필수). list_predict_dates로 유효 날짜 확인.\n"
        "  weekly (bool): True이면 주봉 예측 테이블(STOCK_PREDICT_WEEK_*) 사용. 기본값 False.\n"
        "\n"
        "반환값 컬럼 (STOCK_PREDICT_KR / STOCK_PREDICT_JP):\n"
        "  - data_cutoff (str): 예측 기준일\n"
        "  - code        (str): 종목 코드\n"
        "  - probability (float): 상승 확률 (0~1)\n"
        "  - run_name    (str): 학습 실행 식별자\n"
        "  - seq_len     (int): 입력 시퀀스 길이\n"
        "  - horizon_days(int): 예측 수익 판단 기간(일)\n"
        "  - rise_threshold(float): 상승 판정 임계값\n"
        "  - created_at  (str): 레코드 생성 시각\n"
        "\n"
        "사용 예시:\n"
        "  predict_rows(market='KR', as_of='2025-05-01')              # 한국 2025-05-01 기준 예측\n"
        "  predict_rows(market='JP', as_of='2025-05-01')              # 일본 동일 기준일\n"
        "  predict_rows(market='KR', as_of='2025-05-01', weekly=True) # 주봉 예측\n"
        "\n"
        "활용 팁: probability 상위 종목이 모델이 선택한 매수 후보입니다. "
        "종목명 확인은 list_stocks, 차트 데이터는 stock_data를 추가로 조회하세요."
    ),
)
def predict_rows(
    market: str,
    as_of: str,
    weekly: bool = False,
) -> List[Dict[str, object]]:
    """Return all predict rows for a given data_cutoff date, ordered by probability DESC."""
    market = market.upper()
    if market not in ("KR", "JP"):
        raise ValueError("market must be KR or JP")
    if not as_of:
        raise ValueError("as_of is required")
    table = _predict_table(market, weekly=weekly)
    conn = mysql.connector.connect(**_db_config(market))
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute(
                f"SELECT * FROM {table} WHERE data_cutoff = %s ORDER BY probability DESC",
                (as_of,),
            )
            rows = cur.fetchall()
            return [_normalize_row(row) for row in rows]
    finally:
        conn.close()


@mcp.tool(
    name="scanner_rows",
    description=(
        "볼린저밴드 상단(UpperBand60_1) 돌파 종목을 스캔하여 반환합니다.\n"
        "Close가 UpperBand60_1 초과이면서 UpperBand60_1 * 1.2 미만인 종목을 거래대금 내림차순으로 최대 20개 반환합니다.\n"
        "\n"
        "파라미터:\n"
        "  market         (str): 'KR' 또는 'JP'. 기본값 'JP'.\n"
        "  scan_date      (str): 스캔 기준일 'YYYY-MM-DD'. 생략 시 직전 거래일 자동 사용.\n"
        "  trans_amnt_min (float): 최소 거래대금 필터. 생략 시 시장별 기본값 사용 (JP: 5억, KR: 10억).\n"
        "  close_max      (float): 최대 주가 필터. 생략 시 시장별 기본값 사용 (JP: 1000, KR: 100000).\n"
        "  weekly         (bool): True이면 주봉 테이블(STOCK_DATA_WEEK_*) 기준으로 스캔. 기본값 False(일봉).\n"
        "\n"
        "반환값 컬럼:\n"
        "  - date            (str): 기준일\n"
        "  - code            (str): 종목 코드\n"
        "  - name            (str): 종목명\n"
        "  - close           (float): 종가\n"
        "  - upperband60_1   (float): 볼린저밴드 상단 (60일 기준 1σ)\n"
        "  - transAmnt       (float): 거래대금\n"
        "  - upperband_ratio (float): Close / UpperBand60_1 비율\n"
        "\n"
        "사용 예시:\n"
        "  scanner_rows(market='JP')                           # 일본 직전 거래일 일봉 기준 스캔\n"
        "  scanner_rows(market='KR', scan_date='2025-05-01')  # 한국 특정일 스캔\n"
        "  scanner_rows(market='JP', weekly=True)              # 일본 주봉 기준 스캔\n"
        "  scanner_rows(market='JP', trans_amnt_min=1000000000, close_max=500)  # 조건 직접 지정\n"
        "\n"
        "활용 팁: 상단 돌파 직후 종목을 빠르게 찾을 때 사용하세요. "
        "상세 차트 데이터는 stock_data(일봉) 또는 stock_data_week(주봉)으로 추가 조회하세요."
    ),
)
def scanner_rows(
    market: str = "JP",
    scan_date: str | None = None,
    trans_amnt_min: float | None = None,
    close_max: float | None = None,
    weekly: bool = False,
) -> List[Dict[str, object]]:
    """Return UpperBand scanner rows for a market (KR or JP)."""
    market = market.upper()
    if market not in ("KR", "JP"):
        raise ValueError("market must be KR or JP")
    defaults = _scanner_defaults(market)
    resolved_date = scan_date or defaults.get("date")
    resolved_trans_amnt_min = trans_amnt_min if trans_amnt_min is not None else defaults.get("trans_amnt_min")
    resolved_close_max = close_max if close_max is not None else defaults.get("close_max")
    if not resolved_date:
        raise ValueError("scan_date could not be resolved")
    if resolved_trans_amnt_min is None or resolved_close_max is None:
        raise ValueError("scanner defaults could not be resolved")
    return _fetch_upperband_breakouts(
        market=market,
        scan_date=str(resolved_date),
        trans_amnt_min=float(resolved_trans_amnt_min),
        close_max=float(resolved_close_max),
        weekly=weekly,
    )


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


@app.get("/api/scanner-defaults")
def api_scanner_defaults() -> Response:
    market = request.args.get("market", "JP").upper()
    if market not in ("KR", "JP"):
        return Response("invalid market", status=400)
    payload = json.dumps(_scanner_defaults(market), default=_json_default)
    return Response(payload, mimetype="application/json")


@app.get("/api/scanner")
def api_scanner() -> Response:
    market = request.args.get("market", "JP").upper()
    scan_date = request.args.get("date", "")
    trans_amnt_min = request.args.get("trans_amnt_min", "")
    close_max = request.args.get("close_max", "")
    if market not in ("KR", "JP"):
        return Response("invalid market", status=400)
    if not scan_date or not trans_amnt_min or not close_max:
        return Response("missing date/trans_amnt_min/close_max", status=400)
    try:
        rows = _fetch_upperband_breakouts(
            market=market,
            scan_date=scan_date,
            trans_amnt_min=float(trans_amnt_min),
            close_max=float(close_max),
        )
    except ValueError:
        return Response("invalid numeric parameter", status=400)
    payload = json.dumps({"rows": rows}, default=_json_default)
    return Response(payload, mimetype="application/json")


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
