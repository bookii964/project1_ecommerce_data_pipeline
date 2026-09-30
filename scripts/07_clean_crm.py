# =============================================================================
# 파일명 : 07_clean_crm.py
# 단계   : 4단계 - 정제 규칙 적용 및 정제 파일 생성 (CRM)
#
# [목적]
#   2단계 규칙서대로 값을 실제로 고치고, 중복을 제거하고, 테이블을 분리한다.
#
# [처리 순서 — 이 순서를 지켜야 결과가 맞다]
#   ① 컬럼별 값 정제      (공백/대소문자/특수문자/숫자/전화번호 형식)
#   ② 이름 복원           (이메일과 대조해서 글자반복 오타 수정)
#   ③ 파생 컬럼 생성      (phone_ext / device_count / age_at_signup)
#   ④ 완전 중복 행 제거   ← ①②가 끝난 뒤여야 한다
#   ⑤ 잔여 기본키 충돌 처리
#   ⑥ device 테이블 분리
#
#   ④를 ①보다 먼저 하면 안 되는 이유:
#     'Melissa Peck'과 'Melissa PECK'은 컴퓨터에게 다른 값이다.
#     표기를 먼저 통일해야 같은 행으로 인식되어 중복 제거가 된다.
#     검증 결과 : 통일 전 1,021건 → 통일 후 1,789건 (768건 차이)
#
# [입력]  01_raw/crm_50000_customers_dirty_v3.csv
# [출력]  03_cleaned/crm_customers_cleaned.csv          (고객 테이블)
#         03_cleaned/crm_customer_devices_cleaned.csv   (기기 테이블 — 1:N)
#         04_reports/정제로그_crm.txt                    (단계별 행 수 변화)
#         04_reports/삭제행_crm.csv                      (제거된 중복 행 전체)
#
# =============================================================================
# [매우 중요] 이 정제본은 '분석 전용 사본'이다
# =============================================================================
#   이름·이메일·전화번호는 고객이 직접 입력한 개인정보다.
#   따라서 우리가 표준화한 값은 '분석 목적의 가공값'이며,
#   고객이 입력한 원래 값을 정정한 것이 아니다.
#
#   [사용 범위]
#     허용 : 집계, 통계, 중복 판정, 분석 조인
#     금지 : 고객 응대, 본인 확인, 메일·문자 발송
#            → 이런 용도에는 원본(01_raw) 또는 아래 _raw 컬럼을 사용해야 한다.
#
#   [왜 이런 구분이 필요한가]
#     'MEAN YOUR'처럼 전부 대문자로 입력한 것은 시스템 오염이 아니라
#     고객의 입력 방식일 수 있다. 이를 'Mean Your'로 바꾼 것은 우리 판단이며,
#     분석에는 유리하지만 고객이 입력한 형태는 아니다.
#     반면 'KKeevvin'(글자 반복), 'Tho8mas'(숫자 삽입)는 사람이 입력할 수 없는
#     패턴이고, 이메일과 대조해 복원이 검증되었으므로 시스템 오염으로 판단했다.
#
#   [그래서 원본 값을 함께 저장한다]
#     first_name_raw / last_name_raw / email_raw / phone_number_raw
#     → 정제 전 값을 같은 행에 보관한다.
#     → SQL에서 WHERE first_name != first_name_raw 로 수정된 건을 즉시 조회할 수 있다.
#     → 변경이력 파일을 따로 열지 않아도 테이블 안에서 대조가 가능하다.
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

INPUT_FILE = os.path.join(PROJECT_DIR, "01_raw", "crm_50000_customers_dirty_v3.csv")
CLEAN_DIR = os.path.join(PROJECT_DIR, "03_cleaned")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

MIN_SIGNUP_AGE = 14
PHONE_DIGITS = 10

# 단계별 행 수 변화를 기록할 리스트 (정제 로그용)
steps = []
def log_step(name, rows, note=""):
    steps.append({"단계": name, "행 수": rows, "비고": note})
    print(f"  {name:<34} {rows:>8,}행  {note}")


raw = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(raw):,}행")
print()
print("[처리 진행]")
log_step("0. 원본", len(raw))

# 정제 결과를 담을 표. 원본(raw)은 끝까지 건드리지 않는다.
df = raw.copy()


# -----------------------------------------------------------------------------
# [원본 값 보존] 정제를 시작하기 전에 개인정보 컬럼의 원래 값을 복사해 둔다.
#
#   이 시점에 복사해야 한다. 정제를 시작한 뒤에 복사하면 이미 바뀐 값이 담긴다.
#   대상은 고객이 직접 입력한 개인정보 4개 컬럼이다.
#   (주소·도시·국가도 개인정보지만 표기 정리만 하고 값은 바꾸지 않으므로 제외)
# -----------------------------------------------------------------------------
PRESERVE_COLS = ["first_name", "last_name", "email", "phone_number"]
for col in PRESERVE_COLS:
    df[f"{col}_raw"] = raw[col]

log_step("0-1. 원본 값 보존 컬럼 생성", len(df), f"{len(PRESERVE_COLS)}개 컬럼")


# =============================================================================
# ① 컬럼별 값 정제
# =============================================================================

# -----------------------------------------------------------------------------
# 1-1. 이름 : 숫자·특수문자 제거 → 공백 정리
#   사람 이름에 숫자('Tho8mas')나 특수문자('Tara*')가 들어갈 이유가 없다.
#   주소와 달리 제거해도 안전하다. (주소의 숫자는 번지수이므로 유지한다)
#
#   r"[^A-Za-z ]" 는 "영문자와 공백이 아닌 모든 문자"를 뜻한다.
#   \s+ → " " 는 연속된 공백을 하나로 줄인다.
# -----------------------------------------------------------------------------
for col in ["first_name", "last_name"]:
    df[col] = (df[col].fillna("")
               .str.replace(r"[^A-Za-z ]", "", regex=True)
               .str.replace(r"\s+", " ", regex=True)
               .str.strip())

log_step("1. 이름 숫자·특수문자 제거", len(df))


# -----------------------------------------------------------------------------
# 1-2. 이메일 : 소문자 통일, 공백 제거
# -----------------------------------------------------------------------------
df["email"] = df["email"].str.strip().str.lower()

# 공용 이메일 여부 (이름 검증에 쓸 수 없는 이메일)
shared_email = df["email"].fillna("").str.startswith("shared")


# -----------------------------------------------------------------------------
# 1-3. 주소 관련 : 공백 정리 + Title Case
#   숫자는 유지한다 (번지수)
# -----------------------------------------------------------------------------
for col in ["address", "city", "state", "country"]:
    df[col] = (df[col].fillna("")
               .str.replace(r"\s+", " ", regex=True)
               .str.strip()
               .str.title())

log_step("2. 주소 표기 표준화", len(df))


# -----------------------------------------------------------------------------
# 1-4. 전화번호 : 본체와 내선번호로 분리
#
#   원본: 449.977.1729x282
#     → phone_number : 4499771729  (숫자만 10자리)
#     → phone_ext    : 282
#
#   국가코드(+1-, 001-)는 미국 번호이므로 제거하고 10자리만 남긴다.
# -----------------------------------------------------------------------------
phone_raw = df["phone_number"].fillna("")

# 'x'를 기준으로 앞이 본체, 뒤가 내선
body = phone_raw.str.split("x").str[0]
ext = phone_raw.str.split("x").str[1]      # 'x'가 없으면 NaN

# 숫자만 남긴다
body_digits = body.str.replace(r"\D", "", regex=True)

# 국가코드 제거 : '+1-' 로 시작하면 맨 앞 1자리, '001-' 이면 맨 앞 3자리를 떼어낸다
body_digits = body_digits.where(~body.str.startswith("+1-"), body_digits.str[1:])
body_digits = body_digits.where(~body.str.startswith("001-"), body_digits.str[3:])

df["phone_number"] = body_digits
df["phone_ext"] = ext.str.replace(r"\D", "", regex=True)

# 정제 후에도 10자리가 아니면 플래그로 표시 (값은 유지)
df["phone_flag"] = None
bad_phone = df["phone_number"].str.len() != PHONE_DIGITS
df.loc[bad_phone, "phone_flag"] = f"자릿수이상(≠{PHONE_DIGITS})"

log_step("3. 전화번호 분리 및 표준화", len(df),
         f"내선 분리 {df['phone_ext'].notna().sum():,}건")


# =============================================================================
# ② 이름 복원 — 이메일과 대조
#
#   2단계에서 확정한 규칙:
#     이메일을 쓸 수 있는 경우 (이메일 있고 shared~ 아님)
#       - 현재 이름이 이메일과 일치        → 유지
#       - 반복 글자를 줄이면 일치          → 줄인 값 채택
#       - 둘 다 아니면                     → 유지 + 플래그
#     이메일을 쓸 수 없는 경우
#       - 반복쌍이 2개 이상이면            → 줄인 값 채택 (추정)
#       - 그 외                            → 유지
#
#   '무조건 줄이기'를 쓰지 않는 이유:
#     Aaron → Aron, Lee → Le 처럼 정상 이름이 망가진다.
#     검증 결과 이메일 일치율이 90.0% → 75.9% 로 떨어졌다.
# =============================================================================

def normalize_alpha(series):
    """비교용 정규화 : 영문자만 남기고 소문자로"""
    return series.fillna("").str.replace(r"[^A-Za-z]", "", regex=True).str.lower()

# 이메일에서 이름 부분 추출 : maria.day697@hotmail.com → maria / day
email_local = (df["email"].fillna("").str.split("@").str[0]
               .str.replace(r"\d+$", "", regex=True))
email_first = email_local.str.split(".").str[0]
email_last = email_local.str.split(".").str[-1]

# 이메일을 검증에 쓸 수 있는 행
usable = df["email"].notna() & ~shared_email

df["name_flag"] = None

for col, email_part in [("first_name", email_first), ("last_name", email_last)]:
    current = df[col]
    current_norm = normalize_alpha(current)

    # 반복 글자를 하나로 줄인 형태
    collapsed = current.str.replace(r"([A-Za-z])\1", r"\1", regex=True)
    collapsed_norm = normalize_alpha(collapsed)

    # 반복쌍 개수 (이메일이 없을 때 추정에 사용)
    pair_count = current.str.findall(r"([A-Za-z])\1").apply(len)

    matched = current_norm == email_part                       # 이미 일치
    restorable = (~matched) & (collapsed_norm == email_part)    # 줄이면 일치

    # 채택할 값을 결정한다
    result = current.copy()
    result = result.where(~(usable & restorable), collapsed)                  # 이메일로 복원
    result = result.where(~(~usable & (pair_count >= 2)), collapsed)          # 이메일 없어 추정 복원
    df[col] = result.str.title()

    # 플래그 : 이메일이 있는데 줄여도 일치하지 않는 경우 → 판단 보류
    unresolved = usable & ~matched & ~restorable
    df.loc[unresolved, "name_flag"] = "이메일불일치_보류"

n_restored = (usable & (normalize_alpha(df["first_name"]) == email_first)).sum()
log_step("4. 이름 복원 (이메일 대조)", len(df),
         f"보류 플래그 {df['name_flag'].notna().sum():,}건")


# -----------------------------------------------------------------------------
# 이메일 플래그
# -----------------------------------------------------------------------------
df["email_flag"] = None
df.loc[shared_email, "email_flag"] = "공용이메일"
df.loc[df["email"].isna(), "email_flag"] = "결측"


# =============================================================================
# ③ 파생 컬럼 생성
# =============================================================================

# -----------------------------------------------------------------------------
# 3-1. 가입 시점 나이
#   dob와 signup_date는 형식이 모두 정상이므로 계산에 바로 쓸 수 있다.
#   365.25로 나누는 것은 윤년을 반영한 근사치다.
# -----------------------------------------------------------------------------
dob = pd.to_datetime(df["dob"], errors="coerce", format="%Y-%m-%d")
signup = pd.to_datetime(df["signup_date"], errors="coerce", format="%Y-%m-%d")

df["age_at_signup"] = ((signup - dob).dt.days / 365.25).astype("float").round(0)

# 14세 미만 가입은 값을 고치지 않고 표시만 한다.
# dob와 signup 중 무엇이 틀렸는지 알 수 없고, 실제 미성년 가입일 수도 있다.
df["age_flag"] = None
df.loc[df["age_at_signup"] < MIN_SIGNUP_AGE, "age_flag"] = f"가입시_{MIN_SIGNUP_AGE}세미만"

# -----------------------------------------------------------------------------
# 3-2. 보유 기기 수
#   테이블을 분리한 뒤에도 간단한 집계는 조인 없이 할 수 있게 남겨둔다.
# -----------------------------------------------------------------------------
device_series = df["device_id(s)"].fillna("")
df["device_count"] = device_series.apply(
    lambda v: 0 if v.strip() == "" else len([x for x in v.split(";") if x.strip()])
)

log_step("5. 파생 컬럼 생성", len(df),
         f"14세미만 플래그 {df['age_flag'].notna().sum():,}건")


# =============================================================================
# ④ 완전 중복 행 제거
#
#   ①②로 표기를 통일했으므로, 이제 같은 고객의 중복 등록이 완전히 동일한 행이 되었다.
#   비교 대상은 원본 컬럼들만으로 한다.
#   (파생 컬럼과 플래그는 원본에서 계산된 값이므로 중복 판정에 영향이 없다)
# =============================================================================
#   [주의] 중복 판정에는 _raw 컬럼을 절대 포함시키면 안 된다.
#     'Peck'과 'PECK'은 정제 후 같은 값이 되지만, _raw에는 원래 표기가 그대로 남아 있다.
#     _raw를 비교에 넣으면 두 행이 여전히 다른 행으로 인식되어 중복 제거가 무력화된다.
#     아래 ORIGINAL_COLS는 원본 컬럼명만 사용하므로 _raw 컬럼이 자동으로 제외된다.
ORIGINAL_COLS = [c for c in raw.columns if c != "device_id(s)"] + ["device_id(s)"]

before = len(df)
dup_mask = df.duplicated(subset=ORIGINAL_COLS, keep="first")
removed_full = df[dup_mask].copy()
removed_full["삭제사유"] = "표기통일_후_완전중복"
df = df[~dup_mask].copy()

log_step("6. 완전 중복 행 제거", len(df), f"삭제 {before - len(df):,}행")


# =============================================================================
# ⑤ 잔여 기본키 충돌 처리
#
#   ④로도 안 지워진 행 = customer_id는 같은데 값이 여전히 다른 행.
#   실제 내용은 이름 철자가 한 글자 다른 경우다 (Russel vs Rusel).
#   동일 인물이 확실하므로 한 행만 남긴다.
#
#   남길 행을 고르는 기준 (우선순위 순):
#     ① name_flag가 없는 행 (이메일과 이름이 일치하는 쪽) — 더 신뢰할 수 있다
#     ② 결측이 적은 행
#     ③ 원본에서 먼저 나온 행
# =============================================================================
before = len(df)

# 정렬 키를 만든다. 값이 작을수록 먼저 오고, keep='first'로 남게 된다.
df["_우선순위1"] = df["name_flag"].notna().astype(int)      # 플래그 없는 행이 0 → 우선
df["_우선순위2"] = df.isna().sum(axis=1)                    # 결측이 적은 행이 우선
df["_원본순서"] = range(len(df))

df = df.sort_values(["_우선순위1", "_우선순위2", "_원본순서"])

pk_dup_mask = df.duplicated(subset=["customer_id"], keep="first")
removed_pk = df[pk_dup_mask].copy()
removed_pk["삭제사유"] = "기본키_잔여충돌(철자상이)"
df = df[~pk_dup_mask].copy()

# 정렬용 임시 컬럼 제거 후 원래 순서로 복원
df = df.sort_values("_원본순서").drop(columns=["_우선순위1", "_우선순위2", "_원본순서"])
removed_pk = removed_pk.drop(columns=["_우선순위1", "_우선순위2", "_원본순서"])

log_step("7. 기본키 잔여 충돌 처리", len(df), f"삭제 {before - len(df):,}행")


# =============================================================================
# ⑥ device 테이블 분리 (제1정규형 준수)
#
#   한 칸에 세미콜론으로 여러 값이 들어있던 것을 "기기 1개 = 1행"으로 펼친다.
#   explode() : 리스트가 담긴 셀을 여러 행으로 펼쳐주는 pandas 기능
#
#   왜 분리하는가:
#     SQL에서 '기기 3개 이상 보유 고객'을 찾으려면
#     현재 구조에서는 문자열의 세미콜론을 세야 한다 (느리고 부정확).
#     분리하면 GROUP BY customer_id HAVING COUNT(*) >= 3 으로 간단히 해결된다.
# =============================================================================
devices = (df[["customer_id", "device_id(s)"]]
           .assign(device_id=lambda d: d["device_id(s)"].fillna("").str.split(";"))
           .explode("device_id"))

devices["device_id"] = devices["device_id"].str.strip()
devices = devices[devices["device_id"] != ""][["customer_id", "device_id"]]
devices = devices.drop_duplicates()

log_step("8. device 테이블 분리", len(devices), "(기기 테이블 행 수)")

# 고객 테이블에서는 다중값 컬럼을 제거한다 (device_count로 대체)
df = df.drop(columns=["device_id(s)"])


# =============================================================================
# [저장]
# =============================================================================
CUSTOMER_COLS = [
    # --- 분석용 정제값 ---
    "customer_id", "first_name", "last_name", "email",
    "phone_number", "phone_ext", "gender", "dob", "signup_date",
    "age_at_signup", "address", "city", "state", "country",
    "device_count", "source",
    # --- 원본 보존 (고객 응대·본인 확인 시 이 값을 사용) ---
    "first_name_raw", "last_name_raw", "email_raw", "phone_number_raw",
    # --- 판단 보류 표시 ---
    "name_flag", "email_flag", "phone_flag", "age_flag",
]
df = df[CUSTOMER_COLS]

customers_path = os.path.join(CLEAN_DIR, "crm_customers_cleaned.csv")
devices_path = os.path.join(CLEAN_DIR, "crm_customer_devices_cleaned.csv")

df.to_csv(customers_path, index=False, encoding="utf-8-sig")
devices.to_csv(devices_path, index=False, encoding="utf-8-sig")

# 삭제된 행 전체를 따로 저장한다.
# "무엇을 지웠는지" 증빙이 없으면 정제 작업을 신뢰할 수 없다.
removed = pd.concat([removed_full, removed_pk], ignore_index=True)
removed.to_csv(os.path.join(REPORT_DIR, "삭제행_crm.csv"),
               index=False, encoding="utf-8-sig")

print()
print(f"고객 테이블 저장 : {customers_path}")
print(f"기기 테이블 저장 : {devices_path}")
print(f"삭제 행 기록     : 04_reports/삭제행_crm.csv ({len(removed):,}행)")


# =============================================================================
# [정제 로그]
# =============================================================================
lines = []
lines.append("=" * 78)
lines.append("crm_50000_customers 정제 로그 (4단계)")
lines.append("=" * 78)
lines.append("")
lines.append("[단계별 행 수 변화]")
lines.append("-" * 78)
lines.append(f"{'단계':<36}{'행 수':>10}   비고")
for s in steps:
    lines.append(f"{s['단계']:<36}{s['행 수']:>10,}   {s['비고']}")
lines.append("")
lines.append(f"최종 고객 수 : {len(df):,}명  (원본 {len(raw):,}행 → {len(raw)-len(df):,}행 감소)")
lines.append(f"최종 기기 수 : {len(devices):,}건")
lines.append("")
lines.append("  ※ 행이 줄어든 것은 데이터 손실이 아니라 중복 고객 제거 결과다.")
lines.append("     삭제된 행은 04_reports/삭제행_crm.csv 에 전량 보관되어 있다.")
lines.append("")

lines.append("-" * 78)
lines.append("[기본키 상태]")
lines.append("-" * 78)
lines.append(f"customer_id 고유 개수 : {df['customer_id'].nunique():,}")
lines.append(f"customer_id 중복      : {df['customer_id'].duplicated().sum():,}건  ← 0이어야 정상")
lines.append("")

lines.append("-" * 78)
lines.append("[플래그 현황 — 값을 고치지 않고 표시만 한 건]")
lines.append("-" * 78)
for col in ["name_flag", "email_flag", "phone_flag", "age_flag"]:
    counts = df[col].value_counts(dropna=True)
    lines.append(f"\n  ■ {col}")
    if len(counts) == 0:
        lines.append("      없음")
    for k, v in counts.items():
        lines.append(f"      {k:<28} {v:>8,}건")
lines.append("")

lines.append("-" * 78)
lines.append("[원본 대비 값이 변경된 건수]")
lines.append("-" * 78)
lines.append("  개인정보 컬럼은 원본 값을 _raw 컬럼에 함께 보관한다.")
lines.append("  아래는 정제값과 원본값이 실제로 달라진 건수다.")
lines.append("")
for col in PRESERVE_COLS:
    changed = (df[col].fillna("") != df[f"{col}_raw"].fillna("")).sum()
    lines.append(f"  {col:<16} {changed:>8,}건 / {len(df):,}건 변경")
lines.append("")
lines.append("  ※ 이 정제본은 '분석 전용 사본'이다.")
lines.append("     고객 응대·본인 확인·발송에는 _raw 컬럼 또는 원본 파일을 사용해야 한다.")
lines.append("     SQL에서 수정된 건만 보려면:")
lines.append("       SELECT * FROM crm_customers WHERE first_name <> first_name_raw;")
lines.append("")

lines.append("-" * 78)
lines.append("[정제 후 주요 컬럼 상태]")
lines.append("-" * 78)
lines.append(f"전화번호 10자리 비율   : "
             f"{(df['phone_number'].str.len()==PHONE_DIGITS).sum():,}명 / {len(df):,}명 "
             f"(자릿수 이상 {(df['phone_number'].str.len()!=PHONE_DIGITS).sum():,}건)")
lines.append(f"내선번호 보유 고객     : {df['phone_ext'].notna().sum():,}명")
lines.append(f"이메일 결측            : {df['email'].isna().sum():,}건")
lines.append(f"가입 시점 나이 범위    : "
             f"{df['age_at_signup'].min():.0f}세 ~ {df['age_at_signup'].max():.0f}세")
lines.append(f"기기 2개 이상 보유 고객 : {(df['device_count']>=2).sum():,}명")
lines.append("")
lines.append("[정제 후 이름 샘플 10건]")
lines.append(df[["first_name", "last_name", "email", "name_flag"]].head(10).to_string(index=False))

with open(os.path.join(REPORT_DIR, "정제로그_crm.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print()
print("\n".join(lines))
