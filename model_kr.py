from __future__ import annotations

import argparse
from typing import Iterable, List, Tuple

import math

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
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

# DB에서 가져오는 피처 외에 코드 내에서 계산하는 파생 피처
COMPUTED_COLS = ["RSI_14", "MACD", "MACD_signal"]
ALL_FEATURE_COLS = FEATURE_COLS + COMPUTED_COLS

CLOSE_INDEX = FEATURE_COLS.index("Close")
TRANS_AMNT_INDEX = FEATURE_COLS.index("TransAmnt")


# ── 파생 피처 계산 ──────────────────────────────────────────────────────────────

def compute_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    rsi = np.full(len(closes), 50.0, dtype=np.float32)
    if len(closes) <= period:
        return rsi
    deltas = np.diff(closes.astype(np.float64))
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(gains[:period].mean())
    avg_loss = float(losses[:period].mean())
    rs = avg_gain / (avg_loss + 1e-10)
    rsi[period] = 100.0 - 100.0 / (1.0 + rs)
    for t in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[t]) / period
        avg_loss = (avg_loss * (period - 1) + losses[t]) / period
        rs = avg_gain / (avg_loss + 1e-10)
        rsi[t + 1] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    result = np.empty(len(arr), dtype=np.float32)
    result[0] = float(arr[0])
    k = 2.0 / (period + 1)
    for i in range(1, len(arr)):
        result[i] = arr[i] * k + result[i - 1] * (1.0 - k)
    return result


def compute_macd(
    closes: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Tuple[np.ndarray, np.ndarray]:
    ema_fast = _ema(closes.astype(np.float32), fast)
    ema_slow = _ema(closes.astype(np.float32), slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    return macd_line, signal_line


def append_computed_features(features: np.ndarray, closes: np.ndarray) -> np.ndarray:
    """RSI_14, MACD, MACD_signal 컬럼을 features 배열에 추가."""
    rsi = compute_rsi(closes).reshape(-1, 1)
    macd_line, signal_line = compute_macd(closes)
    return np.concatenate(
        [features, rsi, macd_line.reshape(-1, 1), signal_line.reshape(-1, 1)],
        axis=1,
    )


# ── Focal Loss ─────────────────────────────────────────────────────────────────

class FocalLoss(nn.Module):
    """극단적 클래스 불균형 환경에서 hard example에 집중하는 손실 함수."""

    def __init__(
        self,
        alpha: float = 1.0,
        gamma: float = 2.0,
        pos_weight: torch.Tensor | None = None,
    ):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.pos_weight = pos_weight

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce = F.binary_cross_entropy_with_logits(
            logits, targets, pos_weight=self.pos_weight, reduction="none"
        )
        probs = torch.sigmoid(logits)
        p_t = probs * targets + (1.0 - probs) * (1.0 - targets)
        weight = self.alpha * (1.0 - p_t) ** self.gamma
        return (weight * bce).mean()


# ── 모델 ───────────────────────────────────────────────────────────────────────

class PriceLSTM(nn.Module):
    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        num_layers: int,
        dropout: float,
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
        )
        # 시계열 내 중요 시점에 집중하는 Attention pooling
        self.attn = nn.Linear(hidden_size, 1)
        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.LayerNorm(hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)                       # (B, T, H)
        scores = self.attn(out)                     # (B, T, 1)
        weights = torch.softmax(scores, dim=1)      # (B, T, 1)
        context = (out * weights).sum(dim=1)        # (B, H)
        return self.head(context).squeeze(-1)


# ── DB 헬퍼 ────────────────────────────────────────────────────────────────────

def _build_date_clause(
    start_date: str | None, end_date: str | None
) -> Tuple[str, tuple]:
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


# ── 데이터셋 ───────────────────────────────────────────────────────────────────

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

                    # 파생 피처(RSI, MACD) 계산 및 추가
                    features = append_computed_features(features, closes)

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
                        window_closes = closes[end_idx + 1 : future_idx + 1]
                        if window_closes.size == 0:
                            continue
                        label = (
                            1.0
                            if float(closes[future_idx]) >= target
                            and float(window_closes.min()) >= floor
                            else 0.0
                        )

                        # 글로벌 정규화 대신 윈도우 내 z-score 정규화
                        # → 종목 간 가격 스케일 차이 문제 해소
                        x = features[i : i + self.seq_len].copy()  # (T, F)
                        x_mean = x.mean(axis=0, keepdims=True)
                        x_std = x.std(axis=0, keepdims=True)
                        x = (x - x_mean) / (x_std + 1e-8)

                        yield torch.from_numpy(x), torch.tensor(label, dtype=torch.float32)
        finally:
            conn.close()


# ── 학습 루프 ──────────────────────────────────────────────────────────────────

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
    clip_grad_norm: float,
    use_focal_loss: bool,
    focal_gamma: float,
) -> None:
    def build_criterion(weight: float | None) -> nn.Module:
        pw = torch.tensor([weight], device=device) if weight is not None else None
        if use_focal_loss:
            return FocalLoss(gamma=focal_gamma, pos_weight=pw)
        return nn.BCEWithLogitsLoss(pos_weight=pw) if pw is not None else nn.BCEWithLogitsLoss()

    current_weight = pos_weight
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_f1 = -1.0
    prev_prec: float | None = None
    prev_rec: float | None = None
    metric_eps = 1e-6
    drop_streak = 0

    for epoch in range(1, epochs + 1):
        criterion = build_criterion(current_weight)

        model.train()
        train_loss = 0.0
        train_count = 0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            pred = model(x)
            loss = criterion(pred, y)
            optimizer.zero_grad()
            loss.backward()
            if clip_grad_norm > 0:
                nn.utils.clip_grad_norm_(model.parameters(), clip_grad_norm)
            optimizer.step()
            train_loss += loss.item() * x.size(0)
            train_count += x.size(0)
        train_loss = train_loss / train_count if train_count else 0.0
        scheduler.step()

        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        tp = fp = fn = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
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
        f1 = 2.0 * prec * rec / (prec + rec + 1e-8) if (prec + rec) > 0 else 0.0
        current_lr = scheduler.get_last_lr()[0]

        print(
            f"epoch={epoch} train_loss={train_loss:.6f} val_loss={val_loss:.6f} "
            f"acc={acc:.4f} prec={prec:.4f} rec={rec:.4f} f1={f1:.4f} "
            f"thr={eval_threshold:.2f} lr={current_lr:.6f}"
            + (f" pw={current_weight:.4f}" if current_weight is not None else "")
        )

        best_f1 = max(best_f1, f1)
        torch.save(model.state_dict(), model_out)
        print(f"  -> saved current epoch model (epoch={epoch}, f1={f1:.4f}, best_f1={best_f1:.4f})")

        drop_any = (
            prev_prec is not None
            and prev_rec is not None
            and (prec < prev_prec - metric_eps or rec < prev_rec - metric_eps)
        )
        if adaptive_pos_weight and drop_any and current_weight is not None:
            drop_streak += 1
            # precision 하락 → 양성 과다 예측 → pos_weight 낮춤
            # recall 하락    → 양성 과소 예측 → pos_weight 높임
            if prec < prev_prec - metric_eps:
                current_weight *= (1.0 - pos_weight_step)
            else:
                current_weight *= (1.0 + pos_weight_step)
            current_weight = max(1.0, current_weight)
            print(f"adaptive pos_weight -> {current_weight:.4f}")
            prev_prec = prec
            prev_rec = rec
            if drop_streak >= max(1, drop_patience):
                print("drop streak reached: early stop")
                break
            continue

        drop_streak = 0
        prev_prec = prec
        prev_rec = rec

        # val_loss 대신 F1 기준으로 저장 (불균형 데이터 환경에 적합)
        # if f1 > best_f1:
        #     best_f1 = f1
        #     torch.save(model.state_dict(), model_out)
        #     print(f"  -> saved (best f1={best_f1:.4f})")
        # best_f1 = max(best_f1, f1)
        # torch.save(model.state_dict(), model_out)
        # print(f"  -> saved (epoch={epoch}, f1={f1:.4f}, best_f1={best_f1:.4f})")


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # 데이터 범위
    parser.add_argument("--table", default="STOCK_DATA_KR", help="DB 테이블 이름")
    parser.add_argument("--start-date", default=static.start_date, help="데이터 시작일 (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=static.end_date, help="데이터 종료일 (YYYY-MM-DD)")
    # 윈도우/라벨 정의
    parser.add_argument("--seq-len", type=int, default=60, help="시퀀스 길이(일)")
    parser.add_argument("--horizon-days", type=int, default=10, help="라벨 기준 기간(일)")
    parser.add_argument("--rise-threshold", type=float, default=0.05, help="목표 상승률 (예: 0.05 = +5%%)")
    parser.add_argument("--max-drawdown", type=float, default=0.05, help="기간 내 허용 최대 낙폭")
    parser.add_argument("--min-trans-amnt-sum", type=float, default=5_000_000_000, help="유동성 기간 내 TransAmnt 합 최소값")
    parser.add_argument("--liquidity-days", type=int, default=5, help="TransAmnt 합 계산 기간(일)")
    # 학습/검증 분리
    parser.add_argument("--val-ratio", type=float, default=0.2, help="날짜 기준 검증 비율")
    # 학습 루프
    parser.add_argument("--batch-size", type=int, default=2048, help="배치 크기")
    parser.add_argument("--epochs", type=int, default=30, help="학습 에폭 수")
    parser.add_argument("--lr", type=float, default=1e-3, help="학습률")
    parser.add_argument("--clip-grad-norm", type=float, default=1.0, help="gradient clipping max norm (0=비활성)")
    # 모델 구조
    parser.add_argument("--hidden-size", type=int, default=512, help="LSTM 은닉 크기")
    parser.add_argument("--num-layers", type=int, default=2, help="LSTM 레이어 수")
    parser.add_argument("--dropout", type=float, default=0.3, help="드롭아웃(레이어 2개 이상일 때만 적용)")
    # 체크포인트 및 클래스 불균형
    parser.add_argument("--model-out", default="model_kr.pt", help="모델 저장 경로")
    parser.add_argument("--resume", default=None, help="재개 모델 경로")
    parser.add_argument("--pos-weight", type=float, default=None, help="BCE pos_weight (불균형 보정). None이면 pos_rate로 자동 산출")
    parser.add_argument("--adaptive-pos-weight", action=argparse.BooleanOptionalAction, default=True, help="prec/rec 하락 시 pos_weight 적응 조정")
    parser.add_argument("--pos-weight-step", type=float, default=0.05, help="pos_weight 조정 비율 (예: 0.05 = 5%%)")
    parser.add_argument("--drop-patience", type=int, default=3, help="연속 하락 횟수로 조기 종료")
    # Focal Loss
    parser.add_argument("--use-focal-loss", action=argparse.BooleanOptionalAction, default=True, help="BCEWithLogitsLoss 대신 Focal Loss 사용")
    parser.add_argument("--focal-gamma", type=float, default=2.0, help="Focal Loss gamma 파라미터")
    # 진행 로그 및 평가
    parser.add_argument("--log-codes", action="store_true", help="코드별 로딩 로그 출력")
    parser.add_argument("--log-every", type=int, default=50, help="코드 로그 출력 간격")
    parser.add_argument("--eval-threshold", type=float, default=0.3, help="평가용 확률 임계값")
    parser.add_argument("--pos-rate", type=float, default=0.06,
                        help="실제 양성 비율 (예: 0.06). 지정 시 pos_weight를 재산출하고 bias 초기화에 사용")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    codes = load_codes(args.table, args.start_date, args.end_date)
    if not codes:
        raise RuntimeError("no codes loaded from database")

    print(f"loaded codes={len(codes)}")
    cutoff_date = get_cutoff_date(args.table, args.start_date, args.end_date, args.val_ratio)
    print(f"cutoff_date={cutoff_date.date()}")

    # pos_rate / pos_weight 일관성 처리
    # --pos-rate 지정 시: pos_weight를 재산출하여 bias와 손실함수 가중치를 동일 기준으로 맞춤
    # --pos-weight만 지정 시: pos_weight에서 pos_rate를 역산
    if args.pos_rate is not None:
        if not (0.0 < args.pos_rate < 1.0):
            raise ValueError(f"pos_rate must be in (0, 1), got {args.pos_rate}")
        pos_rate_for_bias = args.pos_rate
        args.pos_weight = (1.0 - args.pos_rate) / args.pos_rate
        print(f"pos_rate={pos_rate_for_bias:.4f} → pos_weight 재산출={args.pos_weight:.4f}")
    elif args.pos_weight is not None:
        pos_rate_for_bias = 1.0 / (1.0 + args.pos_weight)
    else:
        pos_rate_for_bias = None

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
        args.log_codes,
        args.log_every,
        args.max_drawdown,
        args.min_trans_amnt_sum,
        args.liquidity_days,
    )

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=False, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, drop_last=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PriceLSTM(
        input_size=len(ALL_FEATURE_COLS),
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
    ).to(device)
    if args.resume:
        model.load_state_dict(torch.load(args.resume, map_location=device))
    elif pos_rate_for_bias is not None:
        # 출력 레이어 bias를 실제 양성 비율 기준으로 초기화
        # bias = log(p / (1-p)) : sigmoid(bias) ≈ pos_rate → 초기 예측이 데이터 분포에 맞게 시작
        bias_init = math.log(pos_rate_for_bias / (1.0 - pos_rate_for_bias))
        with torch.no_grad():
            model.head[-1].bias.fill_(bias_init)
        print(f"output bias initialized to {bias_init:.4f} (pos_rate={pos_rate_for_bias:.4f})")

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
        args.clip_grad_norm,
        args.use_focal_loss,
        args.focal_gamma,
    )


if __name__ == "__main__":
    main()
