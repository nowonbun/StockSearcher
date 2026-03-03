# StockSearcher Test 폴더 안내

이 폴더는 테스트/보조 도구를 위한 영역입니다. 현재 MariaDB 연결용 MCP 서버와 운영 사양 요약을 포함합니다.

## 1) MCP 서버 (MariaDB)

- 파일: `test/mariadb_mcp_server.py`
- 기능:
  - MariaDB 연결 후 테이블 목록/스키마 조회
  - SELECT/CTE 쿼리 실행
  - 비SELECT 쿼리 실행 (INSERT/UPDATE/DELETE 등)
- 설정:
  - 기본: 프로젝트 루트의 `config.ini`의 `[database]` 섹션 사용
  - 오버라이드 환경변수:
    - `MCP_DB_CONFIG` (config.ini 경로)
    - `MCP_DB_HOST`, `MCP_DB_PORT`, `MCP_DB_USER`, `MCP_DB_PASSWORD`
    - `MCP_DB_NAME` (없으면 `database_jp` → `database_kr` → `database`)
- 실행:
  - `python test/mariadb_mcp_server.py`
- 의존성:
  - `mysql-connector-python`
  - `mcp`

## 2) 운영 사양 요약

프로젝트 핵심 구성과 흐름을 간단히 정리합니다. 상세 내용은 루트의 `README.md`를 참고하세요.

### 주요 파이프라인

- JP 수집: `dataset_jp.py` (JPX + Selenium)
- KR 수집: `dataset_kr.py` (FinanceDataReader)
- 추론: `predict_jp.py`, `predict_kr.py`
- 엔트리포인트: `run.py` (`python run.py jp|kr`)

### 데이터베이스 테이블

- KR:
  - `STOCK_LIST_KR`, `STOCK_DATA_KR`, `STOCK_DATA_WEEK_KR`, `STOCK_PREDICT_KR`
- JP:
  - `STOCK_LIST_JP`, `STOCK_DATA_JP`, `STOCK_DATA_WEEK_JP`, `STOCK_PREDICT_JP`

### config.ini 요약

```
[database]
host = <DB_HOST>
port = 3306
user = <DB_USER>
password = <DB_PASS>
database_jp = stock
database_kr = stock

[default]
output_dir = D:\stock\StockSearcher
start_date = 2020-01-01
end_date = 2099-12-31
period = 5
```

- `output_dir`: 로그/CSV 출력 경로
- `start_date`, `end_date`: KR 수집 기간
- `period`: JP 수집 연도 범위

### Docker 실행 요약

- `docker-compose.yml` 기준 환경변수:
  - `CRON_SCHEDULE_JP`, `CRON_SCHEDULE_KR`
  - `JOB_CMD_JP`, `JOB_CMD_KR`
  - `CRON_LOG_PATH`
- 볼륨:
  - `./config.ini:/app/config.ini:ro`
  - `/root/stock/models:/models:ro`
  - `/root/stock/data:/data`

## 3) 변경 이력 (README2.md 요약)

- `predict_jp.py`, `predict_kr.py`:
  - `data_cutoff = as_of - 1` → `data_cutoff = as_of`
  - DB 최신 날짜가 `as_of`보다 크면 그 날짜를 사용
- `webapp.py`:
  - Plotly `rangebreaks` 추가로 주말 공백 제거

