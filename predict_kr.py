from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
import torch

import function.static as static
import mysql.connector
from model_kr import (
    FEATURE_COLS,
    PriceLSTM,
    compute_feature_stats,
    get_cutoff_date,
    load_codes,
    TRANS_AMNT_INDEX,
)


def _build_not_null_clause(cols: Iterable[str]) -> str:
    return " AND ".join([f"{c} IS NOT NULL" for c in cols])


def _fetch_sequence(
    conn: mysql.connector.MySQLConnection,
    table: str,
    code: str,
    seq_len: int,
    cutoff_date: str | None,
) -> np.ndarray | None:
    not_null = _build_not_null_clause(FEATURE_COLS)
    if cutoff_date:
        query = (
            f"SELECT {', '.join(FEATURE_COLS)} FROM {table} "
            f"WHERE code = %s AND date <= %s AND {not_null} "
            "ORDER BY date DESC LIMIT %s"
        )
        params: Tuple[object, ...] = (code, cutoff_date, seq_len)
    else:
        query = (
            f"SELECT {', '.join(FEATURE_COLS)} FROM {table} "
            f"WHERE code = %s AND {not_null} "
            "ORDER BY date DESC LIMIT %s"
        )
        params = (code, seq_len)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    if len(rows) < seq_len:
        return None
    rows = rows[::-1]
    return np.array(rows, dtype=np.float32)


def predict_probs(
    model: torch.nn.Module,
    table: str,
    codes: List[str],
    seq_len: int,
    mean: np.ndarray,
    std: np.ndarray,
    cutoff_date: str | None,
    log_every: int,
    min_trans_amnt_sum: float | None,
    liquidity_days: int,
) -> List[Tuple[str, float]]:
    results: List[Tuple[str, float]] = []
    log_every = max(1, log_every)
    mean = mean.reshape(1, 1, -1).astype(np.float32)
    std = std.reshape(1, 1, -1).astype(np.float32)

    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        for idx, code in enumerate(codes, start=1):
            if idx == 1 or idx % log_every == 0:
                print(f"[infer] code={code} ({idx})")
            seq = _fetch_sequence(conn, table, code, seq_len, cutoff_date)
            if seq is None:
                continue
            if min_trans_amnt_sum is not None:
                if liquidity_days > seq_len:
                    raise ValueError("liquidity_days cannot exceed seq_len")
                liq_slice = seq[-liquidity_days:, TRANS_AMNT_INDEX]
                if float(liq_slice.sum()) < min_trans_amnt_sum:
                    continue
            x = (seq[None, ...] - mean) / std
            x_t = torch.from_numpy(x)
            with torch.no_grad():
                logit = model(x_t).item()
                prob = float(torch.sigmoid(torch.tensor(logit)).item())
            results.append((code, prob))
    finally:
        conn.close()

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # 데이터 범위 (통계 및 종목 목록).
    parser.add_argument("--table", default="STOCK_DATA_KR", help="DB 테이블 이름")
    parser.add_argument("--start-date", default=static.start_date, help="데이터 시작일 (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=static.end_date, help="데이터 종료일 (YYYY-MM-DD)")
    parser.add_argument("--val-ratio", type=float, default=0.2, help="날짜 기준 검증 비율")
    # 윈도우/라벨 정의 (특징 계산 + DB 저장에 사용).
    parser.add_argument("--seq-len", type=int, default=60, help="시퀀스 길이(일)")
    parser.add_argument("--horizon-days", type=int, default=5, help="라벨 기준 기간(일)")
    parser.add_argument("--rise-threshold", type=float, default=0.10, help="목표 상승률 (예: 0.10 = +10%)")
    parser.add_argument("--min-trans-amnt-sum", type=float, default=5000000000 * 5, help="유동성 기간 내 TransAmnt 합 최소값")
    parser.add_argument("--liquidity-days", type=int, default=5, help="TransAmnt 합 계산 기간(일)")
    # 추론 기준일/모델 선택.
    parser.add_argument("--as-of", default=str(date.today()), help="예측 기준일 (YYYY-MM-DD)")
    parser.add_argument("--model", default="model_kr.pt", help="모델 경로")
    parser.add_argument("--hidden-size", type=int, default=512, help="LSTM 은닉 크기(학습과 동일)")
    parser.add_argument("--num-layers", type=int, default=2, help="LSTM 레이어 수(학습과 동일)")
    parser.add_argument("--dropout", type=float, default=0.1, help="드롭아웃(학습과 동일)")
    # 출력 필터링 및 로그.
    parser.add_argument("--top-k", type=int, default=100, help="확률 상위 K개")
    parser.add_argument("--min-prob", type=float, default=None, help="확률 하한 필터")
    parser.add_argument("--log-every", type=int, default=200, help="코드 로그 출력 간격")
    # DB 저장 옵션 및 단일 코드 지정.
    parser.add_argument("--save-db", action="store_true", help="DB 저장")
    parser.add_argument("--run-name", default=None, help="DB 저장용 태그")
    parser.add_argument("--code", default=None, help="단일 코드 예측")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.code:
        codes = [args.code]
    else:
        codes = load_codes(args.table, args.start_date, args.end_date)
        if not codes:
            raise RuntimeError("no codes loaded from database")
    print(f"loaded codes={len(codes)}")

    cutoff_date = get_cutoff_date(args.table, args.start_date, args.end_date, args.val_ratio)
    mean, std = compute_feature_stats(args.table, args.start_date, args.end_date, cutoff_date)

    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(date) FROM {args.table}")
            max_date_row = cur.fetchone()
        max_date = max_date_row[0] if max_date_row else None
    finally:
        conn.close()

    requested_cutoff = pd.to_datetime(args.as_of).date().isoformat()
    if max_date is not None:
        max_date_str = max_date.isoformat()
        effective_cutoff = min(requested_cutoff, max_date_str)
    else:
        effective_cutoff = requested_cutoff

    model = PriceLSTM(
        input_size=len(FEATURE_COLS),
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
    )
    model.load_state_dict(torch.load(args.model, map_location="cpu"))
    model.eval()

    results = predict_probs(
        model,
        args.table,
        codes,
        args.seq_len,
        mean,
        std,
        effective_cutoff,
        args.log_every,
        args.min_trans_amnt_sum,
        args.liquidity_days,
    )
    print(f"infer done: {len(results)} results")
    results.sort(key=lambda x: x[1], reverse=True)

    if args.min_prob is not None:
        results = [r for r in results if r[1] >= args.min_prob]

    top = results[: args.top_k]
    if not top:
        print("no results")
        return
    print("code,prob")
    for code, prob in top:
        print(f"{code},{prob:.6f}")

    if args.save_db:
        if args.run_name is None:
            args.run_name = args.model
        args.data_cutoff = effective_cutoff
        save_predictions(args, top)


def save_predictions(args: argparse.Namespace, rows: List[Tuple[str, float]]) -> None:
    data_cutoff = getattr(args, "data_cutoff", args.as_of)
    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO STOCK_PREDICT_KR
                    (data_cutoff, code, probability, run_name, seq_len, horizon_days, rise_threshold, created_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, now())
                ON DUPLICATE KEY UPDATE
                    probability = VALUES(probability),
                    run_name = VALUES(run_name),
                    seq_len = VALUES(seq_len),
                    horizon_days = VALUES(horizon_days),
                    rise_threshold = VALUES(rise_threshold),
                    created_at = now()
                """,
                [
                    (
                        data_cutoff,
                        code,
                        float(prob),
                        args.run_name,
                        args.seq_len,
                        args.horizon_days,
                        args.rise_threshold,
                    )
                    for code, prob in rows
                ],
            )
        conn.commit()
        print(f"saved {len(rows)} rows to STOCK_PREDICT_KR")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
