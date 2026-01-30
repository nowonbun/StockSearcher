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
from functools import partial
from datetime import datetime
import json
import time
import os
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
    """DB에서 한국 종목 목록(code, name, market) 로드."""
    conn = mysql.connector.connect(**static.db_config_kr)
    rows: List[Tuple[str, str, str]] = []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CODE, NAME, MARKET FROM STOCK_LIST_KR ORDER BY order_no")
            rows = [(r[0], r[1], r[2]) for r in cur.fetchall()]
    finally:
        conn.close()
    return rows


def save_stock_list() -> None:
    """FinanceDataReader에서 KRX 상장 목록을 받아 STOCK_LIST_KR upsert."""
    df = _fetch_stock_listing()
    # 필요한 컬럼만 추출: Code, Name
    df = df[["Code", "Name"]].copy()
    if "Market" not in df.columns:
        df["Market"] = "KRX"
    df["order_no"] = range(len(df))

    payload = [
        (str(row["Code"]), str(row["Name"]), str(row["Market"]), int(row["order_no"]))
        for _, row in df.iterrows()
    ]

    if not payload:
        _log("STOCK_LIST_KR 저장할 데이터 없음")
        return

    query = (
        "INSERT INTO STOCK_LIST_KR (code, name, market, order_no, create_date, update_date) "
        "VALUES (%s, %s, %s, %s, now(), now()) "
        "ON DUPLICATE KEY UPDATE "
        "name = VALUES(name), market = VALUES(market), order_no = VALUES(order_no), update_date = now()"
    )

    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.executemany(query, payload)
        conn.commit()
        _log(f"STOCK_LIST_KR 갱신 완료: {len(payload)}건")
    except Exception as e:
        conn.rollback()
        _log(f"STOCK_LIST_KR 저장 오류: {e}")
        raise
    finally:
        conn.close()


def _fetch_stock_listing() -> pd.DataFrame:
    last_err: Exception | None = None
    for i in range(3):
        try:
            return fdr.StockListing("KRX")
        except json.JSONDecodeError as e:
            last_err = e
        except Exception as e:
            last_err = e
        if i < 2:
            time.sleep(1)

    _log("KRX listing failed, trying KOSPI/KOSDAQ/KONEX fallback.")
    try:
        frames: List[pd.DataFrame] = []
        for market in ("KOSPI", "KOSDAQ", "KONEX"):
            df_m = fdr.StockListing(market)
            df_m = df_m.copy()
            if "Market" not in df_m.columns:
                df_m["Market"] = market
            frames.append(df_m)
        if frames:
            return pd.concat(frames, ignore_index=True)
    except Exception as e:
        last_err = e

    if last_err is not None:
        raise last_err
    raise RuntimeError("KRX listing failed with no error information.")


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


def _calculate_dmi_wilder(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 20,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Return DI+, DI-, ADX using Wilder smoothing."""
    up_move = highs.diff()
    down_move = lows.shift(1) - lows

    plus_dm = pd.Series(0.0, index=highs.index)
    minus_dm = pd.Series(0.0, index=highs.index)
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    tr = pd.concat(
        [
            highs - lows,
            (highs - closes.shift(1)).abs(),
            (lows - closes.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    n = len(tr)
    if n == 0:
        return (pd.Series(dtype="float64"), pd.Series(dtype="float64"), pd.Series(dtype="float64"))

    sm_tr = pd.Series([None] * n, index=tr.index, dtype="float64")
    sm_plus = pd.Series([None] * n, index=tr.index, dtype="float64")
    sm_minus = pd.Series([None] * n, index=tr.index, dtype="float64")

    if n > period:
        start = 1
        end = period + 1
        sm_tr.iloc[period] = tr.iloc[start:end].sum()
        sm_plus.iloc[period] = plus_dm.iloc[start:end].sum()
        sm_minus.iloc[period] = minus_dm.iloc[start:end].sum()

        for i in range(period + 1, n):
            sm_tr.iloc[i] = sm_tr.iloc[i - 1] - (sm_tr.iloc[i - 1] / period) + tr.iloc[i]
            sm_plus.iloc[i] = sm_plus.iloc[i - 1] - (sm_plus.iloc[i - 1] / period) + plus_dm.iloc[i]
            sm_minus.iloc[i] = sm_minus.iloc[i - 1] - (sm_minus.iloc[i - 1] / period) + minus_dm.iloc[i]

    di_plus = 100.0 * sm_plus / sm_tr
    di_minus = 100.0 * sm_minus / sm_tr
    dx = 100.0 * (di_plus - di_minus).abs() / (di_plus + di_minus)

    adx = pd.Series([None] * n, index=tr.index, dtype="float64")
    first_adx_idx = (period * 2) - 1
    if n > first_adx_idx:
        first_range = dx.iloc[period : first_adx_idx + 1]
        if first_range.notna().all():
            adx.iloc[first_adx_idx] = first_range.mean()
            for i in range(first_adx_idx + 1, n):
                if pd.isna(adx.iloc[i - 1]) or pd.isna(dx.iloc[i]):
                    continue
                adx.iloc[i] = ((adx.iloc[i - 1] * (period - 1)) + dx.iloc[i]) / period

    return di_plus, di_minus, adx


def build_rows_from_df(df: pd.DataFrame) -> List[List[Any]]:
    """원본 DataFrame에서 지표 컬럼 생성 후, DB 적재용 행 리스트 변환.

    반환 스키마:
    [date, Open, High, Low, Close, Volume, TransAmnt,
     5MvAvg, 20MvAvg, 50MvAvg, 60MvAvg, 120MvAvg, 240MvAvg,
     UpperBand60_1, LowerBand60_1, LowerBand60_3, DI_plus, DI_minus, ADX]
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

    di_plus, di_minus, adx = _calculate_dmi_wilder(
        work["High"], work["Low"], work["Close"], period=20
    )
    work["DI_plus"] = di_plus
    work["DI_minus"] = di_minus
    work["ADX"] = adx

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
        "DI_plus",
        "DI_minus",
        "ADX",
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
                float(row["DI_plus"]),
                float(row["DI_minus"]),
                float(row["ADX"]),
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
         UpperBand60_1, LowerBand60_1, LowerBand60_3, DI_plus, DI_minus, ADX)
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
        "DI_plus",
        "DI_minus",
        "ADX",
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
def process_symbol(code: str, include_week: bool = False) -> None:
    """단일 심볼(code)에 대해 일/주봉 수집 및 적재 수행."""
    # 일봉
    df_daily = fdr.DataReader(code, static.start_date, static.end_date)
    rows = build_rows_from_df(df_daily)
    insert_rows("STOCK_DATA_KR", code, rows)

    # 주봉 (금요일 기준 주간 집계)
    if include_week and df_daily is not None and not df_daily.empty:
        weekly = df_daily.resample("W-FRI").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
        )
        w_rows = build_rows_from_df(weekly)
        insert_rows("STOCK_DATA_WEEK_KR", code, w_rows)


def main(include_week: bool = False) -> None:
    global _LOGGER
    common.check_directory(static.dir)
    common.check_directory(os.path.join(static.dir, "log"))
    _LOGGER = common.setup_custom_logger(static.dir, "create_stock_dataset_kr")

    # 목록 저장 → 목록 로드 → 병렬 수집
    save_stock_list()
    stocks = get_stock_list()
    codes = [s[0] for s in stocks]

    max_workers = 5
    _log(f"수집 대상 종목 수: {len(codes)} (max_workers={max_workers})")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(partial(process_symbol, include_week=include_week), codes)


if __name__ == "__main__":
    main()

