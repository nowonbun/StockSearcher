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
TRANS_AMNT_INDEX = FEATURE_COLS.index("TransAmnt")


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
        max_drawdown: float = 0.03,
        min_trans_amnt_sum: float | None = None,
        liquidity_days: int = 5,
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
        self.max_drawdown = max_drawdown
        self.min_trans_amnt_sum = min_trans_amnt_sum
        self.liquidity_days = liquidity_days
        if self.liquidity_days > self.seq_len:
            raise ValueError("liquidity_days cannot exceed seq_len")

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
                        if self.min_trans_amnt_sum is not None:
                            liq_start = end_idx - self.liquidity_days + 1
                            liq_slice = features[liq_start : end_idx + 1, TRANS_AMNT_INDEX]
                            if float(liq_slice.sum()) < self.min_trans_amnt_sum:
                                continue
                        future_idx = end_idx + self.horizon_days
                        if future_idx >= len(closes):
                            continue
                        target = base * (1.0 + self.rise_threshold)
                        floor = base * (1.0 - self.max_drawdown)
                        window = closes[end_idx + 1 : future_idx + 1]
                        if window.size == 0:
                            continue
                        label = 1.0 if float(closes[future_idx]) >= target and float(window.min()) >= floor else 0.0
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
    adaptive_pos_weight: bool,
    pos_weight_step: float,
    drop_patience: int,
) -> None:
    def build_criterion(weight: float | None) -> nn.Module:
        if weight is not None:
            return nn.BCEWithLogitsLoss(pos_weight=torch.tensor([weight], device=device))
        return nn.BCEWithLogitsLoss()

    weight_step = 0.0
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    best_val = float("inf")
    prev_prec: float | None = None
    prev_rec: float | None = None
    metric_eps = 1e-6
    drop_streak = 0
    weight_direction = -1.0
    current_weight = pos_weight
    for epoch in range(1, epochs + 1):
        if adaptive_pos_weight:
            current_weight = current_weight
        else:
            current_weight = pos_weight
        criterion = build_criterion(current_weight)

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
            + (f" pw={current_weight:.4f}" if current_weight is not None else "")
        )

        drop_any = (
            prev_prec is not None
            and prev_rec is not None
            and (prec < prev_prec - metric_eps or rec < prev_rec - metric_eps)
        )
        if adaptive_pos_weight and drop_any:
            print("prec/rec dropped: skip save this epoch")
            drop_streak += 1
            if current_weight is not None:
                weight_direction *= -1.0
                current_weight = current_weight * (1.0 + weight_direction * pos_weight_step)
                print(f"adaptive pos_weight -> {current_weight:.4f}")
            if drop_streak >= max(1, drop_patience):
                print("drop streak reached: early stop")
                break
            continue
        prev_prec = prec
        prev_rec = rec
        drop_streak = 0

        if val_loss < best_val:
            best_val = val_loss
            torch.save(model.state_dict(), model_out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # 데이터 범위.
    parser.add_argument("--table", default="STOCK_DATA_KR", help="DB 테이블 이름")
    parser.add_argument("--start-date", default=static.start_date, help="데이터 시작일 (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=static.end_date, help="데이터 종료일 (YYYY-MM-DD)")
    # 윈도우/라벨 정의.
    parser.add_argument("--seq-len", type=int, default=60, help="시퀀스 길이(일)")
    parser.add_argument("--horizon-days", type=int, default=5, help="라벨 기준 기간(일)")
    parser.add_argument("--rise-threshold", type=float, default=0.10, help="목표 상승률 (예: 0.10 = +10%)")
    parser.add_argument("--max-drawdown", type=float, default=0.03, help="기간 내 허용 최대 낙폭")
    parser.add_argument("--min-trans-amnt-sum", type=float, default=5000000000 * 5, help="유동성 기간 내 TransAmnt 합 최소값")
    parser.add_argument("--liquidity-days", type=int, default=5, help="TransAmnt 합 계산 기간(일)")
    # 학습/검증 분리.
    parser.add_argument("--val-ratio", type=float, default=0.2, help="날짜 기준 검증 비율")
    # 학습 루프.
    parser.add_argument("--batch-size", type=int, default=2048, help="배치 크기")
    parser.add_argument("--epochs", type=int, default=20, help="학습 에폭 수")
    parser.add_argument("--lr", type=float, default=1e-3, help="학습률")
    # 모델 구조.
    parser.add_argument("--hidden-size", type=int, default=512, help="LSTM 은닉 크기")
    parser.add_argument("--num-layers", type=int, default=2, help="LSTM 레이어 수")
    parser.add_argument("--dropout", type=float, default=0.3, help="드롭아웃(레이어 2개 이상일 때만 적용)")
    # 체크포인트 및 클래스 불균형.
    parser.add_argument("--model-out", default="model_kr.pt", help="모델 저장 경로")
    parser.add_argument("--resume", default=None, help="재개 모델 경로")
    parser.add_argument("--pos-weight", type=float, default=17.6, help="BCE pos_weight(불균형 보정)")
    parser.add_argument("--adaptive-pos-weight", action="store_true", help="prec/rec 하락 시 pos_weight 적응 조정")
    parser.add_argument("--pos-weight-step", type=float, default=0.05, help="pos_weight 조정 비율 (예: 0.1 = 10%)")
    parser.add_argument("--drop-patience", type=int, default=3, help="연속 하락 횟수로 조기 종료")
    # 진행 로그 및 평가.
    parser.add_argument("--log-codes", action="store_true", help="코드별 로딩 로그 출력")
    parser.add_argument("--log-every", type=int, default=50, help="코드 로그 출력 간격")
    parser.add_argument("--eval-threshold", type=float, default=0.60, help="평가용 확률 임계값")
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
        args.max_drawdown,
        args.min_trans_amnt_sum,
        args.liquidity_days,
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
        args.max_drawdown,
        args.min_trans_amnt_sum,
        args.liquidity_days,
    )

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=False, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, drop_last=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    #device = torch.device("cpu")
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
        args.adaptive_pos_weight,
        args.pos_weight_step,
        args.drop_patience,
    )


if __name__ == "__main__":
    main()
