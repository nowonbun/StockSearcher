# StockSearcher 변경 요약 (2026-02-21)

## 1) 예측 cutoff 로직 변경
- 대상: `predict_kr.py`, `predict_jp.py`
- 변경 내용:
  - 기존: `data_cutoff = as_of - 1일`
  - 변경: `data_cutoff = as_of`
  - 단, DB에 `max(date)`가 더 이르면 그 날짜로 낮춰 저장 (기존 로직 유지)
- 목적:
  - as_of 날짜까지 데이터를 사용해 추론하고, `data_cutoff`도 같은 날짜로 저장
  - 데이터가 as_of 당일까지 없으면 최신 데이터 날짜로 자동 보정

## 2) 차트의 주말 공백 처리
- 대상: `webapp.py`
- 변경 내용:
  - Plotly x축에 `rangebreaks` 추가
  - 주말(토~일)을 축에서 제거해 캔들 차트의 빈 구간을 숨김

## 3) 데이터셋 구성 요약
- 대상: `dataset_kr.py`, `dataset_jp.py`, `ddl.sql`
- 내용:
  - KRX: `STOCK_LIST_KR`, `STOCK_DATA_KR`, `STOCK_DATA_WEEK_KR`, `STOCK_PREDICT_KR`
  - JPX: `STOCK_LIST_JP`, `STOCK_DATA_JP`, `STOCK_DATA_WEEK_JP`, `STOCK_PREDICT_JP`
  - 일/주 단위 가격 데이터와 예측 결과 테이블을 분리해 운용

## 변경 파일 목록
- `predict_kr.py`
- `predict_jp.py`
- `webapp.py`
