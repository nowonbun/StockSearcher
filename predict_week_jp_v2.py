from __future__ import annotations

import argparse
from datetime import date
from typing import Iterable, List, Tuple

import mysql.connector
import numpy as np
import pandas as pd
import torch

import function.static as static
from model_jp import load_model_checkpoint
from model_week_jp import _RAW_COLS, StockTransformer, load_codes
from model_week_jp_v2 import V2_FEATURE_COLS, V2_MODEL_MODE, compute_v2_features


def _build_not_null_clause(cols: Iterable[str]) -> str:
    return " AND ".join([f"{c} IS NOT NULL" for c in cols if c != "LowerBand60_3"])


def _fetch_sequence_v2(
    conn: mysql.connector.MySQLConnection,
    table: str,
    code: str,
    seq_len: int,
    cutoff_date: str | None,
) -> np.ndarray | None:
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
    return compute_v2_features(raw)


def predict_probs_v2(
    model: torch.nn.Module,
    table: str,
    codes: List[str],
    seq_len: int,
    cutoff_date: str | None,
    log_every: int,
) -> List[Tuple[str, float]]:
    results: List[Tuple[str, float]] = []
    log_every = max(1, log_every)

    conn = mysql.connector.connect(**static.db_config_jp)
    try:
        for idx, code in enumerate(codes, start=1):
            if idx == 1 or idx % log_every == 0:
                print(f"[infer-v2] code={code} ({idx})")
            seq = _fetch_sequence_v2(conn, table, code, seq_len, cutoff_date)
            if seq is None:
                continue
            with torch.no_grad():
                logit = model(torch.from_numpy(seq[None, ...])).item()
                prob = float(torch.sigmoid(torch.tensor(logit)).item())
            results.append((code, prob))
    finally:
        conn.close()
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="STOCK_DATA_WEEK_JP")
    parser.add_argument("--start-date", default=static.start_date)
    parser.add_argument("--end-date", default=static.end_date)
    parser.add_argument("--seq-len", type=int, default=120)
    parser.add_argument("--horizon-days", type=int, default=20)
    parser.add_argument("--rise-threshold", type=float, default=0.09)
    parser.add_argument("--as-of", default=str(date.today()))
    parser.add_argument("--model", default="model_week_jp_v2.pt")
    parser.add_argument("--d-model", type=int, default=256)
    parser.add_argument("--nhead", type=int, default=8)
    parser.add_argument("--num-encoder-layers", type=int, default=3)
    parser.add_argument("--dim-feedforward", type=int, default=512)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--min-prob", type=float, default=None)
    parser.add_argument("--log-every", type=int, default=200)
    parser.add_argument("--save-db", action="store_true")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--code", default=None)
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

    conn = mysql.connector.connect(**static.db_config_jp)
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
        input_size=len(V2_FEATURE_COLS),
        d_model=args.d_model,
        nhead=args.nhead,
        num_encoder_layers=args.num_encoder_layers,
        dim_feedforward=args.dim_feedforward,
        dropout=args.dropout,
    )
    model.load_state_dict(load_model_checkpoint(args.model, V2_MODEL_MODE, map_location="cpu"))
    model.eval()

    results = predict_probs_v2(model, args.table, codes, args.seq_len, effective_cutoff, args.log_every)
    print(f"infer done: {len(results)} results")
    results.sort(key=lambda x: x[1], reverse=True)

    if args.min_prob is not None:
        results = [r for r in results if r[1] >= args.min_prob]

    top = results[:args.top_k]
    if not top:
        print("no results")
        return

    print("code,upside_probability")
    for code, prob in top:
        print(f"{code},{prob:.6f}")

    if args.save_db:
        if args.run_name is None:
            args.run_name = args.model
        args.data_cutoff = effective_cutoff
        save_predictions(args, top)


def save_predictions(args: argparse.Namespace, rows: List[Tuple[str, float]]) -> None:
    data_cutoff = getattr(args, "data_cutoff", args.as_of)
    conn = mysql.connector.connect(**static.db_config_jp)
    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO STOCK_PREDICT_WEEK_JP
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
        print(f"saved {len(rows)} rows to STOCK_PREDICT_WEEK_JP")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
