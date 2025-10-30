"""
일본 주식 데이터 수집/가공/저장을 담당하는 리팩토링 버전.

- 기능 유지: 종목 목록 저장, 일/주봉 데이터 수집, 지표 계산, DB 저장
- 개선 사항:
  - 모듈 최상단으로 import 정리 및 타입 힌트 추가
  - 중복 로직 제거: 일/주 공통 처리 함수로 통합
  - 이동평균/볼린저 계산 경계 처리 명확화(데이터 부족 시 0 반환)
  - DB 입력시 안전한 파라미터 바인딩(executemany) 사용
  - 드라이버 자원 정리 보장
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import mysql.connector
import pandas as pd
import requests

import entity.stock_list_node as stock_list_node
import entity.stock_models as stock_models
import function.common as common
import function.static as static
import function.stock_lib as stock_lib


# ----------------------------
# 종목 목록 관련
# ----------------------------
def get_stock_list_by_url(url: str, timeout: int = 30) -> pd.DataFrame:
    """JPX에서 공개하는 종목 목록을 다운로드해 DataFrame으로 반환.

    실패 시 예외를 발생시킨다.
    """
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return pd.read_excel(BytesIO(resp.content))


def save_stock_list(db_config: dict) -> List[stock_list_node.StockListNode]:
    """종목 목록을 다운로드 후 DB(STOCK_LIST)에 upsert 저장하고 목록을 반환."""
    # https://www.jpx.co.jp/markets/statistics-equities/misc/01.html
    df = get_stock_list_by_url(
        "https://www.jpx.co.jp//markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    )

    stocks: List[stock_list_node.StockListNode] = [
        stock_list_node.StockListNode(*row.tolist())
        for _, row in df.iterrows()
        if row.get("stocktype", "") not in ("ETF／ETN", "PRO Market", "ETF�ETN")
    ]

    # 기존 프로젝트 스타일을 존중: 문자열 쿼리 생성 후 단일 실행
    query = stock_list_node.generateSqlQuery(stocks)
    common.execute_query(db_config, query)
    print("STOCK_LIST 저장 완료")
    return stocks


# ----------------------------
# 시세 데이터 가공
# ----------------------------
def _moving_average(series: Sequence[float], idx: int, window: int) -> float:
    """원본 로직과 동일한 부분창 평균: 데이터가 부족해도 분모는 고정(window)."""
    start = max(0, idx - (window - 1))
    s = series[start : idx + 1]
    return float(sum(s) / window)


def _bollinger_bands(series: Sequence[float], idx: int, window: int, k: float) -> Tuple[float, float, float]:
    """원본과 동일하게 가용 구간으로 계산. 표본이 1개면 표준편차 0 처리."""
    import statistics

    start = max(0, idx - (window - 1))
    w = series[start : idx + 1]
    mean = statistics.mean(w)
    std = float(statistics.stdev(w)) if len(w) >= 2 else 0.0
    upper = mean + std * k
    lower = mean - std * k
    return float(upper), float(mean), float(lower)


def _filter_valid(series: stock_models.StockSeries) -> stock_models.StockSeries:
    """None 값이 포함된 캔들을 제거."""
    return stock_models.StockSeries(
        c for c in series.candles if None not in (c.open, c.high, c.low, c.close, c.volume)
    )


def build_calculated_rows(raw: dict[str, List[Any]]) -> List[List[Any]]:
    """지표 계산을 적용한 행 단위 데이터 생성.

    반환 스키마(헤더 없음):
    [Date, Open, High, Low, Close, Volume, TranAmnt,
     5MvAvg, 20MvAvg, 50MvAvg, 60MvAvg, 120MvAvg, 240MvAvg,
     UpperBand60_1, LowerBand60_1, LowerBand60_3]
    """
    series = stock_models.StockSeries.from_raw(raw)
    series = _filter_valid(series)
    if len(series) == 0:
        return []

    ts = [c.timestamp for c in series.candles]
    op = [float(c.open) for c in series.candles]
    hi = [float(c.high) for c in series.candles]
    lo = [float(c.low) for c in series.candles]
    cl = [float(c.close) for c in series.candles]
    vo = [float(c.volume) for c in series.candles]

    rows: List[List[Any]] = []
    for i in range(len(ts)):
        avg5 = _moving_average(cl, i, 5)
        avg20 = _moving_average(cl, i, 20)
        avg50 = _moving_average(cl, i, 50)
        avg60 = _moving_average(cl, i, 60)
        avg120 = _moving_average(cl, i, 120)
        avg240 = _moving_average(cl, i, 240)

        # 원본 로직과 동일: 0인 경우만 스킵
        if (
            avg5 == 0 or avg20 == 0 or avg50 == 0 or avg60 == 0 or avg120 == 0 or avg240 == 0
        ):
            continue

        up60_1, mid60_1, lo60_1 = _bollinger_bands(cl, i, 60, 1)
        up60_3, mid60_3, lo60_3 = _bollinger_bands(cl, i, 60, 3)

        # 이동평균 구간이 충분하면 볼린저도 충분하므로 0 체크는 생략
        rows.append(
            [
                datetime.fromtimestamp(ts[i] / 1000).strftime("%Y-%m-%d"),
                op[i],
                hi[i],
                lo[i],
                cl[i],
                vo[i],
                cl[i] * vo[i],
                avg5,
                avg20,
                avg50,
                avg60,
                avg120,
                avg240,
                up60_1,
                lo60_1,
                lo60_3,
            ]
        )
    return rows


# ----------------------------
# 원천 데이터 수집
# ----------------------------
def fetch_stock_raw(
    driver: Any,
    symbol: str,
    period_type: str,
    period: int,
    frequency_type: str,
    frequency: int,
    retries: int = 3,
) -> Optional[dict]:
    """야후 파이낸스 차트 API(셀레니움 기반)에서 원시 캔들 데이터 dict 반환."""
    for i in range(retries):
        try:
            lib = stock_lib.StockLib(symbol)
            data = lib.get_historical(driver, period_type, period, frequency_type, frequency)
            if data is None:
                print(f"{symbol} 데이터 없음")
                return None
            return data
        except requests.Timeout:
            print(f"{symbol} timeout")
        except requests.RequestException as e:
            print("error -", e)
        print(f"retry{i} - {symbol}")
    return None


# ----------------------------
# DB 저장
# ----------------------------
def _build_insert_query(
    table: str, include_lowerband60_3: bool
) -> Tuple[str, int]:
    """파라미터 바인딩용 INSERT ... ON DUPLICATE KEY UPDATE 쿼리 생성.

    반환: (query, value_count)
    입력 데이터 튜플 포맷:
        (code, date, open, high, low, close, volume, transamnt,
         5mvavg, 20mvavg, 50mvavg, 60mvavg, 120mvavg, 240mvavg,
         upperband60_1, lowerband60_1[, lowerband60_3])
    """
    cols = [
        "code",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "transamnt",
        "5mvavg",
        "20mvavg",
        "50mvavg",
        "60mvavg",
        "120mvavg",
        "240mvavg",
        "upperband60_1",
        "lowerband60_1",
    ]
    if include_lowerband60_3:
        cols.append("lowerband60_3")

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


def insert_rows(
    table: str,
    code: str,
    rows: List[List[Any]],
    db_config: dict,
    include_lowerband60_3: bool,
) -> None:
    if not rows:
        print(f"{code} 저장할 데이터 없음")
        return

    query, value_count = _build_insert_query(table, include_lowerband60_3)

    payload: List[Tuple[Any, ...]] = []
    for r in rows:
        base = [code] + r[:15]  # date..lowerband60_1까지 15개
        if include_lowerband60_3:
            base.append(r[15])
        payload.append(tuple(base))

    conn = mysql.connector.connect(**db_config)
    try:
        with conn.cursor() as cur:
            cur.executemany(query, payload)
        conn.commit()
        print(f"{code} {table} {len(payload)}건 저장")
    except Exception as e:
        conn.rollback()
        print(e)
        raise
    finally:
        conn.close()


# ----------------------------
# 파이프라인
# ----------------------------
def process_symbol(
    driver: Any,
    code: str,
    period: int,
    db_config: dict,
    freq_type: str,
    table: str,
    include_lowerband60_3: bool,
) -> None:
    raw = fetch_stock_raw(
        driver,
        f"{code}.T",
        stock_lib.PERIOD_TYPE_YEAR,
        period,
        freq_type,
        1,
    )
    if raw is None:
        print(f"{code} 데이터 수집 실패")
        return
    rows = build_calculated_rows(raw)
    insert_rows(table, code, rows, db_config, include_lowerband60_3)


def main() -> None:
    # 종목 목록 저장 및 시세 저장 엔트리포인트
    from selenium import webdriver
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service

    options = webdriver.ChromeOptions()
    # options.add_argument("--headless=new")  # 필요 시 헤드리스

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    try:
        stocks = save_stock_list(static.db_config_jp)

        for s in stocks:
            code = s.code
            try:
                # 일봉
                process_symbol(
                    driver,
                    code,
                    static.period,
                    static.db_config_jp,
                    stock_lib.FREQUENCY_TYPE_DAY,
                    "STOCK_DATA",
                    True,  # lowerband60_3 포함
                )
                # 주봉
                process_symbol(
                    driver,
                    code,
                    static.period,
                    static.db_config_jp,
                    stock_lib.FREQUENCY_TYPE_WEEK,
                    "STOCK_DATA_WEEK",
                    False,  # weekly 테이블은 lowerband60_3 미포함(기존 동작 준수)
                )
            except Exception as e:
                print(e)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
