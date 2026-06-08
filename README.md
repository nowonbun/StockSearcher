# StockSearcher

주식 데이터 수집 자동화를 위한 파이썬 스크립트 모음입니다. 일본과 한국 시장의 일/주봉 데이터를 수집하고, 이동평균 및 볼린저 밴드와 같은 지표를 계산한 뒤 MySQL 데이터베이스에 적재합니다.

## 주요 기능

- **일본 시장 수집 (`dataset_jp.py`)**: Selenium 기반으로 JPX에서 제공하는 종목 목록과 개별 시세 데이터를 다운로드합니다.
- **한국 시장 수집 (`dataset_kr.py`)**: FinanceDataReader를 사용해 KRX 상장 종목의 일/주봉 데이터를 가져옵니다.
- **공통 실행 스크립트 (`run.py`)**: `python run.py [jp|kr]` 명령으로 두 파이프라인을 선택적으로 실행할 수 있습니다.
- **모델 학습/추론**: JP/KR 각각의 모델 학습과 확률 상위 종목 리스트 추론을 지원합니다.

## 디렉터리 구조

```
StockSearcher/
├── config.ini           # DB 및 출력 경로 설정
├── run.py               # 엔트리포인트 스크립트
├── dataset_jp.py        # 일본 주식 데이터 수집 파이프라인
├── dataset_kr.py        # 한국 주식 데이터 수집 파이프라인
├── model_jp.py          # 일본 일봉 모델 학습 스크립트
├── model_kr.py          # 한국 일봉 모델 학습 스크립트
├── model_week_jp.py     # 일본 주봉 모델 학습 스크립트
├── model_week_kr.py     # 한국 주봉 모델 학습 스크립트
├── predict_jp.py        # 일본 일봉 상위 확률 추론 스크립트
├── predict_kr.py        # 한국 일봉 상위 확률 추론 스크립트
├── predict_week_jp.py   # 일본 주봉 상위 확률 추론 스크립트
├── predict_week_kr.py   # 한국 주봉 상위 확률 추론 스크립트
├── function/            # 공통 유틸리티 모듈
├── entity/              # 데이터 모델 정의
├── backup/              # 이전 버전 및 참고용 스크립트
└── chromedriver.exe     # 수동으로 제공된 크롬 드라이버(선택)
```

## 사전 준비

### 1. Python 환경

- Python 3.10 이상을 권장합니다.
- 가상환경 생성 후 필요한 패키지를 설치하세요.

```bash
python -m venv .venv
source .venv\Scripts\activate  # Windows는 .venv\Scripts\activate
pip install --upgrade pip
pip install mysql-connector-python pandas requests selenium webdriver-manager FinanceDataReader torch
```

### 2. MySQL 데이터베이스

- MySQL 서버가 준비되어 있어야 합니다.
- 다음 테이블을 사용합니다(`dataset_jp.py`/`dataset_kr.py` 참고).
  - `STOCK_LIST_JP`, `STOCK_DATA_JP`, `STOCK_DATA_WEEK_JP`
  - `STOCK_LIST_KR`, `STOCK_DATA_KR`, `STOCK_DATA_WEEK_KR`
- 샘플 DDL은 직접 작성하거나 `ddl.sql`을 참고하세요.

### 3. Chrome 및 WebDriver

- 일본 수집 스크립트는 Selenium을 통해 Chrome 브라우저를 사용합니다.
- 로컬에 Chrome이 설치되어 있어야 하며, `webdriver-manager`가 자동으로 드라이버를 내려받습니다.
  - 네트워크 차단 환경이라면 `chromedriver.exe`를 직접 제공하고 `webdriver.Chrome(service=..., options=...)` 부분을 환경에 맞게 수정하세요.

## 설정 (`config.ini`)

`config.ini`를 자신의 환경에 맞게 수정합니다.

```ini
[database]
host = 127.0.0.1
port = 3306
user = root
password = ********
database_jp = stock_dataset_jp
database_kr = stock_dataset_kr

[default]
output_dir = D:\stock\stock_searcher
start_date = 2020-01-01
end_date = 2099-12-31
period = 5
```

- `output_dir`: 로그와 CSV 등 출력이 저장될 루트 경로입니다.
- `start_date`, `end_date`: 한국 데이터 수집 시 조회 기간.
- `period`: 일본 데이터 수집 시 조회 연도 단위(예: `5` → 최근 5년).

## 실행 방법

```bash
# 일본 주식 데이터 수집 및 적재
python run.py jp

# 한국 주식 데이터 수집 및 적재
python run.py kr
```

- 인자를 생략하면 기본값(`jp`)으로 실행됩니다.
- 한국 수집 파이프라인은 기본 5개 스레드로 종목을 병렬 처리합니다.

## MCP 실행 (웹 UI 포함 / `/mcp` 제공)

`webapp.py`는 웹 UI와 MCP 엔드포인트를 함께 제공합니다.

```bash
python webapp.py
```

- 웹 UI: `/`
- MCP Streamable HTTP: `/mcp`
- 로그 WebSocket: `/ws/logs/{name}`

### MCP 제공 도구

- `list_stocks(market="KR"|"JP")`
  - 시장 종목 목록 (`code`, `name`)
- `stock_data(market, code, limit=2000, start_date=None, end_date=None)`
  - 종목 시세 데이터 조회 (최신순 반환)
- `list_predict_dates(market="KR"|"JP", limit=120)`
  - 예측 기준일 `data_cutoff` 목록 조회
- `predict_rows(market, as_of)`
  - 해당 기준일 예측 결과 조회 (`data_cutoff`, `code`, `name`, `probability`, `open`, `close`, `low`, `high`, `volume`)

## GitHub Actions + 서버 자동 배포

`master` 브랜치에 push하면 GitHub Actions가 Docker 이미지를 빌드해 GitHub Container Registry(ghcr.io)에 푸시하고, SSH로 서버에 접속해 자동으로 배포합니다.

### 1. GitHub Secrets / Variables 설정

GitHub 리포지토리 → **Settings → Secrets and variables → Actions**에서 아래를 등록합니다.

| 종류 | 이름 | 값 |
|------|------|----|
| Secret | `DEPLOY_HOST` | 서버 IP 또는 도메인 |
| Secret | `DEPLOY_USER` | SSH 접속 유저 (예: `root`) |
| Secret | `DEPLOY_KEY` | SSH 개인키 전체 내용 (`-----BEGIN OPENSSH PRIVATE KEY-----` 포함) |
| Variable | `DEPLOY_PORT` | SSH 포트 (생략 시 기본값 22) |

> `GITHUB_TOKEN`은 자동 제공되므로 별도 등록 불필요합니다.

### 2. 서버 초기 설정 (최초 1회)

```bash
# Docker 설치 (Ubuntu 기준)
curl -fsSL https://get.docker.com | sh

# 작업 디렉터리 및 볼륨 경로 생성
mkdir -p /root/stock/models /root/stock/data/log

# ghcr.io 로그인 (GitHub Personal Access Token, read:packages 권한 필요)
echo "<GITHUB_PAT>" | docker login ghcr.io -u nowonbun --password-stdin

# 프로덕션 compose 파일 및 config.ini 배치
# (아래 파일을 서버 /root/stock/ 에 복사)
scp docker-compose.prod.yml root@<서버>:/root/stock/
scp config.ini              root@<서버>:/root/stock/

# 모델 파일 배치
scp model_jp.pt model_kr.pt model_week_jp.pt model_week_kr.pt root@<서버>:/root/stock/models/
```

### 3. 서버의 config.ini 예시

```ini
[database]
host = <DB_HOST>
port = 3306
user = <DB_USER>
password = <DB_PASS>
database_jp = stock_dataset_jp
database_kr = stock_dataset_kr

[default]
output_dir = /data
start_date = 2020-01-01
end_date = 2099-12-31
period = 5
```

### 4. 최초 수동 기동 (또는 배포 후 확인)

```bash
cd /root/stock
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f
```

이후 `master` push 시마다 GitHub Actions가 이미지를 새로 빌드하고 서버를 자동으로 재기동합니다.

---

## Docker + cron 실행

JP는 새벽 2시, KR은 새벽 4시에 컨테이너 내부 cron으로 실행하도록 구성했습니다. `model_*.pt`는 Windows 공유 폴더를 마운트해서 사용합니다.

## GPU 사용 (PyTorch CUDA)

Docker에서 GPU를 쓰려면 Docker Desktop에서 WSL2 기반 엔진을 켜고, NVIDIA Container Toolkit이 활성화되어 있어야 합니다.
`docker-compose.yml`은 `runtime: nvidia` 설정을 사용합니다 (compose v1 호환).

GPU 확인:

```bash
docker compose run --rm stocksearcher nvidia-smi
```

### 1. config.ini 출력 경로 조정

컨테이너에서 로그/CSV를 남기려면 `output_dir`를 `/data`로 바꾸는 것을 권장합니다.
데이터셋 로그는 `/data/log/logfile_*_YYYY-MM-DD.log`로 저장됩니다.

```ini
[default]
output_dir = /data
```

### 2. docker-compose.yml 수정

- `d:/stock/shared_models` 경로를 실제 Windows 공유 폴더로 변경하세요.
- `JOB_CMD_JP`/`JOB_CMD_KR`는 실행할 스크립트로 바꿀 수 있습니다.
- 구버전 환경변수명인 `CRON_SCHEDULE_JP2`/`KR2`, `JOB_CMD_JP2`/`KR2`도 하위 호환으로 읽지만, 새 설정은 `JP`/`KR` 이름을 기준으로 맞추는 것을 권장합니다.

```yaml
services:
  stocksearcher:
    environment:
      CRON_SCHEDULE_JP: "0 2 * * *"
      CRON_SCHEDULE_KR: "0 4 * * *"
      JOB_CMD_JP: "python dataset_jp.py && python predict_jp.py --model /models/model_jp.pt --seq-len 120 --top-k 20 --save-db"
      JOB_CMD_KR: "python dataset_kr.py && python predict_kr.py --model /models/model_kr.pt --seq-len 120 --top-k 20 --save-db"
      CRON_LOG_PATH: "/data/log/cron.log"
    volumes:
      - ./config.ini:/app/config.ini:ro
      - d:/stock/shared_models:/models:ro
      - d:/stock/stock_searcher:/data
```

### 3. 빌드/실행

```bash
docker compose up -d --build
```

빌드가 느리면 BuildKit 캐시를 켜세요(필수는 아님).

```bash
setx DOCKER_BUILDKIT 1
```

로그 확인:

```bash
docker compose logs -f
```

윈도우에서 cron 로그 확인:

`d:/stock/stock_searcher/log/cron-YYYY-MM-DD.log`

> cron으로 실행되는 dataset/model/predict의 표준 출력은 날짜별 로그 파일에 기록됩니다. 파일명 접두사는 `CRON_LOG_PATH` 기준입니다.

### 4. 수동 실행 (원할 때 1회 실행)

컨테이너 기본 스케줄은 그대로 두고, 필요할 때만 수동으로 1회 실행할 수 있습니다.

#### 데이터 수집만 수동 실행:

```bash
docker compose run --rm stocksearcher python dataset_jp.py
docker compose exec stocksearcher python dataset_jp.py
docker compose exec -d stocksearcher python dataset_jp.py
```

```bash
docker compose run --rm stocksearcher python dataset_kr.py
docker compose exec stocksearcher python dataset_kr.py
docker compose exec -d stocksearcher python dataset_kr.py
```

#### 추론 수동 실행:

```bash
docker compose run --rm stocksearcher python predict_jp.py --model /models/model_jp.pt --seq-len 120 --save-db
docker compose exec stocksearcher python predict_jp.py --model /models/model_jp.pt --seq-len 120 --save-db
```

```bash
docker compose run --rm stocksearcher python predict_kr.py --model /models/model_kr.pt --seq-len 120 --save-db
docker compose exec stocksearcher python predict_kr.py --model /models/model_kr.pt --seq-len 120 --save-db
```

> 참고: `JOB_CMD_JP`/`JOB_CMD_KR`에 작은따옴표(')는 넣지 마세요. cron 파일 생성 시 충돌할 수 있습니다.
> 웹 UI 수동 실행과 cron 자동 실행이 같은 명령을 보도록 `JOB_CMD_JP`/`JOB_CMD_KR`에 `--save-db`를 포함하는 것을 권장합니다.

## 모델 학습 (JP)

JP 일봉 모델은 향후 N 거래일 내 **목표 수익률을 달성하고 기간 내 최대 낙폭 조건을 지킬 확률**을 예측합니다.
기본 타깃: "20일 내 +8% 이상 상승", 기간 내 최대 낙폭 10% 이내입니다.
기본 실행은 2000-01-01부터 데이터를 사용합니다.
`--trend-label-filter`를 켜면 52주 고점 근접, 20일선 상대 위치, 20/60일선 기울기 조건을 미래 라벨에 추가합니다.

```bash
python model_jp.py
```

위 기본 실행은 JP 일봉 모델 기본 파라미터를 사용합니다(`start-date=2000-01-01`, `seq-len=120`, `horizon-days=20`, `rise-threshold=0.08`, `max-drawdown=0.10`, `epochs=30`, `trend-label-filter=False`, `eval-threshold=0.45`, `threshold-sweep-start=0.35`, `threshold-sweep-end=0.70`).

모델 출력 파일 기본값은 현재 작업 폴더의 `model_jp.pt`입니다.
실험 1 문서와 동일한 파일명(`model_jp_trend_v1.pt`)이 필요하면 `--model-out model_jp_trend_v1.pt`를 명시하세요.
현재 구현은 epoch마다 동일 파일명을 덮어써 저장합니다.

유용한 옵션:

```bash
python model_jp.py --model-out d:\stock\StockSearcher\models\model_jp.pt
python model_jp.py --trend-label-min-high-52w-ratio 0.90
python model_jp.py --trend-label-min-close-vs-ma20 0.00
python model_jp.py --trend-label-min-ma20-slope 0.00
python model_jp.py --no-use-focal-loss
```

기본값으로 focal loss와 adaptive pos-weight는 비활성화되어 있습니다. 켜려면:

```bash
python model_jp.py --adaptive-pos-weight
python model_jp.py --use-focal-loss
```

기존 모델 이어서 학습하려면 `--resume`을 사용하세요.

```bash
python model_jp.py --resume d:\stock\shared_models\model_jp.pt --epochs 10 --model-out d:\stock\shared_models\model_jp_resume.pt
```

## 모델 학습 (KR)

KR 일봉 모델도 향후 N 거래일 내 목표 수익률과 최대 낙폭 조건을 기준으로 라벨을 만듭니다.
기본 타깃: "20일 내 +12% 이상 상승", 기간 내 최대 낙폭 10% 이내입니다.
`--trend-label-filter`를 켜면 52주 고점 근접, 20일선 상대 위치, 20/60일선 기울기 조건을 미래 라벨에 추가합니다.

```bash
python model_kr.py --seq-len 120 --horizon-days 20 --rise-threshold 0.12 --max-drawdown 0.10 --epochs 30 --log-codes
```

모델 출력 파일: 현재 작업 폴더에 `model_kr.pt`로 저장됩니다.
현재 구현은 epoch마다 동일 파일명을 덮어써 저장합니다.

기본값으로 focal loss와 adaptive pos-weight는 비활성화되어 있습니다. 켜려면:

```bash
python model_kr.py --adaptive-pos-weight
python model_kr.py --use-focal-loss
python model_kr.py --clip-grad-norm 1.0
```

기존 모델 이어서 학습하려면 `--resume`을 사용하세요.

```bash
python model_kr.py --resume d:\stock\shared_models\model_kr.pt --epochs 10 --model-out d:\stock\shared_models\model_kr_resume.pt
```

## 모델 입력 피처 요약

입력 차원 변경 후 기존 `.pt` 파일은 새 입력 피처 수와 맞지 않을 수 있으므로 일봉/주봉 모델을 다시 학습해야 합니다.

### 일봉 모델 (`model_jp.py`, `model_kr.py`)

상대/파생 피처 10개를 사용합니다.

- `ret_1d`: 전일 대비 종가 수익률
- `close_vs_ma5`: 종가가 5일 이동평균 대비 얼마나 위/아래인지
- `close_vs_ma20`: 종가가 20일 이동평균 대비 얼마나 위/아래인지
- `close_vs_ma60`: 종가가 60일 이동평균 대비 얼마나 위/아래인지
- `close_vs_ma240`: 종가가 240일 이동평균 대비 얼마나 위/아래인지
- `hl_ratio`: 하루 고가-저가 변동폭을 종가로 나눈 값
- `high_52w_ratio`: 종가가 최근 252거래일 최고가 대비 어느 위치인지
- `ma20_slope_5`: 20일 이동평균의 최근 5일 기울기
- `ma60_slope_10`: 60일 이동평균의 최근 10일 기울기
- `ma120_slope_20`: 120일 이동평균의 최근 20일 기울기

### 주봉 모델 (`model_week_jp.py`, `model_week_kr.py`)

주봉 테이블에 있는 이동평균 기준에 맞춰 상대/파생 피처 8개를 사용합니다.

- `ret_1d`
- `close_vs_ma5`
- `close_vs_ma20`
- `close_vs_ma60`
- `hl_ratio`
- `high_52w_ratio`
- `ma20_slope_5`
- `ma60_slope_10`

### 제외한 피처와 옵션

노이즈를 줄이기 위해 다음 파생 피처 또는 필터성 값은 모델 입력/추세 필터에서 제외했습니다.

- `bb_pos`, `di_diff`, `adx`, `rsi`, `macd_norm`, `macd_sig_norm`
- `vol_vs_ma5`, `vol_vs_ma20`, `vol_vs_ma60`
- `low_52w_ratio`, `ma_alignment`

원본 입력 컬럼 중 `LowerBand60_3`, `DI_plus`, `DI_minus`, `ADX`도 모델 입력에서 제외했습니다.
제거된 CLI 옵션은 사용하지 마세요: `--require-uptrend`, `--trend-label-require-ma-alignment`, 주봉의 `--band-label-min-bb-pos`, `--band-label-max-bb-pos`, `--min-bb-pos`, `--max-bb-pos`.

## 주봉 모델 학습

```bash
python model_week_jp.py --model-out d:\stock\StockSearcher\models\model_week_jp.pt
python model_week_kr.py --model-out d:\stock\StockSearcher\models\model_week_kr.pt
```

주봉도 기본 라벨은 목표 수익률과 최대 낙폭 조건만 사용합니다. 미래 추세 조건을 라벨에 추가하려면 `--trend-label-filter`를 명시하세요.

## 추론 (JP)

특정 날짜 기준으로 상위 확률 종목을 출력합니다. `--as-of`가 2025-01-20이면 2025-01-20까지의 데이터로 추론합니다.
추세 필터는 옵션을 명시한 경우에만 적용됩니다.

```bash
python predict_jp.py --model model_jp.pt --seq-len 120 --as-of 2025-01-20 --top-k 20 \
  --min-high-52w-ratio 0.85 --min-close-vs-ma60 0.0
```

특정 종목만 확인하려면 `--code`를 사용하세요.

```bash
python predict_jp.py --model model_jp.pt --seq-len 120 --as-of 2025-01-20 --code 7203
```

DB에 저장하려면 `--save-db`를 추가합니다.

```bash
python predict_jp.py --model model_jp.pt --seq-len 120 --as-of 2025-01-20 --top-k 20 --save-db
```

## 추론 (KR)

```bash
python predict_kr.py --model model_kr.pt --seq-len 120 --as-of 2025-01-20 --top-k 20 \
  --min-high-52w-ratio 0.85 --min-close-vs-ma60 0.0
```

## 주봉 추론

```bash
python predict_week_jp.py --model model_week_jp.pt --seq-len 120 --as-of 2025-01-20 --top-k 20 \
  --min-high-52w-ratio 0.85
python predict_week_kr.py --model model_week_kr.pt --seq-len 120 --as-of 2025-01-20 --top-k 20 \
  --min-high-52w-ratio 0.85
```

## 간단 백테스트 (예측 → 20/40일 성과 권장)

`backtest_simple.py`는 날짜별로 예측을 만든 뒤, 실제 20/40일 수익률과 승률을 확인하는 용도로 쓰는 것을 권장합니다.

```bash
# JP 예시 (유동성 필터 포함)
python backtest_simple.py --market jp --start-date 2023-01-01 --end-date 2025-12-31 \
  --horizons 20,40 --date-step 5 --top-k 50 --min-trans-amnt-sum 1000000000 --liquidity-days 5

# KR 예시 (JP 기준의 10배)
python backtest_simple.py --market kr --start-date 2023-01-01 --end-date 2025-12-31 \
  --horizons 20,40 --date-step 5 --top-k 50 --min-trans-amnt-sum 10000000000 --liquidity-days 5
```

출력 포맷:

```
as_of,count,avg_ret_20d,hit_20d,avg_ret_40d,hit_40d
```

특정 종목만 확인하려면 `--code`를 사용하세요.

```bash
python predict_kr.py --model model_kr.pt --seq-len 120 --as-of 2025-01-20 --code 005930
```

DB에 저장하려면 `--save-db`를 추가합니다.

```bash
python predict_kr.py --model model_kr.pt --seq-len 120 --as-of 2025-01-20 --top-k 20 --save-db
```

## 출력 및 로그

- `output_dir` 하위에 `log/logfile_*_YYYY-MM-DD.log` 형태로 로그가 생성됩니다.
- 데이터베이스 적재 결과와 에러 메시지가 로그에 기록됩니다.

## 모델 평가 지표 이해

### Precision (정밀도) vs Recall (재현율)

**Precision**: 양성으로 예측한 것 중 실제로 맞은 비율
> "내가 오른다고 찍은 종목 중 진짜 오른 비율"
> → 높을수록 헛다리를 덜 짚음

**Recall**: 실제 양성 중 모델이 잡아낸 비율
> "실제로 오른 종목 중 내가 맞춘 비율"
> → 높을수록 놓치는 종목이 적음

**트레이드오프 관계:**
- threshold 높이면 → Precision↑, Recall↓ (확실한 것만 찍음, 많이 놓침)
- threshold 낮추면 → Precision↓, Recall↑ (많이 찍음, 헛다리도 많음)

**이 프로젝트 맥락에서:**
- Precision이 중요 → 추천한 종목이 실제로 올라야 신뢰할 수 있음
- Recall은 부차적 → 일부 좋은 종목을 놓쳐도 괜찮음

**F1 Score**: Precision과 Recall의 조화평균 → 둘 다 고려한 종합 지표
```
F1 = 2 × (Precision × Recall) / (Precision + Recall)
```

## 자주 묻는 질문

### Q1. SSL 또는 인증 오류가 발생합니다.
- 사내 보안 환경에서 Selenium HTTP 요청이 차단될 수 있습니다. 네트워크 정책을 확인하거나 프록시/방화벽 예외를 설정하세요.

### Q2. `FinanceDataReader` 요청 제한이 걸립니다.
- 공개 API는 요청 제한이 있을 수 있습니다. 필요하면 `process_symbol` 내에 지연/재시도 로직을 추가하세요.

### Q3. 데이터베이스 연결 오류가 납니다.
- `config.ini`의 호스트/포트/계정 정보를 확인하고, 해당 DB와 테이블이 존재하는지 점검하세요.

## 라이선스

본 저장소에는 명시적 라이선스가 포함되어 있지 않습니다. 사용 전 원저작자의 허락을 받으세요.

## 모델 비교 스크립트 (KR)

`scripts/compare_models_kr.ps1`는 hidden_size/num_layers 조합을 자동으로 학습하고,
각 로그의 최소 `val_loss`를 비교해서 표로 출력합니다.

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/compare_models_kr.ps1
```

옵션 예시:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/compare_models_kr.ps1 -Epochs 20 -ModelOutDir d:/stock/shared_models -LogDir logs -PosWeight 8.5
```

---

## 변경 이력

### 2026-02-21

#### 1) 예측 cutoff 로직 변경
- 대상: `predict_kr.py`, `predict_jp.py`
- 기존: `data_cutoff = as_of - 1일` → 변경: `data_cutoff = as_of`
- 단, DB에 `max(date)`가 더 이르면 그 날짜로 낮춰 저장 (기존 로직 유지)
- 목적: as_of 날짜까지 데이터를 사용해 추론하고 `data_cutoff`도 같은 날짜로 저장

#### 2) 차트의 주말 공백 처리
- 대상: `webapp.py`
- Plotly x축에 `rangebreaks` 추가 → 주말(토~일)을 축에서 제거해 캔들 차트 빈 구간 숨김

#### 3) 데이터셋 구성 요약
- KRX: `STOCK_LIST_KR`, `STOCK_DATA_KR`, `STOCK_DATA_WEEK_KR`, `STOCK_PREDICT_KR`
- JPX: `STOCK_LIST_JP`, `STOCK_DATA_JP`, `STOCK_DATA_WEEK_JP`, `STOCK_PREDICT_JP`
- 일/주 단위 가격 데이터와 예측 결과 테이블을 분리해 운용
