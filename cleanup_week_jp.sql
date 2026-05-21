-- ================================================================
-- STOCK_DATA_WEEK_JP 더티 데이터 정리
--
-- 버그 원인:
--   1) Yahoo Finance JP 주봉 타임스탬프 = '월요일 00:00 JST'
--      = '일요일 15:00 UTC'. Docker(UTC) 환경에서 fromtimestamp()
--      를 쓰면 일요일로 저장 → 같은 주 데이터가 일/월 두 row로 생성
--   2) 진행 중인 주봉의 타임스탬프를 Yahoo Finance가 실행 당일 날짜로
--      반환 → 매일 새 row 생성 (화, 수, 목, 금 row 누적)
--
-- 정리 기준: 주봉의 기준일 = 해당 주의 월요일
--
-- 권장 실행 순서:
--   1. dataset_jp.py 코드 수정 (normalize_to_monday) 배포
--   2. python run.py jp  ← 월요일 기준 최신 데이터로 갱신
--   3. 이 SQL 실행
-- ================================================================

-- ---------------------------------------------------------------
-- [0] 정리 전 현황 확인
-- ---------------------------------------------------------------
SELECT
    WEEKDAY(date)  AS weekday_num,   -- 0=Mon, 1=Tue, ..., 6=Sun
    DAYNAME(date)  AS day_name,
    COUNT(*)       AS row_count
FROM STOCK_DATA_WEEK_JP
GROUP BY WEEKDAY(date), DAYNAME(date)
ORDER BY weekday_num;

-- ---------------------------------------------------------------
-- [1] 월요일 row가 이미 있는 주의 비-월요일 row 삭제
--     (일요일 timezone 중복 + 화~금 진행 중 누적 row 제거)
-- ---------------------------------------------------------------
DELETE w1
FROM STOCK_DATA_WEEK_JP w1
WHERE WEEKDAY(w1.date) != 0   -- 비-월요일
  AND EXISTS (
      SELECT 1
      FROM (SELECT code, date FROM STOCK_DATA_WEEK_JP) chk
      WHERE chk.code = w1.code
        AND chk.date = DATE_SUB(w1.date, INTERVAL WEEKDAY(w1.date) DAY)
  );

-- ---------------------------------------------------------------
-- [2] 월요일 row가 없는 주의 비-월요일 row → 월요일로 날짜 변환
--     같은 (code, 주)에 여러 비-월요일 row가 있으면
--     update_date 최신 것(동점이면 가장 늦은 date) 1개만 선택
-- ---------------------------------------------------------------
UPDATE STOCK_DATA_WEEK_JP t1
  JOIN (
      SELECT
          code,
          DATE_SUB(date, INTERVAL WEEKDAY(date) DAY) AS week_mon,
          MAX(update_date)                            AS latest_upd,
          MAX(date)                                   AS latest_date
      FROM STOCK_DATA_WEEK_JP
      WHERE WEEKDAY(date) != 0
      GROUP BY code, week_mon
  ) grp
      ON  grp.code        = t1.code
      AND grp.week_mon    = DATE_SUB(t1.date, INTERVAL WEEKDAY(t1.date) DAY)
      AND grp.latest_upd  = t1.update_date
      AND grp.latest_date = t1.date
SET t1.date = DATE_SUB(t1.date, INTERVAL WEEKDAY(t1.date) DAY)
WHERE WEEKDAY(t1.date) != 0;

-- ---------------------------------------------------------------
-- [3] 남은 비-월요일 row 삭제
--     (step 2에서 같은 주에 여러 row 중 1개만 선택됐으므로
--      선택되지 않은 나머지 정리)
-- ---------------------------------------------------------------
DELETE FROM STOCK_DATA_WEEK_JP WHERE WEEKDAY(date) != 0;

-- ---------------------------------------------------------------
-- [4] 정리 후 확인 (Monday만 남아야 함)
-- ---------------------------------------------------------------
SELECT
    WEEKDAY(date)  AS weekday_num,
    DAYNAME(date)  AS day_name,
    COUNT(*)       AS row_count
FROM STOCK_DATA_WEEK_JP
GROUP BY WEEKDAY(date), DAYNAME(date)
ORDER BY weekday_num;
