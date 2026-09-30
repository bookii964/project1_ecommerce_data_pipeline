# =============================================================================
# 파일명 : 08_verify_crm.py
# 단계   : 5단계 - 정제 결과 검증 (CRM)
#
# [목적]
#   4단계 정제본이 규칙을 지켰는지 기계적으로 확인한다.
#   이 단계를 통과해야 PostgreSQL에 적재할 수 있다.
#
# [product_catalog의 5단계와 달라진 점]
#   ① 테이블이 2개다 → 테이블 간 참조 정합성 검사가 추가된다
#      기기 테이블의 customer_id가 모두 고객 테이블에 존재해야 한다.
#      하나라도 없으면 PostgreSQL에서 외래키(FK) 제약을 걸 때 적재가 실패한다.
#
#   ② 행이 줄어들었다 → "줄어든 것이 의도한 만큼인지" 확인해야 한다
#      원본의 고유 customer_id 개수와 정제본 행 수가 일치해야 한다.
#      일치하지 않으면 중복 제거 과정에서 멀쩡한 고객이 사라졌다는 뜻이다.
#
#   ③ 파생 컬럼이 있다 → 계산이 맞는지 재검산한다
#      device_count가 실제 기기 테이블의 행 수와 맞는지 등.
#      파생 컬럼은 원본에 없던 값이므로 틀려도 눈에 안 보인다. 반드시 검산한다.
#
# [입력]  01_raw/crm_50000_customers_dirty_v3.csv
#         03_cleaned/crm_customers_cleaned.csv
#         03_cleaned/crm_customer_devices_cleaned.csv
# [출력]  04_reports/검증결과_crm.txt
#         04_reports/비교표_crm.csv
#
# [검증 원칙]
#   플래그가 붙은 값은 '의도적으로 남긴 것'이므로 불합격 처리하지 않는다.
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

RAW_FILE = os.path.join(PROJECT_DIR, "01_raw", "crm_50000_customers_dirty_v3.csv")
CUST_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "crm_customers_cleaned.csv")
DEV_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "crm_customer_devices_cleaned.csv")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")

UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                          r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
VALID_GENDER = ["M", "F", "O"]
VALID_SOURCE = ["referral", "web", "app"]
PHONE_DIGITS = 10


raw = read_csv_safe(RAW_FILE, dtype=str, keep_default_na=True)
cust = read_csv_safe(CUST_FILE, dtype=str, keep_default_na=True)
dev = read_csv_safe(DEV_FILE, dtype=str, keep_default_na=True)

print(f"원본       : {len(raw):,}행")
print(f"고객 테이블 : {len(cust):,}행")
print(f"기기 테이블 : {len(dev):,}행")
print()


checks = []
def check(name, expected, actual, passed):
    checks.append({
        "검사항목": name,
        "기대": expected,
        "실제": actual,
        "판정": "합격" if passed else "불합격",
    })


# =============================================================================
# [검사 1] 데이터 손실 검증
#
#   중복을 제거했으므로 행 수는 줄어드는 게 정상이다.
#   중요한 것은 "줄어든 결과가 정확히 고유 고객 수와 같은가"다.
#   원본의 고유 customer_id 개수 = 정제본 행 수 여야 한다.
# =============================================================================
raw_unique_ids = raw["customer_id"].nunique()

check("고객 수 = 원본 고유ID 수",
      f"{raw_unique_ids:,}명",
      f"{len(cust):,}명",
      len(cust) == raw_unique_ids)

# 원본에 있던 ID가 하나도 빠지지 않았는지 (집합 비교)
raw_ids = set(raw["customer_id"])
cust_ids = set(cust["customer_id"])
check("ID 누락 없음", "0건", f"{len(raw_ids - cust_ids):,}건", len(raw_ids - cust_ids) == 0)
check("ID 신규생성 없음", "0건", f"{len(cust_ids - raw_ids):,}건", len(cust_ids - raw_ids) == 0)


# =============================================================================
# [검사 2] 기본키 제약
#   PostgreSQL에서 PRIMARY KEY를 걸려면 중복도 결측도 없어야 한다.
# =============================================================================
check("customer_id 중복 없음", "0건",
      f"{cust['customer_id'].duplicated().sum():,}건",
      cust["customer_id"].duplicated().sum() == 0)

check("customer_id 결측 없음", "0건",
      f"{cust['customer_id'].isna().sum():,}건",
      cust["customer_id"].isna().sum() == 0)

bad_uuid = (~cust["customer_id"].str.match(UUID_PATTERN)).sum()
check("customer_id UUID 형식", "0건 위반", f"{bad_uuid:,}건", bad_uuid == 0)


# =============================================================================
# [검사 3] 테이블 간 참조 정합성 (외래키)
#
#   기기 테이블의 customer_id가 고객 테이블에 전부 존재해야 한다.
#   하나라도 없으면 PostgreSQL에서 FOREIGN KEY 제약 생성이 실패한다.
#
#   isin() : 왼쪽 값들이 오른쪽 목록에 포함되는지 True/False로 반환
# =============================================================================
orphan = (~dev["customer_id"].isin(cust["customer_id"])).sum()
check("기기→고객 참조 정합성", "고아 0건", f"{orphan:,}건", orphan == 0)

bad_dev_uuid = (~dev["device_id"].str.match(UUID_PATTERN)).sum()
check("device_id UUID 형식", "0건 위반", f"{bad_dev_uuid:,}건", bad_dev_uuid == 0)

dev_dup = dev.duplicated().sum()
check("기기 테이블 중복행 없음", "0건", f"{dev_dup:,}건", dev_dup == 0)


# =============================================================================
# [검사 4] 파생 컬럼 재검산
#
#   device_count는 우리가 계산해서 만든 값이다.
#   기기 테이블을 실제로 세어보고 일치하는지 확인한다.
#   파생 컬럼은 틀려도 눈에 보이지 않으므로 반드시 검산해야 한다.
# =============================================================================
actual_count = dev.groupby("customer_id").size().rename("실제기기수")
merged = (cust[["customer_id", "device_count"]]
          .assign(device_count=lambda d: d["device_count"].astype(int))
          .merge(actual_count, on="customer_id", how="left"))
merged["실제기기수"] = merged["실제기기수"].fillna(0).astype(int)

mismatch = (merged["device_count"] != merged["실제기기수"]).sum()
check("device_count 검산", "불일치 0건", f"{mismatch:,}건", mismatch == 0)

# age_at_signup 재검산 : (가입일 - 생년월일) / 365.25 를 다시 계산해서 비교
dob = pd.to_datetime(cust["dob"], errors="coerce")
signup = pd.to_datetime(cust["signup_date"], errors="coerce")
recomputed = ((signup - dob).dt.days / 365.25).round(0)
stored = pd.to_numeric(cust["age_at_signup"], errors="coerce")

age_mismatch = (recomputed != stored).sum()
check("age_at_signup 검산", "불일치 0건", f"{age_mismatch:,}건", age_mismatch == 0)


# =============================================================================
# [검사 4-2] 원본 값 보존 검증
#
#   개인정보 컬럼은 정제값과 함께 원본값(_raw)을 보관한다.
#   여기서 확인할 것은 "_raw에 정말 원본값이 들어있는가"다.
#   실수로 정제 후에 복사했다면 _raw에도 정제된 값이 들어가 보존이 무의미해진다.
#
#   검증 방법 : 같은 customer_id에 대해 원본 파일에 존재했던 값 중 하나와
#              _raw 값이 일치하는지 확인한다.
#              (중복 행이 제거되었으므로 원본에는 여러 변형이 있을 수 있다)
# =============================================================================
PRESERVE_COLS = ["first_name", "last_name", "email", "phone_number"]

for col in PRESERVE_COLS:
    raw_col = f"{col}_raw"

    # 컬럼 존재 여부
    exists = raw_col in cust.columns
    check(f"{raw_col} 컬럼 존재", "존재", "존재" if exists else "없음", exists)
    if not exists:
        continue

    # 원본에 (customer_id, 값) 조합으로 실제 존재했던 값인지 확인
    valid_pairs = set(zip(raw["customer_id"].fillna(""), raw[col].fillna("")))
    actual_pairs = zip(cust["customer_id"].fillna(""), cust[raw_col].fillna(""))
    bad = sum(1 for pair in actual_pairs if pair not in valid_pairs)

    check(f"{raw_col} 원본 일치", "0건 불일치", f"{bad:,}건", bad == 0)

# 원본 보존 컬럼이 정제값과 다른 건수 (참고용 — 판정 대상 아님)
change_counts = {
    col: int((cust[col].fillna("") != cust[f"{col}_raw"].fillna("")).sum())
    for col in PRESERVE_COLS if f"{col}_raw" in cust.columns
}


# =============================================================================
# [검사 5] 이름 규칙
#   플래그(name_flag)가 붙은 행은 판단 보류 건이므로 제외하고 검사한다.
# =============================================================================
unflagged = cust["name_flag"].isna()

for col in ["first_name", "last_name"]:
    s = cust[col].fillna("")
    check(f"{col} 숫자 없음", "0건",
          f"{s.str.contains(r'\d', regex=True).sum():,}건",
          s.str.contains(r"\d", regex=True).sum() == 0)
    check(f"{col} 특수문자 없음", "0건",
          f"{s.str.contains(r'[^A-Za-z ]', regex=True).sum():,}건",
          s.str.contains(r"[^A-Za-z ]", regex=True).sum() == 0)
    check(f"{col} 앞뒤공백 없음", "0건",
          f"{(s != s.str.strip()).sum():,}건",
          (s != s.str.strip()).sum() == 0)


# =============================================================================
# [검사 6] 전화번호
#   플래그가 붙은 9건은 의도적으로 남긴 것이므로 제외한다.
# =============================================================================
phone_ok = cust["phone_flag"].isna()
phone = cust.loc[phone_ok, "phone_number"].fillna("")

check("전화번호 숫자만", "0건 위반",
      f"{phone.str.contains(r'\D', regex=True).sum():,}건",
      phone.str.contains(r"\D", regex=True).sum() == 0)

check(f"전화번호 {PHONE_DIGITS}자리", "0건 위반",
      f"{(phone.str.len() != PHONE_DIGITS).sum():,}건",
      (phone.str.len() != PHONE_DIGITS).sum() == 0)


# =============================================================================
# [검사 7] 범주형 및 날짜
# =============================================================================
check("gender 허용값만", "0건 위반",
      f"{(~cust['gender'].isin(VALID_GENDER)).sum():,}건",
      (~cust["gender"].isin(VALID_GENDER)).sum() == 0)

check("source 허용값만", "0건 위반",
      f"{(~cust['source'].isin(VALID_SOURCE)).sum():,}건",
      (~cust["source"].isin(VALID_SOURCE)).sum() == 0)

check("dob 날짜 파싱", "0건 실패", f"{dob.isna().sum():,}건", dob.isna().sum() == 0)
check("signup_date 날짜 파싱", "0건 실패", f"{signup.isna().sum():,}건", signup.isna().sum() == 0)
check("가입일 ≥ 생년월일", "0건 위반",
      f"{(signup < dob).sum():,}건", (signup < dob).sum() == 0)

# 이메일 형식 (결측 제외)
email = cust["email"]
bad_email = (email.notna() & ~email.fillna("").str.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")).sum()
check("이메일 형식", "0건 위반", f"{bad_email:,}건", bad_email == 0)
check("이메일 소문자 통일", "0건 위반",
      f"{email.fillna('').str.contains(r'[A-Z]', regex=True).sum():,}건",
      email.fillna("").str.contains(r"[A-Z]", regex=True).sum() == 0)


# =============================================================================
# [출력] 검증 결과 리포트
# =============================================================================
result_df = pd.DataFrame(checks)
all_passed = (result_df["판정"] == "합격").all()

lines = []
lines.append("=" * 84)
lines.append("crm_50000_customers 정제 검증 결과 (5단계)")
lines.append("=" * 84)
lines.append("")
lines.append(f"{'검사항목':<30}{'기대':<20}{'실제':<20}{'판정'}")
lines.append("-" * 84)
for _, r in result_df.iterrows():
    lines.append(f"{r['검사항목']:<30}{r['기대']:<20}{str(r['실제']):<20}{r['판정']}")
lines.append("-" * 84)
lines.append("")
lines.append(f"검사 항목 {len(result_df)}개 중 합격 {(result_df['판정']=='합격').sum()}개")
lines.append(f"종합 판정 : "
             f"{'전체 합격 — PostgreSQL 적재 가능' if all_passed else '불합격 항목 있음 — 4단계 재확인 필요'}")
lines.append("")

# -----------------------------------------------------------------------------
# 플래그 현황 (판정 대상이 아님 — 의도적으로 남긴 값)
# -----------------------------------------------------------------------------
lines.append("-" * 84)
lines.append("[의도적으로 남긴 값 — 플래그]")
lines.append("-" * 84)
for col in ["name_flag", "email_flag", "phone_flag", "age_flag"]:
    counts = cust[col].value_counts(dropna=True)
    for k, v in counts.items():
        lines.append(f"  {col:<12} {k:<26} {v:>8,}건")
lines.append("")
lines.append("  ※ 규칙 위반이 아니라 '판단 보류'이므로 불합격 대상이 아니다.")
lines.append("     현업 담당자 확인이 필요한 목록에 해당한다.")
lines.append("")

# -----------------------------------------------------------------------------
# 개인정보 변경 현황 및 사용 범위 고지
# -----------------------------------------------------------------------------
lines.append("-" * 84)
lines.append("[개인정보 컬럼 변경 현황]")
lines.append("-" * 84)
for col, cnt in change_counts.items():
    lines.append(f"  {col:<16} {cnt:>8,}건 / {len(cust):,}건 변경  "
                 f"(원본은 {col}_raw 에 보관)")
lines.append("")
lines.append("  [이 정제본의 사용 범위]")
lines.append("    허용 : 집계, 통계, 중복 판정, 분석 조인")
lines.append("    금지 : 고객 응대, 본인 확인, 메일·문자 발송")
lines.append("           → 이런 용도에는 _raw 컬럼 또는 원본 파일(01_raw)을 사용해야 한다.")
lines.append("")
lines.append("  이름·이메일·전화번호는 고객이 직접 입력한 개인정보다.")
lines.append("  표준화된 값은 분석 목적의 가공값이며, 고객 입력을 정정한 것이 아니다.")
lines.append("")

# -----------------------------------------------------------------------------
# 미복원 오염 잔여 현황 (참고 정보)
#
#   이름 글자반복 오타 중 이메일로 검증할 수 없어 복원하지 못한 건이 남아 있다.
#   판정에는 넣지 않되, 규모를 정확히 알고 있어야 리포트가 정확해진다.
# -----------------------------------------------------------------------------
lines.append("-" * 84)
lines.append("[미복원 잔여 — 참고]")
lines.append("-" * 84)
for col in ["first_name", "last_name"]:
    pairs = cust[col].fillna("").str.findall(r"([A-Za-z])\1").apply(len)
    residual = pairs >= 2
    flagged = residual & cust["name_flag"].notna()
    lines.append(f"  {col} 반복쌍 2개 이상 : {int(residual.sum()):,}건 "
                 f"(그중 플래그 있음 {int(flagged.sum()):,}건)")

lines.append("")
lines.append("  ※ 이 숫자를 전부 '오염 잔여'로 읽으면 안 된다.")
lines.append("     Bennett, Russell, Carroll, Elliott 처럼 반복쌍이 2개인 정상 성씨가 다수 포함된다.")
lines.append("     이 이름들을 줄이지 않은 것이 오히려 규칙이 옳게 작동한 결과다.")
lines.append("     실제 미복원 오염은 플래그가 붙은 건에 한정되며, 이메일이")
lines.append("     다른 사람 것이어서 검증이 불가능했던 경우다. (예: Pphhiillips)")

with open(os.path.join(REPORT_DIR, "검증결과_crm.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))


# =============================================================================
# [출력] Before / After 비교표
# =============================================================================
raw_phone_digits = raw["phone_number"].fillna("").str.replace(r"\D", "", regex=True).str.len()

def count_pattern(series, pattern):
    return int(series.fillna("").str.contains(pattern, regex=True).sum())

compare = [
    {"지표": "전체 행 수", "정제 전": len(raw), "정제 후": len(cust)},
    {"지표": "고유 고객 수", "정제 전": raw["customer_id"].nunique(), "정제 후": cust["customer_id"].nunique()},
    {"지표": "기본키 중복", "정제 전": int(raw["customer_id"].duplicated().sum()), "정제 후": int(cust["customer_id"].duplicated().sum())},
    {"지표": "이름 숫자 포함", "정제 전": count_pattern(raw["first_name"], r"\d") + count_pattern(raw["last_name"], r"\d"), "정제 후": count_pattern(cust["first_name"], r"\d") + count_pattern(cust["last_name"], r"\d")},
    {"지표": "이름 특수문자 포함", "정제 전": count_pattern(raw["first_name"].str.strip(), r"[^A-Za-z ]") + count_pattern(raw["last_name"].str.strip(), r"[^A-Za-z ]"), "정제 후": count_pattern(cust["first_name"], r"[^A-Za-z ]") + count_pattern(cust["last_name"], r"[^A-Za-z ]")},
    {"지표": "이름 앞뒤공백", "정제 전": int((raw["first_name"] != raw["first_name"].str.strip()).sum()), "정제 후": int((cust["first_name"] != cust["first_name"].str.strip()).sum())},
    {"지표": "전화번호 10자리", "정제 전": int((raw_phone_digits == 10).sum()), "정제 후": int((cust["phone_number"].str.len() == 10).sum())},
    {"지표": "전화번호 형식 종류", "정제 전": 7, "정제 후": 1},
    {"지표": "다중값 컬럼(제1정규형 위반)", "정제 전": 1, "정제 후": 0},
    {"지표": "테이블 개수", "정제 전": 1, "정제 후": 2},
]

compare_df = pd.DataFrame(compare)
compare_df.to_csv(os.path.join(REPORT_DIR, "비교표_crm.csv"),
                  index=False, encoding="utf-8-sig")

lines.append("")
lines.append("-" * 84)
lines.append("[정제 전후 비교]")
lines.append("-" * 84)
lines.append(f"{'지표':<32}{'정제 전':>12}{'정제 후':>12}")
for _, r in compare_df.iterrows():
    lines.append(f"{r['지표']:<32}{r['정제 전']:>12,}{r['정제 후']:>12,}")

with open(os.path.join(REPORT_DIR, "검증결과_crm.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print()
print("저장 완료 : 04_reports/검증결과_crm.txt")
print("저장 완료 : 04_reports/비교표_crm.csv")
