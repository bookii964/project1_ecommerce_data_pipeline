# =============================================================================
# 파일명 : 20_detect_clickstream.py
# 단계   : 3단계 - 비정상 데이터 색출 및 유형 분류 (clickstream)
#
# [목적]
#   2단계 규칙서(데이터사전_clickstream.md)를 코드로 옮겨 규칙 위반 건을 찾아낸다.
#   이 단계에서도 데이터를 고치지 않는다.
#
# [50만 행을 다룰 때 주의한 점 3가지]
#
#   ① 라벨(위반유형 이름)의 개수를 반드시 고정한다
#      1단계 프로파일링에서 실제로 겪은 문제다.
#      f"기타('{값}')" 처럼 값을 라벨에 넣으면 라벨이 2만 개까지 늘어나고,
#      라벨마다 50만 행을 훑는 반복문이 돌아 스크립트가 멈춘다.
#      → 라벨은 항상 미리 정해둔 몇 가지여야 한다.
#
#   ② 정상적인 결측은 위반 목록에 넣지 않는다
#      customer_id 결측 15만 건은 '비로그인 행동'이므로 오염이 아니다.
#      이것을 위반으로 기록하면 상세 파일이 불필요하게 15만 행 커지고,
#      오염 건수 집계도 왜곡된다. 요약에 건수만 적는다.
#
#   ③ 컬럼 단위 문제는 행 단위로 기록하지 않는다
#      session_id 가 세션 역할을 못 하는 것은 '컬럼 전체의 문제'다.
#      50만 행에 각각 기록하면 상세 파일이 150만 행이 된다.
#      → 별도 섹션에 컬럼 단위로 한 번만 기록한다.
#
# [입력]  01_raw/clickstream_500k_events.csv
#         03_cleaned/ 마스터 2종 (대조용)
# [출력]  02_profiling/clickstream/
#           - 06_이상데이터_상세.csv
#           - 07_유형별_집계.csv
#           - 08_진단요약.txt
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
OUTPUT_DIR = os.path.join(PROJECT_DIR, "02_profiling", "clickstream")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 2단계에서 확정한 규칙 상수
# -----------------------------------------------------------------------------
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                          r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
VALID_EVENT_TYPES = ["page_view", "search", "add_to_cart", "login"]
PRODUCT_URL = re.compile(r"/product/(PROD-\d{4})")

# 타임스탬프 표기 3종 (전부 유효하며 표기만 다르다)
TS_T_TZ     = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00$"
TS_SPACE_TZ = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+00:00$"
TS_PLAIN    = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+00:00)?$"

# 유효 기간 상한 : 형식별 범위 비교와 밀도 비교로 판정 (규칙서 3-3)
VALID_UNTIL = pd.Timestamp("2025-12-02 23:59:59")

# 상수형 오염값 (고유값 1개)
CONSTANT_TS = "2024/31/01 25:61:00"


df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(df):,}행 × {len(df.columns)}열")
print()


issues = []

def add(mask, column, issue_type, kind):
    """mask가 True인 행을 위반 목록에 추가.
    issue_type 은 반드시 미리 정해둔 고정 문자열이어야 한다."""
    n = int(mask.sum())
    if n == 0:
        return
    sub = df.loc[mask, ["event_id"]].copy()
    sub["행번호"] = sub.index
    sub["컬럼"] = column
    sub["원본값"] = df.loc[mask, column].values
    sub["위반유형"] = issue_type
    sub["분류구분"] = kind
    issues.append(sub)
    print(f"  [{kind}] {column:<14} {issue_type:<26} {n:>8,}건")


# =============================================================================
# [검사 1] 키 컬럼 및 참조 정합성
# =============================================================================
print("[검사 1] 키 컬럼 및 참조 정합성")

add(df["event_id"].isna(), "event_id", "결측", "오염")
add(~df["event_id"].fillna("").str.match(UUID_PATTERN), "event_id", "UUID형식위반", "오염")
add(df["event_id"].duplicated(keep=False), "event_id", "중복", "오염")
add(df.duplicated(keep=False), "event_id", "완전중복행", "오염")

cust = read_csv_safe(os.path.join(CLEAN_DIR, "crm_customers_cleaned.csv"),
                     dtype=str, keep_default_na=True)
prod = read_csv_safe(os.path.join(CLEAN_DIR, "product_catalog_cleaned.csv"),
                     dtype=str, keep_default_na=True)

# 값이 있는 customer_id 만 대조한다.
# 결측은 비로그인 행동이므로 고아 판정 대상이 아니다.
has_cust = df["customer_id"].notna()
add(has_cust & ~df["customer_id"].isin(cust["customer_id"]),
    "customer_id", "고아레코드(고객없음)", "오염")
add(has_cust & ~df["customer_id"].fillna("").str.match(UUID_PATTERN),
    "customer_id", "UUID형식위반", "오염")

# 식별자 컬럼의 앞뒤 공백 검사
#
#   [초안에서 빠뜨렸던 검사 — 실제로 적재 실패를 겪고 추가했다]
#   session_id / device_id / ingest_run_id 는 '분석에 쓸 수 없는 컬럼'으로
#   판정했기 때문에 형식 검사를 생략했다. 그 결과 device_id 9,915건의
#   뒤쪽 공백을 발견하지 못하고, PostgreSQL 적재 단계에서 실패했다.
#     ERROR: invalid input syntax for type uuid: "...3553522de9b4 "
#
#   '분석에 쓰지 않는 컬럼'과 '검사하지 않아도 되는 컬럼'은 다르다.
#   적재 대상인 모든 컬럼은 최소한 형식 검사를 거쳐야 한다.
for col in ["event_id", "session_id", "customer_id", "device_id", "ingest_run_id"]:
    s_col = df[col].fillna("")
    add(s_col != s_col.str.strip(), col, "앞뒤공백", "표준화")

# device_id 형식 검사
#   하이픈 없는 32자리 16진수는 UUID를 다르게 적은 것이므로 표준화 대상이다.
#   그 외(invalid-device-NNNN)는 식별자가 아니므로 오염이다.
dev_strip = df["device_id"].fillna("").str.strip()
no_dash = dev_strip.str.match(r"^[0-9a-fA-F]{32}$")
add(no_dash, "device_id", "하이픈누락(복원가능)", "표준화")
add(~no_dash & ~dev_strip.str.match(UUID_PATTERN),
    "device_id", "형식오류(복원불가)", "오염")

print("  (출력이 없으면 위반 0건 — 정상입니다)")
print()


# =============================================================================
# [검사 2] event_type
# =============================================================================
print("[검사 2] event_type")

et = df["event_type"].fillna("")
add(df["event_type"].isna(), "event_type", "결측", "오염")
add(et != et.str.strip(), "event_type", "앞뒤공백", "표준화")
add(~et.str.strip().isin(VALID_EVENT_TYPES) & (et != ""),
    "event_type", "허용값외", "오염")
print("  (출력이 없으면 위반 0건 — 정상입니다)")
print()


# =============================================================================
# [검사 3] timestamp
#
#   표기 3종은 값이 같고 형식만 다르므로 '표준화'로 분류한다.
#   상수·범위이탈·결측은 값을 신뢰할 수 없으므로 '오염'이다.
# =============================================================================
print("[검사 3] timestamp")

ts = df["timestamp"].fillna("")

# 표기별 마스크 (str.match 는 벡터 연산이라 50만 행도 빠르다)
is_t_tz = ts.str.match(TS_T_TZ)
is_space_tz = ts.str.match(TS_SPACE_TZ)
is_plain = ts.str.match(TS_PLAIN)

add(df["timestamp"].isna(), "timestamp", "결측", "오염")
add(ts == CONSTANT_TS, "timestamp", "상수값(해석불가)", "오염")

# 표준 표기(T구분+마이크로초+시간대)가 아닌 유효 표기 → 형식 통일 대상
add(is_space_tz, "timestamp", "표기차이(공백구분)", "표준화")
add(is_plain, "timestamp", "표기차이(초단위)", "표준화")

# 위 어디에도 해당하지 않는 값 (라벨을 하나로 고정한다)
known = is_t_tz | is_space_tz | is_plain | (ts == CONSTANT_TS) | (ts == "")
add(~known, "timestamp", "미분류형식", "확인필요")

# 유효 기간 초과 검사
#   format='mixed' : 세 가지 표기가 섞여 있어도 알아서 읽는다
#   utc=True 후 tz_localize(None) : 시간대를 떼고 UTC 기준 시각으로 만든다
parsed = pd.to_datetime(ts.where(is_t_tz | is_space_tz | is_plain),
                        format="mixed", utc=True, errors="coerce")
parsed = parsed.dt.tz_localize(None)

add(parsed > VALID_UNTIL, "timestamp", "범위이탈(2025-12-02 초과)", "오염")
print()


# =============================================================================
# [검사 4] page_url 및 product_id 추출 가능성
# =============================================================================
print("[검사 4] page_url")

url = df["page_url"].fillna("")
add(df["page_url"].isna(), "page_url", "결측", "오염")

# URL 표기 오염 5종
#
#   [초안에서 ①만 검사했다가 문제를 겪었다]
#   ④⑤ 때문에 product_id 추출에서 12,576건을 놓치고 있었다.
#   정규식이 대소문자를 구분하고 '/product/' 만 찾았기 때문이다.
#   → 오염 유형을 전수 조사하지 않으면 파생 컬럼도 함께 부정확해진다.
add(url.str.contains(r"/{2,}$", regex=True),
    "page_url", "끝_슬래시중복", "표준화")
add(url.str.match(r"^https?:/{3,}"),
    "page_url", "스킴_슬래시과다", "표준화")
add((url != "") & ~url.str.match(r"^https?://"),
    "page_url", "스킴_누락", "표준화")
add(url.str.contains(r"[A-Z]{4,}", regex=True) & url.str.contains("SHOP"),
    "page_url", "전부_대문자", "표준화")
add(url.str.contains(r"/prod/+PROD-", regex=True),
    "page_url", "경로_축약(/prod/)", "표준화")

# 현재 규칙으로 추출되는 건수와, PROD 코드가 존재하는 전체 건수를 비교한다.
#   차이가 있으면 추출 규칙이 오염을 커버하지 못한다는 뜻이다.
extracted = url.str.extract(PRODUCT_URL)[0]
has_prod_code = url.str.contains(r"PROD-\d{4}", case=False, regex=True)
missed = int((has_prod_code & extracted.isna()).sum())
add(has_prod_code & extracted.isna(),
    "page_url", "상품코드_추출누락", "오염")

# 추출된 상품이 카탈로그에 없으면 오염이다
add(extracted.notna() & ~extracted.isin(prod["product_id"]),
    "page_url", "카탈로그에_없는_상품", "오염")

print(f"  [참고] 상품 코드 추출 성공 : {int(extracted.notna().sum()):,}건 "
      f"({extracted.nunique():,}종)")
print(f"  [참고] 정규화 없이는 {missed:,}건을 놓친다 "
      f"→ 4단계에서 URL 정규화 후 추출한다")
print()


# =============================================================================
# [검사 5] 컬럼 단위 문제 — 행 단위로 기록하지 않는다
#
#   session_id / device_id / ingest_run_id 는 '값'이 아니라 '컬럼 전체'가 문제다.
#   50만 행에 각각 기록하면 상세 파일이 150만 행이 되고,
#   오염 건수 집계도 의미를 잃는다.
#   → 여기서는 지표만 계산하고, 요약 리포트에 컬럼 단위로 적는다.
# =============================================================================
print("[검사 5] 컬럼 활용 가능성 (컬럼 단위)")

dev = read_csv_safe(os.path.join(CLEAN_DIR, "crm_customer_devices_cleaned.csv"),
                    dtype=str, keep_default_na=True)

grouped = df.groupby("session_id")
column_issues = [
    {
        "컬럼": "session_id",
        "문제": "세션 역할 불가",
        "근거": f"세션당 고객 {grouped['customer_id'].nunique().mean():.1f}명 "
                f"/ 기기 {grouped['device_id'].nunique().mean():.1f}개 (각 1이어야 정상)",
        "판정": "분석 사용 금지",
    },
    {
        "컬럼": "device_id",
        "문제": "CRM 기기와 무관",
        "근거": f"CRM 기기 목록과 일치 {int(df['device_id'].isin(dev['device_id']).sum()):,}건 "
                f"/ 고유율 {df['device_id'].nunique()/len(df)*100:.1f}%",
        "판정": "조인·분석 사용 금지",
    },
    {
        "컬럼": "ingest_run_id",
        "문제": "전 행 동일값",
        "근거": f"고유값 {df['ingest_run_id'].nunique()}개",
        "판정": "분석 사용 금지",
    },
]
for item in column_issues:
    print(f"  [구조] {item['컬럼']:<14} {item['문제']:<20} {item['판정']}")
print()


# =============================================================================
# [출력 1] 이상 데이터 상세
# =============================================================================
issue_df = pd.concat(issues, ignore_index=True)
issue_df = issue_df[["행번호", "event_id", "컬럼", "원본값", "위반유형", "분류구분"]]
issue_df = issue_df.sort_values(["행번호", "컬럼"])

issue_df.to_csv(os.path.join(OUTPUT_DIR, "06_이상데이터_상세.csv"),
                index=False, encoding="utf-8-sig")
print(f"06_이상데이터_상세.csv 저장 완료 (총 {len(issue_df):,}건)")


# =============================================================================
# [출력 2] 유형별 집계
# =============================================================================
summary = (
    issue_df.groupby(["컬럼", "분류구분", "위반유형"])
    .size().reset_index(name="건수")
    .sort_values(["컬럼", "분류구분", "건수"], ascending=[True, True, False])
)
summary.to_csv(os.path.join(OUTPUT_DIR, "07_유형별_집계.csv"),
               index=False, encoding="utf-8-sig")
print("07_유형별_집계.csv 저장 완료")


# =============================================================================
# [출력 3] 진단 요약
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("clickstream_500k_events 오염 진단 요약 (3단계)")
lines.append("=" * 84)
lines.append(f"전체 행 수        : {len(df):,}")
lines.append(f"위반 건수(누적)   : {len(issue_df):,}")

affected = issue_df["행번호"].nunique()
lines.append(f"위반이 있는 행 수 : {affected:,} / {len(df):,} ({affected/len(df)*100:.1f}%)")
lines.append("")

lines.append("-" * 84)
lines.append("[분류 구분별 건수]")
lines.append("-" * 84)
for kind, cnt in issue_df["분류구분"].value_counts().items():
    lines.append(f"  {kind:<10} : {cnt:>9,}건")
lines.append("")
lines.append("  오염     = 값을 신뢰할 수 없음. NULL 처리")
lines.append("  표준화   = 값은 맞고 표기만 다름. 형식 통일")
lines.append("  확인필요 = 판단 근거 부족")
lines.append("")

lines.append("-" * 84)
lines.append("[컬럼별 · 유형별 상세]")
lines.append("-" * 84)
for col in df.columns:
    sub = issue_df[issue_df["컬럼"] == col]
    lines.append(f"\n■ {col}  (총 {len(sub):,}건)")
    if len(sub) == 0:
        lines.append("    행 단위 위반 없음")
        continue
    for (kind, itype), cnt in sub.groupby(["분류구분", "위반유형"]).size().items():
        lines.append(f"    [{kind}] {itype:<28} {cnt:>9,}건")

# -----------------------------------------------------------------------------
# 컬럼 단위 문제 (행 단위 위반이 아니므로 별도 섹션)
# -----------------------------------------------------------------------------
lines.append("")
lines.append("-" * 84)
lines.append("[컬럼 단위 문제 — 값은 정상이나 분석에 쓸 수 없음]")
lines.append("-" * 84)
for item in column_issues:
    lines.append(f"\n■ {item['컬럼']}")
    lines.append(f"    문제 : {item['문제']}")
    lines.append(f"    근거 : {item['근거']}")
    lines.append(f"    판정 : {item['판정']}")
lines.append("")
lines.append("  ※ 이 세 컬럼은 결측 0건, 형식 위반 0건이다.")
lines.append("     오염 검사만 했다면 전부 정상으로 판정됐을 것이다.")
lines.append("     행 단위 위반이 아니라 컬럼 전체의 문제이므로 별도로 기록한다.")
lines.append("")

# -----------------------------------------------------------------------------
# 정상적인 결측 (오염이 아님)
# -----------------------------------------------------------------------------
lines.append("-" * 84)
lines.append("[오염이 아닌 결측]")
lines.append("-" * 84)
n_anon = int(df["customer_id"].isna().sum())
lines.append(f"  customer_id 결측 : {n_anon:,}건 ({n_anon/len(df)*100:.1f}%)")
lines.append("")
lines.append("  ※ 비로그인 상태의 행동으로 해석한다. 위반 목록에 포함하지 않았다.")
lines.append("     근거 : event_type 에 'login' 이 존재한다.")
lines.append("            로그인이 이벤트로 기록된다는 것은 그 이전 상태(비로그인)가 있다는 뜻이다.")
lines.append("     → 위반으로 기록하면 상세 파일이 15만 행 커지고 오염 집계가 왜곡된다.")
lines.append("")

# -----------------------------------------------------------------------------
# 4단계 처리 예정
# -----------------------------------------------------------------------------
valid_ts = int((parsed.notna() & (parsed <= VALID_UNTIL)).sum())
lines.append("-" * 84)
lines.append("[4단계 처리 예정]")
lines.append("-" * 84)
lines.append("  형식 통일 : timestamp 표기 3종 → 'YYYY-MM-DD HH:MM:SS' (UTC)")
lines.append("  NULL 처리 : 상수값 / 범위이탈 / 원본결측")
lines.append("  파생 생성 : product_id (page_url에서 추출), is_logged_in")
lines.append("  컬럼 개명 : timestamp → event_time (DB 예약어 회피)")
lines.append("  유지+금지 : session_id / device_id / ingest_run_id")
lines.append("  행 삭제   : 없음")
lines.append("")
lines.append(f"  정제 후 시계열 분석 가능 : {valid_ts:,}건 ({valid_ts/len(df)*100:.1f}%)")
lines.append(f"  정제 후 상품 분석 가능   : {int(extracted.notna().sum()):,}건 "
             f"({extracted.notna().mean()*100:.1f}%)")

with open(os.path.join(OUTPUT_DIR, "08_진단요약.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("08_진단요약.txt 저장 완료")
print()
print("\n".join(lines))
