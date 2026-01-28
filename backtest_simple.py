from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
import torch

import function.static as static
import mysql.connector


def _build_not_null_clause(cols: Iterable[str]) -> str:
    return " AND ".join([f"{c} IS NOT NULL" for c in cols])


def _get_module_and_db(market: str):
    if market == "jp":
        import model_jp as model_mod

        db_config = static.db_config_jp
    else:
        import model_kr as model_mod

        db_config = static.db_config_kr
    return model_mod, db_config


def _fetch_sequence(
    conn: mysql.connector.MySQLConnection,
    table: str,
    code: str,
    seq_len: int,
    as_of: str,
    feature_cols: List[str],
) -> Tuple[np.ndarray, str] | None:
    not_null = _build_not_null_clause(feature_cols)
    cutoff = (pd.to_datetime(as_of).date() - timedelta(days=1)).isoformat()
    query = (
        f"SELECT date, {', '.join(feature_cols)} FROM {table} "
        f"WHERE code = %s AND date <= %s AND {not_null} "
        "ORDER BY date DESC LIMIT %s"
    )
    params: Tuple[object, ...] = (code, cutoff, seq_len)

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    if len(rows) < seq_len:
        return None
    rows = rows[::-1]
    last_date = str(rows[-1][0])
    feats = np.array([r[1:] for r in rows], dtype=np.float32)
    return feats, last_date


def _fetch_close_on_date(
    conn: mysql.connector.MySQLConnection,
    table: str,
    code: str,
    target_date: str,
) -> float | None:
    query = f"SELECT Close FROM {table} WHERE code = %s AND date = %s"
    with conn.cursor() as cur:
        cur.execute(query, (code, target_date))
        row = cur.fetchone()
    if row is None:
        return None
    return float(row[0])


def _get_dates(
    conn: mysql.connector.MySQLConnection,
    table: str,
    start_date: str,
    end_date: str,
) -> List[str]:
    query = f"SELECT DISTINCT date FROM {table} WHERE date BETWEEN %s AND %s ORDER BY date"
    with conn.cursor() as cur:
        cur.execute(query, (start_date, end_date))
        return [str(r[0]) for r in cur.fetchall()]


def _parse_horizons(value: str) -> List[int]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return sorted({int(p) for p in parts})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["jp", "kr"], default="jp", help="시장 선택 (jp/kr)")
    parser.add_argument("--table", default=None, help="DB 테이블 이름(미지정 시 기본값)")
    parser.add_argument("--start-date", default=static.start_date, help="백테스트 시작일 (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=static.end_date, help="백테스트 종료일 (YYYY-MM-DD)")
    parser.add_argument("--as-of-start", default=None, help="추론 시작일 (YYYY-MM-DD)")
    parser.add_argument("--as-of-end", default=None, help="추론 종료일 (YYYY-MM-DD)")
    parser.add_argument("--date-step", type=int, default=5, help="추론 날짜 간격(거래일 기준)")
    parser.add_argument("--max-dates", type=int, default=None, help="최대 추론 날짜 수 제한")
    parser.add_argument("--max-codes", type=int, default=None, help="최대 코드 수 제한")
    parser.add_argument("--seq-len", type=int, default=60, help="시퀀스 길이(일)")
    parser.add_argument("--horizons", default="5,10", help="성과 측정 기간(일) 예: 5,10")
    parser.add_argument("--min-trans-amnt-sum", type=float, default=None, help="유동성 기간 내 TransAmnt 합 최소값")
    parser.add_argument("--liquidity-days", type=int, default=5, help="TransAmnt 합 계산 기간(일)")
    parser.add_argument("--model", default=None, help="모델 경로")
    parser.add_argument("--hidden-size", type=int, default=128, help="LSTM 은닉 크기(학습과 동일)")
    parser.add_argument("--num-layers", type=int, default=2, help="LSTM 레이어 수(학습과 동일)")
    parser.add_argument("--dropout", type=float, default=0.1, help="드롭아웃(학습과 동일)")
    parser.add_argument("--top-k", type=int, default=50, help="확률 상위 K개")
    parser.add_argument("--min-prob", type=float, default=None, help="확률 하한 필터")
    parser.add_argument("--log-every", type=int, default=200, help="코드 로그 출력 간격")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_mod, db_config = _get_module_and_db(args.market)

    table = args.table or ("STOCK_DATA_JP" if args.market == "jp" else "STOCK_DATA_KR")
    model_path = args.model or ("model_jp.pt" if args.market == "jp" else "model_kr.pt")
    feature_cols = model_mod.FEATURE_COLS
    close_index = model_mod.CLOSE_INDEX
    trans_index = model_mod.TRANS_AMNT_INDEX

    conn = mysql.connector.connect(**db_config)
    try:
        dates = _get_dates(conn, table, args.start_date, args.end_date)
    finally:
        conn.close()

    if not dates:
        raise RuntimeError("no dates available")

    as_of_start = args.as_of_start or dates[0]
    as_of_end = args.as_of_end or dates[-1]
    dates = [d for d in dates if as_of_start <= d <= as_of_end]
    dates = dates[:: max(1, args.date_step)]
    if args.max_dates is not None:
        dates = dates[: args.max_dates]

    codes = model_mod.load_codes(table, args.start_date, args.end_date)
    if args.max_codes is not None:
        codes = codes[: args.max_codes]
    if not codes:
        raise RuntimeError("no codes loaded from database")

    cutoff_date = model_mod.get_cutoff_date(table, args.start_date, args.end_date, 0.2)
    mean, std = model_mod.compute_feature_stats(table, args.start_date, args.end_date, cutoff_date)
    mean = mean.reshape(1, 1, -1).astype(np.float32)
    std = std.reshape(1, 1, -1).astype(np.float32)

    model = model_mod.PriceLSTM(
        input_size=len(feature_cols),
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
    )
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()

    horizon_list = _parse_horizons(args.horizons)
    date_index = {d: i for i, d in enumerate(dates)}

    print("as_of,count," + ",".join([f"avg_ret_{h}d,hit_{h}d" for h in horizon_list]))

    conn = mysql.connector.connect(**db_config)
    try:
        for as_of in dates:
            results: List[Tuple[str, float, str, float]] = []
            for idx, code in enumerate(codes, start=1):
                if idx == 1 or idx % max(1, args.log_every) == 0:
                    print(f"[infer] as_of={as_of} code={code} ({idx})")
                seq_info = _fetch_sequence(conn, table, code, args.seq_len, as_of, feature_cols)
                if seq_info is None:
                    continue
                seq, base_date = seq_info
                if args.min_trans_amnt_sum is not None:
                    if args.liquidity_days > args.seq_len:
                        raise ValueError("liquidity_days cannot exceed seq_len")
                    liq_slice = seq[-args.liquidity_days :, trans_index]
                    if float(liq_slice.sum()) < args.min_trans_amnt_sum:
                        continue
                x = (seq[None, ...] - mean) / std
                with torch.no_grad():
                    logit = model(torch.from_numpy(x)).item()
                    prob = float(torch.sigmoid(torch.tensor(logit)).item())
                base_close = float(seq[-1, close_index])
                results.append((code, prob, base_date, base_close))

            if args.min_prob is not None:
                results = [r for r in results if r[1] >= args.min_prob]
            results.sort(key=lambda x: x[1], reverse=True)
            results = results[: args.top_k]

            if not results:
                print(f"{as_of},0," + ",".join(["0,0"] * len(horizon_list)))
                continue

            avg_parts = []
            for h in horizon_list:
                rets = []
                hits = 0
                for code, _, base_date, base_close in results:
                    if base_date not in date_index:
                        continue
                    base_idx = date_index[base_date]
                    future_idx = base_idx + h
                    if future_idx >= len(dates):
                        continue
                    future_date = dates[future_idx]
                    future_close = _fetch_close_on_date(conn, table, code, future_date)
                    if future_close is None or base_close == 0:
                        continue
                    r = (future_close - base_close) / base_close
                    rets.append(r)
                    if r > 0:
                        hits += 1
                if rets:
                    avg_ret = float(np.mean(rets))
                    hit_rate = hits / len(rets)
                else:
                    avg_ret = 0.0
                    hit_rate = 0.0
                avg_parts.append(f"{avg_ret:.4f}")
                avg_parts.append(f"{hit_rate:.4f}")

            print(f"{as_of},{len(results)}," + ",".join(avg_parts))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
