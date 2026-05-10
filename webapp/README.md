# StockSearcher PHP WebApp

## 개요
이 디렉터리는 기존 `webapp.py`를 유지한 상태에서, PHP + Smarty 기반 웹앱을 병행 운영하기 위한 구성입니다.

- 템플릿 엔진: Smarty
- 런타임: PHP 8.3 + Apache (Docker)
- 기본 페이지: `public/index.php`
- 현재 구현 범위:
  - AI 추론 조회 페이지
  - 볼린저 상단(UpperBand) 스캐너 페이지
- 미구현/제외:
  - 배치 실행 UI/로그 스트리밍
  - MCP 엔드포인트

## 폴더 구조
- `public/`: 웹 루트 (엔드포인트)
- `src/`: 부트스트랩/공통 로직
- `templates/`: Smarty 템플릿
- `templates_c/`: Smarty 컴파일 출력
- `cache/`: Smarty 캐시
- `config/`: Smarty 설정
- `Dockerfile`: PHP 웹앱 컨테이너 빌드 정의

## 실행 방법
아래 명령은 `D:\work\StockSearcher` (프로젝트 루트) 기준입니다.

### 1) PHP 웹앱만 실행
```bash
docker compose up -d stocksearcher-php
```

### 2) 로그 확인
```bash
docker compose logs -f stocksearcher-php
```

### 3) 접속
- URL: `http://localhost:9998`

### 4) 중지
```bash
docker compose stop stocksearcher-php
```

### 5) 삭제(컨테이너/네트워크)
```bash
docker compose down
```

## 참고
- 포트 매핑은 루트의 `docker-compose.yml`에서 `9998:80`으로 설정되어 있습니다.
- 기존 Python 서비스(`stocksearcher`)와 병행 실행할 수 있습니다.
