-- =============================================================================
-- 파일명 : 04_create_load_clickstream.sql
-- 단계   : 6단계 - clickstream 테이블 생성 및 적재
--
-- [목적]
--   정제된 clickstream_cleaned.csv 를 담을 테이블을 만들고 데이터를 넣는다.
--   기존 5개 테이블에 이어 6번째 테이블을 추가한다.
--
-- [기존 테이블과 다른 설계 포인트 3가지]
--
--   ① 외래키가 두 개인데 둘 다 NULL 을 허용한다
--      customer_id : 비로그인 이벤트는 값이 없다 (30%)
--      product_id  : 검색·홈 페이지 이벤트는 상품이 없다 (28.7%)
--      → PostgreSQL의 외래키는 값이 NULL이면 검사를 건너뛴다.
--        따라서 'NULL 허용 + 외래키'는 모순이 아니라 정상 설계다.
--        값이 있을 때만 마스터에 존재하는지 확인한다.
--
--   ② '분석에 쓸 수 없는 컬럼'을 주석으로 명시한다
--      session_id / device_id / ingest_run_id 는 값이 정상이라
--      아무 표시가 없으면 다음 사람이 당연히 조인하려고 한다.
--      → COMMENT 로 사용 금지와 그 근거를 컬럼에 붙여둔다.
--        DBeaver에서 컬럼을 보면 바로 확인된다.
--
--   ③ 파생 컬럼의 정합성을 CHECK 로 강제한다
--      is_logged_in 은 customer_id 존재 여부로 만든 값이다.
--      둘이 어긋나면 파생 계산이 잘못됐다는 뜻이므로 DB가 막도록 한다.
--
-- [실행 순서]
--   crm_customers 와 product_catalog 가 이미 적재되어 있어야 한다.
--   (외래키가 참조하므로 마스터가 먼저 있어야 한다)
-- =============================================================================

SET search_path TO portfolio, public;

-- =============================================================================
-- [1] 테이블 생성
-- =============================================================================
DROP TABLE IF EXISTS clickstream CASCADE;

CREATE TABLE clickstream (
    event_id       UUID         NOT NULL,

    -- 분석용 컬럼
    customer_id    UUID,                     -- 비로그인 이벤트는 NULL (150,553건)
    is_logged_in   BOOLEAN      NOT NULL,
    event_type     VARCHAR(20)  NOT NULL,
    page_url       TEXT,                     -- 결측 8,305건. 표기 5종 오염을 정규화
    page_type      VARCHAR(20),              -- 페이지 유형(파생): product_detail 등 5종
    product_id     VARCHAR(9),               -- 상품 페이지가 아니면 NULL
    event_time     TIMESTAMP,                -- 신뢰할 수 없는 값은 NULL (60,090건)

    -- 원본 유지 컬럼 (분석 사용 금지 — 아래 COMMENT 참고)
    session_id     UUID         NOT NULL,
    device_id      UUID,                     -- 복원 불가 4,986건은 NULL
    ingest_run_id  UUID         NOT NULL,

    -- 원본 보존 및 처리 사유
    timestamp_raw  TEXT,
    page_url_raw   TEXT,
    time_flag      TEXT,
    device_flag    TEXT,

    CONSTRAINT pk_clickstream PRIMARY KEY (event_id),

    -- 외래키 : 값이 NULL이면 검사를 건너뛴다.
    --   따라서 비로그인 이벤트(customer_id NULL)도 문제없이 들어간다.
    CONSTRAINT fk_clickstream_customer FOREIGN KEY (customer_id)
        REFERENCES crm_customers (customer_id),
    CONSTRAINT fk_clickstream_product FOREIGN KEY (product_id)
        REFERENCES product_catalog (product_id),

    CONSTRAINT ck_clickstream_event_type CHECK (
        event_type IN ('page_view', 'search', 'add_to_cart', 'login')),

    CONSTRAINT ck_clickstream_page_type CHECK (
        page_type IS NULL OR page_type IN
        ('product_detail', 'search', 'category', 'cart', 'home', 'other')),

    -- page_url 이 있으면 page_type 도 있어야 한다 (파생 정합성)
    CONSTRAINT ck_clickstream_page_pair CHECK (
        (page_url IS NULL) = (page_type IS NULL)),

    -- 파생 컬럼 정합성 : is_logged_in 은 customer_id 존재 여부와 일치해야 한다
    --   어긋나면 파생 계산이 잘못된 것이므로 DB가 막는다
    CONSTRAINT ck_clickstream_login_flag CHECK (
        is_logged_in = (customer_id IS NOT NULL)),

    -- 유효 기간 : 2단계에서 판정한 데이터 수집 구간을 벗어나면 받지 않는다
    CONSTRAINT ck_clickstream_time_range CHECK (
        event_time IS NULL
        OR (event_time >= '2025-09-01' AND event_time <= '2025-12-03')),

    -- 짝 제약 : 시각이 비었으면 반드시 사유가 있어야 한다
    CONSTRAINT ck_clickstream_time_flag CHECK (
        event_time IS NOT NULL OR time_flag IS NOT NULL)
);


-- =============================================================================
-- [2] 컬럼 주석
--
--   '사용 금지' 컬럼에 근거를 붙여두는 것이 이 테이블에서 가장 중요하다.
--   값이 정상이라 표시가 없으면 누구나 조인을 시도하게 된다.
-- =============================================================================
COMMENT ON TABLE clickstream IS
    '클릭스트림 이벤트 로그. 수집 구간 2025-09-02 ~ 2025-12-02 (92일)';

COMMENT ON COLUMN clickstream.customer_id IS
    '행동한 고객. NULL은 오염이 아니라 비로그인 상태의 행동(30.1%)';
COMMENT ON COLUMN clickstream.is_logged_in IS
    '로그인 여부(파생). customer_id 존재 여부로 계산';
COMMENT ON COLUMN clickstream.page_type IS
    '페이지 유형(파생). product_detail / search / category / cart / home';
COMMENT ON COLUMN clickstream.page_url IS
    '정규화된 URL. 원본은 page_url_raw (오염 5종: 끝슬래시·스킴과다·스킴누락·대문자·경로축약)';
COMMENT ON COLUMN clickstream.product_id IS
    'page_url에서 추출한 상품 코드(파생). 검색·홈 페이지는 NULL';
COMMENT ON COLUMN clickstream.event_time IS
    '발생 시각(UTC). 표기 3종을 통일하고 상수·범위이탈·결측은 NULL 처리';
COMMENT ON COLUMN clickstream.time_flag IS
    'NULL 처리 사유: 원본결측 / 상수값 / 범위이탈';

COMMENT ON COLUMN clickstream.device_flag IS
    'device_id 처리 사유: 하이픈복원 / 형식오류(복원불가)';

COMMENT ON COLUMN clickstream.session_id IS
    '[분석 사용 금지] 세션 역할 불가. 한 session_id 안에 고객 평균 43.7명, 기기 62.5개가 섞여 있음';
COMMENT ON COLUMN clickstream.device_id IS
    '[분석 사용 금지] CRM device_id와 다른 체계. crm_customer_devices와 일치 0건, 고유율 99.8%. 형식 오염 4,986건은 NULL';
COMMENT ON COLUMN clickstream.ingest_run_id IS
    '[분석 사용 금지] 적재 배치 번호. 50만 행 전체가 동일한 값';


-- =============================================================================
-- [3] 인덱스
--   조인과 집계에 쓰이는 컬럼에 만든다. 50만 행에서 체감 차이가 크다.
-- =============================================================================
CREATE INDEX idx_clickstream_customer ON clickstream (customer_id);
CREATE INDEX idx_clickstream_product  ON clickstream (product_id);
CREATE INDEX idx_clickstream_time     ON clickstream (event_time);
CREATE INDEX idx_clickstream_type     ON clickstream (event_type);
CREATE INDEX idx_clickstream_pagetype ON clickstream (page_type);


-- =============================================================================
-- [4] 데이터 적재
--
--   \copy 는 psql 전용 명령이다. DBeaver에서는 임포트 마법사를 사용한다.
--   아래 경로를 본인 환경에 맞게 수정한다 (구분자는 슬래시 /).

-- [실행 위치] 이 파일의 경로는 프로젝트 최상단 기준 상대경로다.
--   반드시 project_1 폴더에서 psql 을 실행해야 한다.
--     cd C:\...\project_1
--     psql -U postgres -d portfolio_db -f sql/02_load_data.sql
-- =============================================================================
\copy clickstream FROM '03_cleaned/clickstream_cleaned.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

ANALYZE clickstream;


-- =============================================================================
-- [5] 적재 확인
-- =============================================================================
SELECT COUNT(*) AS 적재건수, 500000 AS 기대건수 FROM clickstream;

SELECT page_type, COUNT(*) FROM portfolio.clickstream GROUP BY 1 ORDER BY 2 DESC;
