# StockSearcher

주식 데이터 수집 자동화를 위한 파이썬 스크립트 모음입니다. 일본과 한국 시장의 일/주봉 데이터를 수집하고, 이동평균 및 볼린저 밴드와 같은 지표를 계산한 뒤 MySQL 데이터베이스에 적재합니다.

## 주요 기능

- **일본 시장 수집 (`dataset_jp.py`)**: Selenium 기반으로 JPX에서 제공하는 종목 목록과 개별 시세 데이터를 다운로드합니다.
- **한국 시장 수집 (`dataset_kr.py`)**: FinanceDataReader를 사용해 KRX 상장 종목의 일/주봉 데이터를 가져옵니다.
- **공통 실행 스크립트 (`run.py`)**: `python run.py [jp|kr]` 명령으로 두 파이프라인을 선택적으로 실행할 수 있습니다.
- **로그/출력 관리**: `config.ini`에 정의된 `output_dir` 하위에 로그 파일과 산출물이 저장됩니다.

## 디렉터리 구조

```
StockSearcher/
├── config.ini           # DB 및 출력 경로 설정
├── run.py               # 엔트리포인트 스크립트
├── dataset_jp.py        # 일본 주식 데이터 수집 파이프라인
├── dataset_kr.py        # 한국 주식 데이터 수집 파이프라인
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
source .venv/bin/activate  # Windows는 .venv\Scripts\activate
pip install --upgrade pip
pip install mysql-connector-python pandas requests selenium webdriver-manager FinanceDataReader
```

### 2. MySQL 데이터베이스

- MySQL 서버가 준비되어 있어야 합니다.
- 다음 테이블을 사용합니다(`dataset_jp.py`/`dataset_kr.py` 참고).
  - `STOCK_LIST`
  - `STOCK_DATA`
  - `STOCK_DATA_WEEK`
- 샘플 DDL은 직접 작성하거나 `entity` 모듈의 SQL 생성 코드를 참고하세요.

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
output_dir = D:\\stock\\stock_searcher
start_date = 2020-01-01
end_date = 2099-12-31
period = 5
```

- `output_dir`: 로그와 CSV 등 출력이 저장될 루트 경로입니다.
- `start_date`, `end_date`: 한국 데이터 수집 시 조회 기간.
- `period`: 일본 데이터 수집 시 조회 연도 단위(예: `5` → 최근 5년).

## 실행 방법

```bash
# 일본 주식 데이터 수집 및 저장
python run.py jp

# 한국 주식 데이터 수집 및 저장
python run.py kr
```

- 인자를 생략하면 기본값(`jp`)이 실행됩니다.
- 한국 수집 파이프라인은 내부적으로 쓰레드 풀(기본 5개)을 사용하여 종목을 병렬 처리합니다.

## 출력 및 로그

- `output_dir` 하위에 `log/logfile_*.log` 형태의 로그가 생성됩니다.
- 데이터베이스 적재 결과는 표준 출력과 로그 파일 양쪽에 기록됩니다.
- 오류 발생 시 로그를 확인하고, 실패한 종목만 재실행하면 됩니다.

## 자주 묻는 질문

### Q1. SSL 또는 인증 오류가 발생합니다.
- 회사 프록시/방화벽 환경에서는 Selenium 혹은 HTTP 요청이 차단될 수 있습니다. 네트워크 정책을 확인하거나 오프라인 데이터 파일을 제공하세요.

### Q2. `FinanceDataReader` 요청 제한이 걸립니다.
- 기본적으로 공개 API를 사용하므로 대량 호출 시 잠시 대기 후 재시도하십시오. 필요하면 `process_symbol` 내에 슬립이나 재시도 로직을 추가할 수 있습니다.

### Q3. 데이터베이스 연결 오류가 납니다.
- `config.ini`에서 호스트/포트/사용자 정보를 다시 확인하고, MySQL에 해당 데이터베이스와 테이블이 존재하는지 확인하세요.

## 라이선스

본 저장소에는 명시적 라이선스가 포함되어 있지 않습니다. 사용 전 원저작자의 허락을 받으세요.
