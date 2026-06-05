from __future__ import annotations

import argparse
from datetime import date
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
import torch

import function.static as static
import mysql.connector
from model_week_kr import (
    RELATIVE_FEATURE_COLS,
    _RAW_COLS,
    StockTransformer,
    compute_relative_features,
    extract_trend_filter_metrics,
    load_codes,
)

DEFAULT_MODEL_KR_TREND_V1 = "model_week_kr.pt"
DEFAULT_DECISION_THRESHOLD_KR_TREND_V1 = 0.50
DEFAULT_TOP_K_KR_TREND_V1 = 30


def _build_not_null_clause(cols: Iterable[str]) -> str:
    return " AND ".join([f"{c} IS NOT NULL" for c in cols if c != "LowerBand60_3"])


def _fetch_sequence(
    conn: mysql.connector.MySQLConnection,
    table: str,
    code: str,
    seq_len: int,
    cutoff_date: str | None,
) -> tuple[np.ndarray, dict[str, float]] | None:
    not_null = _build_not_null_clause(_RAW_COLS)
    if cutoff_date:
        query = (
            f"SELECT {', '.join(_RAW_COLS)} FROM {table} "
            f"WHERE code = %s AND date <= %s AND {not_null} "
            "ORDER BY date DESC LIMIT %s"
        )
        params: Tuple[object, ...] = (code, cutoff_date, seq_len)
    else:
        query = (
            f"SELECT {', '.join(_RAW_COLS)} FROM {table} "
            f"WHERE code = %s AND {not_null} "
            "ORDER BY date DESC LIMIT %s"
        )
        params = (code, seq_len)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    if len(rows) < seq_len:
        return None
    raw = np.array(rows[::-1], dtype=np.float32)
    features = compute_relative_features(raw)
    return features, extract_trend_filter_metrics(features)


def predict_probs(
    model: torch.nn.Module,
    table: str,
    codes: List[str],
    seq_len: int,
    cutoff_date: str | None,
    log_every: int,
    min_trans_amnt_sum: float | None,
    liquidity_days: int,
    min_high_52w_ratio: float | None,
    min_close_vs_ma20: float | None,
    min_close_vs_ma60: float | None,
    min_ma20_slope: float | None,
    min_ma60_slope: float | None,
) -> List[Tuple[str, float]]:
    results: List[Tuple[str, float]] = []
    log_every = max(1, log_every)

    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        for idx, code in enumerate(codes, start=1):
            if idx == 1 or idx % log_every == 0:
                print(f"[infer] code={code} ({idx})")

            # 유동성 필터: raw TransAmnt 별도 조회
            if min_trans_amnt_sum is not None:
                not_null = _build_not_null_clause(_RAW_COLS)
                liq_query = (
                    f"SELECT TransAmnt FROM {table} "
                    f"WHERE code = %s AND {not_null} "
                    "ORDER BY date DESC LIMIT %s"
                )
                if cutoff_date:
                    liq_query = (
                        f"SELECT TransAmnt FROM {table} "
                        f"WHERE code = %s AND date <= %s AND {not_null} "
                        "ORDER BY date DESC LIMIT %s"
                    )
                with conn.cursor() as cur:
                    if cutoff_date:
                        cur.execute(liq_query, (code, cutoff_date, liquidity_days))
                    else:
                        cur.execute(liq_query, (code, liquidity_days))
                    liq_rows = cur.fetchall()
                if len(liq_rows) < liquidity_days:
                    continue
                liq_sum = sum(float(r[0]) for r in liq_rows if r[0] is not None)
                if liq_sum < min_trans_amnt_sum:
                    continue

            seq_info = _fetch_sequence(conn, table, code, seq_len, cutoff_date)
            if seq_info is None:
                continue
            seq, trend_metrics = seq_info

            if min_high_52w_ratio is not None and trend_metrics["high_52w_ratio"] < min_high_52w_ratio:
                continue
            if min_close_vs_ma20 is not None and trend_metrics["close_vs_ma20"] < min_close_vs_ma20:
                continue
            if min_close_vs_ma60 is not None and trend_metrics["close_vs_ma60"] < min_close_vs_ma60:
                continue
            if min_ma20_slope is not None and trend_metrics["ma20_slope_5"] < min_ma20_slope:
                continue
            if min_ma60_slope is not None and trend_metrics["ma60_slope_10"] < min_ma60_slope:
                continue
            x_t = torch.from_numpy(seq[None, ...])
            with torch.no_grad():
                logit = model(x_t).item()
                prob = float(torch.sigmoid(torch.tensor(logit)).item())
            results.append((code, prob))
    finally:
        conn.close()

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="STOCK_DATA_WEEK_KR")
    parser.add_argument("--start-date", default=static.start_date)
    parser.add_argument("--end-date", default=static.end_date)
    parser.add_argument("--seq-len", type=int, default=120)
    parser.add_argument("--horizon-days", type=int, default=8)
    parser.add_argument("--rise-threshold", type=float, default=0.12)
    parser.add_argument("--min-trans-amnt-sum", type=float, default=1_000_000_000)
    parser.add_argument("--liquidity-days", type=int, default=5)
    parser.add_argument("--as-of", default=str(date.today()), help="추론 기준일 (YYYY-MM-DD)")
    parser.add_argument("--model", default=DEFAULT_MODEL_KR_TREND_V1)
    parser.add_argument("--d-model", type=int, default=256)
    parser.add_argument("--nhead", type=int, default=8)
    parser.add_argument("--num-encoder-layers", type=int, default=3)
    parser.add_argument("--dim-feedforward", type=int, default=512)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K_KR_TREND_V1)
    parser.add_argument("--min-high-52w-ratio", type=float, default=None, help="52주 고점 근접 비율 최소값")
    parser.add_argument("--min-close-vs-ma20", type=float, default=None, help="close_vs_ma20 최소값 (model_kr.py trend label 기본값과 일치)")
    parser.add_argument("--min-close-vs-ma60", type=float, default=None, help="close_vs_ma60 최소값 (학습 라벨 외 추가 보수 필터가 필요할 때만 사용)")
    parser.add_argument("--min-ma20-slope", type=float, default=None, help="ma20_slope_5 최소값 (model_kr.py trend label 기본값과 일치)")
    parser.add_argument("--min-ma60-slope", type=float, default=None, help="ma60_slope_10 최소값 (model_kr.py trend label 기본값과 일치)")
    parser.add_argument("--min-prob", type=float, default=None)
    parser.add_argument("--decision-threshold", type=float, default=DEFAULT_DECISION_THRESHOLD_KR_TREND_V1)
    parser.add_argument("--log-every", type=int, default=200)
    parser.add_argument("--save-db", action="store_true")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--code", default=None, help="단일 코드 추론")
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

    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(date) FROM {args.table}")
            row = cur.fetchone()
        max_date = row[0] if row else None
    finally:
        conn.close()

    requested_cutoff = pd.to_datetime(args.as_of).date().isoformat()
    effective_cutoff = min(requested_cutoff, max_date.isoformat()) if max_date else requested_cutoff

    model = StockTransformer(
        input_size=len(RELATIVE_FEATURE_COLS),
        d_model=args.d_model,
        nhead=args.nhead,
        num_encoder_layers=args.num_encoder_layers,
        dim_feedforward=args.dim_feedforward,
        dropout=args.dropout,
    )
    model.load_state_dict(torch.load(args.model, map_location="cpu", weights_only=True))
    model.eval()

    results = predict_probs(
        model,
        args.table,
        codes,
        args.seq_len,
        effective_cutoff,
        args.log_every,
        args.min_trans_amnt_sum,
        args.liquidity_days,
        args.min_high_52w_ratio,
        args.min_close_vs_ma20,
        args.min_close_vs_ma60,
        args.min_ma20_slope,
        args.min_ma60_slope,
    )
    print(f"infer done: {len(results)} results")
    results.sort(key=lambda x: x[1], reverse=True)

    effective_threshold = None
    if args.min_prob is not None and args.decision_threshold is not None:
        effective_threshold = max(args.min_prob, args.decision_threshold)
    elif args.min_prob is not None:
        effective_threshold = args.min_prob
    elif args.decision_threshold is not None:
        effective_threshold = args.decision_threshold

    if effective_threshold is not None:
        print(f"apply threshold={effective_threshold:.4f}")
        results = [r for r in results if r[1] >= effective_threshold]

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
                INSERT INTO STOCK_PREDICT_WEEK_KR
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
                    (data_cutoff, code, float(prob), args.run_name,
                     args.seq_len, args.horizon_days, args.rise_threshold)
                    for code, prob in rows
                ],
            )
        conn.commit()
        print(f"saved {len(rows)} rows to STOCK_PREDICT_WEEK_KR")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
