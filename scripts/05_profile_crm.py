# =============================================================================
# 파일명 : 05_profile_crm.py
# 단계   : 1단계 - 컬럼별 프로파일링 (CRM 고객 마스터)
#
# [목적]
#   crm_50000_customers 파일을 관찰해서 "무엇이 정상인지"를 파악한다.
#   product_catalog와 동일한 목적이지만, 데이터 성격이 달라 접근 방식을 바꾼다.
#
# [product_catalog와 달라진 점 3가지]
#
#   ① 행이 100배 많다 (500행 → 50,000행)
#      → iterrows()로 한 행씩 돌면 느리다. pandas 벡터 연산을 쓴다.
#        벡터 연산이란 "컬럼 전체에 한 번에 연산을 적용"하는 방식이다.
#        예: df['name'].str.strip()  ← 5만 개를 한 번에 처리
#
#   ② 컬럼이 14개다
#      → 모든 컬럼의 고유값을 전부 출력하면 파일이 수십만 줄이 된다.
#        컬럼을 성격별로 나눠서 다르게 관찰한다.
#          - 범주형(gender, source, state) : 고유값 전체 확인
#          - 식별자(customer_id, email)     : 중복·형식만 확인
#          - 자유 텍스트(name, address)     : 오염 패턴별 건수만 집계
#
#   ③ 새로운 유형의 문제가 있다
#      - 기본키 중복 : customer_id가 유일하지 않다
#      - 다중값 컬럼 : device_id(s) 한 칸에 여러 값이 세미콜론으로 들어있다
#      - 컬럼 간 모순 : 생년월일과 가입일을 함께 봐야 발견되는 오류
#      → 컬럼을 하나씩 보는 것만으로는 못 찾는다. 교차 검증 항목을 따로 만든다.
#
# [입력]  01_raw/crm_50000_customers_dirty_v3.csv
# [출력]  02_profiling/crm/
#           - 01_기본정보.txt          : 행/열, 결측, 고유값 요약
#           - 02_범주형_값분포.txt      : 값 종류가 적은 컬럼의 전체 목록
#           - 03_텍스트_오염패턴.csv    : 이름/주소 등의 오염 유형별 건수
#           - 04_중복검사.csv          : customer_id 중복 건 전체 목록
#           - 05_교차검증.txt          : 컬럼을 함께 봐야 보이는 문제
# =============================================================================

import os
import re
import pandas as pd


# -----------------------------------------------------------------------------
# [공통] 인코딩 안전 읽기 (엑셀로 저장된 파일 대응)
# -----------------------------------------------------------------------------
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
OUTPUT_DIR = os.path.join(PROJECT_DIR, "02_profiling", "crm")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [1] 원본 읽기 (전부 문자열로 — 오염을 있는 그대로 보기 위해)
# -----------------------------------------------------------------------------
df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(df):,}행 × {len(df.columns)}열")
print()


# =============================================================================
# [출력 1] 기본 정보
# =============================================================================
lines = []
lines.append("=" * 88)
lines.append("crm_50000_customers 기본 정보")
lines.append("=" * 88)
lines.append(f"전체 행 수 : {len(df):,}")
lines.append(f"전체 열 수 : {len(df.columns)}")
lines.append("")
lines.append("컬럼 목록 및 추정 역할")
lines.append("-" * 88)
role_guess = {
    "customer_id": "고객 고유번호 (기본키 후보)",
    "first_name": "이름",
    "last_name": "성",
    "email": "이메일",
    "phone_number": "전화번호",
    "gender": "성별 (범주형)",
    "dob": "생년월일",
    "signup_date": "가입일",
    "address": "상세주소",
    "city": "도시",
    "state": "주/도",
    "country": "국가",
    "device_id(s)": "보유 기기 ID (여러 개 가능)",
    "source": "유입 경로 (범주형)",
}
for c in df.columns:
    lines.append(f"  {c:<16} {role_guess.get(c, '(미분류)')}")
lines.append("")

lines.append("-" * 88)
lines.append("[컬럼별 결측 및 고유값]")
lines.append("-" * 88)
lines.append(f"{'컬럼명':<16}{'결측':>10}{'결측률':>10}{'고유값':>12}{'고유율':>10}")
for c in df.columns:
    n_null = df[c].isna().sum()
    n_uniq = df[c].nunique()
    lines.append(
        f"{c:<16}{n_null:>10,}{n_null/len(df)*100:>9.1f}%{n_uniq:>12,}{n_uniq/len(df)*100:>9.1f}%"
    )
lines.append("")
lines.append("  ※ 고유율 100%에 가까우면 식별자 성격, 낮으면 범주형 성격이다.")
lines.append("     customer_id는 기본키 후보이므로 고유율이 100%여야 정상이다.")
lines.append("")

lines.append("-" * 88)
lines.append("[중복 검사]")
lines.append("-" * 88)
n_full_dup = df.duplicated().sum()
n_id_dup_rows = df["customer_id"].duplicated(keep=False).sum()
n_id_dup_keys = df.loc[df["customer_id"].duplicated(keep=False), "customer_id"].nunique()
lines.append(f"모든 컬럼이 동일한 완전 중복 행 : {n_full_dup:,}건")
lines.append(f"customer_id가 겹치는 행 수      : {n_id_dup_rows:,}건")
lines.append(f"겹치는 customer_id 종류         : {n_id_dup_keys:,}개")
lines.append("")
lines.append("  ※ 두 숫자가 다른 것이 핵심이다.")
lines.append("     완전 중복은 '똑같은 행이 두 번 들어온 것'이라 하나만 남기면 된다.")
lines.append("     하지만 customer_id는 같은데 다른 컬럼 값이 미묘하게 다른 행도 있다.")
lines.append("     (예: 이름이 'Melissa Peck' vs 'Melissa PECK')")
lines.append("     이런 '준중복'은 표기를 먼저 통일한 뒤에야 중복으로 인식된다.")
lines.append("     → 즉 정제 순서가 중복 제거 결과를 바꾼다. 2단계에서 순서를 정할 것이다.")

with open(os.path.join(OUTPUT_DIR, "01_기본정보.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("01_기본정보.txt 저장 완료")


# =============================================================================
# [출력 2] 범주형 컬럼 값 분포
#   값 종류가 적은 컬럼은 전체 목록을 봐야 오염을 찾을 수 있다.
#   state(50종), country(243종)는 많지만 의미상 범주형이므로 함께 확인한다.
# =============================================================================
CATEGORICAL = ["gender", "source", "state", "country"]

lines = []
lines.append("=" * 88)
lines.append("범주형 컬럼 값 분포")
lines.append("=" * 88)
lines.append("")

for c in CATEGORICAL:
    counts = df[c].value_counts(dropna=False)
    lines.append("-" * 88)
    lines.append(f"[{c}]  고유값 {df[c].nunique():,}종  /  결측 {df[c].isna().sum():,}건")
    lines.append("-" * 88)
    # 종류가 많으면 상위 30개만 (전체를 다 보려면 별도 CSV를 확인)
    show = counts if len(counts) <= 60 else counts.head(30)
    for value, cnt in show.items():
        lines.append(f"  '{value}'  →  {cnt:,}건")
    if len(counts) > 60:
        lines.append(f"  ... (총 {len(counts)}종 중 상위 30종만 표시)")
    lines.append("")

with open(os.path.join(OUTPUT_DIR, "02_범주형_값분포.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("02_범주형_값분포.txt 저장 완료")


# =============================================================================
# [출력 3] 텍스트 컬럼 오염 패턴 집계
#
#   이름·주소 같은 자유 텍스트는 고유값이 수천 개라 목록을 봐도 소용없다.
#   대신 "어떤 패턴의 오염이 몇 건인지"를 센다.
#
#   벡터 연산 사용 예 :
#     df[c].str.strip()          → 컬럼 전체의 앞뒤 공백 제거
#     df[c].str.contains(정규식)  → 조건에 맞는 행을 True/False로 반환
#     .sum()                     → True 개수를 센다 (True=1로 계산되므로)
# =============================================================================
TEXT_COLUMNS = ["first_name", "last_name", "address", "city"]

rows = []
for c in TEXT_COLUMNS:
    s = df[c].fillna("")
    stripped = s.str.strip()

    rows.append({
        "컬럼": c,
        "앞뒤공백": int((s != stripped).sum()),
        "전부대문자": int(stripped.str.isupper().sum()),
        "전부소문자": int(stripped.str.islower().sum()),
        "숫자포함": int(stripped.str.contains(r"\d", regex=True).sum()),
        "특수문자포함": int(stripped.str.contains(r"[^A-Za-z0-9 .]", regex=True).sum()),
        # 같은 글자가 3번 이상 반복되거나, 반복 글자쌍이 2개 이상 → 문자 중복 오염 의심
        # (Aaron, Lee, Brooks 처럼 반복이 1개인 정상 이름과 구분하기 위한 기준)
        "반복글자쌍_2개이상": int(
            stripped.str.findall(r"([A-Za-z])\1").apply(len).ge(2).sum()
        ),
    })

pattern_df = pd.DataFrame(rows)
pattern_df.to_csv(
    os.path.join(OUTPUT_DIR, "03_텍스트_오염패턴.csv"),
    index=False, encoding="utf-8-sig"
)
print("03_텍스트_오염패턴.csv 저장 완료")
print()
print(pattern_df.to_string(index=False))
print()


# =============================================================================
# [출력 4] customer_id 중복 건 전체 목록
#   기본키 중복은 가장 심각한 문제이므로 전 건을 따로 뽑아둔다.
#   같은 id끼리 나란히 정렬해서, 어떤 컬럼이 다른지 눈으로 비교할 수 있게 한다.
# =============================================================================
dup_mask = df["customer_id"].duplicated(keep=False)
dup_df = df[dup_mask].sort_values("customer_id").copy()

# 각 중복 그룹에서 완전히 동일한 행인지, 일부만 다른 행인지 구분해서 표시한다
def classify_group(group):
    # drop_duplicates() 후 1행만 남으면 모든 행이 동일 → '완전중복'
    return "완전중복" if len(group.drop_duplicates()) == 1 else "준중복(일부컬럼 상이)"

dup_df["중복유형"] = dup_df.groupby("customer_id", group_keys=False).apply(
    lambda g: pd.Series([classify_group(g)] * len(g), index=g.index)
)

dup_df.to_csv(
    os.path.join(OUTPUT_DIR, "04_중복검사.csv"),
    index=False, encoding="utf-8-sig"
)
print("04_중복검사.csv 저장 완료")


# =============================================================================
# [출력 5] 교차 검증 — 컬럼을 함께 봐야 보이는 문제
#
#   컬럼을 하나씩 볼 때는 다 정상으로 보이는데, 두 컬럼을 같이 보면
#   모순이 드러나는 경우가 있다. 이런 오류가 실무에서 가장 찾기 어렵다.
# =============================================================================
lines = []
lines.append("=" * 88)
lines.append("교차 검증 — 컬럼 간 모순 확인")
lines.append("=" * 88)
lines.append("")

# --- 검증 A : 생년월일 vs 가입일 ---------------------------------------------
# 날짜 형식은 둘 다 YYYY-MM-DD로 깨끗하다. 문제는 '값의 조합'이다.
dob = pd.to_datetime(df["dob"], errors="coerce")
signup = pd.to_datetime(df["signup_date"], errors="coerce")
age_at_signup = (signup - dob).dt.days / 365.25

lines.append("-" * 88)
lines.append("[A] 생년월일(dob) vs 가입일(signup_date)")
lines.append("-" * 88)
lines.append(f"  dob 날짜 형식 오류      : {dob.isna().sum():,}건")
lines.append(f"  signup 날짜 형식 오류   : {signup.isna().sum():,}건")
lines.append(f"  dob 범위                : {dob.min().date()} ~ {dob.max().date()}")
lines.append(f"  signup 범위             : {signup.min().date()} ~ {signup.max().date()}")
lines.append("")
lines.append(f"  가입 시점 나이 최소     : {age_at_signup.min():.1f}세")
lines.append(f"  가입 시점 나이 최대     : {age_at_signup.max():.1f}세")
lines.append(f"  가입일이 생일보다 앞선 행 : {(age_at_signup < 0).sum():,}건")
lines.append(f"  가입 시점 14세 미만     : {(age_at_signup < 14).sum():,}건")
lines.append("")
lines.append("  ※ 날짜 형식은 전부 정상인데도 문제가 있다.")
lines.append("     한 컬럼만 보면 1954~2007년생, 2013~2025년 가입으로 전부 그럴듯하다.")
lines.append("     두 컬럼을 함께 봐야 '6세에 가입한 고객' 같은 모순이 드러난다.")
lines.append("     → 이런 건을 오염으로 볼지, 실제 미성년 가입으로 볼지는 2단계에서 판단한다.")
lines.append("")

# --- 검증 B : 이메일 vs 이름 ------------------------------------------------
# 이메일이 'firstname.lastname숫자@도메인' 형식이라, 이름과 대조할 수 있다.
# 이름이 오염된 경우(KKeevvin) 이메일로 원래 이름을 추정할 수 있는지 확인한다.
def normalize_alpha(value):
    """영문자만 남기고 소문자로 — 비교를 위한 정규화"""
    return re.sub(r"[^a-z]", "", str(value).lower())

email_local = df["email"].fillna("").str.split("@").str[0]
email_local_nodigit = email_local.str.replace(r"\d+$", "", regex=True)
email_first = email_local_nodigit.str.split(".").str[0]
email_last = email_local_nodigit.str.split(".").str[-1]

name_first = df["first_name"].map(normalize_alpha)
name_last = df["last_name"].map(normalize_alpha)

match = (name_first == email_first) & (name_last == email_last)
has_email = df["email"].notna()
shared_email = df["email"].fillna("").str.startswith("shared")

lines.append("-" * 88)
lines.append("[B] 이메일 vs 이름")
lines.append("-" * 88)
lines.append(f"  이메일 결측                 : {(~has_email).sum():,}건")
lines.append(f"  이메일 중복                 : {df['email'].dropna().duplicated().sum():,}건")
lines.append(f"  공용 이메일(shared~)        : {shared_email.sum():,}건")
lines.append(f"  이메일과 이름이 일치         : {match.sum():,}건 ({match.mean()*100:.1f}%)")
lines.append(f"  이메일과 이름이 불일치       : {(has_email & ~match).sum():,}건")
lines.append("")
lines.append("  ※ 이메일이 'firstname.lastname숫자@도메인' 형식이므로 이름과 대조가 가능하다.")
lines.append("     'KKeevvin Cantu' 의 이메일이 kevin.cantu968@gmail.com 이라는 점은,")
lines.append("     이메일을 이름 복원의 참고자료로 쓸 수 있다는 뜻이다.")
lines.append("     단, 불일치 건 중에는 아래 3가지가 섞여 있어 구분이 필요하다:")
lines.append("       ① 이름이 오염된 경우      → 이메일로 복원 가능")
lines.append("       ② 공용 이메일(shared~)    → 대조 불가")
lines.append("       ③ 아예 다른 사람의 이메일  → 이메일 자체가 오염 (예: Denise Cooper / diana.smith@)")
lines.append("     → 무조건 이메일을 믿고 이름을 덮어쓰면 안 된다. 2단계에서 조건을 정한다.")
lines.append("")

# --- 검증 C : device_id(s) 다중값 -------------------------------------------
# 한 칸에 여러 값이 세미콜론으로 들어있다. 관계형 DB 설계 원칙(1정규형) 위반이다.
device_counts = df["device_id(s)"].fillna("").str.count(";") + 1
exploded = df["device_id(s)"].fillna("").str.split(";").explode().str.strip()
exploded = exploded[exploded != ""]

lines.append("-" * 88)
lines.append("[C] device_id(s) — 한 칸에 값이 여러 개")
lines.append("-" * 88)
lines.append("  기기 개수별 고객 수")
for n, cnt in device_counts.value_counts().sort_index().items():
    lines.append(f"    {n}개 보유 : {cnt:,}명")
lines.append("")
lines.append(f"  총 기기 등록 건수 : {len(exploded):,}건")
lines.append(f"  고유 기기 ID      : {exploded.nunique():,}개")
lines.append(f"  중복 등록된 기기   : {len(exploded) - exploded.nunique():,}건")
lines.append("")
lines.append("  ※ 이것은 '오염'이 아니라 '구조 문제'다.")
lines.append("     관계형 데이터베이스 설계 원칙(제1정규형)은")
lines.append("     '한 칸에는 값이 하나만 들어가야 한다'고 요구한다.")
lines.append("     지금 상태로는 SQL에서 '기기 3개 이상 보유 고객'을 찾기가 매우 어렵다.")
lines.append("     → 6단계에서 customer_devices 라는 별도 테이블로 분리할 예정이다.")
lines.append("        (고객 1명이 기기 여러 개를 갖는 1:N 관계)")
lines.append("")

# --- 검증 D : 지역 정보 일관성 ----------------------------------------------
lines.append("-" * 88)
lines.append("[D] 지역 정보 (city / state / country)")
lines.append("-" * 88)
lines.append(f"  state 고유값   : {df['state'].nunique()}종")
lines.append(f"  country 고유값 : {df['country'].nunique()}종")
us_rows = df["country"].fillna("").str.contains("United States")
lines.append(f"  country가 미국인 행 : {us_rows.sum():,}건 (전체의 {us_rows.mean()*100:.1f}%)")
lines.append("")
lines.append("  ※ state 값은 Oregon, Delaware 등 미국 50개 주 이름인데,")
lines.append("     country는 243개국으로 퍼져 있고 미국은 극소수다.")
lines.append("     즉 'Oregon주에 사는 포르투갈 거주자' 같은 조합이 대량으로 존재한다.")
lines.append("     → 지역 정보 자체가 신뢰할 수 없다는 뜻이므로,")
lines.append("        2단계에서 이 컬럼들을 분석에 쓸지 말지 판단해야 한다.")

with open(os.path.join(OUTPUT_DIR, "05_교차검증.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("05_교차검증.txt 저장 완료")
print()
print("\n".join(lines))
print()
print(f"모든 결과 저장 위치 : {OUTPUT_DIR}")
