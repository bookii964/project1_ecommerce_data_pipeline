# 작업 기록 — clickstream 테이블 적재 (시도 → 실패 → 수정 → 성공)

> **이 문서의 역할**
> 최종 결과만 남기면 "왜 이런 규칙이 생겼는지"를 알 수 없다.
> 실패한 시도와 그때 나온 오류, 진단 방법, 수정 내용을 순서대로 기록한다.
>
> 포트폴리오에서 이 문서는 **문제 해결 과정**을 보여주는 자료가 된다.
> 정제 스크립트는 결과물이고, 이 기록은 그 결과에 도달한 경로다.
>
> 작업 환경 : PostgreSQL 16 / 대상 테이블 `portfolio.clickstream` / 50만 행

---

## 요약 — 무엇을 몇 번 시도했는가

| 회차 | 실행한 것 | 결과 | 원인 |
|---|---|---|---|
| 1차 | DDL 생성 + `\copy` 적재 | **실패** (0행) | `device_id` 뒤쪽 공백 9,915건 |
| 2차 | 공백 제거 후 재적재 | **실패** (0행) | `device_id` 형식 오염 10,016건 |
| 3차 | 형식 정제 후 재적재 | **성공** (500,000행) | — |
| 검증 | 검증 쿼리 10종 실행 | 1건 오탐 | 검증 쿼리 조건이 과도하게 엄격 |
| 최종 | 쿼리 수정 + URL 정규화 후 재적재 | **전체 통과** | — |

**적재가 두 번 실패한 것이 이 작업의 핵심 성과다.** 실패 덕분에 4단계 정제에서 빠진 처리 두 가지를 발견했다.

---

## 1차 시도 — DDL 생성 및 적재

### 실행한 것

```
psql -d portfolio_db -f 04_create_load_clickstream.sql
```

이 파일은 세 가지를 순서대로 수행한다.

1. `CREATE TABLE clickstream` — 컬럼 12개, 제약조건 7개, 인덱스 4개
2. `COMMENT ON COLUMN` — 컬럼별 주석
3. `\copy clickstream FROM '...clickstream_cleaned.csv'` — 적재

### 나온 결과

```
CREATE TABLE
COMMENT
...
CREATE INDEX
ERROR:  invalid input syntax for type uuid: "8ef2607c-31a4-43d9-86df-3553522de9b4 "
CONTEXT:  COPY clickstream, line 26, column device_id: "8ef2607c-31a4-43d9-86df-3553522de9b4 "

 적재건수 | 기대건수
----------+----------
        0 |   500000
```

**테이블은 만들어졌지만 데이터는 0행이다.**

### 오류 읽기

`invalid input syntax for type uuid` 는 "이 값을 UUID로 바꿀 수 없다"는 뜻이다.
`CONTEXT` 줄이 결정적이다. **26번째 줄, device_id 컬럼**이라고 위치를 알려준다.

값을 보면 `...de9b4 ` — **끝에 공백이 하나 붙어 있다.** 따옴표 안쪽 마지막 문자를 봐야 보인다.

PostgreSQL의 UUID 타입은 공백이 붙은 값을 거부한다. 문자열(TEXT)로 선언했다면 그냥 들어갔겠지만, 그러면 형식 오염을 발견하지 못한 채 넘어갔을 것이다.

### 진단 — 전수 조사

한 건만 고치면 다음 행에서 또 걸린다. 전체 규모를 먼저 파악한다.

```python
for c in ['event_id','session_id','customer_id','device_id','ingest_run_id']:
    s = df[c].dropna()
    print(c, (s != s.str.strip()).sum())
```

```
event_id         앞뒤공백       0건
session_id       앞뒤공백       0건
customer_id      앞뒤공백       0건
device_id        앞뒤공백   9,915건     ← 여기
ingest_run_id    앞뒤공백       0건
```

**`device_id` 만 9,915건에 공백이 있었다.**

### 왜 놓쳤는가

1단계 프로파일링에서 `device_id`를 **"분석에 쓸 수 없는 컬럼"으로 판정**했다.
근거는 CRM 기기 목록과 일치 0건, 고유율 99.8%였다.

그 판정 이후 **이 컬럼의 형식 검사를 생략했다.** 3단계 색출 스크립트에도 `device_id` 검사가 없었다.

> **교훈** : '분석에 쓰지 않는 컬럼'과 '검사하지 않아도 되는 컬럼'은 다르다.
> 분석에 쓰지 않아도 **적재 대상이면 자료형 변환은 통과해야 한다.**

### 수정

`21_clean_clickstream.py` 에 식별자 공백 제거를 추가했다.

```python
ID_COLUMNS = ["event_id", "session_id", "customer_id", "device_id", "ingest_run_id"]
for col in ID_COLUMNS:
    df[col] = df[col].str.strip()
```

`3단계 색출 스크립트(20_detect)` 에도 같은 검사를 추가했다. **정제만 고치면 다음에 또 놓친다. 검출 단계에서 잡히도록 해야 한다.**

---

## 2차 시도 — 공백 제거 후 재적재

### 실행한 것

```
python 21_clean_clickstream.py     # 정제본 재생성
psql -d portfolio_db -f 04_create_load_clickstream.sql
```

정제 스크립트 출력에 처리 건수가 찍혔다.

```
  1. 원본 값 보존 컬럼 생성        timestamp_raw
     device_id 앞뒤공백 제거 : 9,915건
  1-2. 식별자 공백 정리 완료
```

### 나온 결과

```
ERROR:  invalid input syntax for type uuid: "invalid-device-6314"
CONTEXT:  COPY clickstream, line 370, column device_id: "invalid-device-6314"

 적재건수 | 기대건수
----------+----------
        0 |   500000
```

**또 실패했다.** 같은 컬럼이지만 이번엔 다른 종류의 값이다.

`invalid-device-6314` 는 공백 문제가 아니다. **UUID 형식 자체가 아니다.**

### 진단 — 형식 위반 전수 조사

이번엔 공백만 보지 않고 UUID 패턴 자체를 검사했다.

```python
U = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-...$')
for c in ID_COLUMNS:
    bad = s[~s.str.match(U)]
    print(c, len(bad), list(bad.unique()[:3]))
```

```
event_id         형식위반       0건
session_id       형식위반       0건
customer_id      형식위반       0건
device_id        형식위반  10,016건  샘플 ['17213ae6f43f48e48b3dbf2719109f2d', ...]
ingest_run_id    형식위반       0건
```

샘플에 두 종류가 보였다. `invalid-device-NNNN` 과 **하이픈이 없는 32자리 16진수**다.
두 번째는 UUID를 하이픈 없이 적은 것으로 보인다. 나눠서 세어봤다.

```python
NODASH = re.compile(r'^[0-9a-fA-F]{32}$')
nodash = bad.str.match(NODASH)
```

```
device_id 형식위반 10,016
  ├ 하이픈 없는 32자리 16진수 : 5,030
  └ 그 외                    : 4,986   ['invalid-device-6314', ...]
```

### 판단 — 두 종류를 다르게 처리한다

| 유형 | 건수 | 성격 | 처리 |
|---|---|---|---|
| 하이픈 없는 32자리 | 5,030 | UUID를 다르게 적은 것. **값이 같다** | 하이픈 복원 (표준화) |
| `invalid-device-NNNN` | 4,986 | 식별자가 아니다 | **NULL 처리** |

하이픈 복원은 값을 바꾸는 게 아니라 표기를 되돌리는 것이다.

```
17213ae6f43f48e48b3dbf2719109f2d
→ 17213ae6-f43f-48e4-8b3d-bf2719109f2d
```

### 복원 후 재확인 — 2단계 판정이 여전히 맞는가

하이픈이 없어서 CRM과 매칭되지 않았을 가능성을 확인해야 했다.
2단계에서 "CRM 기기와 일치 0건"이라고 판정했는데, 그게 단순히 형식 차이 때문이었다면 판정을 뒤집어야 한다.

```python
fix = bad[nodash].str.replace(...)   # 하이픈 복원
print(fix.isin(dev['device_id']).sum())
```

```
하이픈 복원 후 CRM 기기와 일치: 0
```

**여전히 0건이다.** 2단계 판정('다른 체계의 식별자')은 유효하다.

이 확인을 건너뛰었다면 "형식 때문에 못 맞춘 것"과 "실제로 다른 값"을 구분하지 못한 채 넘어갔을 것이다.

### 수정

```python
# ② 하이픈 복원
no_dash = dev.str.match(NO_DASH_PATTERN)
restored = dev.str.replace(r"^(.{8})(.{4})(.{4})(.{4})(.{12})$",
                           r"\1-\2-\3-\4-\5", regex=True)
df.loc[no_dash, "device_id"] = restored[no_dash]
df.loc[no_dash, "device_flag"] = "하이픈복원"

# ③ 복원 불가 → NULL
still_bad = ~df["device_id"].str.match(UUID_PATTERN)
df.loc[still_bad, "device_flag"] = "형식오류(복원불가)"
df.loc[still_bad, "device_id"] = None
```

DDL도 함께 고쳤다. `device_id`가 NULL을 가질 수 있게 되었으므로 `NOT NULL`을 제거하고, `device_flag` 컬럼을 추가했다.

```sql
device_id      UUID,          -- 복원 불가 4,986건은 NULL
device_flag    TEXT,
```

---

## 3차 시도 — 형식 정제 후 재적재

### 실행한 것

```
python 21_clean_clickstream.py
psql -d portfolio_db -f 04_create_load_clickstream.sql
```

```
  1-2. 식별자 공백 정리 완료
     하이픈 복원 : 5,030건 / 복원불가 NULL : 4,986건
  1-3. device_id 형식 정제 완료
  2. 타임스탬프 정제              유효 439,910건 / NULL 60,090건
  3. product_id 추출             356,366건 (500종)
  4. is_logged_in 파생           로그인 349,447건 / 비로그인 150,553건
```

### 나온 결과

```
CREATE TABLE
CREATE INDEX
COPY 500000
ANALYZE

 적재건수 | 기대건수
----------+----------
   500000 |   500000
```

**성공.** 제약조건 7개가 모두 활성화된 상태에서 50만 행이 하나도 거부되지 않았다.

특히 이 제약이 통과한 것이 의미가 있다.

```sql
CONSTRAINT ck_clickstream_login_flag CHECK (
    is_logged_in = (customer_id IS NOT NULL))
```

`is_logged_in` 은 파이썬에서 계산한 파생 컬럼이다. **DB가 그 계산을 다시 검산해서 통과시킨 것**이다.

---

## 검증 — 쿼리 10종 실행

```
psql -d portfolio_db -f 05_verify_clickstream.sql
```

### 통과한 항목

```
         테이블         | 실제건수 | 기대건수
------------------------+----------+----------
 1_product_catalog      |      500 |      500
 2_crm_customers        |    48200 |    48200
 3_crm_customer_devices |    51854 |    51854
 4_orders               |   300000 |   300000
 5_support_tickets      |    30000 |    30000
 6_clickstream          |   500000 |   500000
```

```
    컬럼     | null건수 | 기대값
-------------+----------+--------
 customer_id |   150553 | 150553
 device_id   |     4986 |   4986
 event_time  |    60090 |  60090
 page_url    |     8305 |   8305
 product_id  |   143634 | 143634
```

```
    관계     | 고아건수
-------------+----------
 클릭 → 상품 |        0
 클릭 → 고객 |        0

 is_logged_in_불일치건수 : 0
```

### 걸린 항목 하나

```
 product_id_추출오류건수
-------------------------
                    6163
```

`product_id`가 `page_url`에서 제대로 추출됐는지 검산하는 쿼리였다.

### 진단 — 실제 값을 본다

건수만 보고 판단하지 않고 실제 행을 뽑았다.

```sql
SELECT page_url, product_id
  FROM clickstream
 WHERE product_id IS NOT NULL
   AND page_url NOT LIKE '%/product/' || product_id
 LIMIT 5;
```

```
                   page_url                    | product_id
-----------------------------------------------+------------
 https://shop.example.com/product/PROD-0187/// | PROD-0187
 https://shop.example.com/product/PROD-0161/// | PROD-0161
 https://shop.example.com/product/PROD-0335/// | PROD-0335
```

**추출은 정확했다.** URL 끝에 슬래시가 3개 붙어 있어서, 내 쿼리 조건이 값을 잘못 판정한 것이다.

내가 쓴 조건은 이랬다.

```sql
page_url NOT LIKE '%/product/' || product_id
```

이 조건은 **product_id가 URL의 맨 끝에 있어야 한다**는 뜻이다. 뒤에 슬래시가 붙으면 불일치로 잡힌다.

> **교훈** : 검증에서 오류가 나오면 데이터를 의심하기 전에 검증 조건을 먼저 확인한다.
> 이번 6,163건은 데이터 오류가 아니라 **검증 코드의 오류**였다.

### 부수 발견 — URL 표기 오염

검증 오탐을 조사하다 URL 표기 문제를 발견했다.

```sql
SELECT COUNT(DISTINCT page_url) AS 현재,
       COUNT(DISTINCT regexp_replace(page_url,'/+$','')) AS 정규화후
  FROM clickstream WHERE page_url IS NOT NULL;
```

```
 현재url종류 | 정규화후
-------------+----------
        3020 |     2516
```

**같은 페이지가 슬래시 개수 때문에 다른 URL로 집계되고 있었다.** 504종이 중복이다.

URL별 인기 페이지를 집계하면 같은 상품이 여러 줄로 쪼개져 나온다. 검증 오탐이 없었다면 발견하지 못했을 문제다.

### 수정 두 가지

**① 검증 쿼리 조건 완화**

```sql
AND page_url NOT LIKE '%/product/' || product_id || '%'
```

**② 정제 스크립트에 URL 정규화 추가**

```python
df["page_url"] = url_before.str.replace(r"/{2,}$", "/", regex=True)
```

슬래시가 **2개 이상일 때만** 하나로 줄인다. 홈 페이지는 `https://shop.example.com/` 이고 끝 슬래시 1개가 정상이므로, 무조건 제거하면 원본과 달라진다.

---

## 최종 재실행 — 전체 통과

```
python 21_clean_clickstream.py
```

```
  2-2. page_url 슬래시 정리       8,231건
```

```
psql -d portfolio_db -f 04_create_load_clickstream.sql
psql -d portfolio_db -f 05_verify_clickstream.sql
```

```
 적재건수 : 500000
 product_id_추출오류건수 : 0
```

### 최종 검증 결과

| 검증 항목 | 결과 |
|---|---|
| 6개 테이블 행 수 | 전부 일치 (총 930,554행) |
| NULL 건수 5개 컬럼 | 전부 일치 |
| 고아 레코드 (2개 관계) | 0건 |
| `is_logged_in` 정합성 | 0건 불일치 |
| `product_id` 추출 정확도 | 0건 오류 |
| 수집 구간 | 2025-09-02 ~ 2025-12-02 (92일, 일평균 4,782건) |

### 행동 유형별 대응 확인

```
  행동유형   |  전체  | 상품있음 | 로그인상태 | 시각유효
-------------+--------+----------+------------+----------
 page_view   | 300414 |   285273 |     210006 |   264442
 search      |  74946 |        0 |      52300 |    65954
 add_to_cart |  74827 |    71093 |      52402 |    65708
 login       |  49813 |        0 |      34739 |    43806
```

`search`와 `login`에 상품이 0건인 것이 정상이다. 로그인 화면과 검색 결과 페이지에 특정 상품 코드가 있을 이유가 없다.

### 상품 기준 6개 테이블 연결

```
 product_id |  카테고리  | 조회수 | 장바구니 | 주문수
------------+------------+--------+----------+--------
 PROD-0397  | kitchen    |    636 |      130 |    439
 PROD-0030  | kitchen    |    633 |      123 |    440
 PROD-0295  | automotive |    626 |      161 |    455
```

클릭스트림 + 주문 + 카탈로그가 상품 기준으로 연결된다. 7단계 분석의 출발점이다.

---

## 이 작업에서 얻은 것

### 수정한 파일

| 파일 | 수정 내용 |
|---|---|
| `20_detect_clickstream.py` | 식별자 공백 검사, `device_id` 형식 검사, URL 슬래시 검사 추가 |
| `21_clean_clickstream.py` | 식별자 공백 제거, `device_id` 형식 정제, URL 정규화 추가 |
| `04_create_load_clickstream.sql` | `device_id` NOT NULL 제거, `device_flag` 컬럼 추가 |
| `05_verify_clickstream.sql` | `product_id` 검증 조건 완화 |

### 원칙 3가지

**① '분석에 쓰지 않는 컬럼'과 '검사하지 않아도 되는 컬럼'은 다르다**
`device_id`를 사용 금지로 판정한 뒤 형식 검사를 생략했더니 적재가 두 번 실패했다.
적재 대상인 모든 컬럼은 최소한 형식 검사를 거쳐야 한다.

**② 검증에서 오류가 나오면 검증 조건을 먼저 의심한다**
6,163건 오탐은 데이터 문제가 아니라 내 쿼리 조건 문제였다.
건수만 보고 데이터를 고치기 시작했다면 정확한 값을 훼손했을 것이다.

**③ 정제만 고치지 않고 검출도 고친다**
정제 스크립트만 수정하면 다음 파일에서 같은 오염을 또 놓친다.
`20_detect`에 검사를 추가해서, 앞으로는 3단계에서 잡히도록 했다.

### 왜 자료형을 UUID로 선언한 것이 옳았는가

`device_id`를 TEXT로 선언했다면 공백과 `invalid-device-6314`가 그대로 들어갔을 것이다.
적재는 성공했겠지만 오염은 발견되지 않았다.

**엄격한 자료형과 제약조건은 적재를 어렵게 만드는 대신, 오염을 찾아준다.**
적재 실패는 비용이 아니라 정보다.
