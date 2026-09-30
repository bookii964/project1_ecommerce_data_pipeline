-- =============================================================================
-- 파일명 : 05_verify_clickstream.sql
-- 단계   : 6단계 - clickstream 적재 검증 및 6개 테이블 연결 확인
--
-- [목적]
--   ① clickstream 이 제대로 적재됐는지 확인한다
--   ② 6개 테이블이 하나의 관계형 구조로 연결되는지 확인한다
--
-- [실행 방법]
--   DBeaver SQL 편집기에서 쿼리를 하나씩 실행한다 (Ctrl + Enter).
-- =============================================================================

SET search_path TO portfolio, public;


-- =============================================================================
-- [검증 1] 전체 테이블 행 수
--   6개 테이블이 모두 들어갔는지 한눈에 확인한다.
-- =============================================================================
SELECT '1_product_catalog'      AS 테이블, COUNT(*) AS 실제건수,    500 AS 기대건수 FROM product_catalog
UNION ALL SELECT '2_crm_customers',        COUNT(*),  48200 FROM crm_customers
UNION ALL SELECT '3_crm_customer_devices', COUNT(*),  51854 FROM crm_customer_devices
UNION ALL SELECT '4_orders',               COUNT(*), 300000 FROM orders
UNION ALL SELECT '5_support_tickets',      COUNT(*),  30000 FROM support_tickets
UNION ALL SELECT '6_clickstream',          COUNT(*), 500000 FROM clickstream
ORDER BY 1;


-- =============================================================================
-- [검증 2] clickstream NULL 건수 대조
--
--   정제 단계에서 의도적으로 비운 건수와 일치해야 한다.
--   숫자가 다르면 적재 중 값이 유실됐거나, 빈 문자열이 NULL로 잘못 변환된 것이다.
-- =============================================================================
SELECT 'event_time'  AS 컬럼, COUNT(*) - COUNT(event_time)  AS null건수,  60090 AS 기대값 FROM clickstream
UNION ALL SELECT 'customer_id', COUNT(*) - COUNT(customer_id), 150553 FROM clickstream
UNION ALL SELECT 'product_id',  COUNT(*) - COUNT(product_id),  143634 FROM clickstream
UNION ALL SELECT 'page_url',    COUNT(*) - COUNT(page_url),      8305 FROM clickstream
UNION ALL SELECT 'device_id',   COUNT(*) - COUNT(device_id),     4986 FROM clickstream
ORDER BY 1;


-- =============================================================================
-- [검증 3] 참조 정합성
--
--   외래키를 걸어뒀으므로 적재 성공이 곧 증거지만, 명시적으로 세어 남긴다.
--   customer_id 와 product_id 는 NULL 을 허용하므로 값이 있는 행만 대조한다.
-- =============================================================================
SELECT '클릭 → 고객' AS 관계, COUNT(*) AS 고아건수
  FROM clickstream c
  LEFT JOIN crm_customers m ON c.customer_id = m.customer_id
 WHERE c.customer_id IS NOT NULL AND m.customer_id IS NULL
UNION ALL
SELECT '클릭 → 상품', COUNT(*)
  FROM clickstream c
  LEFT JOIN product_catalog p ON c.product_id = p.product_id
 WHERE c.product_id IS NOT NULL AND p.product_id IS NULL;


-- =============================================================================
-- [검증 4] 파생 컬럼 정합성
--
--   is_logged_in 은 customer_id 존재 여부로 만든 값이다.
--   CHECK 제약을 걸어뒀으므로 위반이 있으면 적재 자체가 실패한다.
--   그래도 명시적으로 확인한다 (제약이 실제로 작동했다는 기록).
-- =============================================================================
SELECT COUNT(*) AS is_logged_in_불일치건수
  FROM clickstream
 WHERE is_logged_in <> (customer_id IS NOT NULL);

-- product_id 는 page_url 에서 추출한 값이다. URL과 일치하는지 재검산한다.
--
--   [주의] 처음에는 조건을 아래처럼 썼다가 6,163건이 걸렸다.
--       page_url NOT LIKE '%/product/' || product_id
--   product_id 가 URL의 '맨 끝'에 있어야 한다는 조건이어서,
--   'https://.../product/PROD-0187///' 처럼 뒤에 슬래시가 붙은 URL이
--   전부 오류로 잡혔다. 추출은 정확했고 검증 조건이 잘못된 것이었다.
--   → 뒤에 무엇이 붙어도 되도록 '%' 를 양쪽에 둔다.
SELECT COUNT(*) AS product_id_추출오류건수
  FROM clickstream
 WHERE product_id IS NOT NULL
   AND page_url NOT LIKE '%/product/' || product_id || '%';


-- =============================================================================
-- [검증 5] 자료형 변환 및 유효 구간
--
--   문자열이 TIMESTAMP 로 제대로 변환됐는지 확인한다.
--   문자열로 들어갔다면 최소·최대가 사전순으로 나와 이상하게 보인다.
-- =============================================================================
SELECT MIN(event_time)                       AS 수집시작,
       MAX(event_time)                       AS 수집종료,
       COUNT(DISTINCT DATE(event_time))      AS 수집일수,
       COUNT(event_time)                     AS 유효이벤트,
       ROUND(COUNT(event_time)::numeric
             / COUNT(DISTINCT DATE(event_time)), 0) AS 일평균이벤트
  FROM clickstream;


-- =============================================================================
-- [검증 6] 행동 유형 분포와 상품 추출 대응
--
--   login 과 search 에 상품이 0건이어야 정상이다.
--   로그인 화면과 검색 결과 페이지에 특정 상품 코드가 있을 이유가 없다.
--   '상식과 맞는지' 확인하는 것도 검증이다.
--
--   FILTER (WHERE ...) : 조건에 맞는 행만 세는 문법. CASE WHEN 보다 읽기 쉽다.
-- =============================================================================
SELECT event_type                                          AS 행동유형,
       COUNT(*)                                            AS 전체,
       COUNT(*) FILTER (WHERE product_id IS NOT NULL)      AS 상품있음,
       COUNT(*) FILTER (WHERE is_logged_in)                AS 로그인상태,
       COUNT(*) FILTER (WHERE event_time IS NOT NULL)      AS 시각유효
  FROM clickstream
 GROUP BY event_type
 ORDER BY 전체 DESC;


-- =============================================================================
-- [검증 7] NULL 처리 사유별 내역
--   무엇을 왜 비웠는지 DB에서 바로 확인할 수 있다.
-- =============================================================================
SELECT COALESCE(time_flag, '(정상)') AS 시각처리사유,
       COUNT(*)                      AS 건수
  FROM clickstream
 GROUP BY time_flag
 ORDER BY 건수 DESC;

SELECT COALESCE(device_flag, '(정상)') AS device처리사유,
       COUNT(*)                        AS 건수
  FROM clickstream
 GROUP BY device_flag
 ORDER BY 건수 DESC;


-- =============================================================================
-- [검증 8] 6개 테이블 전체 연결 — 관계형 구조 완성 확인
--
--   고객 한 명을 기준으로 모든 테이블을 이어본다.
--   이 쿼리가 결과를 내면 6개 테이블이 하나의 구조로 연결된 것이다.
--
--   [주의] 여러 테이블을 한 번에 LEFT JOIN 하면 행이 곱해진다.
--     고객 1명이 주문 10건, 문의 3건이면 조인 결과가 30행이 된다.
--     그래서 각 테이블을 먼저 집계한 뒤 합치는 방식을 쓴다.
--     이렇게 미리 집계한 결과를 붙이는 것을 서브쿼리 조인이라고 한다.
-- =============================================================================
SELECT c.first_name || ' ' || c.last_name AS 고객명,
       c.device_count                     AS 등록기기,
       COALESCE(o.주문수, 0)              AS 주문수,
       COALESCE(o.구매액, 0)              AS 구매액,
       COALESCE(t.문의수, 0)              AS 문의수,
       COALESCE(v.조회수, 0)              AS 상품조회,
       COALESCE(v.장바구니, 0)            AS 장바구니
  FROM crm_customers c
  LEFT JOIN (SELECT customer_id,
                    COUNT(*)          AS 주문수,
                    SUM(order_amount) AS 구매액
               FROM orders
              GROUP BY customer_id) o ON c.customer_id = o.customer_id
  LEFT JOIN (SELECT customer_id, COUNT(*) AS 문의수
               FROM support_tickets
              GROUP BY customer_id) t ON c.customer_id = t.customer_id
  LEFT JOIN (SELECT customer_id,
                    COUNT(*) FILTER (WHERE event_type = 'page_view')   AS 조회수,
                    COUNT(*) FILTER (WHERE event_type = 'add_to_cart') AS 장바구니
               FROM clickstream
              WHERE customer_id IS NOT NULL
              GROUP BY customer_id) v ON c.customer_id = v.customer_id
 WHERE o.주문수 IS NOT NULL
   AND v.조회수 IS NOT NULL
 ORDER BY 구매액 DESC NULLS LAST
 LIMIT 10;


-- =============================================================================
-- [검증 9] 상품 기준 연결 — 클릭스트림 + 주문 + 카탈로그
--
--   "조회는 많았지만 주문은 적은 상품"을 찾을 수 있는 구조인지 확인한다.
--   7단계 분석에서 쓸 형태의 쿼리다.
-- =============================================================================
SELECT p.product_id,
       p.category                                    AS 카테고리,
       COALESCE(v.조회수, 0)                          AS 조회수,
       COALESCE(v.장바구니, 0)                        AS 장바구니,
       COALESCE(o.주문수, 0)                          AS 주문수
  FROM product_catalog p
  LEFT JOIN (SELECT product_id,
                    COUNT(*) FILTER (WHERE event_type = 'page_view')   AS 조회수,
                    COUNT(*) FILTER (WHERE event_type = 'add_to_cart') AS 장바구니
               FROM clickstream
              WHERE product_id IS NOT NULL
              GROUP BY product_id) v ON p.product_id = v.product_id
  LEFT JOIN (SELECT product_id, COUNT(*) AS 주문수
               FROM orders
              WHERE status = 'success'
              GROUP BY product_id) o ON p.product_id = o.product_id
 ORDER BY 조회수 DESC
 LIMIT 10;


-- =============================================================================
-- [검증 10] 제약조건 현황
--   6개 테이블에 걸린 제약조건을 확인한다.
--   정제 규칙이 DB 수준에서 강제되고 있다는 증거다.
-- =============================================================================
SELECT tc.table_name      AS 테이블,
       tc.constraint_type AS 종류,
       COUNT(*)           AS 개수
  FROM information_schema.table_constraints tc
 WHERE tc.table_schema = 'portfolio'
 GROUP BY tc.table_name, tc.constraint_type
 ORDER BY 1, 2;
