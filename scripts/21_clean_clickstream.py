# =============================================================================
# 파일명 : 21_clean_clickstream.py
# 단계   : 4단계 - 정제 규칙 적용 및 정제 파일 생성 (clickstream)
#
# [목적]
#   2단계 규칙서(데이터사전_clickstream.md)대로 값을 정리하고 새 파일로 저장한다.
#
# [이 파일에서 하는 일 4가지]
#   ① 타임스탬프 표기 3종을 하나로 통일한다
#   ② 신뢰할 수 없는 타임스탬프를 NULL 처리한다 (상수·범위이탈·결측)
#   ③ page_url 에서 product_id 를 추출한다  ← 원본에 없던 관계를 만든다
#   ④ is_logged_in 파생 컬럼을 만든다
#
# [고치지 않는 것]
#   session_id / device_id / ingest_run_id 는 값을 건드리지 않는다.
#   형식은 정상이고 값도 틀리지 않았다. '의미가 없어서 못 쓰는' 컬럼이므로
#   고칠 대상이 아니라 사용하지 않을 대상이다.
#   → 컬럼은 원본 그대로 남기고, DB 주석과 문서에 '사용 금지'를 기록한다.
#     지우지 않는 이유는, 향후 다른 배치가 추가되면 의미를 가질 수 있기 때문이다.
#
# [입력]  01_raw/clickstream_500k_events.csv
# [출력]  03_cleaned/clickstream_cleaned.csv
#         04_reports/정제로그_clickstream.txt
# =============================================================================

import os
import re
import pandas as pd


def read_csv_safe(path, **kwargs):
    for encoding in ["utf-8-sig", "cp949", "utf-8"]:
        try:
            df = pd.read_csv(path, encoding=encoding, **kwargs)
            if encoding != "utf-8-sig":
                print(f"  [주의] {os.path.basename(path)} 은 {encoding} 인코딩입니다.")
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩 판별 실패: {path}")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

INPUT_FILE = os.path.join(PROJECT_DIR, "01_raw", "clickstream_500k_events.csv")
CLEAN_DIR = os.path.join(PROJECT_DIR, "03_cleaned")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 2단계에서 확정한 규칙 상수
# -----------------------------------------------------------------------------
# 타임스탬프 표기 3종 — 전부 유효하며 표기만 다르다
TS_T_TZ     = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00$"
TS_SPACE_TZ = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+00:00$"
TS_PLAIN    = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+00:00)?$"

# 유효 기간 상한 (규칙서 3-3의 근거 참고)
#   두 표기가 정확히 이 날짜까지만 존재하고, 이후 구간은 일평균이 200배 낮다
VALID_UNTIL = pd.Timestamp("2025-12-02 23:59:59")

CONSTANT_TS = "2024/31/01 25:61:00"
PRODUCT_URL = re.compile(r"/product/(PROD-\d{4})")

# 출력 타임스탬프 형식 (PostgreSQL의 TIMESTAMP 타입이 그대로 인식한다)
DT_FORMAT = "%Y-%m-%d %H:%M:%S"


raw = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(raw):,}행")
print()
print("[처리 진행]")

df = raw.copy()


# =============================================================================
# ① 원본 값 보존
#    타임스탬프는 6만 건을 NULL 처리하므로 원본을 남겨야 추적이 된다.
# =============================================================================
df["timestamp_raw"] = raw["timestamp"]
df["page_url_raw"] = raw["page_url"]
print("  1. 원본 값 보존 컬럼 생성        timestamp_raw, page_url_raw")


# =============================================================================
# ①-2 식별자 컬럼의 앞뒤 공백 제거
#
#   [이 처리를 빠뜨려서 실제로 적재에 실패했다 — 기록용]
#     device_id 9,915건에 뒤쪽 공백이 붙어 있었다.
#     '8ef2607c-31a4-43d9-86df-3553522de9b4 '  ← 끝에 공백
#
#   왜 놓쳤는가:
#     device_id 를 '분석에 쓸 수 없는 컬럼'으로 판정한 뒤,
#     형식 검사를 소홀히 했다.
#
#   왜 문제가 되는가:
#     분석에 쓰지 않아도 DB 적재 시 자료형 변환은 통과해야 한다.
#     PostgreSQL의 UUID 타입은 뒤에 공백이 붙은 값을 거부한다.
#       ERROR: invalid input syntax for type uuid: "...9b4 "
#
#   교훈:
#     '분석에 쓰지 않는 컬럼'과 '검사하지 않아도 되는 컬럼'은 다르다.
#     적재 대상인 모든 컬럼은 최소한 형식 검사를 거쳐야 한다.
# =============================================================================
ID_COLUMNS = ["event_id", "session_id", "customer_id", "device_id", "ingest_run_id"]
for col in ID_COLUMNS:
    before = int((df[col].fillna("") != df[col].fillna("").str.strip()).sum())
    df[col] = df[col].str.strip()
    if before:
        print(f"     {col} 앞뒤공백 제거 : {before:,}건")

print("  1-2. 식별자 공백 정리 완료")


# =============================================================================
# ①-3 device_id 형식 정제
#
#   [이 처리도 초안에서 빠져 있었다 — 적재 실패로 발견]
#   device_id 를 '분석 사용 금지'로 판정한 뒤 형식 검사를 생략했더니,
#   PostgreSQL 적재에서 두 번 연속 실패했다.
#
#   실제 오염은 3종류였다:
#     ① 앞뒤 공백                     9,915건 → 위에서 제거
#     ② 하이픈 없는 32자리 16진수      5,030건 → 하이픈 복원 (표준화)
#          '17213ae6f43f48e48b3dbf2719109f2d'
#        →  '17213ae6-f43f-48e4-8b3d-bf2719109f2d'
#     ③ 'invalid-device-6314' 형태     4,986건 → 복원 불가, NULL 처리
#
#   ②는 UUID 를 하이픈 없이 적은 것이므로 값이 같다. 표기만 복원한다.
#   ③은 값 자체가 식별자가 아니므로 되살릴 근거가 없다.
#
#   ※ 하이픈을 복원해도 CRM 기기 목록과는 여전히 0건 일치한다.
#     2단계 판정('다른 체계의 식별자')은 그대로 유효하다.
# =============================================================================
UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
NO_DASH_PATTERN = r"^[0-9a-fA-F]{32}$"

dev = df["device_id"].fillna("")
df["device_flag"] = None

# ② 하이픈 복원 : 32자리를 8-4-4-4-12 로 나눈다
no_dash = dev.str.match(NO_DASH_PATTERN)
restored = dev.str.replace(r"^(.{8})(.{4})(.{4})(.{4})(.{12})$",
                           r"\1-\2-\3-\4-\5", regex=True)
df.loc[no_dash, "device_id"] = restored[no_dash]
df.loc[no_dash, "device_flag"] = "하이픈복원"

# ③ 복원 불가 : UUID 형식도 아니고 32자리 16진수도 아닌 값
still_bad = ~df["device_id"].fillna("").str.match(UUID_PATTERN)
df.loc[still_bad, "device_flag"] = "형식오류(복원불가)"
df.loc[still_bad, "device_id"] = None

print(f"     하이픈 복원 : {int(no_dash.sum()):,}건 / "
      f"복원불가 NULL : {int(still_bad.sum()):,}건")
print("  1-3. device_id 형식 정제 완료")


# =============================================================================
# ② 타임스탬프 — 표기 통일 → 유효성 판정 → NULL 처리
#
#   [표기 3종을 통일해도 값이 변하지 않는 이유]
#     '2025-09-13 07:00:51.923083+00:00' (공백 구분)
#     '2025-09-13T07:00:51.923083+00:00' (T 구분)
#     두 값은 같은 시각을 다르게 적은 것이다.
#     시간대가 전부 +00:00(UTC)이므로 시간대를 떼도 시각이 바뀌지 않는다.
# =============================================================================
ts = df["timestamp"].fillna("")

is_t_tz = ts.str.match(TS_T_TZ)
is_space_tz = ts.str.match(TS_SPACE_TZ)
is_plain = ts.str.match(TS_PLAIN)
is_valid_format = is_t_tz | is_space_tz | is_plain

# format='mixed' : 세 표기가 섞여 있어도 알아서 읽는다
# utc=True → tz_localize(None) : 시간대를 떼고 UTC 기준 시각으로 만든다
parsed = pd.to_datetime(ts.where(is_valid_format),
                        format="mixed", utc=True, errors="coerce")
parsed = parsed.dt.tz_localize(None)

# 처리 사유 기록 (NULL 처리한 이유를 반드시 남긴다)
df["time_flag"] = None
df.loc[df["timestamp"].isna(), "time_flag"] = "원본결측"
df.loc[ts == CONSTANT_TS, "time_flag"] = "상수값"

out_of_range = parsed > VALID_UNTIL
df.loc[out_of_range, "time_flag"] = "범위이탈"

# 형식이 유효하지 않거나 파싱에 실패한 값 (예상: 0건)
unparsed = (ts != "") & (ts != CONSTANT_TS) & parsed.isna()
df.loc[unparsed, "time_flag"] = "형식오류"

# 범위를 벗어난 값은 비운다
parsed = parsed.where(~out_of_range)

# 문자열로 저장한다. PostgreSQL의 TIMESTAMP 타입이 이 형식을 그대로 인식한다.
df["event_time"] = parsed.dt.strftime(DT_FORMAT)

n_valid = int(df["event_time"].notna().sum())
print(f"  2. 타임스탬프 정제              유효 {n_valid:,}건 / "
      f"NULL {len(df)-n_valid:,}건")


# =============================================================================
# ②-2 page_url 표기 정규화
#
#   [처음에는 끝의 중복 슬래시만 정리했다가 문제를 발견했다 — 기록용]
#     초안 규칙 : 끝의 '///' 를 '/' 로 줄이기
#     결과      : URL 고유값이 3,020 → 3,019 로 거의 줄지 않았다.
#     원인      : '/product/PROD-0027/' 와 '/product/PROD-0027' 은
#                 여전히 다른 값이다. 끝 슬래시를 남긴 것이 문제였다.
#
#   전수 조사하니 URL 표기 오염이 5종류였다.
#     ① 끝 슬래시 중복   .../PROD-0187///
#     ② 스킴 슬래시 과다 http://///shop.example.com/...   8,298건
#     ③ 스킴 누락        shop.example.com/product/...     8,195건
#     ④ 전부 대문자      HTTPS://SHOP.EXAMPLE.COM/PRODUCT/PROD-0412  8,482건
#     ⑤ 경로 축약        /prod////PROD-0391               6,213건
#
#   ④⑤ 때문에 product_id 추출에서 12,576건을 놓치고 있었다.
#   정규식이 대소문자를 구분하고 '/product/' 만 찾았기 때문이다.
#
#   [정규화 규칙 — 정해진 형태로 통일한다]
#     https://shop.example.com + 경로
#     - 소문자 통일 (단 상품 코드 PROD-0000 은 대문자 유지)
#     - 스킴·호스트를 표준 형태로 재구성
#     - 경로의 중복 슬래시를 하나로
#     - /prod/ → /product/
#     - 끝 슬래시 제거 (홈은 '/' 유지)
# =============================================================================
CANONICAL_HOST = "https://shop.example.com"

def normalize_url(value):
    if value == "" or pd.isna(value):
        return None

    s = str(value).strip().lower()          # 소문자 통일

    s = re.sub(r"^https?:/*", "", s)        # 스킴 제거 (슬래시 개수 무관)
    s = re.sub(r"^shop\.example\.com", "", s)  # 호스트 제거 → 경로만 남김

    if not s.startswith("/"):
        s = "/" + s if s else "/"

    s = re.sub(r"/{2,}", "/", s)            # 경로의 중복 슬래시 정리
    s = re.sub(r"^/prod/", "/product/", s)  # 경로 축약 복원

    if len(s) > 1:
        s = s.rstrip("/")                   # 끝 슬래시 제거 (홈 '/' 는 유지)

    # 상품 코드는 대문자로 복원한다 (PROD-0412 형식이 표준)
    s = re.sub(r"(prod-)(\d{4})", lambda m: "PROD-" + m.group(2), s)

    return CANONICAL_HOST + (s if s else "/")

# 값 종류가 3,020개뿐이므로 고유값에만 함수를 적용한다.
# 50만 행에 직접 적용하는 것보다 훨씬 빠르다.
url_before = df["page_url"].fillna("")
url_map = {v: normalize_url(v) for v in url_before.unique()}
df["page_url"] = url_before.map(url_map)

n_url_fixed = int((url_before.replace("", None) != df["page_url"]).sum())
print(f"  2-2. page_url 정규화            {n_url_fixed:,}건 변경 / "
      f"고유값 {url_before[url_before!=''].nunique():,} → {df['page_url'].nunique():,}")


# =============================================================================
# ③ product_id 추출 — 원본에 없던 관계를 만든다
#
#   page_url 안의 상품 코드를 뽑아 별도 컬럼으로 만든다.
#     https://shop.example.com/product/PROD-0109  →  PROD-0109
#
#   추출된 500종이 전부 카탈로그에 존재함을 1·3단계에서 확인했다.
#   추출되지 않는 URL(검색·홈·결측)은 NULL 로 둔다.
# =============================================================================
#   정규화된 URL 에서 추출한다. 정규화 전에 추출하면
#   대문자 URL과 경로 축약형에서 12,576건을 놓친다.
df["product_id"] = df["page_url"].fillna("").str.extract(PRODUCT_URL)[0]

n_product = int(df["product_id"].notna().sum())
print(f"  3. product_id 추출             {n_product:,}건 "
      f"({df['product_id'].nunique():,}종)")


# =============================================================================
# ③-2 page_type 파생 — 페이지 유형 분류
#
#   URL을 정규화한 덕분에 페이지 유형을 안정적으로 분류할 수 있다.
#   정규화 전에는 같은 유형이 여러 표기로 흩어져 분류가 불가능했다.
#
#   퍼널 분석과 시각화에서 이 컬럼이 바로 쓰인다.
#   (URL 문자열을 매번 LIKE 로 자르지 않아도 된다)
# =============================================================================
def classify_page(url):
    if pd.isna(url):
        return None
    path = url.replace(CANONICAL_HOST, "")
    if path.startswith("/product/"):
        return "product_detail"
    if path.startswith("/search"):
        return "search"
    if path.startswith("/category/"):
        return "category"
    if path.startswith("/cart"):
        return "cart"
    if path in ("", "/"):
        return "home"
    return "other"

page_map = {v: classify_page(v) for v in df["page_url"].dropna().unique()}
df["page_type"] = df["page_url"].map(lambda v: page_map.get(v))

print(f"  3-2. page_type 분류            {df['page_type'].nunique()}종")


# =============================================================================
# ④ is_logged_in 파생 — 로그인 여부
#
#   customer_id 결측은 오염이 아니라 '비로그인 상태의 행동'이다.
#   SQL에서 매번 IS NULL 을 쓰는 대신 참/거짓 컬럼을 만들어 두면
#   집계 쿼리가 짧아지고 의도가 분명해진다.
#     비교) WHERE customer_id IS NOT NULL
#           WHERE is_logged_in = true      ← 의도가 드러난다
# =============================================================================
df["is_logged_in"] = df["customer_id"].notna()

n_login = int(df["is_logged_in"].sum())
print(f"  4. is_logged_in 파생           로그인 {n_login:,}건 / "
      f"비로그인 {len(df)-n_login:,}건")


# =============================================================================
# [저장]
#   timestamp 컬럼을 event_time 으로 대체한다.
#   'timestamp' 는 PostgreSQL의 자료형 이름이라 컬럼명으로 쓰면 혼동이 생긴다.
# =============================================================================
OUTPUT_COLS = [
    # --- 키 ---
    "event_id",
    # --- 분석용 ---
    "customer_id", "is_logged_in", "event_type",
    "page_url", "page_type", "product_id", "event_time",
    # --- 원본 유지 (분석 사용 금지 — 문서와 DB 주석에 명시) ---
    "session_id", "device_id", "ingest_run_id",
    # --- 원본 보존 및 처리 사유 ---
    "timestamp_raw", "page_url_raw", "time_flag", "device_flag",
]
df = df[OUTPUT_COLS]

output_path = os.path.join(CLEAN_DIR, "clickstream_cleaned.csv")
df.to_csv(output_path, index=False, encoding="utf-8-sig")

print()
print(f"정제 파일 저장 : {output_path}")


# =============================================================================
# [정제 로그]
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("clickstream_500k_events 정제 로그 (4단계)")
lines.append("=" * 84)
lines.append(f"원본 행 수 : {len(raw):,}")
lines.append(f"정제 행 수 : {len(df):,}   ← 행을 삭제하지 않았으므로 동일해야 정상")
lines.append("")
lines.append("  ※ 타임스탬프가 없어도 행동 유형과 상품 분석은 가능하므로 행을 지우지 않는다.")
lines.append("")

lines.append("-" * 84)
lines.append("[컬럼 구성 변화]")
lines.append("-" * 84)
lines.append(f"  원본 : {len(raw.columns)}열  {list(raw.columns)}")
lines.append(f"  정제 : {len(df.columns)}열")
lines.append("")
lines.append("  신규 컬럼")
lines.append("    product_id     : page_url 에서 추출 (product_catalog 참조)")
lines.append("    is_logged_in   : customer_id 존재 여부")
lines.append("    event_time     : 정제된 타임스탬프")
lines.append("    timestamp_raw  : 원본 보존")
lines.append("    time_flag      : NULL 처리 사유")
lines.append("")
lines.append("  개명")
lines.append("    timestamp → event_time")
lines.append("    (timestamp 는 PostgreSQL 자료형 이름이라 컬럼명 사용 시 혼동이 생긴다)")
lines.append("")

lines.append("-" * 84)
lines.append("[타임스탬프 정제 결과]")
lines.append("-" * 84)
lines.append(f"  유효           : {n_valid:>8,}건 ({n_valid/len(df)*100:>4.1f}%)")
for reason, cnt in df["time_flag"].value_counts().items():
    lines.append(f"  NULL — {reason:<8} : {cnt:>8,}건 ({cnt/len(df)*100:>4.1f}%)")
lines.append("")

valid_time = pd.to_datetime(df["event_time"].dropna())
lines.append(f"  유효 구간      : {valid_time.min()} ~ {valid_time.max()}")
lines.append(f"  일수           : {valid_time.dt.date.nunique():,}일")
lines.append(f"  일평균 이벤트   : {n_valid / valid_time.dt.date.nunique():,.0f}건")
lines.append("")
lines.append("  ※ 표기 3종(T구분 / 공백구분 / 초단위)을 하나로 통일했다.")
lines.append("     시간대가 전부 +00:00(UTC)이므로 시간대를 떼도 시각이 변하지 않는다.")
lines.append("")

lines.append("-" * 84)
lines.append("[파생 컬럼 결과]")
lines.append("-" * 84)
lines.append(f"  product_id 추출 : {n_product:,}건 ({n_product/len(df)*100:.1f}%) / "
             f"{df['product_id'].nunique():,}종")
lines.append(f"  로그인 이벤트    : {n_login:,}건 ({n_login/len(df)*100:.1f}%)")
lines.append(f"  비로그인 이벤트  : {len(df)-n_login:,}건 "
             f"({(len(df)-n_login)/len(df)*100:.1f}%)")
lines.append("")

lines.append("  [event_type 별 product_id 추출 현황]")
crosstab = pd.crosstab(df["event_type"], df["product_id"].notna())
crosstab.columns = ["상품 없음", "상품 있음"]
lines.append(crosstab.to_string())
lines.append("")
lines.append("  ※ login 과 search 에 상품이 0건인 것이 정상이다.")
lines.append("     로그인 화면과 검색 결과 페이지에 특정 상품 코드가 있을 이유가 없다.")
lines.append("")

lines.append("-" * 84)
lines.append("[page_url 표기 정규화]")
lines.append("-" * 84)
lines.append(f"  값이 변경된 건수 : {n_url_fixed:,}건")
lines.append(f"  URL 고유값       : {url_before[url_before!=''].nunique():,}개 → "
             f"{df['page_url'].nunique():,}개")
lines.append("")
lines.append("  [정규화된 페이지 유형]")
for k, v in df["page_type"].value_counts(dropna=False).items():
    lines.append(f"      {str(k):<16} {v:>8,}건")
lines.append("")
lines.append("  ※ 오염 5종(끝 슬래시 / 스킴 과다 / 스킴 누락 / 대문자 / 경로 축약)을")
lines.append("     하나의 표준 형태로 통일했다.")
lines.append("     대문자 URL과 경로 축약형 때문에 product_id 추출에서")
lines.append("     12,576건을 놓치고 있었고, 정규화 후 368,942건으로 늘었다.")
lines.append("")

lines.append("-" * 84)
lines.append("[device_id 형식 정제 결과]")
lines.append("-" * 84)
for reason, cnt in df["device_flag"].value_counts().items():
    lines.append(f"  {reason:<20} {cnt:>8,}건")
lines.append(f"  {'정상(무처리)':<20} {int(df['device_flag'].isna().sum()):>8,}건")
lines.append("")
lines.append("  ※ 이 컬럼은 분석에 쓰지 않지만 형식 정제는 했다.")
lines.append("     분석에 쓰지 않아도 DB 적재 시 자료형 변환은 통과해야 한다.")
lines.append("     실제로 이 처리를 빠뜨려 PostgreSQL 적재가 두 번 실패했다.")
lines.append("")

lines.append("-" * 84)
lines.append("[분석 사용 금지 컬럼 — 의미상 사용하지 않음]")
lines.append("-" * 84)
lines.append("  session_id    : 세션 역할 불가 (세션당 고객 43.7명 / 기기 62.5개)")
lines.append("  device_id     : CRM 기기 목록과 일치 0건, 고유율 99.8%")
lines.append("  ingest_run_id : 전 행 동일값 (고유값 1개)")
lines.append("")
lines.append("  ※ 값을 고치지 않았다. 틀린 값이 아니라 '의미가 없는' 컬럼이므로")
lines.append("     고칠 대상이 아니라 사용하지 않을 대상이다.")
lines.append("     컬럼을 지우지 않는 이유는 향후 다른 적재 배치가 추가되면")
lines.append("     ingest_run_id 가 의미를 가질 수 있기 때문이다.")
lines.append("")

lines.append("-" * 84)
lines.append("[원본 값 보존]")
lines.append("-" * 84)
lines.append("  타임스탬프 6만 건을 NULL 처리했으므로 원본을 timestamp_raw 에 남겼다.")
lines.append("")
lines.append("  SQL 예시 — NULL 처리된 이벤트의 원본값 확인:")
lines.append("    SELECT time_flag, timestamp_raw, COUNT(*)")
lines.append("    FROM   clickstream")
lines.append("    WHERE  event_time IS NULL")
lines.append("    GROUP  BY 1, 2")
lines.append("    ORDER  BY 3 DESC;")

with open(os.path.join(REPORT_DIR, "정제로그_clickstream.txt"), "w",
          encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print()
print("\n".join(lines))
