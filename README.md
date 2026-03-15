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
├── model_jp.py          # 일본 모델 학습 스크립트
├── model_kr.py          # 한국 모델 학습 스크립트
├── predict_jp.py        # 일본 상위 확률 추론 스크립트
├── predict_kr.py        # 한국 상위 확률 추론 스크립트
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

## MCP ?? (?? ???? /mcp ??)

`webapp.py`? ? UI? MCP? ?? ???? ?????.

```bash
python webapp.py
```

- ? UI: `/`
- MCP Streamable HTTP: `/mcp`
- ?? WebSocket: `/ws/logs/{name}`

### MCP ?? ??

- `list_stocks(market="KR"|"JP")`
  - ?? ??? (`code`, `name`)
- `stock_data(market, code, limit=2000, start_date=None, end_date=None)`
  - ?? ??? ?? ?? (?? ??)
- `list_predict_dates(market="KR"|"JP", limit=120)`
  - ??? ???? `data_cutoff` ?? ??
- `predict_rows(market, as_of)`
  - ?? ??? ?? ?? (`data_cutoff`, `code`, `name`, `probability`, `open`, `close`, `low`, `high`, `volume`)

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

```yaml
services:
  stocksearcher:
    environment:
      CRON_SCHEDULE_JP: "0 2 * * *"
      CRON_SCHEDULE_KR: "0 4 * * *"
      JOB_CMD_JP: "python dataset_jp.py && python predict_jp.py --model /models/model_jp.pt --seq-len 60 --top-k 20 --save-db"
      JOB_CMD_KR: "python dataset_kr.py && python predict_kr.py --model /models/model_kr.pt --seq-len 60 --top-k 20 --save-db"
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
docker compose run --rm stocksearcher python predict_jp.py --model /models/model_jp.pt --seq-len 60 --save-db
docker compose exec stocksearcher python predict_jp.py --model /models/model_jp.pt --seq-len 60 --save-db
```

```bash
docker compose run --rm stocksearcher python predict_kr.py --model /models/model_kr.pt --seq-len 60 --save-db
docker compose exec stocksearcher python predict_kr.py --model /models/model_kr.pt --seq-len 60 --save-db
```

> 참고: `JOB_CMD_JP`/`JOB_CMD_KR`에 작은따옴표(')는 넣지 마세요. cron 파일 생성 시 충돌할 수 있습니다.

## 모델 학습 (JP)

JP 모델은 향후 N 거래일 내 지정한 상승률 이상을 달성할 확률을 예측합니다.
기본 타깃: "5일 내 +10% 이상 상승".

```bash
python model_jp.py --seq-len 60 --horizon-days 5 --rise-threshold 0.10 --epochs 30 --log-codes
```

모델 출력 파일: 현재 작업 폴더에 `model_jp.pt`로 저장됩니다.

유용한 옵션:

```bash
python model_jp.py --model-out d:\stock\StockSearcher\models\model_jp.pt
python model_jp.py --pos-weight 3.0
```

prec/rec 하락 시 pos-weight를 자동으로 조정하고 연속 하락이면 종료하려면:

```bash
python model_jp.py --adaptive-pos-weight --pos-weight-step 0.1 --drop-patience 3
```

기존 모델 이어서 학습하려면 `--resume`을 사용하세요.

```bash
python model_jp.py --resume d:\stock\shared_models\model_jp.pt --epochs 10 --model-out d:\stock\shared_models\model_jp_resume.pt
```

## 모델 학습 (KR)

KR 모델은 JP와 동일한 방식으로 학습합니다.

```bash
python model_kr.py --seq-len 60 --horizon-days 5 --rise-threshold 0.10 --epochs 30 --log-codes
```

모델 출력 파일: 현재 작업 폴더에 `model_kr.pt`로 저장됩니다.

prec/rec 하락 시 pos-weight를 자동으로 조정하고 연속 하락이면 종료하려면:

```bash
python model_kr.py --adaptive-pos-weight --pos-weight-step 0.1 --drop-patience 3
```

기존 모델 이어서 학습하려면 `--resume`을 사용하세요.

```bash
python model_kr.py --resume d:\stock\shared_models\model_kr.pt --epochs 10 --model-out d:\stock\shared_models\model_kr_resume.pt
```

## 추론 (JP)

특정 날짜 기준으로 상위 확률 종목을 출력합니다. `--as-of`가 2025-01-20이면 2025-01-19까지의 데이터로 추론합니다.

```bash
python predict_jp.py --model model_jp.pt --seq-len 60 --as-of 2025-01-20 --top-k 20
```

특정 종목만 확인하려면 `--code`를 사용하세요.

```bash
python predict_jp.py --model model_jp.pt --seq-len 60 --as-of 2025-01-20 --code 7203
```

DB에 저장하려면 `--save-db`를 추가합니다.

```bash
python predict_jp.py --model model_jp.pt --seq-len 60 --as-of 2025-01-20 --top-k 20 --save-db
```

## 추론 (KR)

```bash
python predict_kr.py --model model_kr.pt --seq-len 60 --as-of 2025-01-20 --top-k 20
```

## 간단 백테스트 (예측 → 5/10일 성과)

`backtest_simple.py`는 날짜별로 예측을 만든 뒤, 실제 5/10일 수익률과 승률을 간단히 확인합니다.

```bash
# JP 예시 (유동성 필터 포함)
python backtest_simple.py --market jp --start-date 2023-01-01 --end-date 2025-12-31 \
  --horizons 5,10 --date-step 5 --top-k 50 --min-trans-amnt-sum 1000000000 --liquidity-days 5

# KR 예시 (JP 기준의 10배)
python backtest_simple.py --market kr --start-date 2023-01-01 --end-date 2025-12-31 \
  --horizons 5,10 --date-step 5 --top-k 50 --min-trans-amnt-sum 10000000000 --liquidity-days 5
```

출력 포맷:

```
as_of,count,avg_ret_5d,hit_5d,avg_ret_10d,hit_10d
```

특정 종목만 확인하려면 `--code`를 사용하세요.

```bash
python predict_kr.py --model model_kr.pt --seq-len 60 --as-of 2025-01-20 --code 005930
```

DB에 저장하려면 `--save-db`를 추가합니다.

```bash
python predict_kr.py --model model_kr.pt --seq-len 60 --as-of 2025-01-20 --top-k 20 --save-db
```

## 출력 및 로그

- `output_dir` 하위에 `log/logfile_*_YYYY-MM-DD.log` 형태로 로그가 생성됩니다.
- 데이터베이스 적재 결과와 에러 메시지가 로그에 기록됩니다.

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
