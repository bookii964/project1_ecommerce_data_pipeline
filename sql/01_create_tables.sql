-- =============================================================================
-- 파일명 : 01_create_tables.sql
-- 단계   : 6단계 - PostgreSQL 테이블 생성 (DDL)
--
-- [목적]
--   정제 완료된 CSV 5개를 담을 테이블을 만든다.
--
-- [DDL이란]
--   Data Definition Language. 테이블의 '구조'를 정의하는 SQL이다.
--   데이터를 넣고 빼는 SQL(SELECT, INSERT)과 구분해서 부른다.
--
-- [이 파일의 설계 원칙]
--
--   ① 제약조건(CONSTRAINT)을 최대한 걸어둔다
--      제약조건은 "이 조건을 어기는 데이터는 받지 않는다"는 규칙이다.
--      2단계 규칙서에서 정한 내용을 DB 수준에서 다시 한 번 선언한다.
--      → 적재가 성공하면 그 자체로 정제가 제대로 됐다는 증거가 된다.
--        1~5단계의 파이썬 검증과 독립적인 두 번째 검증 장치다.
--
--   ② NULL을 허용할 컬럼과 금지할 컬럼을 구분한다
--      키 컬럼은 NOT NULL, 정제 과정에서 비운 컬럼은 NULL 허용.
--      "여기는 비어도 된다"는 것도 설계의 일부다.
--
--   ③ 컬럼에 주석(COMMENT)을 남긴다
--      나중에 DBeaver에서 테이블을 열면 주석이 보인다.
--      _raw 나 _flag 컬럼은 이름만으로 용도를 알기 어려우므로 필수다.
--
-- [실행 순서 주의]
--   외래키(FK)는 참조 대상이 먼저 있어야 만들 수 있다.
--   따라서 테이블 생성과 데이터 적재 모두 아래 순서를 지켜야 한다.
--     1) product_catalog   (참조되는 쪽)
--     2) crm_customers     (참조되는 쪽)
--     3) crm_customer_devices
--     4) orders
--     5) support_tickets
-- =============================================================================


-- =============================================================================
-- [준비] 스키마 생성
--
--   스키마란 테이블을 담는 폴더 같은 개념이다.
--   기본 스키마(public)에 그냥 만들 수도 있지만, 별도 스키마를 쓰면
--   프로젝트 테이블과 시스템 테이블이 섞이지 않아 관리가 쉽다.
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS portfolio;

-- 이후 테이블 이름을 스키마 없이 써도 portfolio 스키마를 먼저 찾도록 설정한다.
-- (이 설정은 현재 접속에서만 유효하다. DBeaver에서 창을 새로 열면 다시 실행해야 한다)
SET search_path TO portfolio, public;


-- =============================================================================
-- [1] product_catalog — 상품 마스터
-- =============================================================================
DROP TABLE IF EXISTS product_catalog CASCADE;

CREATE TABLE product_catalog (
    product_id    VARCHAR(9)   NOT NULL,
    product_name  TEXT         NOT NULL,
    category      VARCHAR(20)  NOT NULL,
    price         NUMERIC(12,2),          -- 음수·0원을 정제에서 NULL 처리했으므로 NULL 허용
    name_flag     TEXT,
    price_flag    TEXT,

    -- 기본키 : 중복과 NULL을 동시에 막는다
    CONSTRAINT pk_product_catalog PRIMARY KEY (product_id),

    -- 형식 제약 : PROD- 뒤에 숫자 4자리
    --   ~ 는 정규표현식 일치 연산자다 (PostgreSQL 문법)
    CONSTRAINT ck_product_id_format CHECK (product_id ~ '^PROD-[0-9]{4}$'),

    -- 허용값 제약 : 2단계 규칙서에서 정한 8종 + unknown
    CONSTRAINT ck_product_category CHECK (category IN (
        'automotive','beauty','clothing','electronics',
        'home','kitchen','sports','toys','unknown')),

    -- 값 범위 제약 : 가격은 0보다 커야 한다 (NULL은 이 검사를 통과한다)
    CONSTRAINT ck_product_price CHECK (price IS NULL OR price > 0)
);

COMMENT ON TABLE  product_catalog IS '상품 마스터. 정제본 product_catalog_cleaned.csv';
COMMENT ON COLUMN product_catalog.price      IS '판매 단가. 음수·0원은 정제 시 NULL 처리';
COMMENT ON COLUMN product_catalog.name_flag  IS '사람 확인이 필요한 상품명 사유(끝자리 숫자 등)';
COMMENT ON COLUMN product_catalog.price_flag IS 'NULL 처리 사유 또는 고가 이상치 표시';


-- =============================================================================
-- [2] crm_customers — 고객 마스터
--
--   customer_id 를 UUID 타입으로 선언한다.
--   문자열로 둘 수도 있지만 UUID 타입을 쓰면
--     - 형식이 틀린 값은 적재 단계에서 거부된다 (별도 CHECK가 필요 없다)
--     - 저장 공간이 절반이고 조인이 빠르다 (16바이트 vs 36바이트)
-- =============================================================================
DROP TABLE IF EXISTS crm_customers CASCADE;

CREATE TABLE crm_customers (
    customer_id       UUID         NOT NULL,
    first_name        TEXT         NOT NULL,
    last_name         TEXT         NOT NULL,
    email             TEXT,                    -- 결측 1,000건 존재
    phone_number      VARCHAR(20),
    phone_ext         VARCHAR(10),             -- 내선번호. 없는 고객이 많으므로 NULL 허용
    gender            CHAR(1)      NOT NULL,
    dob               DATE         NOT NULL,
    signup_date       DATE         NOT NULL,
    age_at_signup     NUMERIC(5,1),            -- 정제본에 29.0 형태로 저장되어 있음
    address           TEXT,
    city              TEXT,
    state             TEXT,
    country           TEXT,
    device_count      SMALLINT     NOT NULL,
    source            VARCHAR(10)  NOT NULL,

    -- 개인정보 원본 보존 컬럼 (분석용 정제값과 구분)
    first_name_raw    TEXT,
    last_name_raw     TEXT,
    email_raw         TEXT,
    phone_number_raw  TEXT,

    name_flag         TEXT,
    email_flag        TEXT,
    phone_flag        TEXT,
    age_flag          TEXT,

    CONSTRAINT pk_crm_customers PRIMARY KEY (customer_id),

    CONSTRAINT ck_customer_gender CHECK (gender IN ('M','F','O')),
    CONSTRAINT ck_customer_source CHECK (source IN ('referral','web','app')),

    -- 논리 제약 : 가입일은 생년월일보다 뒤여야 한다
    CONSTRAINT ck_customer_dates CHECK (signup_date >= dob),

    -- 논리 제약 : 미래 날짜 금지
    CONSTRAINT ck_customer_dob_past CHECK (dob <= CURRENT_DATE),

    CONSTRAINT ck_customer_device_count CHECK (device_count >= 0)
);

COMMENT ON TABLE  crm_customers IS
    '고객 마스터. 분석 전용 사본. 고객 응대·본인확인에는 _raw 컬럼 또는 원본 파일을 사용해야 함';
COMMENT ON COLUMN crm_customers.first_name_raw IS
    '정제 전 원본 표기. 고객이 입력한 값 그대로';
COMMENT ON COLUMN crm_customers.age_at_signup IS
    '가입 시점 나이(파생 컬럼). signup_date - dob 로 계산';
COMMENT ON COLUMN crm_customers.device_count IS
    '보유 기기 수(파생 컬럼). crm_customer_devices 의 행 수와 일치';
COMMENT ON COLUMN crm_customers.state IS
    '주/도. country 와 모순되는 사례가 다수 — 분석 축으로 사용 비권장';
COMMENT ON COLUMN crm_customers.age_flag IS
    '가입 시점 14세 미만 등 확인이 필요한 사유';


-- =============================================================================
-- [3] crm_customer_devices — 고객 보유 기기 (1:N)
--
--   원본 CSV에서는 한 칸에 세미콜론으로 여러 기기가 들어 있었다.
--   제1정규형(한 칸에 값 하나)을 지키기 위해 별도 테이블로 분리했다.
--
--   기본키를 (customer_id, device_id) 두 컬럼 조합으로 잡는다.
--   이런 것을 복합 기본키(composite primary key)라고 한다.
--   같은 고객이 같은 기기를 두 번 등록하는 것을 막아준다.
-- =============================================================================
DROP TABLE IF EXISTS crm_customer_devices CASCADE;

CREATE TABLE crm_customer_devices (
    customer_id  UUID NOT NULL,
    device_id    UUID NOT NULL,

    CONSTRAINT pk_customer_devices PRIMARY KEY (customer_id, device_id),

    -- 외래키 : 존재하지 않는 고객의 기기는 들어올 수 없다
    --   ON DELETE CASCADE : 고객이 삭제되면 그 고객의 기기 행도 함께 삭제된다
    CONSTRAINT fk_devices_customer FOREIGN KEY (customer_id)
        REFERENCES crm_customers (customer_id) ON DELETE CASCADE
);

COMMENT ON TABLE crm_customer_devices IS
    '고객-기기 관계 (1:N). 원본의 다중값 컬럼 device_id(s) 를 제1정규형으로 분리';


-- =============================================================================
-- [4] orders — 주문 거래
-- =============================================================================
DROP TABLE IF EXISTS orders CASCADE;

CREATE TABLE orders (
    order_id          UUID         NOT NULL,
    customer_id       UUID         NOT NULL,
    product_id        VARCHAR(9)   NOT NULL,
    order_amount      NUMERIC(12,2),           -- 51,525건 NULL (상수 오염 처리)
    order_date        DATE,                    -- 90,000건 NULL (비표준 형식 처리)
    payment_method    VARCHAR(10)  NOT NULL,
    status            VARCHAR(10)  NOT NULL,
    quantity          SMALLINT,                -- 44,867건 NULL

    -- 원본 보존 (NULL 처리 건이 많아 추적이 필수)
    order_amount_raw  TEXT,
    order_date_raw    TEXT,
    quantity_raw      TEXT,

    amount_flag       TEXT,
    date_flag         TEXT,
    quantity_flag     TEXT,
    payment_flag      TEXT,
    status_flag       TEXT,

    CONSTRAINT pk_orders PRIMARY KEY (order_id),

    CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id)
        REFERENCES crm_customers (customer_id),
    CONSTRAINT fk_orders_product FOREIGN KEY (product_id)
        REFERENCES product_catalog (product_id),

    CONSTRAINT ck_orders_payment CHECK (payment_method IN ('card','cash','upi','wallet')),
    CONSTRAINT ck_orders_status  CHECK (status IN ('success','failed','refunded')),

    CONSTRAINT ck_orders_amount   CHECK (order_amount IS NULL OR order_amount > 0),
    CONSTRAINT ck_orders_quantity CHECK (quantity IS NULL OR quantity BETWEEN 1 AND 5),
    CONSTRAINT ck_orders_date     CHECK (order_date IS NULL OR order_date <= CURRENT_DATE),

    -- NULL과 사유의 짝 제약 : 값이 비었으면 반드시 사유가 있어야 한다
    --   5단계 파이썬 검증에서 확인한 규칙을 DB에도 선언한다
    CONSTRAINT ck_orders_amount_flag CHECK (order_amount IS NOT NULL OR amount_flag IS NOT NULL),
    CONSTRAINT ck_orders_date_flag   CHECK (order_date   IS NOT NULL OR date_flag   IS NOT NULL)
);

COMMENT ON TABLE  orders IS '주문 거래. 정제본 orders_cleaned.csv';
COMMENT ON COLUMN orders.order_date IS
    '주문일. 상수형 오염·적재시각 추정값은 NULL 처리 (사유는 date_flag)';
COMMENT ON COLUMN orders.order_amount IS
    '주문 금액. 상수값(0 / 1,200 / -50)은 시스템 대체값으로 판단해 NULL 처리';
COMMENT ON COLUMN orders.order_date_raw IS '정제 전 원본 문자열. NULL 처리된 값의 추적용';


-- =============================================================================
-- [5] support_tickets — 고객 지원 티켓
--
--   이 테이블에는 다른 파일에 없는 특징이 있다.
--   날짜 12,626건이 '계산으로 복원된 값'이다 (원본에 없던 값을 만들어냈다).
--   그래서 date_flag 를 반드시 함께 봐야 한다.
-- =============================================================================
DROP TABLE IF EXISTS support_tickets CASCADE;

CREATE TABLE support_tickets (
    ticket_id              UUID         NOT NULL,
    customer_id            UUID         NOT NULL,
    issue_type             VARCHAR(10)  NOT NULL,
    sentiment              VARCHAR(10)  NOT NULL,
    ticket_created         TIMESTAMP,               -- 2,687건 NULL (복원 불가)
    ticket_resolved        TIMESTAMP,
    resolution_time_hours  NUMERIC(6,1) NOT NULL,   -- 완전히 깨끗한 컬럼
    support_agent          TEXT         NOT NULL,

    ticket_created_raw     TEXT,
    ticket_resolved_raw    TEXT,
    support_agent_raw      TEXT,

    date_flag              TEXT,
    issue_flag             TEXT,
    sentiment_flag         TEXT,
    agent_flag             TEXT,

    CONSTRAINT pk_support_tickets PRIMARY KEY (ticket_id),

    CONSTRAINT fk_tickets_customer FOREIGN KEY (customer_id)
        REFERENCES crm_customers (customer_id),

    CONSTRAINT ck_tickets_issue CHECK (issue_type IN ('payment','delay','refund','product')),
    CONSTRAINT ck_tickets_sentiment CHECK (sentiment IN ('positive','neutral','negative')),

    CONSTRAINT ck_tickets_resolution CHECK (resolution_time_hours > 0),

    -- 논리 제약 : 해결이 접수보다 앞설 수 없다
    CONSTRAINT ck_tickets_order CHECK (
        ticket_created IS NULL OR ticket_resolved IS NULL
        OR ticket_resolved >= ticket_created),

    -- 짝 제약 : 두 날짜는 함께 있거나 함께 없어야 한다
    --   한쪽만 있으면 복원 로직이 빠뜨린 케이스라는 뜻이다
    CONSTRAINT ck_tickets_date_pair CHECK (
        (ticket_created IS NULL) = (ticket_resolved IS NULL))
);

COMMENT ON TABLE  support_tickets IS '고객 지원 티켓. 정제본 support_tickets_cleaned.csv';
COMMENT ON COLUMN support_tickets.ticket_created IS
    '접수 일시. 12,626건은 resolution_time_hours 기준 계산으로 복원된 값 (date_flag 확인 필요)';
COMMENT ON COLUMN support_tickets.resolution_time_hours IS
    '처리 소요 시간. 원본이 완전히 깨끗한 컬럼으로, 날짜 복원의 기준이 되었다';
COMMENT ON COLUMN support_tickets.date_flag IS
    '접수일시_복원(...) / 해결일시_복원(...) / 복원불가(양쪽무효). NULL이면 원본 그대로';


-- =============================================================================
-- [인덱스] 조회 성능을 위한 인덱스
--
--   인덱스란 책의 색인과 같다. 특정 값을 빨리 찾기 위한 별도 구조다.
--   기본키에는 자동으로 만들어지지만, 외래키와 자주 쓰는 조건 컬럼에는
--   직접 만들어야 한다. 30만 행 조인에서 체감 차이가 크다.
-- =============================================================================
CREATE INDEX idx_orders_customer   ON orders (customer_id);
CREATE INDEX idx_orders_product    ON orders (product_id);
CREATE INDEX idx_orders_date       ON orders (order_date);
CREATE INDEX idx_orders_status     ON orders (status);

CREATE INDEX idx_tickets_customer  ON support_tickets (customer_id);
CREATE INDEX idx_tickets_created   ON support_tickets (ticket_created);
CREATE INDEX idx_tickets_issue     ON support_tickets (issue_type);

CREATE INDEX idx_devices_device    ON crm_customer_devices (device_id);


-- =============================================================================
-- [확인] 생성된 테이블 목록
-- =============================================================================
SELECT table_name,
       (SELECT COUNT(*) FROM information_schema.columns c
         WHERE c.table_name = t.table_name AND c.table_schema = 'portfolio') AS 컬럼수
  FROM information_schema.tables t
 WHERE table_schema = 'portfolio'
 ORDER BY table_name;


