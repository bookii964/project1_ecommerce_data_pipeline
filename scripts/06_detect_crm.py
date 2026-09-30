# =============================================================================
# 파일명 : 06_detect_crm.py
# 단계   : 3단계 - 비정상 데이터 색출 및 유형 분류 (CRM)
#
# [목적]
#   2단계 규칙서(데이터사전_crm.md)를 코드로 옮겨서 규칙 위반 건을 전부 찾아낸다.
#   이 단계에서도 데이터를 고치지 않는다. 찾아서 기록만 한다.
#
# [product_catalog의 3단계와 달라진 점]
#   ① iterrows() 대신 벡터 연산(마스크 방식)을 쓴다
#      마스크란 각 행이 조건에 맞는지를 True/False로 나타낸 컬럼이다.
#      예: mask = df['first_name'].str.contains(r'\d')
#          → 5만 개의 True/False가 한 번에 만들어진다
#      product_catalog 방식(한 행씩 for문)으로 5만 행을 돌면 수십 배 느리다.
#
#   ② 분류 구분에 '구조'를 추가했다
#      device_id(s)처럼 값이 틀린 게 아니라 테이블 설계가 잘못된 경우다.
#
#   ③ 중복 검사와 교차 검증이 추가됐다
#      한 컬럼만 봐서는 찾을 수 없는 문제들이다.
#
# [입력]  01_raw/crm_50000_customers_dirty_v3.csv
# [출력]  02_profiling/crm/
#           - 06_이상데이터_상세.csv   : 위반 1건당 1행
#           - 07_유형별_집계.csv       : 컬럼×유형별 건수
#           - 08_진단요약.txt          : 사람이 읽는 요약
#
# [분류 구분 4가지]
#   오염     : 값 자체가 틀림. 반드시 고쳐야 함
#   표준화   : 값은 맞는데 표기만 다름
#   확인필요 : 맞는지 틀린지 알 수 없음. 값을 유지하고 플래그만
#   구조     : 값은 정상이나 테이블 설계가 관계형 원칙에 어긋남
# =============================================================================

import os
import re
import pandas as pd


def read_csv_safe(path, **kwargs):
    """인코딩 안전 읽기 (엑셀로 저장된 CP949 파일 대응)"""
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
OUTPUT_DIR = os.path.join(PROJECT_DIR, "02_profiling", "crm")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 2단계에서 확정한 규칙 상수
# -----------------------------------------------------------------------------
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                          r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
VALID_GENDER = ["M", "F", "O"]
VALID_SOURCE = ["referral", "web", "app"]
MIN_SIGNUP_AGE = 14          # 이 나이 미만 가입은 '확인필요'
PHONE_DIGITS = 10            # 내선·국가코드를 뺀 전화번호 본체 자릿수


df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(df):,}행 × {len(df.columns)}열")
print()


# -----------------------------------------------------------------------------
# [위반 기록 도구]
#   마스크(True/False 배열)를 받아서, True인 행들을 위반 목록에 추가한다.
#   product_catalog에서는 for문 안에서 한 건씩 기록했지만,
#   여기서는 조건에 맞는 행을 한꺼번에 담는다.
# -----------------------------------------------------------------------------
issues = []

def add(mask, column, issue_type, kind):
    """mask가 True인 행을 위반 목록에 추가"""
    n = int(mask.sum())
    if n == 0:
        return
    sub = df.loc[mask, ["customer_id"]].copy()
    sub["행번호"] = sub.index
    sub["컬럼"] = column
    # 해당 컬럼의 원본값을 함께 기록 (나중에 눈으로 확인할 때 필요)
    sub["원본값"] = df.loc[mask, column].values if column in df.columns else ""
    sub["위반유형"] = issue_type
    sub["분류구분"] = kind
    issues.append(sub)
    print(f"  [{kind}] {column:<14} {issue_type:<22} {n:>7,}건")


# =============================================================================
# [검사 1] customer_id — 기본키
# =============================================================================
print("[검사 1] customer_id")

cid = df["customer_id"].fillna("")

# 형식 위반 : UUID 패턴이 아닌 값
add(~cid.str.match(UUID_PATTERN), "customer_id", "UUID형식위반", "오염")
add(df["customer_id"].isna(), "customer_id", "결측", "오염")

# 중복 : 같은 id가 2번 이상 등장하는 모든 행
dup_all = df["customer_id"].duplicated(keep=False)

# 완전 중복(14개 컬럼 전부 동일)과 준중복(일부만 다름)을 구분한다.
# duplicated()는 '앞에 같은 행이 있었는가'를 보므로, keep=False로 모든 관련 행을 잡는다.
full_dup = df.duplicated(keep=False)
add(full_dup, "customer_id", "완전중복행", "오염")
add(dup_all & ~full_dup, "customer_id", "준중복(일부컬럼_상이)", "오염")
print()


# =============================================================================
# [검사 2] first_name / last_name
# =============================================================================
print("[검사 2] 이름")

for col in ["first_name", "last_name"]:
    s = df[col].fillna("")
    stripped = s.str.strip()

    add(df[col].isna(), col, "결측", "오염")
    add(s != stripped, col, "앞뒤공백", "표준화")
    add(stripped.str.isupper() & (stripped != ""), col, "전부대문자", "표준화")
    add(stripped.str.islower() & (stripped != ""), col, "전부소문자", "표준화")

    # 사람 이름에 숫자가 들어갈 이유가 없다 → 오염
    add(stripped.str.contains(r"\d", regex=True), col, "숫자삽입", "오염")

    # 영문자와 공백 외의 문자 (예: Tara*, Jonathan!) → 오염
    add(stripped.str.contains(r"[^A-Za-z ]", regex=True), col, "특수문자부착", "오염")

    # 같은 글자가 붙어서 반복되는 쌍이 2개 이상 → 글자 반복 오타
    #   findall(r'([A-Za-z])\1') 은 'aa','bb' 같은 반복쌍을 모두 찾는다
    #   Aaron(1개), Lee(1개) 같은 정상 이름과 구분하기 위해 2개 이상만 잡는다
    pair_count = stripped.str.findall(r"([A-Za-z])\1").apply(len)
    add(pair_count >= 2, col, "글자반복_오타(쌍2개이상)", "오염")
print()


# =============================================================================
# [검사 3] email
# =============================================================================
print("[검사 3] email")

email = df["email"].fillna("")

add(df["email"].isna(), "email", "결측(필수항목아님)", "확인필요")
add(email.str.strip() != email, "email", "앞뒤공백", "표준화")
add(email.str.contains(r"[A-Z]", regex=True), "email", "대문자포함", "표준화")

# 이메일 형식 검사 (결측이 아닌 행만)
valid_email_form = email.str.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
add(df["email"].notna() & ~valid_email_form, "email", "형식위반", "오염")

# 공용 이메일 : 이름 검증에 쓸 수 없으므로 표시가 필요하다
shared_email = email.str.startswith("shared")
add(shared_email, "email", "공용이메일", "확인필요")

# 이메일 중복 (2번째 등장부터)
add(df["email"].notna() & df["email"].duplicated(keep=False) & ~shared_email,
    "email", "이메일중복", "확인필요")
print()


# =============================================================================
# [검사 4] 이름 vs 이메일 교차 검증
#   컬럼 하나만 봐서는 알 수 없는 문제다.
#   이메일이 'firstname.lastname숫자@도메인' 형식이므로 이름과 대조할 수 있다.
# =============================================================================
print("[검사 4] 이름 vs 이메일 교차검증")

def normalize_alpha(series):
    """영문자만 남기고 소문자로 — 비교용 정규화"""
    return series.fillna("").str.replace(r"[^A-Za-z]", "", regex=True).str.lower()

# 이메일에서 이름 부분 추출 : maria.day697@hotmail.com → maria / day
email_local = email.str.split("@").str[0].str.replace(r"\d+$", "", regex=True)
email_first = email_local.str.split(".").str[0]
email_last = email_local.str.split(".").str[-1]

name_first = normalize_alpha(df["first_name"])
name_last = normalize_alpha(df["last_name"])

# 반복 글자를 줄인 형태도 함께 비교한다 (KKeevvin → kevin)
collapsed_first = name_first.str.replace(r"([a-z])\1", r"\1", regex=True)
collapsed_last = name_last.str.replace(r"([a-z])\1", r"\1", regex=True)

# 이메일을 검증에 쓸 수 있는 행 : 이메일이 있고 공용이 아닌 경우
usable = df["email"].notna() & ~shared_email

matched = (name_first == email_first) & (name_last == email_last)
restorable = ((collapsed_first == email_first) & (collapsed_last == email_last)) & ~matched

# 복원 가능 : 반복 글자를 줄이면 이메일과 일치 → 4단계에서 자동 복원
add(usable & restorable, "first_name", "이메일로_복원가능", "오염")

# 불일치 : 줄여도 이메일과 다름 → 무엇이 틀렸는지 알 수 없으므로 유지+플래그
add(usable & ~matched & ~restorable, "first_name", "이메일_불일치(판단보류)", "확인필요")
print()


# =============================================================================
# [검사 5] phone_number
# =============================================================================
print("[검사 5] phone_number")

phone = df["phone_number"].fillna("")

add(df["phone_number"].isna(), "phone_number", "결측", "오염")

# 내선번호 포함 : 'x' 뒤에 붙은 숫자
add(phone.str.contains("x"), "phone_number", "내선번호_포함", "표준화")

# 국가코드 접두 : +1- 또는 001-
add(phone.str.startswith("+1-") | phone.str.startswith("001-"),
    "phone_number", "국가코드_접두", "표준화")

# 구분자 혼재 : 점, 하이픈, 괄호가 섞여 있음
add(phone.str.contains(r"[.\-()]", regex=True), "phone_number", "구분자_혼재", "표준화")

# 내선과 국가코드를 제거한 본체가 10자리인지 확인
#   split('x')[0] → 내선 제거
#   국가코드 제거 후 숫자만 남긴 길이를 센다
body = phone.str.split("x").str[0]
body_digits = body.str.replace(r"\D", "", regex=True)
# +1- 또는 001- 로 시작하면 국가번호를 떼어낸다
body_digits = body_digits.where(~body.str.startswith("+1-"), body_digits.str[1:])
body_digits = body_digits.where(~body.str.startswith("001-"), body_digits.str[3:])

add(df["phone_number"].notna() & (body_digits.str.len() != PHONE_DIGITS),
    "phone_number", f"본체_자릿수이상(≠{PHONE_DIGITS})", "오염")
print()


# =============================================================================
# [검사 6] gender / source — 허용값 검사
# =============================================================================
print("[검사 6] gender / source")

add(~df["gender"].isin(VALID_GENDER), "gender", "허용값외", "오염")
add(~df["source"].isin(VALID_SOURCE), "source", "허용값외", "오염")
print("  (위반이 없으면 아무것도 출력되지 않습니다 — 정상입니다)")
print()


# =============================================================================
# [검사 7] dob / signup_date — 날짜 및 조합 검증
# =============================================================================
print("[검사 7] 날짜")

# errors='coerce' : 날짜로 못 바꾸는 값은 NaT(결측)로 만든다 → 형식 위반 검출
dob = pd.to_datetime(df["dob"], errors="coerce", format="%Y-%m-%d")
signup = pd.to_datetime(df["signup_date"], errors="coerce", format="%Y-%m-%d")

add(df["dob"].notna() & dob.isna(), "dob", "날짜형식위반", "오염")
add(df["signup_date"].notna() & signup.isna(), "signup_date", "날짜형식위반", "오염")

today = pd.Timestamp.today().normalize()
add(dob > today, "dob", "미래날짜", "오염")
add(signup > today, "signup_date", "미래날짜", "오염")

# 가입일이 생년월일보다 앞선 경우 = 태어나기 전에 가입
add(signup < dob, "signup_date", "가입일이_생년월일보다_앞섬", "오염")

# 가입 시점 나이가 기준 미만 → 값을 고칠 근거가 없으므로 확인필요
age_at_signup = (signup - dob).dt.days / 365.25
add(age_at_signup < MIN_SIGNUP_AGE, "signup_date",
    f"가입시_{MIN_SIGNUP_AGE}세미만", "확인필요")
print()


# =============================================================================
# [검사 8] 주소 관련 컬럼
#   주의 : address의 숫자는 번지수이므로 오염이 아니다.
#          이름과 같은 기준을 적용하면 5만 건 전부 오탐이 된다.
# =============================================================================
print("[검사 8] 주소")

for col in ["address", "city", "state", "country"]:
    s = df[col].fillna("")
    stripped = s.str.strip()
    add(df[col].isna(), col, "결측", "오염")
    add(s != stripped, col, "앞뒤공백", "표준화")
    add(stripped.str.isupper() & (stripped != ""), col, "전부대문자", "표준화")
    add(stripped.str.islower() & (stripped != ""), col, "전부소문자", "표준화")

# state(미국 주)와 country(미국 아님)의 모순
us_country = df["country"].fillna("").str.contains("United States")
has_state = df["state"].notna()
add(has_state & ~us_country, "state", "state-country_모순", "확인필요")
print()


# =============================================================================
# [검사 9] device_id(s) — 구조 문제
# =============================================================================
print("[검사 9] device_id(s)")

device = df["device_id(s)"].fillna("")
add(df["device_id(s)"].isna(), "device_id(s)", "결측", "오염")

# 한 칸에 값이 2개 이상 = 제1정규형 위반
add(device.str.contains(";"), "device_id(s)", "다중값(제1정규형_위반)", "구조")

# 개별 기기 ID의 형식 검사 (분리해서 확인)
exploded = device.str.split(";").explode().str.strip()
exploded = exploded[exploded != ""]
bad_device = ~exploded.str.match(UUID_PATTERN)
print(f"  [참고] 개별 기기 ID {len(exploded):,}건 중 형식위반 {int(bad_device.sum()):,}건")
print(f"  [참고] 고유 기기 ID {exploded.nunique():,}개 "
      f"(중복 등록 {len(exploded) - exploded.nunique():,}건)")
print()


# =============================================================================
# [출력 1] 이상 데이터 상세
# =============================================================================
issue_df = pd.concat(issues, ignore_index=True)
issue_df = issue_df[["행번호", "customer_id", "컬럼", "원본값", "위반유형", "분류구분"]]
issue_df = issue_df.sort_values(["행번호", "컬럼"])

issue_df.to_csv(
    os.path.join(OUTPUT_DIR, "06_이상데이터_상세.csv"),
    index=False, encoding="utf-8-sig"
)
print(f"06_이상데이터_상세.csv 저장 완료 (총 {len(issue_df):,}건)")


# =============================================================================
# [출력 2] 유형별 집계
# =============================================================================
summary = (
    issue_df.groupby(["컬럼", "분류구분", "위반유형"])
    .size().reset_index(name="건수")
    .sort_values(["컬럼", "분류구분", "건수"], ascending=[True, True, False])
)
summary.to_csv(
    os.path.join(OUTPUT_DIR, "07_유형별_집계.csv"),
    index=False, encoding="utf-8-sig"
)
print("07_유형별_집계.csv 저장 완료")


# =============================================================================
# [출력 3] 진단 요약
# =============================================================================
lines = []
lines.append("=" * 78)
lines.append("crm_50000_customers 오염 진단 요약 (3단계)")
lines.append("=" * 78)
lines.append(f"전체 행 수        : {len(df):,}")
lines.append(f"위반 건수(누적)   : {len(issue_df):,}")

affected = issue_df["행번호"].nunique()
lines.append(f"위반이 있는 행 수 : {affected:,} / {len(df):,} ({affected/len(df)*100:.1f}%)")
lines.append("")
lines.append("  ※ 두 숫자를 구분해야 한다.")
lines.append("     한 행이 여러 컬럼에서 위반할 수 있고, 한 값에 여러 오염이 겹칠 수 있다.")
lines.append("     예: ' KKeevvin '는 앞뒤공백 + 글자반복 2건으로 집계된다.")
lines.append("")

lines.append("-" * 78)
lines.append("[분류 구분별 건수]")
lines.append("-" * 78)
for kind, cnt in issue_df["분류구분"].value_counts().items():
    lines.append(f"  {kind:<10} : {cnt:>8,}건")
lines.append("")
lines.append("  오염     = 값이 틀림. 4단계에서 수정 또는 삭제")
lines.append("  표준화   = 값은 맞고 표기만 다름. 형식 통일")
lines.append("  확인필요 = 정답을 알 수 없음. 값 유지 + 플래그 표시")
lines.append("  구조     = 값은 정상이나 테이블 설계 문제. 테이블 분리로 해결")
lines.append("")

lines.append("-" * 78)
lines.append("[컬럼별 · 유형별 상세]")
lines.append("-" * 78)
for col in df.columns:
    sub = issue_df[issue_df["컬럼"] == col]
    lines.append(f"\n■ {col}  (총 {len(sub):,}건)")
    if len(sub) == 0:
        lines.append("    위반 없음 — 정상 컬럼")
        continue
    for (kind, itype), cnt in sub.groupby(["분류구분", "위반유형"]).size().items():
        lines.append(f"    [{kind}] {itype:<28} {cnt:>8,}건")

lines.append("")
lines.append("-" * 78)
lines.append("[4단계 처리 예정 요약]")
lines.append("-" * 78)
lines.append(f"  자동 수정   : 표기 표준화 및 오염 값 정정")
lines.append(f"  행 삭제     : 표기 통일 후 완전 중복 행 (약 1,789건 예상)")
lines.append(f"  플래그 표시 : {int((issue_df['분류구분']=='확인필요').sum()):,}건")
lines.append(f"  테이블 분리 : device_id(s) → customer_devices")

with open(os.path.join(OUTPUT_DIR, "08_진단요약.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("08_진단요약.txt 저장 완료")
print()
print("\n".join(lines))
