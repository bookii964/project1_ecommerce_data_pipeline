-- =============================================================================
-- 파일명 : 06_analysis.sql
-- 단계   : 7단계 - SQL 비즈니스 분석
--
-- [목적]
--   정제·적재된 6개 테이블로 비즈니스 질문에 답한다.
--
-- [분석 전에 반드시 확인할 것 — 아래 A절을 먼저 실행하라]
--   테이블마다 데이터 수집 기간이 다르고, 컬럼마다 사용 가능한 모수가 다르다.
--   이것을 확인하지 않고 집계하면 숫자가 나오지만 그 숫자가 틀린다.
--   실제로 이 파일의 A-2 쿼리에서 전환율 100%라는 불가능한 결과를 얻었고,
--   원인이 기간 불일치였다. (자세한 내용은 04_reports/분석리포트.md)
--
-- [실행 방법]
--   DBeaver SQL 편집기에서 쿼리를 하나씩 실행한다 (Ctrl + Enter).
--   결과를 CSV로 내보내려면 결과 그리드 우클릭 → Export resultset.
-- =============================================================================

SET search_path TO portfolio, public;


-- #############################################################################
-- A. 분석 전제 확인
-- #############################################################################

-- -----------------------------------------------------------------------------
-- [A-1] 테이블별 데이터 수집 기간
--
--   가장 먼저 확인해야 하는 쿼리다.
--   여러 테이블을 조인해 기간별로 비교하려면 기간이 겹쳐야 한다.
-- -----------------------------------------------------------------------------
SELECT 'orders'      AS 테이블, MIN(order_date)::text AS 시작, MAX(order_date)::text AS 종료,
       COUNT(*) AS 사용가능건수
  FROM orders WHERE order_date IS NOT NULL
UNION ALL
SELECT 'support_tickets', MIN(ticket_created)::text, MAX(ticket_created)::text, COUNT(*)
  FROM support_tickets WHERE ticket_created IS NOT NULL
UNION ALL
SELECT 'clickstream', MIN(event_time)::text, MAX(event_time)::text, COUNT(*)
  FROM clickstream WHERE event_time IS NOT NULL;


-- -----------------------------------------------------------------------------
-- [A-2] 컬럼별 분석 가능 모수
--
--   정제 과정에서 신뢰할 수 없는 값을 NULL 처리했으므로,
--   컬럼마다 쓸 수 있는 행 수가 다르다.
--   "월별 매출 합계"와 "카테고리별 매출 합계"의 총액이 다른 이유가 여기 있다.
--   → 결과를 제시할 때 반드시 모수를 함께 밝혀야 한다.
-- -----------------------------------------------------------------------------
SELECT 'orders.order_date'   AS 컬럼, COUNT(order_date)   AS 사용가능,
       COUNT(*) - COUNT(order_date)   AS null건수,
       ROUND(100.0 * COUNT(order_date) / COUNT(*), 1) AS 사용가능률
  FROM orders
UNION ALL
SELECT 'orders.order_amount', COUNT(order_amount), COUNT(*) - COUNT(order_amount),
       ROUND(100.0 * COUNT(order_amount) / COUNT(*), 1) FROM orders
UNION ALL
SELECT 'clickstream.event_time', COUNT(event_time), COUNT(*) - COUNT(event_time),
       ROUND(100.0 * COUNT(event_time) / COUNT(*), 1) FROM clickstream
UNION ALL
SELECT 'tickets.ticket_created', COUNT(ticket_created), COUNT(*) - COUNT(ticket_created),
       ROUND(100.0 * COUNT(ticket_created) / COUNT(*), 1) FROM support_tickets
ORDER BY 1;


-- #############################################################################
-- B. 매출 분석
-- #############################################################################

-- -----------------------------------------------------------------------------
-- [B-1] 월별 매출 추이
--
--   성공한 주문만 집계한다. 실패·환불 주문을 포함하면 매출이 과대 계상된다.
--   to_char(날짜, 'YYYY-MM') : 날짜를 '2025-07' 형태 문자열로 바꾼다.
--
--   ※ 모수 : order_date 가 있는 210,000건 (전체의 70.0%)
-- -----------------------------------------------------------------------------
SELECT to_char(order_date, 'YYYY-MM')            AS 월,
       COUNT(*)                                  AS 주문수,
       ROUND(SUM(order_amount) / 1000000, 1)     AS 매출_백만,
       ROUND(AVG(order_amount))                  AS 평균주문액
  FROM orders
 WHERE order_date IS NOT NULL
   AND status = 'success'
   AND order_amount IS NOT NULL
 GROUP BY 1
 ORDER BY 1;


-- -----------------------------------------------------------------------------
-- [B-2] 카테고리별 매출 기여도
--
--   합계만 보면 "상품이 많은 카테고리가 매출도 많다"는 당연한 결과가 나온다.
--   상품 1개당 주문 수를 함께 봐야 카테고리 자체의 성과를 비교할 수 있다.
-- -----------------------------------------------------------------------------
SELECT p.category                                      AS 카테고리,
       COUNT(DISTINCT p.product_id)                    AS 상품수,
       COUNT(o.order_id)                               AS 주문수,
       ROUND(SUM(o.order_amount) / 1000000, 1)         AS 매출_백만,
       ROUND(COUNT(o.order_id)::numeric
             / COUNT(DISTINCT p.product_id), 1)        AS 상품당주문수,
       ROUND(AVG(o.order_amount))                      AS 평균주문액
  FROM product_catalog p
  LEFT JOIN orders o
         ON p.product_id = o.product_id
        AND o.status = 'success'
        AND o.order_amount IS NOT NULL
 GROUP BY p.category
 ORDER BY 매출_백만 DESC;


-- -----------------------------------------------------------------------------
-- [B-3] 결제수단별 주문 상태
--
--   특정 결제수단의 실패율이 높다면 결제 시스템 점검이 필요하다는 신호다.
--
--   COUNT(*) FILTER (WHERE 조건) : 조건에 맞는 행만 센다.
--     CASE WHEN 조건 THEN 1 END 를 세는 것과 같지만 훨씬 읽기 쉽다.
-- -----------------------------------------------------------------------------
SELECT payment_method                                                      AS 결제수단,
       COUNT(*)                                                            AS 전체주문,
       ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'success')  / COUNT(*), 1) AS 성공률,
       ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'failed')   / COUNT(*), 1) AS 실패율,
       ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'refunded') / COUNT(*), 1) AS 환불율
  FROM orders
 GROUP BY payment_method
 ORDER BY 전체주문 DESC;


-- #############################################################################
-- C. 고객 분석
-- #############################################################################

-- -----------------------------------------------------------------------------
-- [C-1] 유입경로별 고객 성과
--
--   referral / web / app 중 어느 경로가 더 가치 있는 고객을 데려오는가.
--
--   ※ 주문이 없는 고객도 분모에 포함해야 정확하다.
--     LEFT JOIN 을 쓰고 COALESCE 로 0 처리한다.
-- -----------------------------------------------------------------------------
SELECT c.source                                                AS 유입경로,
       COUNT(DISTINCT c.customer_id)                           AS 고객수,
       ROUND(COUNT(o.order_id)::numeric
             / COUNT(DISTINCT c.customer_id), 2)               AS 인당주문수,
       ROUND(SUM(o.order_amount) / COUNT(DISTINCT c.customer_id)) AS 인당구매액
  FROM crm_customers c
  LEFT JOIN orders o
         ON c.customer_id = o.customer_id
        AND o.status = 'success'
 GROUP BY c.source
 ORDER BY 인당구매액 DESC;


-- -----------------------------------------------------------------------------
-- [C-2] 구매액 상위 고객
--
--   여러 테이블을 한 번에 LEFT JOIN 하면 행이 곱해진다.
--   고객 1명이 주문 10건, 문의 3건이면 조인 결과가 30행이 되어 집계가 틀린다.
--   → 각 테이블을 먼저 집계한 뒤 붙인다 (서브쿼리 조인).
-- -----------------------------------------------------------------------------
SELECT c.first_name || ' ' || c.last_name AS 고객명,
       c.source                           AS 유입경로,
       c.age_at_signup                    AS 가입시나이,
       COALESCE(o.주문수, 0)              AS 주문수,
       COALESCE(o.구매액, 0)              AS 구매액,
       COALESCE(t.문의수, 0)              AS 문의수,
       COALESCE(v.조회수, 0)              AS 상품조회
  FROM crm_customers c
  LEFT JOIN (SELECT customer_id, COUNT(*) AS 주문수, SUM(order_amount) AS 구매액
               FROM orders WHERE status = 'success' GROUP BY customer_id) o
         ON c.customer_id = o.customer_id
  LEFT JOIN (SELECT customer_id, COUNT(*) AS 문의수
               FROM support_tickets GROUP BY customer_id) t
         ON c.customer_id = t.customer_id
  LEFT JOIN (SELECT customer_id, COUNT(*) AS 조회수
               FROM clickstream
              WHERE event_type = 'page_view' AND customer_id IS NOT NULL
              GROUP BY customer_id) v
         ON c.customer_id = v.customer_id
 ORDER BY 구매액 DESC NULLS LAST
 LIMIT 20;


-- -----------------------------------------------------------------------------
-- [C-3] 문의 건수와 구매 행태의 관계
--
--   "문의가 많은 고객은 이탈 위험이 큰가, 아니면 관여도가 높은 우량 고객인가"
--
--   [해석 주의] 평균 구매액만 비교하면 오해할 수 있다.
--     구매액 = 주문수 × 건당단가 이므로,
--     구매액이 높은 이유가 '많이 사서'인지 '비싸게 사서'인지 구분해야 한다.
--     그래서 세 지표를 함께 본다.
-- -----------------------------------------------------------------------------
SELECT CASE WHEN t.문의수 IS NULL THEN '문의 없음'
            WHEN t.문의수 = 1     THEN '문의 1건'
            ELSE                       '문의 2건 이상' END      AS 구분,
       COUNT(*)                                                 AS 고객수,
       ROUND(AVG(COALESCE(o.주문수, 0)), 2)                     AS 평균주문수,
       ROUND(AVG(COALESCE(o.구매액, 0)))                        AS 평균구매액,
       ROUND(AVG(o.구매액 / NULLIF(o.주문수, 0)))               AS 건당단가
  FROM crm_customers c
  LEFT JOIN (SELECT customer_id, COUNT(*) AS 주문수, SUM(order_amount) AS 구매액
               FROM orders WHERE status = 'success' GROUP BY customer_id) o
         ON c.customer_id = o.customer_id
  LEFT JOIN (SELECT customer_id, COUNT(*) AS 문의수
               FROM support_tickets GROUP BY customer_id) t
         ON c.customer_id = t.customer_id
 GROUP BY 1
 ORDER BY 1;


-- -----------------------------------------------------------------------------
-- [C-4] 문의 수와 주문 수의 상관계수
--
--   C-3 에서 그룹별 차이가 보이더라도, 그것이 실제 관계인지 확인해야 한다.
--   corr(a, b) : 두 값의 상관계수를 구한다. -1 ~ 1 사이 값이며
--                0에 가까우면 관계가 없다는 뜻이다.
-- -----------------------------------------------------------------------------
SELECT ROUND(corr(주문수, 문의수)::numeric, 4) AS 주문수_문의수_상관계수
  FROM (
        SELECT c.customer_id,
               COALESCE(o.n, 0) AS 주문수,
               COALESCE(t.n, 0) AS 문의수
          FROM crm_customers c
          LEFT JOIN (SELECT customer_id, COUNT(*) n FROM orders GROUP BY 1) o
                 ON c.customer_id = o.customer_id
          LEFT JOIN (SELECT customer_id, COUNT(*) n FROM support_tickets GROUP BY 1) t
                 ON c.customer_id = t.customer_id
       ) x;


-- #############################################################################
-- D. 고객 지원(CS) 분석
-- #############################################################################

-- -----------------------------------------------------------------------------
-- [D-1] 문의 유형별 처리 시간과 감정
--
--   처리 시간이 긴 유형은 인력 배치나 프로세스 개선 대상이다.
--   부정 감정 비율이 높은 유형은 고객 경험 개선 대상이다.
-- -----------------------------------------------------------------------------
SELECT issue_type                                                        AS 문의유형,
       COUNT(*)                                                          AS 건수,
       ROUND(AVG(resolution_time_hours), 1)                              AS 평균처리시간,
       ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY resolution_time_hours)::numeric, 1) AS 중앙처리시간,
       ROUND(100.0 * COUNT(*) FILTER (WHERE sentiment = 'negative') / COUNT(*), 1) AS 부정비율,
       ROUND(100.0 * COUNT(*) FILTER (WHERE sentiment = 'positive') / COUNT(*), 1) AS 긍정비율
  FROM support_tickets
 GROUP BY issue_type
 ORDER BY 평균처리시간 DESC;


-- -----------------------------------------------------------------------------
-- [D-2] 처리 시간과 감정의 관계
--
--   "오래 기다린 고객은 더 부정적인가"
--   처리 시간을 구간으로 나눠 감정 분포를 비교한다.
--
--   width_bucket(값, 최소, 최대, 구간수) : 값을 균등 구간으로 나눠 번호를 준다.
-- -----------------------------------------------------------------------------
SELECT CASE width_bucket(resolution_time_hours, 0, 240, 4)
            WHEN 1 THEN '1) 0~60시간'
            WHEN 2 THEN '2) 60~120시간'
            WHEN 3 THEN '3) 120~180시간'
            ELSE        '4) 180시간 이상' END                            AS 처리시간구간,
       COUNT(*)                                                          AS 건수,
       ROUND(100.0 * COUNT(*) FILTER (WHERE sentiment = 'negative') / COUNT(*), 1) AS 부정비율,
       ROUND(100.0 * COUNT(*) FILTER (WHERE sentiment = 'neutral')  / COUNT(*), 1) AS 중립비율,
       ROUND(100.0 * COUNT(*) FILTER (WHERE sentiment = 'positive') / COUNT(*), 1) AS 긍정비율
  FROM support_tickets
 GROUP BY 1
 ORDER BY 1;


-- -----------------------------------------------------------------------------
-- [D-3] 상담원별 처리 실적
--
--   담당자 1,556종 표기를 200명으로 정제한 결과를 활용한다.
--   정제하지 않았다면 같은 사람이 여러 명으로 쪼개져 실적이 나뉘었을 것이다.
-- -----------------------------------------------------------------------------
SELECT support_agent                                                      AS 상담원,
       COUNT(*)                                                           AS 처리건수,
       ROUND(AVG(resolution_time_hours), 1)                               AS 평균처리시간,
       ROUND(100.0 * COUNT(*) FILTER (WHERE sentiment = 'negative') / COUNT(*), 1) AS 부정비율
  FROM support_tickets
 GROUP BY support_agent
HAVING COUNT(*) >= 100          -- 표본이 적은 상담원은 제외 (평균이 불안정)
 ORDER BY 평균처리시간 ASC
 LIMIT 15;


-- #############################################################################
-- E. 퍼널 분석 — 조회 → 장바구니 → 구매
-- #############################################################################

-- -----------------------------------------------------------------------------
-- [E-1] 잘못된 퍼널 계산 — 왜 틀렸는지 확인용
--
--   [주의] 이 쿼리는 틀린 결과를 낸다. 비교를 위해 남겨둔다.
--
--   clickstream 전체 기간의 조회 고객과 orders 전체 기간의 구매 고객을 비교한다.
--   두 테이블의 수집 기간이 다르다는 것을 고려하지 않았다.
--     clickstream : 2025-09-02 ~ 2025-12-02 (3개월)
--     orders      : 2023-12-03 ~ 2025-12-01 (2년)
--   → 구매 고객이 2년치라서 전환율이 100%를 넘는 불가능한 결과가 나온다.
-- -----------------------------------------------------------------------------
SELECT (SELECT COUNT(DISTINCT customer_id) FROM clickstream
         WHERE is_logged_in AND event_type = 'page_view')            AS 조회고객,
       (SELECT COUNT(DISTINCT customer_id) FROM orders
         WHERE status = 'success')                                   AS 구매고객_전기간;


-- -----------------------------------------------------------------------------
-- [E-2] 올바른 퍼널 계산 — 기간을 맞춘다
--
--   clickstream 의 수집 기간(2025-09-02 ~ 2025-12-02)으로 주문도 잘라낸다.
--   또한 단계별로 '앞 단계를 거친 고객'만 세야 퍼널이 성립한다.
--     조회한 고객 중 장바구니에 담은 사람
--     장바구니에 담은 고객 중 구매한 사람
-- -----------------------------------------------------------------------------
WITH 조회 AS (
    SELECT DISTINCT customer_id FROM clickstream
     WHERE is_logged_in AND event_type = 'page_view' AND event_time IS NOT NULL
),
장바구니 AS (
    SELECT DISTINCT customer_id FROM clickstream
     WHERE is_logged_in AND event_type = 'add_to_cart' AND event_time IS NOT NULL
),
구매 AS (
    SELECT DISTINCT customer_id FROM orders
     WHERE status = 'success'
       AND order_date BETWEEN '2025-09-02' AND '2025-12-02'
)
SELECT '1_상품조회'    AS 단계, COUNT(*) AS 고객수, 100.0 AS 직전단계대비 FROM 조회
UNION ALL
SELECT '2_장바구니', COUNT(*),
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM 조회), 1)
  FROM 장바구니 WHERE customer_id IN (SELECT customer_id FROM 조회)
UNION ALL
SELECT '3_구매', COUNT(*),
       ROUND(100.0 * COUNT(*) /
             (SELECT COUNT(*) FROM 장바구니 WHERE customer_id IN (SELECT customer_id FROM 조회)), 1)
  FROM 구매 WHERE customer_id IN (SELECT customer_id FROM 장바구니)
 ORDER BY 1;


-- -----------------------------------------------------------------------------
-- [E-3] 상품별 조회-구매 전환
--
--   "조회는 많은데 팔리지 않는 상품"을 찾는다.
--   가격 문제, 상세 페이지 문제, 품절 등을 점검할 후보가 된다.
--
--   ※ 주문은 clickstream 기간으로 잘라 조건을 맞춘다.
-- -----------------------------------------------------------------------------
WITH 클릭 AS (
    SELECT product_id,
           COUNT(*) FILTER (WHERE event_type = 'page_view')   AS 조회수,
           COUNT(*) FILTER (WHERE event_type = 'add_to_cart') AS 장바구니수
      FROM clickstream
     WHERE product_id IS NOT NULL AND event_time IS NOT NULL
     GROUP BY product_id
),
주문 AS (
    SELECT product_id, COUNT(*) AS 주문수
      FROM orders
     WHERE status = 'success'
       AND order_date BETWEEN '2025-09-02' AND '2025-12-02'
     GROUP BY product_id
)
SELECT k.product_id,
       p.category                                      AS 카테고리,
       p.price                                         AS 단가,
       k.조회수,
       k.장바구니수,
       COALESCE(m.주문수, 0)                           AS 주문수,
       ROUND(100.0 * k.장바구니수 / k.조회수, 1)       AS 조회_장바구니율,
       ROUND(100.0 * COALESCE(m.주문수, 0) / k.조회수, 1) AS 조회_구매율
  FROM 클릭 k
  JOIN product_catalog p ON k.product_id = p.product_id
  LEFT JOIN 주문 m       ON k.product_id = m.product_id
 WHERE k.조회수 >= 100                 -- 표본이 적으면 비율이 불안정하다
 ORDER BY 조회_구매율 ASC              -- 전환이 낮은 순 = 개선 후보
 LIMIT 15;


-- -----------------------------------------------------------------------------
-- [E-4] 비로그인 이벤트 비중
--
--   전체 이벤트의 30%는 로그인하지 않은 상태의 행동이다.
--   퍼널 분석은 customer_id 가 필요하므로 이 30%가 빠진다.
--   → 분석 결과를 제시할 때 이 한계를 함께 밝혀야 한다.
-- -----------------------------------------------------------------------------
SELECT event_type                                                        AS 행동유형,
       COUNT(*)                                                          AS 전체,
       COUNT(*) FILTER (WHERE is_logged_in)                              AS 로그인,
       COUNT(*) FILTER (WHERE NOT is_logged_in)                          AS 비로그인,
       ROUND(100.0 * COUNT(*) FILTER (WHERE NOT is_logged_in) / COUNT(*), 1) AS 비로그인비율
  FROM clickstream
 GROUP BY event_type
 ORDER BY 전체 DESC;


-- #############################################################################
-- F. 데이터 품질이 분석 결과에 미치는 영향
--
--   정제 단계에서 내린 판단이 실제 숫자를 얼마나 바꾸는지 확인한다.
--   이 절은 포트폴리오에서 정제 작업의 가치를 보여주는 근거가 된다.
-- #############################################################################

-- -----------------------------------------------------------------------------
-- [F-1] 고가 이상치 11건이 평균 단가에 미치는 영향
--
--   product_catalog 정제에서 고가 이상치를 삭제하지 않고 플래그만 남겼다.
--   그 결정 덕분에 '포함 / 제외' 두 기준을 모두 계산할 수 있다.
-- -----------------------------------------------------------------------------
SELECT '전체 포함'                    AS 기준,
       COUNT(*)                        AS 상품수,
       ROUND(AVG(price))               AS 평균단가,
       ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY price)::numeric) AS 중앙단가
  FROM product_catalog WHERE price IS NOT NULL
UNION ALL
SELECT '고가 이상치 제외', COUNT(*), ROUND(AVG(price)),
       ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY price)::numeric)
  FROM product_catalog WHERE price IS NOT NULL AND price_flag IS NULL;


-- -----------------------------------------------------------------------------
-- [F-2] 티켓 날짜 복원이 시계열 분석에 미치는 영향
--
--   support_tickets 에서 처리시간 컬럼을 근거로 날짜 12,626건을 복원했다.
--   복원하지 않았다면 월별 문의 건수가 절반 규모로 보였을 것이다.
-- -----------------------------------------------------------------------------
SELECT to_char(ticket_created, 'YYYY-MM')                    AS 월,
       COUNT(*)                                              AS 복원포함,
       COUNT(*) FILTER (WHERE date_flag IS NULL)             AS 원본만,
       ROUND(100.0 * COUNT(*) FILTER (WHERE date_flag IS NULL) / COUNT(*), 1) AS 원본비율
  FROM support_tickets
 WHERE ticket_created IS NOT NULL
 GROUP BY 1
 ORDER BY 1
 LIMIT 12;


-- -----------------------------------------------------------------------------
-- [F-3] NULL 처리된 값의 원본 확인
--
--   원본 보존 컬럼(_raw)이 있으므로, 무엇을 왜 비웠는지 DB에서 바로 확인된다.
--   정제 결과에 의문이 생기면 이 쿼리로 근거를 제시할 수 있다.
-- -----------------------------------------------------------------------------
SELECT date_flag                     AS 처리사유,
       order_date_raw                AS 원본값,
       COUNT(*)                      AS 건수
  FROM orders
 WHERE order_date IS NULL
 GROUP BY 1, 2
 ORDER BY 3 DESC;
