-- =============================================================================
-- 파일명 : 03_verify_load.sql
-- 단계   : 6단계 - 적재 후 검증
--
-- [목적]
--   CSV가 DB에 정확히 들어갔는지, 테이블 간 관계가 성립하는지 확인한다.
--
-- [파이썬 검증(5단계)과 무엇이 다른가]
--   5단계는 CSV 파일을 검사했다. 이 단계는 DB에 들어간 결과를 검사한다.
--   적재 과정에서 값이 잘리거나 형변환이 잘못될 수 있으므로 다시 확인해야 한다.
--   예: 소수점이 사라지거나, 날짜가 다른 시간대로 변환되는 경우
--
-- [실행 방법]
--   DBeaver SQL 편집기에서 쿼리를 하나씩 실행한다 (커서를 두고 Ctrl+Enter).
--   전체를 한 번에 실행하려면 Alt+X 를 누른다.
-- =============================================================================

SET search_path TO portfolio, public;


-- =============================================================================
-- [검증 1] 행 수 대조
--   정제 단계에서 확인한 건수와 DB의 건수가 일치해야 한다.
--   UNION ALL 은 여러 SELECT 결과를 위아래로 이어붙인다.
-- =============================================================================
SELECT '1_product_catalog' AS 테이블
,COUNT(*) AS 실제건수
,500 AS 기대건수 
FROM product_catalog
UNION ALL
SELECT '2_crm_customers',        COUNT(*),  48200 FROM crm_customers
UNION ALL
SELECT '3_crm_customer_devices', COUNT(*),  51854 FROM crm_customer_devices
UNION ALL
SELECT '4_orders',               COUNT(*), 300000 FROM orders
UNION ALL
SELECT '5_support_tickets',      COUNT(*),  30000 FROM support_tickets
ORDER BY 1
;


-- =============================================================================
-- [검증 2] 참조 정합성 (고아 레코드)
--
--   외래키 제약을 걸어뒀으므로 적재가 성공했다는 것만으로도
--   고아 레코드가 없다는 증거다. 그래도 명시적으로 세어 리포트에 남긴다.
--
--   LEFT JOIN + IS NULL 은 "왼쪽에는 있는데 오른쪽에는 없는 행"을 찾는 방법이다.
-- =============================================================================
SELECT '주문 → 고객'   AS 관계,
       COUNT(*)        AS 고아건수
  FROM orders o
  LEFT JOIN crm_customers c ON o.customer_id = c.customer_id
 WHERE c.customer_id IS NULL
UNION ALL
SELECT '주문 → 상품',   COUNT(*)
  FROM orders o
  LEFT JOIN product_catalog p ON o.product_id = p.product_id
 WHERE p.product_id IS NULL
UNION ALL
SELECT '티켓 → 고객',   COUNT(*)
  FROM support_tickets t
  LEFT JOIN crm_customers c ON t.customer_id = c.customer_id
 WHERE c.customer_id IS NULL
UNION ALL
SELECT '기기 → 고객',   COUNT(*)
  FROM crm_customer_devices d
  LEFT JOIN crm_customers c ON d.customer_id = c.customer_id
 WHERE c.customer_id IS NULL;


-- =============================================================================
-- [검증 3] 파생 컬럼 재검산
--
--   device_count 는 파이썬에서 계산해 넣은 값이다.
--   DB에서 기기 테이블을 실제로 세어 대조한다.
--   파생 컬럼은 틀려도 눈에 보이지 않으므로 반드시 검산해야 한다.
--
--   COALESCE(a, b) : a가 NULL이면 b를 쓴다. 기기가 없는 고객은 0으로 센다.
-- =============================================================================
SELECT COUNT(*) AS device_count_불일치건수
  FROM crm_customers c
  LEFT JOIN (
        SELECT customer_id, COUNT(*) AS 실제기기수
          FROM crm_customer_devices
         GROUP BY customer_id
       ) d ON c.customer_id = d.customer_id
 WHERE c.device_count <> COALESCE(d.실제기기수, 0);


-- =============================================================================
-- [검증 4] support_tickets 세 컬럼 관계식
--
--   해결일시 − 접수일시 = 처리시간 이 성립해야 한다.
--   날짜 12,626건을 이 관계식으로 복원했으므로, DB에서도 확인한다.
--
--   EXTRACT(EPOCH FROM 간격) : 시간 간격을 초 단위 숫자로 바꾼다. 3600으로 나누면 시간이다.
--   ABS(...) < 0.001 : 부동소수점 오차를 감안한 비교
-- =============================================================================
SELECT COUNT(*) AS 관계식_불일치건수
  FROM support_tickets
 WHERE ticket_created IS NOT NULL
   AND ABS(EXTRACT(EPOCH FROM (ticket_resolved - ticket_created)) / 3600
           - resolution_time_hours) > 0.001;


-- =============================================================================
-- [검증 5] NULL 건수 대조
--
--   정제 단계에서 의도적으로 비운 건수와 DB의 NULL 건수가 일치해야 한다.
--   숫자가 다르면 적재 과정에서 값이 유실되거나 빈 문자열이 NULL로
--   잘못 변환된 것이다.
--
--   COUNT(*) 는 전체 행을, COUNT(컬럼) 은 NULL이 아닌 행만 센다.
--   따라서 COUNT(*) - COUNT(컬럼) 이 NULL 건수다.
-- =============================================================================
SELECT 'orders.order_date'   AS 컬럼,
       COUNT(*) - COUNT(order_date)   AS null건수, 90000 AS 기대값 FROM orders
UNION ALL
SELECT 'orders.order_amount',
       COUNT(*) - COUNT(order_amount), 51525 FROM orders
UNION ALL
SELECT 'orders.quantity',
       COUNT(*) - COUNT(quantity),     44867 FROM orders
UNION ALL
SELECT 'tickets.ticket_created',
       COUNT(*) - COUNT(ticket_created), 2687 FROM support_tickets
UNION ALL
SELECT 'products.price',
       COUNT(*) - COUNT(price),           71 FROM product_catalog
ORDER BY 1;


-- =============================================================================
-- [검증 6] 범주형 값 분포
--   허용값만 들어갔는지, 분포가 정제 로그와 같은지 확인한다.
-- =============================================================================
SELECT 'payment_method' AS 컬럼, payment_method AS 값, COUNT(*) AS 건수
  FROM orders GROUP BY payment_method
UNION ALL
SELECT 'status', status, COUNT(*) FROM orders GROUP BY status
UNION ALL
SELECT 'issue_type', issue_type, COUNT(*) FROM support_tickets GROUP BY issue_type
UNION ALL
SELECT 'sentiment', sentiment, COUNT(*) FROM support_tickets GROUP BY sentiment
UNION ALL
SELECT 'category', category, COUNT(*) FROM product_catalog GROUP BY category
 ORDER BY 1, 3 DESC;


-- =============================================================================
-- [검증 7] 자료형이 제대로 변환됐는지
--
--   CSV는 전부 문자열이다. DB에 넣을 때 숫자·날짜로 변환된다.
--   이 변환이 제대로 됐는지 확인한다.
--   문자열로 들어갔다면 MIN/MAX 결과가 사전순으로 나와서 이상하게 보인다.
-- =============================================================================
SELECT MIN(order_date)   AS 주문일_최소,
       MAX(order_date)   AS 주문일_최대,
       MIN(order_amount) AS 금액_최소,
       MAX(order_amount) AS 금액_최대,
       ROUND(AVG(order_amount), 2) AS 금액_평균
  FROM orders;

SELECT MIN(ticket_created) AS 접수_최소,
       MAX(ticket_resolved) AS 해결_최대,
       MIN(resolution_time_hours) AS 처리시간_최소,
       MAX(resolution_time_hours) AS 처리시간_최대
  FROM support_tickets;


-- =============================================================================
-- [검증 8] 원본 보존 컬럼이 살아 있는지
--
--   정제값과 원본값이 다른 건수를 센다.
--   이 숫자가 0이면 _raw 컬럼에 정제값이 잘못 들어갔다는 뜻이다.
-- =============================================================================
SELECT 'crm.first_name' AS 컬럼,
       COUNT(*) FILTER (WHERE first_name <> first_name_raw) AS 값이_변경된건수
  FROM crm_customers
UNION ALL
SELECT 'crm.phone_number',
       COUNT(*) FILTER (WHERE phone_number <> phone_number_raw)
  FROM crm_customers
UNION ALL
SELECT 'orders.order_date',
       COUNT(*) FILTER (WHERE order_date IS NULL AND order_date_raw IS NOT NULL)
  FROM orders
UNION ALL
SELECT 'tickets.ticket_created(복원)',
       COUNT(*) FILTER (WHERE date_flag LIKE '접수일시_복원%'
                           OR date_flag LIKE '해결일시_복원%')
  FROM support_tickets;


-- =============================================================================
-- [검증 9] 조인이 실제로 되는지 — 5개 테이블 전체 연결
--
--   이 쿼리가 결과를 내면 관계형 구조가 완성됐다는 뜻이다.
--   7단계 분석의 기초가 되는 형태다.
-- =============================================================================
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS 고객명,
       c.device_count                     AS 보유기기수,
       COUNT(DISTINCT o.order_id)         AS 주문수,
       SUM(o.order_amount)                AS 총구매액,
       COUNT(DISTINCT t.ticket_id)        AS 문의수
  FROM crm_customers c
  LEFT JOIN orders o          ON c.customer_id = o.customer_id
  LEFT JOIN support_tickets t ON c.customer_id = t.customer_id
 GROUP BY c.customer_id, c.first_name, c.last_name, c.device_count
HAVING COUNT(DISTINCT o.order_id) > 0
   AND COUNT(DISTINCT t.ticket_id) > 0
 ORDER BY 총구매액 DESC NULLS LAST
 LIMIT 10;


-- =============================================================================
-- [검증 10] 제약조건이 실제로 걸려 있는지 확인
--
--   DDL에 선언한 제약조건이 DB에 반영됐는지 목록으로 확인한다.
--   제약조건은 앞으로 잘못된 데이터가 들어오는 것을 막아주는 안전장치다.
-- =============================================================================
SELECT tc.table_name  AS 테이블,
       tc.constraint_type AS 종류,
       COUNT(*)       AS 개수
  FROM information_schema.table_constraints tc
 WHERE tc.table_schema = 'portfolio'
 GROUP BY tc.table_name, tc.constraint_type
 ORDER BY 1, 2;
