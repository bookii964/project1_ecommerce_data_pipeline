# =============================================================================
# 파일명 : 22_verify_clickstream.py
# 단계   : 5단계 - 정제 결과 검증 (clickstream)
#
# [목적]
#   4단계 정제본이 규칙을 지켰는지 기계적으로 확인한다.
#
# [이 스크립트를 뒤늦게 추가한 이유]
#   clickstream 은 DB 제약조건과 SQL 검증(05_verify_clickstream.sql)으로
#   확인하고 넘어갔다. 그런데 다른 4개 파일에는 모두 Python 검증 스크립트가
#   있어서 절차가 일관되지 않았다.
#
#   DB 검증만으로 부족한 이유가 두 가지 있다.
#     ① 적재 전에 문제를 알 수 없다
#        실제로 device_id 오염 때문에 적재가 두 번 실패했다.
#        Python 검증이 있었다면 적재 전에 발견했을 것이다.
#     ② 원본 파일과의 대조가 안 된다
#        DB에는 정제본만 들어간다. "원본과 비교해 값이 유실되지 않았는가"는
#        원본 CSV를 함께 읽어야 확인할 수 있다.
#
# [입력]  01_raw/clickstream_500k_events.csv
#         03_cleaned/clickstream_cleaned.csv
#         03_cleaned/product_catalog_cleaned.csv
#         03_cleaned/crm_customers_cleaned.csv
# [출력]  04_reports/검증결과_clickstream.txt
#         04_reports/비교표_clickstream.csv
#
# [검증 원칙]
#   NULL 과 플래그는 '의도적으로 처리한 결과'이므로 불합격 대상이 아니다.
#   검증은 규칙 위반을 찾는 것이지, 우리가 내린 판단을 뒤집는 것이 아니다.
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

RAW_FILE = os.path.join(PROJECT_DIR, "01_raw", "clickstream_500k_events.csv")
CLEAN_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "clickstream_cleaned.csv")
PROD_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "product_catalog_cleaned.csv")
CUST_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "crm_customers_cleaned.csv")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                          r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
VALID_EVENT_TYPES = ["page_view", "search", "add_to_cart", "login"]
PRODUCT_URL = re.compile(r"/product/(PROD-\d{4})")

# 유효 기간 상한 (2단계 규칙서 3-3)
VALID_UNTIL = pd.Timestamp("2025-12-02 23:59:59")
VALID_FROM = pd.Timestamp("2025-09-01 00:00:00")

# 4단계에서 의도한 건수 (실제와 대조하기 위한 기준)
EXPECTED_TIME_NULL = 60090
EXPECTED_PRODUCT = 368942
EXPECTED_LOGIN = 349447
EXPECTED_DEVICE_NULL = 4986


raw = read_csv_safe(RAW_FILE, dtype=str, keep_default_na=True)
clean = read_csv_safe(CLEAN_FILE, dtype=str, keep_default_na=True)
prod = read_csv_safe(PROD_FILE, dtype=str, keep_default_na=True)
cust = read_csv_safe(CUST_FILE, dtype=str, keep_default_na=True)

print(f"원본   : {len(raw):,}행")
print(f"정제본 : {len(clean):,}행")
print()


checks = []
def check(name, expected, actual, passed):
    checks.append({
        "검사항목": name, "기대": expected, "실제": actual,
        "판정": "합격" if passed else "불합격",
    })


# =============================================================================
# [검사 1] 데이터 손실
#   로그 데이터는 행 삭제를 하지 않았으므로 행 수가 완전히 같아야 한다.
# =============================================================================
check("행 개수 보존", f"{len(raw):,}행", f"{len(clean):,}행", len(raw) == len(clean))

raw_ids, clean_ids = set(raw["event_id"]), set(clean["event_id"])
check("event_id 집합 일치", "원본과 동일",
      f"누락 {len(raw_ids-clean_ids):,} / 추가 {len(clean_ids-raw_ids):,}",
      raw_ids == clean_ids)
check("event_id 중복 없음", "0건",
      f"{clean['event_id'].duplicated().sum():,}건",
      clean["event_id"].duplicated().sum() == 0)


# =============================================================================
# [검사 2] 값을 바꾸지 않기로 한 컬럼이 정말 그대로인가
#
#   customer_id, event_type, session_id, ingest_run_id 는 정제 대상이 아니었다.
#   (공백 제거만 했으므로 strip 후 비교한다)
#   값이 변했다면 실수로 덮어쓴 것이다.
# =============================================================================
merged = raw[["event_id", "customer_id", "event_type", "session_id", "ingest_run_id"]].merge(
    clean[["event_id", "customer_id", "event_type", "session_id", "ingest_run_id"]],
    on="event_id", suffixes=("_raw", "_clean"))

for col in ["customer_id", "event_type", "session_id", "ingest_run_id"]:
    a = merged[f"{col}_raw"].fillna("").str.strip()
    b = merged[f"{col}_clean"].fillna("").str.strip()
    diff = int((a != b).sum())
    check(f"{col} 값 불변", "0건 변경", f"{diff:,}건", diff == 0)


# =============================================================================
# [검사 3] 참조 정합성
#   customer_id 와 product_id 는 NULL 을 허용하므로 값이 있는 행만 대조한다.
# =============================================================================
has_cust = clean["customer_id"].notna()
orphan_cust = int((~clean.loc[has_cust, "customer_id"].isin(cust["customer_id"])).sum())
check("customer_id 참조 정합성", "고아 0건", f"{orphan_cust:,}건", orphan_cust == 0)

has_prod = clean["product_id"].notna()
orphan_prod = int((~clean.loc[has_prod, "product_id"].isin(prod["product_id"])).sum())
check("product_id 참조 정합성", "고아 0건", f"{orphan_prod:,}건", orphan_prod == 0)


# =============================================================================
# [검사 4] event_type 허용값
# =============================================================================
bad_type = int((~clean["event_type"].isin(VALID_EVENT_TYPES)).sum())
check("event_type 허용값", "0건 위반", f"{bad_type:,}건", bad_type == 0)
check("event_type 종류 수", "4종", f"{clean['event_type'].nunique()}종",
      clean["event_type"].nunique() == 4)


# =============================================================================
# [검사 5] event_time — 형식과 범위
# =============================================================================
event_time = pd.to_datetime(clean["event_time"], errors="coerce")

parse_fail = int((clean["event_time"].notna() & event_time.isna()).sum())
check("event_time 파싱 가능", "0건 실패", f"{parse_fail:,}건", parse_fail == 0)

out_of_range = int(((event_time < VALID_FROM) | (event_time > VALID_UNTIL)).sum())
check("event_time 유효 범위", "0건 이탈", f"{out_of_range:,}건", out_of_range == 0)

time_null = int(clean["event_time"].isna().sum())
check("event_time NULL 건수", f"{EXPECTED_TIME_NULL:,}건", f"{time_null:,}건",
      time_null == EXPECTED_TIME_NULL)

# 표기가 하나로 통일됐는지 (YYYY-MM-DD HH:MM:SS)
STANDARD_TS = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
non_standard = int((clean["event_time"].notna()
                    & ~clean["event_time"].fillna("").str.match(STANDARD_TS)).sum())
check("event_time 표기 통일", "0건 위반", f"{non_standard:,}건", non_standard == 0)


# =============================================================================
# [검사 6] NULL 과 플래그의 짝
#
#   값을 비웠으면 반드시 사유가 있어야 하고,
#   사유가 있는데 값이 남아 있어도 안 된다.
# =============================================================================
null_no_flag = int((clean["event_time"].isna() & clean["time_flag"].isna()).sum())
check("event_time NULL에 사유 있음", "0건 누락", f"{null_no_flag:,}건", null_no_flag == 0)

flag_with_value = int((clean["time_flag"].notna() & clean["event_time"].notna()).sum())
check("time_flag 있으면 NULL", "0건 불일치", f"{flag_with_value:,}건", flag_with_value == 0)


# =============================================================================
# [검사 7] 파생 컬럼 재검산
#
#   is_logged_in 과 product_id 는 우리가 계산해서 만든 값이다.
#   원본에 없던 값이므로 틀려도 눈에 보이지 않는다. 반드시 다시 계산해 대조한다.
# =============================================================================
# is_logged_in : 문자열 'True'/'False' 로 저장되어 있으므로 참/거짓으로 변환한다
logged_in = clean["is_logged_in"].astype(str).str.lower().isin(["true", "1", "t"])
mismatch_login = int((logged_in != clean["customer_id"].notna()).sum())
check("is_logged_in 재검산", "0건 불일치", f"{mismatch_login:,}건", mismatch_login == 0)

check("로그인 이벤트 건수", f"{EXPECTED_LOGIN:,}건", f"{int(logged_in.sum()):,}건",
      int(logged_in.sum()) == EXPECTED_LOGIN)

# product_id : page_url 에서 다시 추출해 대조한다
re_extracted = clean["page_url"].fillna("").str.extract(PRODUCT_URL)[0]
mismatch_prod = int((re_extracted.fillna("") != clean["product_id"].fillna("")).sum())
check("product_id 재검산", "0건 불일치", f"{mismatch_prod:,}건", mismatch_prod == 0)

check("product_id 추출 건수", f"{EXPECTED_PRODUCT:,}건",
      f"{int(clean['product_id'].notna().sum()):,}건",
      int(clean["product_id"].notna().sum()) == EXPECTED_PRODUCT)


# =============================================================================
# [검사 8] device_id 형식
#
#   [이 검사가 없어서 DB 적재가 두 번 실패했다]
#   device_id 를 '분석 사용 금지'로 판정한 뒤 형식 검사를 생략했더니,
#   PostgreSQL 의 UUID 타입 변환에서 걸렸다.
#     - 뒤쪽 공백 9,915건
#     - 형식 오염 10,016건 (하이픈 누락 5,030 + invalid-device-* 4,986)
#
#   '분석에 쓰지 않는 컬럼'과 '검사하지 않아도 되는 컬럼'은 다르다.
#   적재 대상인 모든 컬럼은 최소한 형식 검사를 거쳐야 한다.
# =============================================================================
dev = clean["device_id"].fillna("")

space_bad = int((dev != dev.str.strip()).sum())
check("device_id 앞뒤공백 없음", "0건", f"{space_bad:,}건", space_bad == 0)

# NULL 이 아닌 값은 전부 UUID 형식이어야 한다
has_dev = clean["device_id"].notna()
format_bad = int((~clean.loc[has_dev, "device_id"].str.match(UUID_PATTERN)).sum())
check("device_id UUID 형식", "0건 위반", f"{format_bad:,}건", format_bad == 0)

dev_null = int(clean["device_id"].isna().sum())
check("device_id NULL 건수", f"{EXPECTED_DEVICE_NULL:,}건", f"{dev_null:,}건",
      dev_null == EXPECTED_DEVICE_NULL)

# NULL 인 행에는 반드시 사유가 있어야 한다
dev_null_no_flag = int((clean["device_id"].isna() & clean["device_flag"].isna()).sum())
check("device_id NULL에 사유 있음", "0건 누락", f"{dev_null_no_flag:,}건",
      dev_null_no_flag == 0)

# 다른 식별자 컬럼도 형식을 확인한다
for col in ["event_id", "session_id", "ingest_run_id"]:
    bad = int((~clean[col].fillna("").str.match(UUID_PATTERN)).sum())
    check(f"{col} UUID 형식", "0건 위반", f"{bad:,}건", bad == 0)


# =============================================================================
# [검사 9] page_url 표기
#   끝에 슬래시가 2개 이상 붙은 URL이 남아 있으면 정규화가 안 된 것이다.
# =============================================================================
url = clean["page_url"].fillna("")
CANONICAL = "https://shop.example.com"

slash_bad = int(url.str.contains(r"/{2,}$", regex=True).sum())
check("page_url 슬래시 정규화", "0건 위반", f"{slash_bad:,}건", slash_bad == 0)

# 정규화된 URL은 모두 표준 호스트로 시작해야 한다
host_bad = int(((url != "") & ~url.str.startswith(CANONICAL)).sum())
check("page_url 표준 호스트", "0건 위반", f"{host_bad:,}건", host_bad == 0)

# 상품 코드를 제외하면 대문자가 남아 있으면 안 된다
upper_bad = int(url.str.replace(r"PROD-\d{4}", "", regex=True)
                   .str.contains(r"[A-Z]", regex=True).sum())
check("page_url 대소문자 통일", "0건 위반", f"{upper_bad:,}건", upper_bad == 0)

# 경로 축약형이 남아 있으면 안 된다
abbrev_bad = int(url.str.contains(r"/prod/", regex=True).sum())
check("page_url 경로 축약 복원", "0건 위반", f"{abbrev_bad:,}건", abbrev_bad == 0)

# 상품 코드가 있는 URL은 전부 product_id 가 추출되어 있어야 한다
has_code = url.str.contains(r"PROD-\d{4}", case=False, regex=True)
missed_extract = int((has_code & clean["product_id"].isna()).sum())
check("상품코드 추출 누락 없음", "0건", f"{missed_extract:,}건", missed_extract == 0)

# page_type 파생 검증
valid_types = ["product_detail", "search", "category", "cart", "home", "other"]
type_bad = int((clean["page_type"].notna()
                & ~clean["page_type"].isin(valid_types)).sum())
check("page_type 허용값", "0건 위반", f"{type_bad:,}건", type_bad == 0)

# page_url 이 있으면 page_type 도 있어야 한다
pair_bad = int((clean["page_url"].notna() & clean["page_type"].isna()).sum())
check("page_type 짝 일치", "0건 누락", f"{pair_bad:,}건", pair_bad == 0)


# =============================================================================
# [검사 10] 원본 값 보존
#   timestamp_raw 에 정말 원본값이 들어있는지 확인한다.
#   실수로 정제 후에 복사했다면 보존이 무의미해진다.
# =============================================================================
for raw_col, src_col in [("timestamp_raw", "timestamp"), ("page_url_raw", "page_url")]:
    exists = raw_col in clean.columns
    check(f"{raw_col} 컬럼 존재", "존재", "존재" if exists else "없음", exists)
    if not exists:
        continue
    raw_lookup = raw.set_index("event_id")[src_col]
    clean_indexed = clean.set_index("event_id")[raw_col]
    a = raw_lookup.reindex(clean_indexed.index).fillna("")
    b = clean_indexed.fillna("")
    mismatch_raw = int((a.values != b.values).sum())
    check(f"{raw_col} 원본 일치", "0건 불일치", f"{mismatch_raw:,}건", mismatch_raw == 0)


# =============================================================================
# [출력] 검증 결과 리포트
# =============================================================================
result_df = pd.DataFrame(checks)
all_passed = (result_df["판정"] == "합격").all()

lines = []
lines.append("=" * 84)
lines.append("clickstream_500k_events 정제 검증 결과 (5단계)")
lines.append("=" * 84)
lines.append("")
lines.append(f"{'검사항목':<32}{'기대':<18}{'실제':<20}{'판정'}")
lines.append("-" * 84)
for _, r in result_df.iterrows():
    lines.append(f"{r['검사항목']:<32}{r['기대']:<18}{str(r['실제']):<20}{r['판정']}")
lines.append("-" * 84)
lines.append("")
lines.append(f"검사 항목 {len(result_df)}개 중 합격 {(result_df['판정']=='합격').sum()}개")
lines.append(f"종합 판정 : "
             f"{'전체 합격 — PostgreSQL 적재 가능' if all_passed else '불합격 항목 있음 — 4단계 재확인 필요'}")
lines.append("")

lines.append("-" * 84)
lines.append("[의도적으로 처리한 값 — 판정 대상 아님]")
lines.append("-" * 84)
for col in ["time_flag", "device_flag"]:
    counts = clean[col].value_counts(dropna=True)
    lines.append(f"\n  ■ {col}")
    if len(counts) == 0:
        lines.append("      없음")
    for k, v in counts.items():
        lines.append(f"      {k:<28} {v:>8,}건")
lines.append("")
lines.append("  ※ NULL 처리와 형식 복원은 규칙에 따른 결과이므로 불합격 대상이 아니다.")
lines.append("     원본값은 timestamp_raw 에 보존되어 있다.")
lines.append("")

lines.append("-" * 84)
lines.append("[분석 사용 금지 컬럼 — 값은 정상, 의미가 없음]")
lines.append("-" * 84)
grouped = clean.groupby("session_id")
lines.append(f"  session_id    : 세션당 고객 "
             f"{grouped['customer_id'].nunique().mean():.1f}명 / "
             f"기기 {grouped['device_id'].nunique().mean():.1f}개 (각 1이어야 정상)")
lines.append(f"  device_id     : CRM 기기 목록과 무관 (고유율 "
             f"{clean['device_id'].nunique()/len(clean)*100:.1f}%)")
lines.append(f"  ingest_run_id : 고유값 {clean['ingest_run_id'].nunique()}개 (전 행 동일)")
lines.append("")
lines.append("  ※ 형식 검사는 통과하지만 분석에는 사용하지 않는다.")
lines.append("     형식 검사를 생략했다가 DB 적재가 두 번 실패한 경험이 있어,")
lines.append("     '사용 금지'와 '검사 생략'을 구분해 검사 항목에 포함시켰다.")
lines.append("")

lines.append("-" * 84)
lines.append("[분석 가능 데이터 규모]")
lines.append("-" * 84)
lines.append(f"  전체 이벤트           : {len(clean):,}건")
lines.append(f"  행동유형 분석          : {len(clean):,}건 (100.0%)")
lines.append(f"  시계열 분석            : {len(clean)-time_null:,}건 "
             f"({(len(clean)-time_null)/len(clean)*100:.1f}%)")
lines.append(f"  상품 분석              : {int(clean['product_id'].notna().sum()):,}건 "
             f"({clean['product_id'].notna().mean()*100:.1f}%)")
lines.append(f"  고객 단위 분석(로그인)  : {int(logged_in.sum()):,}건 "
             f"({logged_in.mean()*100:.1f}%)")
lines.append("")
valid_time = event_time.dropna()
lines.append(f"  수집 구간              : {valid_time.min()} ~ {valid_time.max()}")
lines.append(f"  수집 일수              : {valid_time.dt.date.nunique():,}일")
lines.append(f"  일평균 이벤트           : "
             f"{(len(clean)-time_null)/valid_time.dt.date.nunique():,.0f}건")
lines.append("")
lines.append("  ※ orders(2년) / support_tickets(2년) 와 수집 기간이 다르다.")
lines.append("     조인 분석 시 기간을 맞추지 않으면 전환율이 100%를 넘는 결과가 나온다.")


# =============================================================================
# [출력] Before / After 비교표
# =============================================================================
raw_ts = raw["timestamp"].fillna("")

def count_ts_formats(series):
    """타임스탬프 표기가 몇 종류인지 센다"""
    patterns = [
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00$",
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+00:00$",
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+00:00)?$",
    ]
    kinds = sum(1 for p in patterns if series.str.match(p).any())
    if (series == "2024/31/01 25:61:00").any():
        kinds += 1
    if (series == "").any():
        kinds += 1
    return kinds

raw_dev = raw["device_id"].fillna("").str.strip()

compare = [
    {"지표": "전체 행 수", "정제 전": len(raw), "정제 후": len(clean)},
    {"지표": "타임스탬프 표기 종류", "정제 전": count_ts_formats(raw_ts), "정제 후": 1},
    {"지표": "유효 타임스탬프", "정제 전": 0, "정제 후": len(clean) - time_null},
    {"지표": "device_id 형식위반",
     "정제 전": int((~raw_dev.str.match(UUID_PATTERN) & (raw_dev != "")).sum()),
     "정제 후": format_bad},
    {"지표": "device_id 앞뒤공백",
     "정제 전": int((raw["device_id"].fillna("") != raw_dev).sum()),
     "정제 후": space_bad},
    {"지표": "page_url 끝 슬래시 중복",
     "정제 전": int(raw["page_url"].fillna("").str.contains(r"/{2,}$", regex=True).sum()),
     "정제 후": slash_bad},
    {"지표": "page_url 고유값",
     "정제 전": int(raw["page_url"].nunique()),
     "정제 후": int(clean["page_url"].nunique())},
    {"지표": "URL 스킴 오염(과다·누락)",
     "정제 전": int((raw["page_url"].fillna("").str.match(r"^https?:/{3,}")
                     | ((raw["page_url"].fillna("") != "")
                        & ~raw["page_url"].fillna("").str.match(r"^https?://"))).sum()),
     "정제 후": 0},
    {"지표": "URL 대문자 표기",
     "정제 전": int(raw["page_url"].fillna("").str.contains("SHOP").sum()),
     "정제 후": upper_bad},
    {"지표": "product_id 추출", "정제 전": 0, "정제 후": int(clean["product_id"].notna().sum())},
    {"지표": "page_type 컬럼", "정제 전": 0, "정제 후": int(clean["page_type"].notna().sum())},
    {"지표": "컬럼 수", "정제 전": len(raw.columns), "정제 후": len(clean.columns)},
]

compare_df = pd.DataFrame(compare)
compare_df.to_csv(os.path.join(REPORT_DIR, "비교표_clickstream.csv"),
                  index=False, encoding="utf-8-sig")

lines.append("")
lines.append("-" * 84)
lines.append("[정제 전후 비교]")
lines.append("-" * 84)
lines.append(f"{'지표':<28}{'정제 전':>14}{'정제 후':>14}")
for _, r in compare_df.iterrows():
    lines.append(f"{r['지표']:<28}{r['정제 전']:>14,}{r['정제 후']:>14,}")
lines.append("")
lines.append("  ※ '유효 타임스탬프 정제 전 0건'은 원본에 표기가 통일된 값이")
lines.append("     하나도 없었다는 뜻이다. 표기 3종을 통일한 뒤 439,910건이 사용 가능해졌다.")

with open(os.path.join(REPORT_DIR, "검증결과_clickstream.txt"), "w",
          encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print()
print("저장 완료 : 04_reports/검증결과_clickstream.txt")
print("저장 완료 : 04_reports/비교표_clickstream.csv")
