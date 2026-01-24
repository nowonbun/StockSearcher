from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
import torch

import function.static as static
import mysql.connector
from model_jp import (
    FEATURE_COLS,
    PriceLSTM,
    compute_feature_stats,
    get_cutoff_date,
    load_codes,
)


def _build_not_null_clause(cols: Iterable[str]) -> str:
    return " AND ".join([f"{c} IS NOT NULL" for c in cols])


def _fetch_sequence(
    conn: mysql.connector.MySQLConnection,
    table: str,
    code: str,
    seq_len: int,
    as_of: str | None,
) -> np.ndarray | None:
    not_null = _build_not_null_clause(FEATURE_COLS)
    if as_of:
        cutoff = (pd.to_datetime(as_of).date() - timedelta(days=1)).isoformat()
        query = (
            f"SELECT {', '.join(FEATURE_COLS)} FROM {table} "
            f"WHERE code = %s AND date <= %s AND {not_null} "
            "ORDER BY date DESC LIMIT %s"
        )
        params: Tuple[object, ...] = (code, cutoff, seq_len)
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
    as_of: str | None,
    log_every: int,
) -> List[Tuple[str, float]]:
    results: List[Tuple[str, float]] = []
    mean = mean.reshape(1, 1, -1).astype(np.float32)
    std = std.reshape(1, 1, -1).astype(np.float32)

    conn = mysql.connector.connect(**static.db_config_jp)
    try:
        for idx, code in enumerate(codes, start=1):
            if idx == 1 or idx % log_every == 0:
                print(f"[infer] code={code} ({idx})")
            seq = _fetch_sequence(conn, table, code, seq_len, as_of)
            if seq is None:
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
    parser.add_argument("--table", default="STOCK_DATA_JP")
    parser.add_argument("--start-date", default=static.start_date)
    parser.add_argument("--end-date", default=static.end_date)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seq-len", type=int, default=60)
    parser.add_argument("--horizon-days", type=int, default=5)
    parser.add_argument("--rise-threshold", type=float, default=0.10)
    parser.add_argument("--as-of", default=str(date.today()))
    parser.add_argument("--model", default="model_jp.pt")
    parser.add_argument("--top-k", type=int, default=20)
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

    cutoff_date = get_cutoff_date(args.table, args.start_date, args.end_date, args.val_ratio)
    mean, std = compute_feature_stats(args.table, args.start_date, args.end_date, cutoff_date)

    model = PriceLSTM(
        input_size=len(FEATURE_COLS),
        hidden_size=64,
        num_layers=2,
        dropout=0.1,
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
        args.as_of,
        args.log_every,
    )
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
        save_predictions(args, top)


def save_predictions(args: argparse.Namespace, rows: List[Tuple[str, float]]) -> None:
    conn = mysql.connector.connect(**static.db_config_jp)
    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO STOCK_PREDICT_JP
                    (as_of, code, probability, run_name, seq_len, horizon_days, rise_threshold, created_at)
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
                        args.as_of,
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
        print(f"saved {len(rows)} rows to STOCK_PREDICT_JP")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
