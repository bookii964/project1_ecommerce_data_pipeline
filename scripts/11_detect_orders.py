# =============================================================================
# 파일명 : 11_detect_orders.py
# 단계   : 3단계 - 비정상 데이터 색출 및 유형 분류 (orders)
#
# [목적]
#   2단계 규칙서(데이터사전_orders.md)를 코드로 옮겨 규칙 위반 건을 전부 찾아낸다.
#   이 단계에서도 데이터를 고치지 않는다. 찾아서 기록만 한다.
#
# [앞선 파일들의 3단계와 달라진 점]
#   ① 참조 정합성 검사가 들어간다
#      주문의 customer_id / product_id가 마스터에 존재하는지 확인한다.
#      마스터 파일(정제본)을 함께 읽어야 하므로 입력이 3개다.
#
#   ② 날짜를 '형식별'로 분류해서 센다
#      단순히 "형식 위반 9만 건"이 아니라, 어떤 형식인지 구분해야
#      4단계에서 각각을 어떻게 처리할지 판정할 수 있다.
#
#   ③ '복원가능'을 별도 유형으로 표시한다
#      quantity의 'five'는 오염이지만 5로 되살릴 수 있다.
#      '-3'은 오염이고 되살릴 수 없다(NULL 처리).
#      같은 '오염'이라도 처리 방법이 달라서 유형명에 구분을 남긴다.
#
# [입력]  01_raw/orders_300k_dirty.csv
#         03_cleaned/crm_customers_cleaned.csv     (마스터 — 대조용)
#         03_cleaned/product_catalog_cleaned.csv   (마스터 — 대조용)
# [출력]  02_profiling/orders/
#           - 05_이상데이터_상세.csv   : 위반 1건당 1행
#           - 06_유형별_집계.csv       : 컬럼×유형별 건수
#           - 07_진단요약.txt          : 사람이 읽는 요약
#
# [분류 구분]
#   오염     : 값 자체가 틀림. 수정 또는 NULL 처리
#   표준화   : 값은 맞는데 표기만 다름
#   확인필요 : 정답을 알 수 없음 (orders에는 해당 항목이 없다)
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

INPUT_FILE = os.path.join(PROJECT_DIR, "01_raw", "orders_300k_dirty.csv")
CUST_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "crm_customers_cleaned.csv")
PROD_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "product_catalog_cleaned.csv")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "02_profiling", "orders")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 2단계에서 확정한 규칙 상수
# -----------------------------------------------------------------------------
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                          r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PRODUCT_PATTERN = re.compile(r"^PROD-\d{4}$")
STANDARD_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

VALID_PAYMENT = ["card", "cash", "upi", "wallet"]
VALID_STATUS = ["success", "failed", "refunded"]
VALID_QUANTITY = ["1", "2", "3", "4", "5"]

# 1단계에서 확인한 상수형 날짜 오염값 (각각 고유값이 1개뿐)
CONSTANT_DATES = ["2024/31/01", "31-12-2023", "2025/01/10 12:00"]


df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
cust = read_csv_safe(CUST_FILE, dtype=str, keep_default_na=True)
prod = read_csv_safe(PROD_FILE, dtype=str, keep_default_na=True)

print(f"원본 읽기 완료 : {len(df):,}행 × {len(df.columns)}열")
print(f"마스터 : 고객 {len(cust):,}명 / 상품 {len(prod):,}개")
print()


# -----------------------------------------------------------------------------
# [위반 기록 도구]
#   마스크(True/False 배열)를 받아 True인 행을 위반 목록에 추가한다.
# -----------------------------------------------------------------------------
issues = []

def add(mask, column, issue_type, kind):
    n = int(mask.sum())
    if n == 0:
        return
    sub = df.loc[mask, ["order_id"]].copy()
    sub["행번호"] = sub.index
    sub["컬럼"] = column
    sub["원본값"] = df.loc[mask, column].values
    sub["위반유형"] = issue_type
    sub["분류구분"] = kind
    issues.append(sub)
    print(f"  [{kind}] {column:<16} {issue_type:<28} {n:>8,}건")


# =============================================================================
# [검사 1] 키 컬럼 — order_id / customer_id / product_id
# =============================================================================
print("[검사 1] 키 컬럼 및 참조 정합성")

add(df["order_id"].isna(), "order_id", "결측", "오염")
add(~df["order_id"].fillna("").str.match(UUID_PATTERN), "order_id", "UUID형식위반", "오염")
add(df["order_id"].duplicated(keep=False), "order_id", "중복", "오염")
add(df.duplicated(keep=False), "order_id", "완전중복행", "오염")

add(~df["customer_id"].fillna("").str.match(UUID_PATTERN),
    "customer_id", "UUID형식위반", "오염")
add(~df["product_id"].fillna("").str.match(PRODUCT_PATTERN),
    "product_id", "형식위반", "오염")

# 참조 정합성 : 마스터에 없는 키를 가리키는 주문 = 고아 레코드
#   isin() 은 왼쪽 값이 오른쪽 목록에 있는지 True/False로 반환한다
add(~df["customer_id"].isin(cust["customer_id"]),
    "customer_id", "고아레코드(고객없음)", "오염")
add(~df["product_id"].isin(prod["product_id"]),
    "product_id", "고아레코드(상품없음)", "오염")

print("  (출력이 없으면 위반 0건 — 정상입니다)")
print()


# =============================================================================
# [검사 2] order_amount
#
#   [1단계에서 놓쳤다가 3단계에서 발견한 것]
#   금액에도 날짜와 같은 '상수형 오염'이 있다.
#   정상 금액값의 최대 반복은 3건인데, 아래 3개 값만 1만 건 넘게 반복된다.
#     '0'      12,988건
#     '1,200'  12,897건   ← 이 값만 유일하게 천단위 쉼표를 사용한다
#     '-50'    12,810건
#   → 실제 거래 금액이 아니라 시스템 대체값(sentinel)으로 판단한다.
#     `1,200`은 형식만 보면 1200.00으로 변환 가능하지만, 변환하면
#     "1,200원 주문이 12,897건" 이라는 없는 사실을 만들어낸다.
#     (order_date의 상수값을 변환하지 않는 것과 같은 이유)
# =============================================================================
print("[검사 2] order_amount")

amount_raw = df["order_amount"].fillna("")
amount_strip = amount_raw.str.strip()

add(df["order_amount"].isna(), "order_amount", "결측", "오염")
add((amount_raw != amount_strip) & (amount_strip != ""),
    "order_amount", "앞뒤공백", "표준화")

# 상수형 오염 3종 : 각각 1만 건 넘게 동일한 값이 반복된다
AMOUNT_CONSTANTS = ["0", "1,200", "-50"]
for const in AMOUNT_CONSTANTS:
    add(amount_strip == const, "order_amount", f"상수값('{const}')", "오염")

# 숫자로 변환해서 값 자체의 문제를 검사한다
amount_num = pd.to_numeric(
    amount_strip.str.replace(",", "", regex=False).replace("", None),
    errors="coerce")

add(df["order_amount"].notna() & amount_num.isna(),
    "order_amount", "숫자변환불가", "오염")

# 상수 3종에 해당하지 않는 음수·0원 (상수와 중복 집계하지 않기 위해 제외)
not_constant = ~amount_strip.isin(AMOUNT_CONSTANTS)
add(not_constant & (amount_num < 0), "order_amount", "음수(상수외)", "오염")
add(not_constant & (amount_num == 0), "order_amount", "0원(상수외)", "오염")

# 소수점 자릿수는 값이 아니라 표기 문제
not_standard_form = ~amount_strip.str.match(r"^\d+\.\d{2}$")
add(not_constant & amount_num.notna() & (amount_num > 0) & not_standard_form,
    "order_amount", "소수점_자릿수불일치", "표준화")
print()


# =============================================================================
# [검사 3] order_date — 형식별로 분류해서 센다
#
#   중요 : 상수형 오염값과 ISO 형식을 구분해서 세야 한다.
#          둘 다 NULL 처리 대상이지만 사유가 다르므로
#          4단계에서 date_flag에 다른 값을 기록한다.
# =============================================================================
print("[검사 3] order_date")

date_raw = df["order_date"].fillna("").str.strip()

add(df["order_date"].isna(), "order_date", "결측", "오염")

# 상수형 3종 : 고유값이 1개뿐이므로 날짜가 아니라 시스템 대체값
for const in CONSTANT_DATES:
    add(date_raw == const, "order_date", f"상수값('{const}')", "오염")

# ISO 형식 : 시각이 1~2분에 집중되고 미래 날짜 포함 → 적재 시각으로 판단
add(date_raw.str.contains("T"), "order_date", "적재시각추정(ISO8601)", "오염")

# 위에 해당하지 않으면서 표준 형식도 아닌 값 (예상: 0건)
known_bad = date_raw.isin(CONSTANT_DATES) | date_raw.str.contains("T") | (date_raw == "")
add(~known_bad & ~date_raw.str.match(STANDARD_DATE),
    "order_date", "미분류_형식위반", "오염")

# 표준 형식이지만 날짜로 성립하지 않는 값 (예: 2024-02-31)
standard_mask = date_raw.str.match(STANDARD_DATE)
parsed = pd.to_datetime(date_raw.where(standard_mask), errors="coerce", format="%Y-%m-%d")
add(standard_mask & parsed.isna(), "order_date", "불가능한_날짜", "오염")

# 미래 날짜 (표준 형식 중에서)
today = pd.Timestamp.today().normalize()
add(parsed > today, "order_date", "미래날짜", "오염")
print()


# =============================================================================
# [검사 4] payment_method
#   한 값에 여러 오염이 겹쳐 있으므로 한 겹씩 벗겨내며 전부 기록한다.
# =============================================================================
print("[검사 4] payment_method")

pay = df["payment_method"].fillna("")

add(df["payment_method"].isna(), "payment_method", "결측", "오염")
add(pay != pay.str.strip(), "payment_method", "앞뒤공백", "오염")

work = pay.str.strip()
add(work != work.str.lower(), "payment_method", "대문자표기", "오염")

work = work.str.lower()
add(work.str.contains(r"[^a-z]", regex=True), "payment_method", "특수문자_삽입", "오염")

# 특수문자를 제거한 뒤에도 허용값에 없으면 오타 또는 축약형
work_clean = work.str.replace(r"[^a-z]", "", regex=True)
unknown = ~work_clean.isin(VALID_PAYMENT) & (work_clean != "")

# 축약형 / 전치오타를 구분해서 기록한다.
#
#   [2단계 규칙서에서 수정된 부분]
#   처음에는 '앞글자 매칭(startswith)'으로 축약형을 복원하려 했다.
#   그런데 'cd'는 'card'의 앞글자가 아니어서 매칭에 실패했다.
#   실제 오염 패턴은 '중간 글자를 생략한 축약'이었다.
#     card → crd (모음 a 생략) → cd (r까지 생략)
#   그래서 '부분열(subsequence) 매칭'으로 규칙을 바꿨다.
#     부분열 매칭 = 글자 순서를 유지한 채 일부만 남긴 형태인지 확인
#     'cd'  → c__d 로 'card' 안에 순서대로 존재 → 부분열
#     'crd' → c_rd 로 'card' 안에 순서대로 존재 → 부분열
#   후보가 1개일 때만 복원하므로 안전하다.
def is_subsequence(short, full):
    """short의 글자들이 full 안에 순서대로 등장하는지 확인"""
    iterator = iter(full)
    return all(char in iterator for char in short)

def classify_payment(value):
    if value in VALID_PAYMENT or value == "":
        return None
    # ① 부분열 매칭 (중간 글자 생략형 축약)
    candidates = [v for v in VALID_PAYMENT if is_subsequence(value, v)]
    if len(candidates) == 1:
        return f"축약형(→{candidates[0]})"
    # ② 글자 구성이 같으면 순서만 뒤바뀐 전치 오타 (crad ↔ card)
    for v in VALID_PAYMENT:
        if sorted(value) == sorted(v):
            return f"전치오타(→{v})"
    return "복원불가_미확인값"

pay_class = work_clean.map(classify_payment)
for label in pay_class.dropna().unique():
    add(pay_class == label, "payment_method", label, "오염")
print()


# =============================================================================
# [검사 5] status
# =============================================================================
print("[검사 5] status")

st = df["status"].fillna("")

add(df["status"].isna(), "status", "결측", "오염")
add(st != st.str.strip(), "status", "앞뒤공백", "오염")

work = st.str.strip()
add(work != work.str.lower(), "status", "대소문자_불일치", "오염")

work = work.str.lower()

def classify_status(value):
    if value in VALID_STATUS or value == "":
        return None
    candidates = [v for v in VALID_STATUS if v.startswith(value)]
    if len(candidates) == 1:
        return f"축약형(→{candidates[0]})"
    return "복원불가_미확인값"

st_class = work.map(classify_status)
for label in st_class.dropna().unique():
    add(st_class == label, "status", label, "오염")
print()


# =============================================================================
# [검사 6] quantity
#   같은 '오염'이라도 복원 가능한지를 유형명에 남긴다.
#     'five'  → 5로 복원 가능 (해석이 유일함)
#     '2.0'   → 2로 표기만 다름 (표준화)
#     '-3','0',' ' → 복원 불가, NULL 처리
# =============================================================================
print("[검사 6] quantity")

qty = df["quantity"].fillna("")
qty_strip = qty.str.strip()

add(df["quantity"].isna(), "quantity", "결측", "오염")
add((qty != qty_strip) & (qty_strip != ""), "quantity", "앞뒤공백", "표준화")

# 공백만 들어있는 값 = 실질 결측
add((qty != "") & (qty_strip == ""), "quantity", "공백(실질결측)", "오염")

# 영어 수사 표기 : 해석이 유일하므로 복원 가능
add(qty_strip.str.lower() == "five", "quantity", "문자표기(five)_복원가능", "오염")

# 소수 표기 : 값은 같고 표기만 다름
add(qty_strip.str.match(r"^\d+\.\d+$"), "quantity", "소수표기(2.0)", "표준화")

qty_num = pd.to_numeric(qty_strip.replace("", None), errors="coerce")

# 음수 : status와 교차 검증한 결과 환불과 무관한 무작위 오염 (규칙서 3-3)
add(qty_num < 0, "quantity", "음수(복원불가)", "오염")
add(qty_num == 0, "quantity", "0개(복원불가)", "오염")
add(qty_num > 5, "quantity", "정상범위(1~5)초과", "오염")
print()


# =============================================================================
# [출력 1] 이상 데이터 상세
# =============================================================================
issue_df = pd.concat(issues, ignore_index=True)
issue_df = issue_df[["행번호", "order_id", "컬럼", "원본값", "위반유형", "분류구분"]]
issue_df = issue_df.sort_values(["행번호", "컬럼"])

issue_df.to_csv(os.path.join(OUTPUT_DIR, "05_이상데이터_상세.csv"),
                index=False, encoding="utf-8-sig")
print(f"05_이상데이터_상세.csv 저장 완료 (총 {len(issue_df):,}건)")
print("  ※ 파일이 큽니다. 엑셀로 열기보다 06_유형별_집계.csv 를 먼저 확인하세요.")


# =============================================================================
# [출력 2] 유형별 집계
# =============================================================================
summary = (
    issue_df.groupby(["컬럼", "분류구분", "위반유형"])
    .size().reset_index(name="건수")
    .sort_values(["컬럼", "분류구분", "건수"], ascending=[True, True, False])
)
summary.to_csv(os.path.join(OUTPUT_DIR, "06_유형별_집계.csv"),
               index=False, encoding="utf-8-sig")
print("06_유형별_집계.csv 저장 완료")


# =============================================================================
# [출력 3] 진단 요약
# =============================================================================
lines = []
lines.append("=" * 80)
lines.append("orders_300k 오염 진단 요약 (3단계)")
lines.append("=" * 80)
lines.append(f"전체 행 수        : {len(df):,}")
lines.append(f"위반 건수(누적)   : {len(issue_df):,}")

affected = issue_df["행번호"].nunique()
lines.append(f"위반이 있는 행 수 : {affected:,} / {len(df):,} ({affected/len(df)*100:.1f}%)")
lines.append("")
lines.append("  ※ 두 숫자를 구분해야 한다. 한 행이 여러 컬럼에서 위반할 수 있고,")
lines.append("     한 값에 여러 오염이 겹칠 수 있다. (예: ' UPI ' → 공백 + 대문자 2건)")
lines.append("")

lines.append("-" * 80)
lines.append("[분류 구분별 건수]")
lines.append("-" * 80)
for kind, cnt in issue_df["분류구분"].value_counts().items():
    lines.append(f"  {kind:<10} : {cnt:>9,}건")
lines.append("")
lines.append("  오염   = 값이 틀림. 4단계에서 수정 또는 NULL 처리")
lines.append("  표준화 = 값은 맞고 표기만 다름. 형식 통일")
lines.append("")

lines.append("-" * 80)
lines.append("[컬럼별 · 유형별 상세]")
lines.append("-" * 80)
for col in df.columns:
    sub = issue_df[issue_df["컬럼"] == col]
    lines.append(f"\n■ {col}  (총 {len(sub):,}건)")
    if len(sub) == 0:
        lines.append("    위반 없음 — 정상 컬럼")
        continue
    for (kind, itype), cnt in sub.groupby(["분류구분", "위반유형"]).size().items():
        lines.append(f"    [{kind}] {itype:<30} {cnt:>9,}건")

# -----------------------------------------------------------------------------
# 참조 정합성은 별도로 명시한다 (거래 데이터의 핵심 지표)
# -----------------------------------------------------------------------------
lines.append("")
lines.append("-" * 80)
lines.append("[참조 정합성 — 거래 데이터의 핵심 검사]")
lines.append("-" * 80)
orphan_c = int((~df["customer_id"].isin(cust["customer_id"])).sum())
orphan_p = int((~df["product_id"].isin(prod["product_id"])).sum())
lines.append(f"  고아 주문(고객 없음) : {orphan_c:,}건")
lines.append(f"  고아 주문(상품 없음) : {orphan_p:,}건")
if orphan_c == 0 and orphan_p == 0:
    lines.append("  → 전부 0건. 6단계에서 외래키(FOREIGN KEY) 제약을 걸 수 있다.")

# -----------------------------------------------------------------------------
# 4단계 처리 예정 요약
# -----------------------------------------------------------------------------
usable_date = int(date_raw.str.match(STANDARD_DATE).sum())
lines.append("")
lines.append("-" * 80)
lines.append("[4단계 처리 예정]")
lines.append("-" * 80)
lines.append("  자동 수정 : 결제수단 11종→4종, 상태 10종→3종, 'five'→5, '2.0'→2")
lines.append("  NULL 처리 : 금액 상수 3종(0, 1,200, -50), 수량 음수·0·공백, 비표준 날짜 4종")
lines.append("  행 삭제   : 없음 (한 컬럼이 깨져도 다른 컬럼은 분석에 사용 가능)")
lines.append("  원본 보존 : order_amount_raw / order_date_raw / quantity_raw")
lines.append("")
lines.append(f"  정제 후 날짜 사용 가능 주문 : {usable_date:,}건 "
             f"({usable_date/len(df)*100:.1f}%)")

with open(os.path.join(OUTPUT_DIR, "07_진단요약.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("07_진단요약.txt 저장 완료")
print()
print("\n".join(lines))
