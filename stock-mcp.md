StockSearcher MCP 사용 방법

결론
StockSearcher의 MCP는 `webapp.py`에서 `FastMCP`로 정의되며, HTTP 경로 `/mcp`에 마운트된다. 클라이언트는 MCP 툴 호출로 아래 4개 도구를 사용한다.

기본 정보
- MCP 서버 경로: `/mcp`
- 앱 구성: `FastMCP("stocksearcher-mcp", streamable_http_path="/")` → `mcp.streamable_http_app()`을 `/mcp`에 마운트
- 시장 구분: `KR`, `JP`

제공 MCP 툴
1. `list_stocks`
- 설명: 시장별 종목 리스트 조회
- 파라미터
  - `market` (string, optional, default `KR`): `KR` 또는 `JP`
- 반환: `{code, name}` 객체 배열

2. `stock_data`
- 설명: 특정 종목의 시세/지표 시계열 조회 (날짜 내림차순)
- 파라미터
  - `market` (string, required): `KR` 또는 `JP`
  - `code` (string, required): 종목 코드
  - `limit` (int, optional, default 2000): 최대 행 수
  - `start_date` (string, optional): 시작일 (`YYYY-MM-DD`)
  - `end_date` (string, optional): 종료일 (`YYYY-MM-DD`)
- 반환: `STOCK_DATA_*` 테이블 전체 컬럼을 포함한 행 배열

3. `list_predict_dates`
- 설명: 예측 데이터 기준일(`data_cutoff`) 목록 조회
- 파라미터
  - `market` (string, optional, default `KR`): `KR` 또는 `JP`
  - `limit` (int, optional, default 120): 최대 날짜 개수
- 반환: 날짜 문자열 배열 (`YYYY-MM-DD`)

4. `predict_rows`
- 설명: 특정 기준일의 예측 결과 조회
- 파라미터
  - `market` (string, required): `KR` 또는 `JP`
  - `as_of` (string, required): 기준일 (`YYYY-MM-DD`)
- 반환: `{data_cutoff, code, name, probability, open, close, low, high, volume}` 배열

오류/검증
- `market`가 `KR/JP`가 아니면 오류 발생
- `stock_data`는 `code` 누락 시 오류 발생
- `predict_rows`는 `as_of` 누락 시 오류 발생

참고
- MCP는 `webapp.py`의 `create_asgi_app()`에서 `/mcp`에 마운트된다.
- 실제 통신 포맷은 사용하는 MCP 클라이언트(예: 내부 MCP 클라이언트, 도구 호출 인터페이스)에 따라 다르며, 위 툴 스펙에 맞춰 호출하면 된다.
