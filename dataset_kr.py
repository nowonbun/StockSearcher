"""
한국 주식 데이터 수집/가공을 리팩터링한 버전.

- 기능 개요: 종목 목록 저장, 일/주봉 데이터 수집, 지표 계산, DB 적재
- 개선 사항:
  - 모듈 최상단 import 정리 및 의존성 명확화
  - 중복 로직 제거 및 공통 유틸로 분리
  - 이동평균/볼린저 계산을 벡터화(DataFrame rolling)로 단순화
  - DB 적재 시 파라미터 바인딩(executemany) 사용 및 커넥션 자원 정리 보장
  - 병렬 처리 구조 유지(ThreadPoolExecutor)
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Iterable, List, Sequence, Tuple

import FinanceDataReader as fdr
import mysql.connector
import pandas as pd

import function.common as common
import function.static as static


# ----------------------------
# 로깅 도우미
# ----------------------------
_LOGGER = None


def _log(msg: str) -> None:
    global _LOGGER
    if _LOGGER is not None:
        common.write_log(_LOGGER, msg)
    else:
        print(msg)


# ----------------------------
# 종목 목록
# ----------------------------
def get_stock_list() -> List[Tuple[str, str, str]]:
    """DB에서 종목 목록(code, name, market) 로드."""
    conn = mysql.connector.connect(**static.db_config_kr)
    rows: List[Tuple[str, str, str]] = []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CODE, NAME, MARKET FROM STOCK_LIST ORDER BY order_no")
            rows = [(r[0], r[1], r[2]) for r in cur.fetchall()]
    finally:
        conn.close()
    return rows


def save_stock_list() -> None:
    """FinanceDataReader에서 KRX 상장 목록을 받아 STOCK_LIST upsert."""
    df = fdr.StockListing("KRX")
    # 필요한 컬럼만 추출: Code, Name
    df = df[["Code", "Name"]].copy()
    df["Market"] = "KRX"
    df["order_no"] = range(len(df))

    payload = [
        (str(row["Code"]), str(row["Name"]), str(row["Market"]), int(row["order_no"]))
        for _, row in df.iterrows()
    ]

    if not payload:
        _log("STOCK_LIST 저장할 데이터 없음")
        return

    query = (
        "INSERT INTO STOCK_LIST (code, name, market, order_no, create_date, update_date) "
        "VALUES (%s, %s, %s, %s, now(), now()) "
        "ON DUPLICATE KEY UPDATE "
        "name = VALUES(name), market = VALUES(market), order_no = VALUES(order_no), update_date = now()"
    )

    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.executemany(query, payload)
        conn.commit()
        _log(f"STOCK_LIST 갱신 완료: {len(payload)}건")
    except Exception as e:
        conn.rollback()
        _log(f"STOCK_LIST 저장 오류: {e}")
        raise
    finally:
        conn.close()


# ----------------------------
# 지표 계산
# ----------------------------
REQ_COLS = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
]


def build_rows_from_df(df: pd.DataFrame) -> List[List[Any]]:
    """원본 DataFrame에서 지표 컬럼 생성 후, DB 적재용 행 리스트 변환.

    반환 스키마:
    [date, Open, High, Low, Close, Volume, TransAmnt,
     5MvAvg, 20MvAvg, 50MvAvg, 60MvAvg, 120MvAvg, 240MvAvg,
     UpperBand60_1, LowerBand60_1, LowerBand60_3]
    """
    if df is None or df.empty:
        return []

    # 원본 컬럼 정리 및 결측치 제거 전처리
    work = df.copy()
    # 필요한 컬럼만 사용하고 타입 보정
    for c in REQ_COLS:
        if c not in work.columns:
            return []
    work = work[REQ_COLS]

    # 이동평균 및 표준편차(60)
    work["5MvAvg"] = work["Close"].rolling(window=5).mean()
    work["20MvAvg"] = work["Close"].rolling(window=20).mean()
    work["50MvAvg"] = work["Close"].rolling(window=50).mean()
    work["60MvAvg"] = work["Close"].rolling(window=60).mean()
    work["120MvAvg"] = work["Close"].rolling(window=120).mean()
    work["240MvAvg"] = work["Close"].rolling(window=240).mean()

    work["60Std"] = work["Close"].rolling(window=60).std()

    work["UpperBand60_1"] = work["60MvAvg"] + work["60Std"] * 1.0
    work["LowerBand60_1"] = work["60MvAvg"] - work["60Std"] * 1.0
    work["LowerBand60_3"] = work["60MvAvg"] - work["60Std"] * 3.0

    work["TransAmnt"] = work["Close"] * work["Volume"]

    # 필요한 모든 컬럼이 채워진 구간만 사용
    needed = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "TransAmnt",
        "5MvAvg",
        "20MvAvg",
        "50MvAvg",
        "60MvAvg",
        "120MvAvg",
        "240MvAvg",
        "UpperBand60_1",
        "LowerBand60_1",
        "LowerBand60_3",
    ]
    work = work.dropna(subset=needed)
    if work.empty:
        return []

    # 인덱스가 DatetimeIndex라고 가정; 문자열 날짜로 변환
    if not isinstance(work.index, pd.DatetimeIndex):
        # 가능한 경우 날짜로 파싱 시도
        try:
            work.index = pd.to_datetime(work.index)
        except Exception:
            pass

    rows: List[List[Any]] = []
    for dt, row in work.iterrows():
        date_str = dt.strftime("%Y-%m-%d") if isinstance(dt, pd.Timestamp) else str(dt)
        rows.append(
            [
                date_str,
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                float(row["Volume"]),
                float(row["TransAmnt"]),
                float(row["5MvAvg"]),
                float(row["20MvAvg"]),
                float(row["50MvAvg"]),
                float(row["60MvAvg"]),
                float(row["120MvAvg"]),
                float(row["240MvAvg"]),
                float(row["UpperBand60_1"]),
                float(row["LowerBand60_1"]),
                float(row["LowerBand60_3"]),
            ]
        )
    return rows


# ----------------------------
# DB 적재
# ----------------------------
def _build_insert_query(table: str) -> Tuple[str, int]:
    """INSERT ... ON DUPLICATE KEY UPDATE 쿼리 생성.

    값 포맷:
        (code, date, Open, High, Low, Close, Volume, TransAmnt,
         5MvAvg, 20MvAvg, 50MvAvg, 60MvAvg, 120MvAvg, 240MvAvg,
         UpperBand60_1, LowerBand60_1, LowerBand60_3)
    """
    cols = [
        "code",
        "date",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "TransAmnt",
        "5MvAvg",
        "20MvAvg",
        "50MvAvg",
        "60MvAvg",
        "120MvAvg",
        "240MvAvg",
        "UpperBand60_1",
        "LowerBand60_1",
        "LowerBand60_3",
    ]

    placeholders = ",".join(["%s"] * len(cols))
    insert_cols = ", ".join(cols) + ", create_date, update_date"
    query = (
        f"INSERT INTO {table} ({insert_cols}) VALUES ("
        f"{placeholders}, now(), now()) "
        "ON DUPLICATE KEY UPDATE "
        + ", ".join([f"{c} = VALUES({c})" for c in cols[2:]])
        + ", update_date = now()"
    )
    return query, len(cols)


def insert_rows(table: str, code: str, rows: List[List[Any]]) -> None:
    if not rows:
        _log(f"{code} {table}: 적재할 데이터 없음")
        return

    query, _ = _build_insert_query(table)
    payload: List[Tuple[Any, ...]] = []
    for r in rows:
        base = [code] + r  # r는 date..LowerBand60_3 총 16개
        payload.append(tuple(base))

    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.executemany(query, payload)
        conn.commit()
        _log(f"{code} {table}: {len(payload)}건 upsert")
    except Exception as e:
        conn.rollback()
        _log(f"{code} {table} 저장 오류: {e}")
        raise
    finally:
        conn.close()


# ----------------------------
# 수집 파이프라인
# ----------------------------
def process_symbol(code: str) -> None:
    """단일 심볼(code)에 대해 일/주봉 수집 및 적재 수행."""
    # 일봉
    df_daily = fdr.DataReader(code, static.start_date, static.end_date)
    rows = build_rows_from_df(df_daily)
    insert_rows("STOCK_DATA", code, rows)

    # 주봉 (금요일 기준 주간 집계)
    if df_daily is not None and not df_daily.empty:
        weekly = df_daily.resample("W-FRI").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        )
        w_rows = build_rows_from_df(weekly)
        insert_rows("STOCK_DATA_WEEK", code, w_rows)


def main() -> None:
    global _LOGGER
    _LOGGER = common.setup_custom_logger(static.dir, "create_stock_dataset_kr2")

    # 목록 저장 → 목록 로드 → 병렬 수집
    save_stock_list()
    stocks = get_stock_list()
    codes = [s[0] for s in stocks]

    max_workers = 5
    _log(f"수집 대상 종목 수: {len(codes)} (max_workers={max_workers})")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(process_symbol, codes)


if __name__ == "__main__":
    main()

