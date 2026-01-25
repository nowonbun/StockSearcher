from __future__ import annotations

import argparse
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, IterableDataset

import function.static as static
import mysql.connector


FEATURE_COLS = [
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

CLOSE_INDEX = FEATURE_COLS.index("Close")


class PriceLSTM(nn.Module):
    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int,
        dropout: float,
    ):
        super().__init__()
        # nn.LSTM: 순환 신경망 모듈. 시계열처럼 “순서”가 있는 입력을 처리하고, 내부에 기억(state)을 유지해. 출력은 (시퀀스 출력, 마지막 state) 형태.

        # hidden_size=64: LSTM의 은닉 상태 차원. 클수록 모델이 표현할 수 있는 정보가 늘어나지만 파라미터/연산도 늘어남.
        # num_layers=2: LSTM을 2층으로 쌓음. 1층보다 복잡한 패턴을 잡을 수 있지만 과적합/느려질 수 있음.
        # dropout=0.1: 층 사이에 10% 확률로 뉴런을 끄는 정규화. 과적합 방지 목적. (LSTM에서는 층 사이에만 적용됨)
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
        )

        # nn.Sequential: 여러 레이어를 순서대로 묶어 한 번에 forward 하게 하는 컨테이너. 자체가 모델 종류는 아니고, Linear/ReLU/Dropout 같은 레이어를 직렬로 연결하는 용도야.
        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        last = out[:, -1, :]
        return self.head(last).squeeze(-1)


def _build_date_clause(start_date: str | None, end_date: str | None) -> Tuple[str, Tuple[str, str] | Tuple[()]]:
    if start_date and end_date:
        return "date BETWEEN %s AND %s", (start_date, end_date)
    return "1=1", ()


def _build_not_null_clause(cols: Iterable[str]) -> str:
    return " AND ".join([f"{c} IS NOT NULL" for c in cols])


def load_codes(
    table: str,
    start_date: str | None,
    end_date: str | None,
) -> List[str]:
    date_clause, params = _build_date_clause(start_date, end_date)
    query = f"SELECT DISTINCT code FROM {table} WHERE {date_clause} ORDER BY code"
    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_cutoff_date(
    table: str,
    start_date: str | None,
    end_date: str | None,
    val_ratio: float,
) -> pd.Timestamp:
    date_clause, params = _build_date_clause(start_date, end_date)
    query = f"SELECT DISTINCT date FROM {table} WHERE {date_clause} ORDER BY date"
    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            dates = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    if not dates:
        raise ValueError("no dates available to split")
    cut_idx = int(len(dates) * (1.0 - val_ratio))
    return pd.Timestamp(dates[max(0, min(len(dates) - 1, cut_idx))])


def compute_feature_stats(
    table: str,
    start_date: str | None,
    end_date: str | None,
    cutoff_date: pd.Timestamp,
) -> Tuple[np.ndarray, np.ndarray]:
    date_clause, params = _build_date_clause(start_date, end_date)
    not_null = _build_not_null_clause(FEATURE_COLS)
    where = f"{date_clause} AND date <= %s AND {not_null}"
    params = params + (cutoff_date.date(),)

    avg_cols = ", ".join([f"AVG({c}) AS avg_{c}" for c in FEATURE_COLS])
    std_cols = ", ".join([f"STDDEV_POP({c}) AS std_{c}" for c in FEATURE_COLS])
    query = f"SELECT {avg_cols}, {std_cols} FROM {table} WHERE {where}"

    conn = mysql.connector.connect(**static.db_config_kr)
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise ValueError("no training rows before cutoff date")

    mean = np.array(row[: len(FEATURE_COLS)], dtype=np.float32)
    std = np.array(row[len(FEATURE_COLS) :], dtype=np.float32)
    std[std == 0] = 1.0
    return mean, std


class WindowIterableDataset(IterableDataset):
    def __init__(
        self,
        table: str,
        codes: List[str],
        start_date: str | None,
        end_date: str | None,
        seq_len: int,
        horizon_days: int,
        rise_threshold: float,
        cutoff_date: pd.Timestamp,
        split: str,
        mean: np.ndarray,
        std: np.ndarray,
        log_codes: bool,
        log_every: int,
    ):
        super().__init__()
        self.seq_len = seq_len
        self.horizon_days = horizon_days
        self.rise_threshold = rise_threshold
        self.cutoff_date = pd.Timestamp(cutoff_date)
        self.split = split
        self.mean = mean.reshape(1, 1, -1).astype(np.float32)
        self.std = std.reshape(1, 1, -1).astype(np.float32)
        self.table = table
        self.codes = codes
        self.start_date = start_date
        self.end_date = end_date
        self.log_codes = log_codes
        self.log_every = max(1, log_every)

    def __iter__(self):
        date_clause, date_params = _build_date_clause(self.start_date, self.end_date)
        not_null = _build_not_null_clause(FEATURE_COLS)
        where = f"code = %s AND {date_clause} AND {not_null}"
        query = (
            f"SELECT date, {', '.join(FEATURE_COLS)} FROM {self.table} "
            f"WHERE {where} ORDER BY date"
        )

        conn = mysql.connector.connect(**static.db_config_kr)
        try:
            with conn.cursor() as cur:
                for idx, code in enumerate(self.codes, start=1):
                    params = (code,) + date_params
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    if not rows:
                        continue
                    if self.log_codes and (idx == 1 or idx % self.log_every == 0):
                        print(f"[{self.split}] loading code={code} rows={len(rows)} ({idx})")

                    dates = np.array([r[0] for r in rows])
                    features = np.array([r[1:] for r in rows], dtype=np.float32)
                    closes = features[:, CLOSE_INDEX]

                    max_start = len(features) - (self.seq_len + self.horizon_days) + 1
                    if max_start <= 0:
                        continue
                    for i in range(max_start):
                        end_idx = i + self.seq_len - 1
                        label_date = pd.Timestamp(dates[end_idx])
                        if self.split == "train" and label_date > self.cutoff_date:
                            continue
                        if self.split == "val" and label_date <= self.cutoff_date:
                            continue

                        base = closes[end_idx]
                        if base == 0:
                            continue
                        future_slice = closes[end_idx + 1 : end_idx + self.horizon_days + 1]
                        if future_slice.size == 0:
                            continue
                        target = base * (1.0 + self.rise_threshold)
                        label = 1.0 if float(future_slice.max()) >= target else 0.0
                        x = (features[i : i + self.seq_len][None, ...] - self.mean) / self.std
                        yield torch.from_numpy(x.squeeze(0)), torch.tensor(label, dtype=torch.float32)
        finally:
            conn.close()


def train_loop(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    device: torch.device,
    epochs: int,
    lr: float,
    model_out: str,
    pos_weight: float | None,
    eval_threshold: float,
) -> None:
    if pos_weight is not None:
        criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight], device=device))
    else:
        criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    best_val = float("inf")
    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        train_count = 0
        for x, y in train_loader:
            x = x.to(device)
            y = y.to(device)
            pred = model(x)
            loss = criterion(pred, y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * x.size(0)
            train_count += x.size(0)
        train_loss = train_loss / train_count if train_count else 0.0

        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        tp = 0
        fp = 0
        fn = 0
        with torch.no_grad():
            for x, y in val_loader:
                x = x.to(device)
                y = y.to(device)
                pred = model(x)
                loss = criterion(pred, y)
                val_loss += loss.item() * x.size(0)
                probs = torch.sigmoid(pred)
                preds = (probs >= eval_threshold).float()
                correct += (preds == y).sum().item()
                tp += ((preds == 1) & (y == 1)).sum().item()
                fp += ((preds == 1) & (y == 0)).sum().item()
                fn += ((preds == 0) & (y == 1)).sum().item()
                total += y.size(0)
        val_loss = val_loss / total if total else 0.0
        acc = correct / total if total else 0.0
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0

        print(
            f"epoch={epoch} train_loss={train_loss:.6f} val_loss={val_loss:.6f} "
            f"acc={acc:.4f} prec={prec:.4f} rec={rec:.4f} thr={eval_threshold:.2f}"
        )

        if val_loss < best_val:
            best_val = val_loss
            torch.save(model.state_dict(), model_out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # 데이터 범위.
    parser.add_argument("--table", default="STOCK_DATA_KR")
    parser.add_argument("--start-date", default=static.start_date)
    parser.add_argument("--end-date", default=static.end_date)
    # 윈도우/라벨 정의.
    parser.add_argument("--seq-len", type=int, default=60)
    parser.add_argument("--horizon-days", type=int, default=5)
    parser.add_argument("--rise-threshold", type=float, default=0.10)
    # 학습/검증 분리.
    parser.add_argument("--val-ratio", type=float, default=0.2)
    # 학습 루프.
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--lr", type=float, default=1e-3)
    # 모델 구조.
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    # 체크포인트 및 클래스 불균형.
    parser.add_argument("--model-out", default="model_kr.pt")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--pos-weight", type=float, default=11.66)
    # 진행 로그 및 평가.
    parser.add_argument("--log-codes", action="store_true")
    parser.add_argument("--log-every", type=int, default=50)
    parser.add_argument("--eval-threshold", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    codes = load_codes(args.table, args.start_date, args.end_date)
    if not codes:
        raise RuntimeError("no codes loaded from database")

    print(f"loaded codes={len(codes)}")
    cutoff_date = get_cutoff_date(args.table, args.start_date, args.end_date, args.val_ratio)
    mean, std = compute_feature_stats(args.table, args.start_date, args.end_date, cutoff_date)

    train_ds = WindowIterableDataset(
        args.table,
        codes,
        args.start_date,
        args.end_date,
        args.seq_len,
        args.horizon_days,
        args.rise_threshold,
        cutoff_date,
        "train",
        mean,
        std,
        args.log_codes,
        args.log_every,
    )
    val_ds = WindowIterableDataset(
        args.table,
        codes,
        args.start_date,
        args.end_date,
        args.seq_len,
        args.horizon_days,
        args.rise_threshold,
        cutoff_date,
        "val",
        mean,
        std,
        args.log_codes,
        args.log_every,
    )

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=False, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, drop_last=False)

    device = torch.device("cpu")
    model = PriceLSTM(
        input_size=len(FEATURE_COLS),
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
    ).to(device)
    if args.resume:
        model.load_state_dict(torch.load(args.resume, map_location=device))

    train_loop(
        model,
        train_loader,
        val_loader,
        device,
        args.epochs,
        args.lr,
        args.model_out,
        args.pos_weight,
        args.eval_threshold,
    )


if __name__ == "__main__":
    main()
