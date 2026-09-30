-- =============================================================================
-- 파일명 : 02_load_data.sql
-- 단계   : 6단계 - 정제 데이터 적재
--
-- [목적]
--   03_cleaned 폴더의 CSV 5개를 PostgreSQL 테이블에 넣는다.
--
-- [적재 순서가 중요한 이유]
--   외래키(FK) 제약 때문이다.
--   orders 테이블은 customer_id 가 crm_customers 에 존재해야만 행을 받는다.
--   따라서 참조되는 테이블을 먼저 채워야 한다.
--
--     1) product_catalog        (참조 대상)
--     2) crm_customers          (참조 대상)
--     3) crm_customer_devices   (고객 참조)
--     4) orders                 (고객 + 상품 참조)
--     5) support_tickets        (고객 참조)
--
--   순서를 어기면 "violates foreign key constraint" 오류가 난다.
--   이 오류는 데이터가 잘못된 게 아니라 순서를 어겼다는 신호다.
--
-- [실행 방법]
--   이 파일은 psql 전용 명령(\copy)을 사용한다.
--   DBeaver SQL 편집기에서는 \copy 가 동작하지 않는다.
--   → DBeaver를 쓰려면 가이드 문서의 '방법 B(임포트 마법사)'를 따른다.
--   → psql 을 쓰려면 아래 명령으로 이 파일을 실행한다.
--
--     "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -d portfolio_db -f 02_load_data.sql
--
-- [경로 수정 필요]
--   아래 경로를 본인 환경에 맞게 바꿔야 한다.
--   윈도우 경로는 슬래시(/)를 쓰거나 역슬래시를 두 번(\\) 쓴다.
-- =============================================================================

-- =============================================================================
-- [필수 0단계] 이 파일을 실행하기 전에 반드시 할 일
--
--   ① 01_create_tables.sql 을 먼저 실행해 테이블을 만들어야 한다.
--      테이블이 없으면 "릴레이션(relation)이 없습니다" 오류가 난다.
--
--   ② 명령 프롬프트에서 아래 두 줄을 먼저 실행한다 (한글 인코딩 설정).
--        chcp 65001
--        set PGCLIENTENCODING=UTF8
--      하지 않으면 "UHC 인코딩에 대응되는 문자 코드가 없습니다" 오류가 난다.
-- =============================================================================

-- psql이 이 파일을 UTF-8로 읽도록 지정한다.
--   윈도우 명령 프롬프트의 기본 인코딩은 UHC(CP949)여서,
--   UTF-8로 저장된 한글 주석·컬럼명을 잘못 해석해 오류가 난다.
--   이 한 줄이 그것을 막아준다.
--   ※ \encoding 은 psql 전용 명령이다. DBeaver에서는 이 줄을 지우고 실행한다.
\encoding UTF8

SET search_path TO portfolio, public;


-- =============================================================================
-- [준비] 재실행을 위한 초기화
--
--   적재를 다시 할 때 기존 데이터를 지운다.
--   TRUNCATE 는 DELETE 보다 훨씬 빠르다 (행을 하나씩 지우지 않고 통째로 비운다).
--   CASCADE 는 이 테이블을 참조하는 테이블의 데이터도 함께 비운다.
--
--   ※ 처음 적재할 때는 실행할 필요가 없어서 주석(--)으로 막아두었다.
--     두 번째 적재부터는 아래 두 줄 앞의 -- 를 지우고 실행한다.
--     테이블이 아직 없는 상태에서 실행하면 "릴레이션이 없습니다" 오류가 난다.
-- =============================================================================
TRUNCATE TABLE support_tickets, orders, crm_customer_devices,
               crm_customers, product_catalog CASCADE;


-- =============================================================================
-- [적재] CSV → 테이블
--
--   \copy 옵션 설명
--     FORMAT csv        : CSV 형식으로 읽는다
--     HEADER true       : 첫 줄은 컬럼명이므로 건너뛴다
--                         (덤으로 파일 앞의 BOM 문자도 함께 무시된다)
--     ENCODING 'UTF8'   : 파일 인코딩을 지정한다
--
--   CSV의 빈 칸은 자동으로 NULL 로 들어간다.
--   따라서 우리가 의도적으로 비운 값(order_date 등)이 그대로 NULL 이 된다.

-- [실행 위치] 이 파일의 경로는 프로젝트 최상단 기준 상대경로다.
--   반드시 project_1 폴더에서 psql 을 실행해야 한다.
--     cd C:\...\project_1
--     psql -U postgres -d portfolio_db -f sql/02_load_data.sql

-- =============================================================================

-- 1) 상품 마스터 (500행)
\copy product_catalog FROM '03_cleaned/product_catalog_cleaned.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- 2) 고객 마스터 (48,200행)
\copy crm_customers FROM '03_cleaned/crm_customers_cleaned.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- 3) 고객-기기 (51,854행)
\copy crm_customer_devices FROM '03_cleaned/crm_customer_devices_cleaned.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- 4) 주문 (300,000행)
\copy orders FROM '03_cleaned/orders_cleaned.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- 5) 지원 티켓 (30,000행)
\copy support_tickets FROM '03_cleaned/support_tickets_cleaned.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')


-- =============================================================================
-- [마무리] 통계 정보 갱신
--
--   ANALYZE 는 각 테이블의 데이터 분포를 조사해 기록한다.
--   PostgreSQL이 쿼리 실행 계획을 세울 때 이 정보를 참고하므로,
--   대량 적재 후에 한 번 실행해주면 이후 조회가 빨라진다.
-- =============================================================================
ANALYZE product_catalog;
ANALYZE crm_customers;
ANALYZE crm_customer_devices;
ANALYZE orders;
ANALYZE support_tickets;


-- =============================================================================
-- [확인] 적재 건수
-- =============================================================================
SELECT 'product_catalog'      AS 테이블, COUNT(*) AS 적재건수 FROM product_catalog
UNION ALL SELECT 'crm_customers',        COUNT(*) FROM crm_customers
UNION ALL SELECT 'crm_customer_devices', COUNT(*) FROM crm_customer_devices
UNION ALL SELECT 'orders',               COUNT(*) FROM orders
UNION ALL SELECT 'support_tickets',      COUNT(*) FROM support_tickets;
