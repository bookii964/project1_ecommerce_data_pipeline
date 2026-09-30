# 6단계 — PostgreSQL 적재 가이드 (DBeaver)

> 정제 완료된 CSV 5개를 PostgreSQL에 넣고, 제대로 들어갔는지 확인하는 단계다.
>
> **이 단계의 숨은 목적**
> 단순히 데이터를 옮기는 작업이 아니다.
> 테이블에 제약조건(CONSTRAINT)을 걸어두면, **적재가 성공한다는 것 자체가
> 정제가 제대로 됐다는 증거**가 된다.
> 1~5단계의 파이썬 검증과 독립적인 두 번째 검증 장치다.

---

## 0. 사용할 파일

| 파일 | 역할 | 두는 곳 |
|---|---|---|
| `01_create_tables.sql` | 테이블 구조 생성 (DDL) | `sql/` 폴더 신규 생성 권장 |
| `02_load_data.sql` | CSV 적재 (psql 방식) | `sql/` |
| `03_verify_load.sql` | 적재 후 검증 쿼리 | `sql/` |

프로젝트 폴더에 `sql` 폴더를 하나 만들어 세 파일을 넣으세요.

---

## 1. DBeaver에서 PostgreSQL 접속

1. DBeaver 좌측 상단 **새 데이터베이스 연결** 아이콘(플러그 모양) 클릭
2. **PostgreSQL** 선택 → 다음
3. 접속 정보 입력

| 항목 | 값 |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `postgres` |
| Username | `postgres` |
| Password | PostgreSQL 설치 시 정한 비밀번호 |

4. **Test Connection** 클릭 → `Connected` 확인 → **완료**

드라이버 다운로드 창이 뜨면 **Download**를 누릅니다. 이건 접속용 부품(JDBC 드라이버)이고 PostgreSQL 서버와는 별개입니다.

---

## 2. 프로젝트용 데이터베이스 생성

기본 DB(`postgres`)에 테이블을 만들지 않고 별도 DB를 씁니다. 프로젝트 데이터와 시스템 데이터를 섞지 않는 것이 관리에 좋습니다.

1. 좌측 **Database Navigator**에서 방금 만든 연결을 클릭
2. 상단 메뉴 **SQL 편집기 → 새 SQL 편집기** (또는 `Ctrl + ]`)
3. 아래를 입력하고 실행 (커서를 두고 `Ctrl + Enter`)

```sql
CREATE DATABASE portfolio_db;
```

4. Navigator에서 연결을 **우클릭 → 새로 고침**(F5) → `Databases` 아래 `portfolio_db`가 보이는지 확인

**중요 — 접속 DB 전환**
새로 만든 DB에 작업하려면 접속을 바꿔야 합니다. `portfolio_db`를 **더블클릭**하면 굵은 글씨로 바뀌며 활성화됩니다. 이후 여는 SQL 편집기는 이 DB에 연결됩니다.

이걸 놓치면 `postgres` DB에 테이블이 만들어져서 나중에 헷갈립니다.

---

## 3. 테이블 생성 (DDL 실행)

1. `portfolio_db`가 활성화된 상태에서 새 SQL 편집기 열기
2. 메뉴 **파일 → 열기**로 `01_create_tables.sql` 불러오기
3. **`Alt + X`** (스크립트 전체 실행)

정상이면 마지막에 테이블 5개 목록이 나옵니다.

```
crm_customer_devices    2
crm_customers          24
orders                 16
product_catalog         6
support_tickets        15
```

### 이 DDL이 만드는 것

**테이블 5개와 관계**

```
crm_customers ──┬── crm_customer_devices   (1:N)
                ├── orders ── product_catalog
                └── support_tickets
```

**제약조건 총 52개** — 이게 핵심입니다.

| 종류 | 개수 | 역할 |
|---|---|---|
| PRIMARY KEY | 5 | 중복·NULL 방지 |
| FOREIGN KEY | 4 | 존재하지 않는 고객·상품 참조 방지 |
| CHECK | 44 | 허용값·범위·논리 규칙 강제 |

CHECK 제약의 예시입니다.

```sql
-- 2단계 규칙서에서 정한 category 8종 + unknown 만 허용
CHECK (category IN ('automotive','beauty', ... ,'unknown'))

-- 수량은 1~5, 단 NULL은 허용 (정제에서 의도적으로 비웠으므로)
CHECK (quantity IS NULL OR quantity BETWEEN 1 AND 5)

-- 해결일시가 접수일시보다 앞설 수 없다
CHECK (ticket_resolved >= ticket_created)

-- 값이 비었으면 반드시 사유(flag)가 있어야 한다
CHECK (order_date IS NOT NULL OR date_flag IS NOT NULL)
```

**마지막 제약이 특히 의미 있습니다.** 5단계 파이썬 검증에서 확인했던 "NULL과 플래그의 짝" 규칙을 DB가 앞으로도 계속 강제합니다.

---

## 4. 데이터 적재 — 두 가지 방법

### 방법 A. psql 사용 (권장, 빠름)

`\copy`는 PostgreSQL 서버가 직접 파일을 읽는 방식이라 가장 빠릅니다. 30만 행이 몇 초 안에 들어갑니다.

> **먼저 확인 — 3단계(테이블 생성)를 끝냈나요?**
> 테이블이 없는 상태에서 적재하면 이 오류가 납니다.
>
> ```
> 오류: "product_catalog" 이름의 릴레이션(relation)이 없습니다
> ```
>
> `릴레이션(relation)`은 테이블을 뜻하는 용어입니다. **그릇이 없으니 담을 수 없다**는 의미입니다.
> DBeaver에서 DDL을 실행했더라도, `postgres` DB에 만들어졌을 수 있습니다.
> 아래 쿼리로 `portfolio_db`에 테이블이 있는지 확인하세요.
>
> ```sql
> SELECT table_name FROM information_schema.tables WHERE table_schema = 'portfolio';
> ```
>
> 5개가 안 나오면 3단계를 다시 하세요. psql로 DDL을 실행하려면 아래처럼 하면 됩니다.
>
> ```
> cd <프로젝트 폴더>
> "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d portfolio_db -f sql/01_create_tables.sql
> ```

1. **명령 프롬프트**를 엽니다 (DBeaver가 아닙니다)

1-1. **한글 인코딩을 먼저 설정합니다.** 아래 두 줄을 입력하세요.

```
chcp 65001
set PGCLIENTENCODING=UTF8
```

**이걸 건너뛰면 이 오류가 납니다.**

```
오류: 0xed 0x85 바이트로 조합된 문자(인코딩: "UHC")와
      대응되는 문자 코드가 "UTF8" 인코딩에는 없습니다
```

SQL 파일은 UTF-8로 저장되어 있는데, 윈도우 명령 프롬프트는 기본적으로 **UHC(CP949)** 로 읽습니다. 파일 안의 한글 주석과 컬럼명(`테이블`, `적재건수`)에서 충돌합니다.

| 명령 | 역할 |
|---|---|
| `chcp 65001` | 명령 프롬프트를 UTF-8 모드로 전환 |
| `set PGCLIENTENCODING=UTF8` | psql이 파일을 UTF-8로 읽도록 지정 |

이 설정은 **현재 창에서만 유효**합니다. 창을 닫으면 다시 입력해야 합니다.

> 4단계에서 엑셀이 CSV를 CP949로 저장해 스크립트가 멈춘 일이 있었습니다.
> 같은 뿌리의 문제입니다. **한국 윈도우 환경에서 UTF-8과 CP949 충돌은 계속 나타납니다.**
2. `02_load_data.sql`을 메모장이나 VSCode로 열어 **파일 경로가 맞는지 확인**합니다

```
'03_cleaned/product_catalog_cleaned.csv'
```

**상대경로입니다.** `\copy` 는 psql 을 실행한 위치를 기준으로 파일을 찾으므로, 반드시 프로젝트 최상단 폴더에서 실행해야 합니다.

경로 구분자는 슬래시(`/`)입니다. 역슬래시(`\`)를 쓰면 오류가 납니다.

3. **먼저 `psql.exe`의 실제 경로를 확인합니다.**

설치된 PostgreSQL 버전에 따라 폴더 이름이 다릅니다(`16`, `17`, `18` 등). 확인하지 않고 실행하면 아래 오류가 납니다.

```
지정된 경로를 찾을 수 없습니다.
```

명령 프롬프트에 아래를 입력하세요.

```
dir "C:\Program Files\PostgreSQL"
```

설치된 버전 폴더가 보입니다.

```
    <DIR>          16
```

이 경우 버전은 `16`이므로 실제 경로는 이렇게 됩니다.

```
C:\Program Files\PostgreSQL\16\bin\psql.exe
```

**`Program Files` 아래에 아무것도 없다면** 다른 위치에 설치된 것입니다. 아래 명령으로 전체 검색하세요. (시간이 조금 걸립니다)

```
where /r C:\ psql.exe
```

또는 **시작 메뉴에서 `SQL Shell (psql)`을 검색 → 우클릭 → 파일 위치 열기**를 하면 해당 폴더가 바로 열립니다. 주소창의 경로를 복사해 쓰면 됩니다.

4. 확인한 경로로 명령을 실행합니다. **아래 두 곳을 본인 값으로 바꾸세요.**

```
cd <프로젝트 폴더>
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d portfolio_db -f sql/02_load_data.sql
```

| 바꿀 부분 | 내용 |
|---|---|
| `<프로젝트 폴더>` | `project_1` 폴더의 실제 위치 |
| `16` | 3번에서 확인한 버전 번호 |

**두 가지가 중요합니다.**

**① 반드시 `cd` 로 프로젝트 폴더에 먼저 이동합니다.** SQL 파일 안의 CSV 경로가 상대경로(`03_cleaned/...`)여서, 실행 위치가 다르면 파일을 찾지 못합니다.

```
could not open file "03_cleaned/product_catalog_cleaned.csv" for reading
```

**② psql.exe 경로의 따옴표를 빼면 안 됩니다.** `Program Files`에 공백이 있어서, 따옴표가 없으면 명령이 중간에서 끊깁니다.

비밀번호를 물으면 입력합니다. 정상이면 이렇게 나옵니다.

```
COPY 500
COPY 48200
COPY 51854
COPY 300000
COPY 30000
```

### 방법 B. DBeaver 임포트 마법사

psql이 번거로우면 DBeaver GUI로도 됩니다. 다만 **30만 행에서 수 분 이상 걸립니다.**

1. Navigator에서 `portfolio_db → Schemas → portfolio → Tables` 펼치기
2. `product_catalog` **우클릭 → 데이터 가져오기**
3. **CSV** 선택 → 다음
4. `product_catalog_cleaned.csv` 파일 선택
5. 설정에서 **Encoding을 `UTF-8`로 확인** (기본값이 다를 수 있음)
6. 컬럼 매핑 화면에서 CSV 컬럼과 테이블 컬럼이 **이름으로 자동 연결**됐는지 확인
7. 진행 → 완료

**반드시 아래 순서로 5개를 각각 임포트하세요.**

```
1) product_catalog
2) crm_customers
3) crm_customer_devices
4) orders
5) support_tickets
```

순서를 어기면 `violates foreign key constraint` 오류가 납니다. 데이터가 잘못된 게 아니라 **참조 대상이 아직 없다는 뜻**입니다.

---

## 5. 적재 검증

새 SQL 편집기에서 `03_verify_load.sql`을 열고 쿼리를 하나씩 실행합니다(`Ctrl + Enter`).

### 실제 검증 결과

**① 행 수 대조**

| 테이블 | 실제 | 기대 |
|---|---|---|
| product_catalog | 500 | 500 |
| crm_customers | 48,200 | 48,200 |
| crm_customer_devices | 51,854 | 51,854 |
| orders | 300,000 | 300,000 |
| support_tickets | 30,000 | 30,000 |

**② 참조 정합성 — 고아 레코드 전부 0건**

```
주문 → 고객   0
주문 → 상품   0
티켓 → 고객   0
기기 → 고객   0
```

**③ 파생 컬럼 재검산**

```
device_count 불일치        0건
세 컬럼 관계식 불일치       0건
```

`device_count`는 파이썬에서 계산한 값입니다. DB에서 기기 테이블을 실제로 세어 대조했습니다.
티켓의 `해결일시 − 접수일시 = 처리시간` 관계식도 30,000건 전부 성립합니다.

**④ NULL 건수 대조**

| 컬럼 | NULL | 기대 |
|---|---|---|
| orders.order_date | 90,000 | 90,000 |
| orders.order_amount | 51,525 | 51,525 |
| orders.quantity | 44,867 | 44,867 |
| tickets.ticket_created | 2,687 | 2,687 |
| products.price | 71 | 71 |

정제 단계에서 의도적으로 비운 건수와 DB의 NULL 건수가 정확히 일치합니다.
**이 대조가 중요한 이유** — CSV의 빈 칸이 NULL이 아니라 빈 문자열로 들어가는 사고가 흔합니다. 그러면 `WHERE order_date IS NULL`이 0건을 반환해서 분석이 틀어집니다.

**⑤ 자료형 변환 확인**

```
주문일 : 2023-12-03 ~ 2025-12-01
금액   : 100.01 ~ 999,969.87  (평균 52,428.51)
처리시간: 1.0 ~ 240.0 시간
```

CSV는 전부 문자열입니다. 날짜와 숫자로 제대로 변환됐는지 확인하는 절차입니다. 문자열로 들어갔다면 최소·최대가 사전순으로 나와 이상하게 보입니다.

**⑥ 5개 테이블 전체 조인**

```sql
SELECT c.first_name || ' ' || c.last_name AS 고객명,
       COUNT(DISTINCT o.order_id)  AS 주문수,
       SUM(o.order_amount)         AS 총구매액,
       COUNT(DISTINCT t.ticket_id) AS 문의수
  FROM crm_customers c
  LEFT JOIN orders o          ON c.customer_id = o.customer_id
  LEFT JOIN support_tickets t ON c.customer_id = t.customer_id
 GROUP BY c.customer_id, c.first_name, c.last_name
 ORDER BY 총구매액 DESC;
```

결과 예시

| 고객명 | 주문수 | 총구매액 | 문의수 |
|---|---|---|---|
| John G*** | 22 | 9,233,230.38 | 6 |
| Richard B*** | 7 | 8,437,841.00 | 5 |
| Stacy J*** | 12 | 8,188,049.25 | 3 |

**이 쿼리가 결과를 내면 관계형 구조가 완성된 것**이고, 7단계 분석의 출발점이 됩니다.

---

## 6. 자주 나는 오류와 원인

| 오류 메시지 | 원인 | 해결 |
|---|---|---|
| `violates foreign key constraint` | 적재 순서를 어김 | product_catalog → crm_customers 순으로 다시 |
| `violates check constraint "ck_..."` | 규칙을 위반한 값이 있음 | 4단계 정제 스크립트를 다시 실행 |
| `invalid input syntax for type uuid` | UUID 형식이 아닌 값 | 정제본이 최신인지 확인 |
| `invalid byte sequence for encoding "UTF8"` | 파일이 CP949로 저장됨 | **엑셀로 CSV를 저장한 흔적.** 4단계 스크립트 재실행 |
| `"orders" 이름의 릴레이션이 없습니다` | **테이블 미생성** 또는 스키마 경로 미설정 | 3단계 DDL을 `portfolio_db`에서 실행했는지 확인 |
| `0xed 0x85 ... "UHC" ... "UTF8"` | 명령 프롬프트 인코딩 충돌 | `chcp 65001` + `set PGCLIENTENCODING=UTF8` 후 재실행 |
| `could not open file ... for reading` | **프로젝트 폴더에서 실행하지 않음** | `cd`로 `project_1` 이동 후 재실행 |
| `지정된 경로를 찾을 수 없습니다` | **`psql.exe` 경로가 틀림** (버전 폴더명 불일치) | `dir "C:\Program Files\PostgreSQL"` 로 버전 확인 후 경로 수정 |
| `'psql'은(는) 내부 또는 외부 명령... 아닙니다` | 전체 경로 없이 `psql` 만 입력 | 큰따옴표로 감싼 전체 경로 사용 |
| `psql: error: FATAL: password authentication failed` | 비밀번호 오류 | 설치 시 정한 `postgres` 비밀번호 확인 |

**`check constraint` 위반이 나면 오히려 좋은 신호입니다.** DB가 잘못된 데이터를 막아준 것이고, 정제에 빠진 부분을 알려주는 것입니다. 제약조건을 걸어두는 이유가 여기 있습니다.

---

## 7. 이 단계에서 확인된 것

정제 결과가 **파이썬과 무관한 두 번째 검증**을 통과했습니다.

| 검증 주체 | 방식 | 결과 |
|---|---|---|
| 파이썬 (5단계) | 규칙별 검사 함수 | 각 파일 31~34개 항목 전체 합격 |
| **PostgreSQL (6단계)** | **제약조건 52개** | **전량 적재 성공** |

제약조건을 다 걸어둔 상태에서 430,554행이 하나도 거부되지 않았습니다. 정제 규칙과 DB 스키마가 서로 모순되지 않는다는 뜻입니다.

포트폴리오에서는 이렇게 서술할 수 있습니다.

> 정제 규칙을 DB 제약조건(PK 5, FK 4, CHECK 44)으로 재선언하고,
> 제약이 활성화된 상태에서 43만 행을 무결점 적재하여 정제 품질을 교차 검증함.

---

## 8. 참고 — 한 가지 남은 흔적

검증 쿼리 결과에 `Mmeellissa M***`라는 고객명이 보입니다.

CRM 정제에서 글자 중복 오타를 이메일과 대조해 복원했는데, 이 고객은 **이메일이 다른 사람 것**이어서 검증에 실패했습니다. 규칙에 따라 `name_flag = '이메일불일치_보류'`를 붙이고 원본을 유지했습니다.

추측으로 고쳤다면 잘못된 이름을 만들 수 있었습니다. **고치지 못한 것을 표시해두면, 나중에 이렇게 눈에 띌 때 원인을 바로 설명할 수 있습니다.**

```sql
-- 확인이 필요한 고객 목록 조회
SELECT customer_id, first_name, last_name, email, name_flag
  FROM crm_customers
 WHERE name_flag IS NOT NULL
 LIMIT 20;
```