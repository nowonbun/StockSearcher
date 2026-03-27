# StockSearcher 세션 인수인계 요약

## 디렉토리
`D:\work\StockSearcher\`

---

## 소스 파일 구조

| 파일 | 모델 | DB | 상태 |
|------|------|----|------|
| `model2_jp.py` | MeanReversionGRU | db_config_jp | 17 피처 완료 |
| `model3_jp.py` | StockTransformer | db_config_jp | 17 피처 완료 |
| `model2_kr.py` | MeanReversionGRU | db_config_kr | 17 피처 완료 |
| `model3_kr.py` | StockTransformer | db_config_kr | 17 피처 완료 (신규 생성) |

---

## 피처 17개 (4개 파일 공통)

`ret_1d, close_vs_ma5/20/60/240, bb_pos, hl_ratio, di_diff, adx, rsi, macd_norm, macd_sig_norm, vol_vs_ma5/20/60, high_52w_ratio, low_52w_ratio`

- `vol_vs_ma{5,20,60}` = Volume / rolling_mean(Volume, window) - 1, clip [-3, 3]
- `high_52w_ratio` = close / 252일 rolling max(High), clip [0, 1]
- `low_52w_ratio` = close / 252일 rolling min(Low) - 1, clip [0, 2]

---

## JP 실험 결과 (상세: TEST_jp_20260323.md)

| 실험 | 모델 | 피처 | 라벨 | best f1 | prec 최고 | val_loss 최저 | prec/기저율 |
|------|------|------|------|---------|-----------|---------------|-------------|
| #4 | GRU | 12 | 5일/3% | 0.3911 | 0.2617 | 1.0496 | 1.16x |
| #5 | Transformer | 12 | 5일/3% | 0.3800 | 0.2508 | 1.0691 | 1.11x |
| #6 | Transformer | 15 | 5일/3% | 0.3871 | 0.2574 | 1.0752 | 1.14x |
| #7 | Transformer | 17 | 5일/3% | 미완료 | 0.2592 @ep4 | — | — |
| **#8** | **Transformer** | **17** | **3일/5%** | **0.2831** | **0.2013** | **1.0144** | **2.31x** |
| #9 | GRU | 17 | 3일/5% | 0.2802 | 0.2031 | 1.0930 | 2.33x |

### 핵심 결론

1. **라벨 재설계(3일/5%)가 가장 큰 개선 요인**
   - 5일/3% (pos_rate 22.6%) → 정상 변동 내 달성 가능 → 라벨 노이즈 → prec 천장 0.26
   - 3일/5% (pos_rate 8.73%) → 수급/재료 있어야 달성 → 신호 품질 개선 → prec/기저율 2.31x
   - 기대수익: 0.2013 × 5% = **1.01%/예측** (이전 0.2617 × 3% = 0.79% 대비 +28%)

2. **Transformer > GRU** (동일 조건 비교)
   - val_loss 최솟값: 1.0144 vs 1.0930
   - GRU는 ep6 이후 val_loss 급등(1.09 → 1.35), train_loss 계속 하락 → 전형적 과적합

3. **모니터링 기준**
   - val_loss 최저점 = 실질 수렴 시점 (best f1 epoch ≠ 신뢰 기준)
   - threshold 0.55 이상 유지 = 모델 자신감 높음
   - discrimination 시작 epoch이 빠를수록 bias 초기화 / 피처 효과 있음

---

## KR 실험 계획 (상세: TEST_KR_20260325.md)

### 실험 #1 — Transformer 기준선 (model3_kr)

```bash
python model3_kr.py --d-model 256 --nhead 8 --dim-feedforward 512 --num-encoder-layers 3 --horizon-days 3 --rise-threshold 0.05 --max-drawdown 0.04 --pos-rate 0.10
```

> `--pos-rate 0.10`은 추정값. epoch 1 로그의 `val_pos_rate` 확인 후 필요시 재실행.

### 실험 #2 — GRU 공정 비교 (model2_kr)

```bash
python model2_kr.py --seq-len 120 --horizon-days 3 --rise-threshold 0.05 --max-drawdown 0.04 --hidden-size 256 --dropout 0.3 --pos-rate <실험#1 val_pos_rate>
```

---

## 로그 위치

```
D:\work\StockSearcher\log\model{2,3}_{jp,kr}_YYYYMMDD_HHMMSS.log
```

---

## 참조 파일

| 파일 | 내용 |
|------|------|
| `TEST_jp_20260323.md` | JP 실험 #1~#9 전체 기록 및 분석 |
| `TEST_KR_20260325.md` | KR 실험 계획 및 기록 |
| `SESSION_SUMMARY.md` | 이 파일 |
