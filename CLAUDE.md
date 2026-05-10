# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 작업 원칙 (AGENTS.md 준수)

- 답변과 작업 보고는 **한국어**로 한다.
- 결론 먼저, 근거는 뒤에.
- 변경은 필요한 범위로 최소화. 큰 리팩터링보다 국소 수정 우선.
- KR/JP 로직은 시장별 차이를 유지하고, 공통화는 명확한 이점이 있을 때만 한다.
- 코드 수정 후 최소 검증 순서: 문법 오류 → import/runtime 진입 → 영향 받은 기능 국소 실행.

## 실행 명령

모든 스크립트는 **프로젝트 루트**에서 실행해야 한다(`function/static.py`가 `config.ini`를 CWD 기준으로 읽음).

```bash
# 데이터 수집
python run.py jp              # 일본 (기본값)
python run.py kr              # 한국

# 모델 학습
python model_jp.py            # JP: seq=120, horizon=20일, rise=8%, drawdown=10%
python model_kr.py --seq-len 120 --horizon-days 20 --rise-threshold 0.12 --max-drawdown 0.10 --epochs 30 --log-codes

# 추론 (상위 종목 선출)
python predict_jp.py --model model_jp.pt --seq-len 120 --top-k 20 --save-db
python predict_kr.py --model model_kr.pt --seq-len 120 --top-k 20 --save-db

# 특정 날짜 기준 추론
python predict_jp.py --model model_jp.pt --seq-len 120 --as-of 2025-01-20 --top-k 20
# 특정 종목 단건 확인
python predict_jp.py --model model_jp.pt --seq-len 120 --as-of 2025-01-20 --code 7203

# 백테스트
python backtest_simple.py --market jp --start-date 2023-01-01 --end-date 2025-12-31 \
  --horizons 20,40 --date-step 5 --top-k 50 --min-trans-amnt-sum 1000000000 --liquidity-days 5

# 웹 서버 (Flask + MCP, 포트 9999)
python webapp.py

# Docker
docker compose up -d --build
docker compose logs -f
docker compose run --rm stocksearcher python dataset_jp.py   # 수동 1회 실행
```

## 아키텍처

### 전체 흐름

```
dataset_{jp,kr}.py  →  DB (STOCK_LIST/DATA)
                         ↓
model_{jp,kr}.py    →  model_{jp,kr}.pt (학습)
                         ↓
predict_{jp,kr}.py  →  DB (STOCK_PREDICT_{JP,KR})
                         ↓
webapp.py           →  웹 UI (/) + MCP (/mcp) + WebSocket (/ws/logs/{name})
webapp/             →  PHP+Smarty 웹앱 (포트 9998, stocksearcher-php 컨테이너)
```

### 핵심 모듈

| 파일 | 역할 |
|------|------|
| `function/static.py` | config.ini 파싱 + `db_config_jp`, `db_config_kr`, `dir`, `start_date`, `end_date`, `period` 전역 제공 |
| `function/common.py` | 로거 초기화, DB 쿼리 실행, CSV 저장, 시퀀스 생성 등 공통 유틸 |
| `entity/stock_models.py` | `StockCandle`, `StockSeries` 데이터 컨테이너 |
| `model_jp.py` | `StockTransformer` 모델 정의 + 학습 루프. `predict_jp.py`가 이 파일에서 직접 import |
| `model_kr.py` | KR용 동일 구조 |
| `predict_jp.py` | `model_jp.py`의 `StockTransformer`, feature cols, compute 함수를 import해 추론 |
| `webapp.py` | Flask(WSGI) + FastMCP를 Starlette로 마운트. 태스크 상태를 `TASKS` dict로 관리 |

### DB 스키마 요약

- **KR**: `STOCK_LIST_KR` → `STOCK_DATA_KR` / `STOCK_DATA_WEEK_KR` → `STOCK_PREDICT_KR` / `STOCK_PREDICT_WEEK_KR`
- **JP**: `STOCK_LIST_JP` → `STOCK_DATA_JP` / `STOCK_DATA_WEEK_JP` → `STOCK_PREDICT_JP` / `STOCK_PREDICT_WEEK_JP`
- `STOCK_DATA_*` PK: `(code, date)`. 이동평균(5/20/50/60/120/240MvAvg), 볼린저밴드(UpperBand60_1 등), DMI(DI_plus, DI_minus, ADX) 포함.
- `STOCK_PREDICT_*` PK: `(data_cutoff, code)`. `data_cutoff`는 추론 기준일.
- 스키마 변경 시 `ddl.sql` 먼저 확인. KR과 JP의 컬럼 수가 다름(JP에 240MvAvg 추가).

### 설정

`config.ini`는 프로젝트 루트에 위치. Docker에서는 환경변수 `OUTPUT_DIR`로 `output_dir`을 오버라이드.

```ini
[database]
host / port / user / password / database_jp / database_kr

[default]
output_dir   # 로그/CSV 저장 루트. Docker에서는 /data
start_date / end_date  # KR 수집 기간
period       # JP 수집 연도 단위
```

### Docker 구성

- `stocksearcher`: Python 서비스 (포트 9999). cron으로 JP/KR 파이프라인 자동 실행.
- `stocksearcher-php`: PHP+Smarty 웹앱 (포트 9998). Python 서비스를 `PYTHON_API_URL`로 참조.
- 모델 파일(`model_jp.pt`, `model_kr.pt`)은 볼륨 마운트(`/models`)로 주입. 저장소에 커밋하지 않음.
- cron 로그: `{CRON_LOG_PATH}` 기준 날짜별 파일.

### MCP 도구 (webapp.py `/mcp`)

| 도구 | 파라미터 |
|------|---------|
| `list_stocks` | `market="KR"\|"JP"` |
| `stock_data` | `market, code, limit=2000, start_date, end_date` |
| `list_predict_dates` | `market="KR"\|"JP", limit=120` |
| `predict_rows` | `market, as_of` |
| `stock_data_week` | `market, code, limit=500, start_date, end_date` |

MCP 파라미터나 반환 형식 변경 시 `README.md`와 `stock-mcp.md`를 함께 갱신한다.

## 주의 사항

- `predict_jp.py`는 `model_jp.py`에서 `StockTransformer`, `_RAW_COLS`, `RELATIVE_FEATURE_COLS`, `compute_relative_features`, `extract_trend_filter_metrics`, `load_codes`를 직접 import한다. 모델 클래스나 feature 컬럼 변경 시 predict 스크립트 호환성을 반드시 확인한다.
- `function/static.py`는 import 시점에 `config.ini`를 파싱한다. 스크립트를 프로젝트 루트가 아닌 위치에서 실행하면 설정을 찾지 못한다.
- `JOB_CMD_JP`/`JOB_CMD_KR` 환경변수에 작은따옴표(')를 넣으면 cron 파일 생성이 실패한다.
