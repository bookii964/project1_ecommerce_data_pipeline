# =============================================================================
# 파일명 : 12_clean_orders.py
# 단계   : 4단계 - 정제 규칙 적용 및 정제 파일 생성 (orders)
#
# [목적]
#   2단계 규칙서(데이터사전_orders.md)대로 값을 실제로 고치고 새 파일로 저장한다.
#
# [orders의 특징 — 앞선 파일들과 다른 점]
#   ① 행을 하나도 삭제하지 않는다
#      거래 데이터는 한 컬럼이 깨져도 다른 컬럼은 분석에 쓸 수 있다.
#      날짜가 없는 주문도 '어떤 고객이 어떤 상품을 샀는가'는 유효하다.
#      → 300,000행이 그대로 300,000행으로 유지되어야 한다.
#
#   ② NULL 처리가 많다 (날짜 90,000 / 금액 51,525 / 수량 44,867)
#      그래서 원본 값 보존이 필수다. 무엇이 어떤 값에서 비워졌는지
#      테이블 안에서 바로 확인할 수 있어야 한다.
#
#   ③ '형식 변환이 가능해도 하지 않는' 값이 있다
#      '2024/31/01' → 2024-01-31 로 바꿀 수 있지만 바꾸지 않는다.
#      '1,200' → 1200.00 으로 바꿀 수 있지만 바꾸지 않는다.
#      둘 다 같은 값이 1만 건 넘게 반복되는 시스템 대체값이라,
#      변환하면 없는 사실을 만들어내기 때문이다. (근거는 규칙서 2절 참고)
#
# [입력]  01_raw/orders_300k_dirty.csv
# [출력]  03_cleaned/orders_cleaned.csv
#         04_reports/정제로그_orders.txt
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
CLEAN_DIR = os.path.join(PROJECT_DIR, "03_cleaned")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 2단계에서 확정한 규칙 상수
# -----------------------------------------------------------------------------
VALID_PAYMENT = ["card", "cash", "upi", "wallet"]
VALID_STATUS = ["success", "failed", "refunded"]
STANDARD_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 상수형 오염값 : 같은 값이 1만 건 넘게 반복되는 시스템 대체값
# (정상 날짜는 730종, 정상 금액은 243,046종으로 흩어져 있다)
CONSTANT_DATES = {
    "2024/31/01": "상수값",
    "31-12-2023": "상수값",
    "2025/01/10 12:00": "상수값",
}
CONSTANT_AMOUNTS = ["0", "1,200", "-50"]


raw = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(raw):,}행")
print()
print("[처리 진행]")

df = raw.copy()


# -----------------------------------------------------------------------------
# [원본 값 보존]
#   NULL 처리가 많은 컬럼은 정제 전 값을 같은 행에 남긴다.
#   반드시 정제를 시작하기 전에 복사해야 한다.
# -----------------------------------------------------------------------------
PRESERVE_COLS = ["order_amount", "order_date", "quantity"]
for col in PRESERVE_COLS:
    df[f"{col}_raw"] = raw[col]

print(f"  0. 원본 값 보존 컬럼 생성       {len(PRESERVE_COLS)}개")


# =============================================================================
# [1] order_amount
#
#   처리 순서
#     ① 앞뒤 공백 제거
#     ② 상수 3종은 NULL 처리 (형식 변환하지 않는다)
#     ③ 나머지를 숫자로 변환, 소수점 2자리로 통일
#     ④ 그래도 0 이하이거나 변환 실패면 NULL 처리
# =============================================================================
amount_strip = df["order_amount"].fillna("").str.strip()

df["amount_flag"] = None

# 원본 결측
df.loc[df["order_amount"].isna(), "amount_flag"] = "원본결측"

# 상수 3종 → NULL (사유를 값과 함께 기록해서 나중에 구분할 수 있게 한다)
for const in CONSTANT_AMOUNTS:
    df.loc[amount_strip == const, "amount_flag"] = f"상수값({const})"

# 숫자 변환 (쉼표 제거는 하되, 상수 '1,200'은 이미 위에서 플래그 처리됨)
amount_num = pd.to_numeric(
    amount_strip.str.replace(",", "", regex=False).replace("", None),
    errors="coerce")

# 상수로 표시된 행과 결측은 값을 비운다
is_constant = amount_strip.isin(CONSTANT_AMOUNTS)
amount_num = amount_num.where(~is_constant, None)

# 상수 외에 0 이하이거나 변환 실패한 값도 NULL 처리
extra_bad = (~is_constant) & df["order_amount"].notna() & (
    amount_num.isna() | (amount_num <= 0))
df.loc[extra_bad, "amount_flag"] = "값오류(0이하 또는 변환불가)"
amount_num = amount_num.where(~extra_bad, None)

df["order_amount"] = amount_num.round(2)

print(f"  1. order_amount 정제           "
      f"NULL {int(df['order_amount'].isna().sum()):,}건")


# =============================================================================
# [2] order_date
#
#   표준 형식(YYYY-MM-DD)만 남기고 나머지는 전부 NULL 처리한다.
#   형식 변환이 가능한 값도 변환하지 않는다. 근거는 규칙서 2절과
#   scripts/10_evidence_orders_date.py 참고.
# =============================================================================
date_strip = df["order_date"].fillna("").str.strip()

df["date_flag"] = None
df.loc[df["order_date"].isna(), "date_flag"] = "원본결측"

for const, reason in CONSTANT_DATES.items():
    df.loc[date_strip == const, "date_flag"] = f"{reason}({const})"

df.loc[date_strip.str.contains("T"), "date_flag"] = "적재시각추정(ISO8601)"

# 표준 형식인 값만 날짜로 변환한다.
# 표준 형식이면서 실제로 존재하지 않는 날짜(예: 2024-02-31)는 변환 실패 → NULL
is_standard = date_strip.str.match(STANDARD_DATE)
parsed = pd.to_datetime(date_strip.where(is_standard), errors="coerce",
                        format="%Y-%m-%d")

df.loc[is_standard & parsed.isna(), "date_flag"] = "불가능한날짜"

# 표준 형식이 아닌 값 중 위에서 분류되지 않은 것 (예상: 0건)
unclassified = (~is_standard) & df["order_date"].notna() & df["date_flag"].isna()
df.loc[unclassified, "date_flag"] = "미분류_형식위반"

# 날짜 컬럼은 YYYY-MM-DD 문자열로 저장한다.
# PostgreSQL의 DATE 타입이 이 형식을 그대로 인식한다.
df["order_date"] = parsed.dt.strftime("%Y-%m-%d")

print(f"  2. order_date 정제             "
      f"NULL {int(df['order_date'].isna().sum()):,}건")


# =============================================================================
# [3] payment_method
#
#   ① 앞뒤 공백 제거 → ② 소문자 → ③ 영문자 외 제거 → ④ 매핑
#
#   ④ 매핑 규칙 (2단계에서 수정된 부분)
#     부분열 매칭 : 글자 순서를 유지한 채 일부만 남긴 축약형
#       'cd' → c__d → card,  'crd' → c_rd → card
#     전치 오타   : 글자 구성이 같고 순서만 다름
#       'crad' → card
#     후보가 1개일 때만 복원한다. 2개 이상이면 원본을 유지하고 플래그 처리.
# =============================================================================
def is_subsequence(short, full):
    """short의 글자들이 full 안에 순서대로 등장하는지 확인"""
    iterator = iter(full)
    return all(char in iterator for char in short)

def map_payment(value):
    if value == "":
        return None, "결측"
    if value in VALID_PAYMENT:
        return value, None
    # ① 부분열 매칭 (중간 글자 생략형 축약)
    candidates = [v for v in VALID_PAYMENT if is_subsequence(value, v)]
    if len(candidates) == 1:
        return candidates[0], None
    # ② 전치 오타 (글자 구성 동일)
    for v in VALID_PAYMENT:
        if sorted(value) == sorted(v):
            return v, None
    return value, "복원불가"

pay_clean = (df["payment_method"].fillna("")
             .str.strip()
             .str.lower()
             .str.replace(r"[^a-z]", "", regex=True))

# 값 종류가 11개뿐이므로, 고유값에만 함수를 적용하고 매핑으로 되돌린다.
# 30만 행에 함수를 직접 적용하는 것보다 훨씬 빠르다.
pay_map = {v: map_payment(v) for v in pay_clean.unique()}
df["payment_method"] = pay_clean.map(lambda v: pay_map[v][0])
df["payment_flag"] = pay_clean.map(lambda v: pay_map[v][1])

print(f"  3. payment_method 정제         "
      f"{df['payment_method'].nunique()}종으로 통일")


# =============================================================================
# [4] status
#   앞글자 매칭으로 축약형을 복원한다.
#   ('suc' → success, 'ref' → refunded, 'fail' → failed 모두 후보가 1개)
# =============================================================================
def map_status(value):
    if value == "":
        return None, "결측"
    if value in VALID_STATUS:
        return value, None
    candidates = [v for v in VALID_STATUS if v.startswith(value)]
    if len(candidates) == 1:
        return candidates[0], None
    return value, "복원불가"

status_clean = df["status"].fillna("").str.strip().str.lower()
status_map = {v: map_status(v) for v in status_clean.unique()}
df["status"] = status_clean.map(lambda v: status_map[v][0])
df["status_flag"] = status_clean.map(lambda v: status_map[v][1])

print(f"  4. status 정제                 "
      f"{df['status'].nunique()}종으로 통일")


# =============================================================================
# [5] quantity
#
#   'five' → 5   : 해석이 유일하고 정상 범위 안이므로 복원
#   '2.0'  → 2   : 값은 같고 표기만 다름
#   '-3', '0', ' ' → NULL : 복원 근거가 없음
#
#   '-3'을 절댓값 3으로 바꾸지 않는다.
#   status와 교차 검증한 결과 환불과 무관한 무작위 오염으로 확인됐다.
#   부호만 뒤집으면 근거 없이 주문 수량 44,817개를 만들어내는 셈이 된다.
# =============================================================================
WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

qty_strip = df["quantity"].fillna("").str.strip().str.lower()

df["quantity_flag"] = None
df.loc[df["quantity"].isna(), "quantity_flag"] = "원본결측"
df.loc[df["quantity"].notna() & (qty_strip == ""), "quantity_flag"] = "공백(실질결측)"

# 영어 수사를 숫자로 바꾼다
qty_work = qty_strip.replace(WORD_NUMBERS)

# 숫자로 변환 ('2.0'도 여기서 2.0으로 읽힌다)
qty_num = pd.to_numeric(qty_work.replace("", None), errors="coerce")

# 정상 범위(1~5)를 벗어나면 NULL 처리하고 사유를 기록한다
df.loc[qty_num < 0, "quantity_flag"] = "음수"
df.loc[qty_num == 0, "quantity_flag"] = "0개"
df.loc[qty_num > 5, "quantity_flag"] = "범위초과"
df.loc[df["quantity"].notna() & (qty_strip != "") & qty_num.isna(),
       "quantity_flag"] = "숫자변환불가"

valid_qty = (qty_num >= 1) & (qty_num <= 5)
# Int64 : 결측을 허용하는 정수 타입. 일반 int는 NULL을 담을 수 없다.
df["quantity"] = qty_num.where(valid_qty).astype("Int64")

print(f"  5. quantity 정제               "
      f"NULL {int(df['quantity'].isna().sum()):,}건")


# =============================================================================
# [저장]
# =============================================================================
OUTPUT_COLS = [
    # --- 키 (변경 없음) ---
    "order_id", "customer_id", "product_id",
    # --- 분석용 정제값 ---
    "order_amount", "order_date", "payment_method", "status", "quantity",
    # --- 원본 보존 ---
    "order_amount_raw", "order_date_raw", "quantity_raw",
    # --- 처리 사유 ---
    "amount_flag", "date_flag", "quantity_flag", "payment_flag", "status_flag",
]
df = df[OUTPUT_COLS]

output_path = os.path.join(CLEAN_DIR, "orders_cleaned.csv")
df.to_csv(output_path, index=False, encoding="utf-8-sig", float_format="%.2f")

print()
print(f"정제 파일 저장 : {output_path}")


# =============================================================================
# [정제 로그]
# =============================================================================
lines = []
lines.append("=" * 80)
lines.append("orders_300k 정제 로그 (4단계)")
lines.append("=" * 80)
lines.append(f"원본 행 수 : {len(raw):,}")
lines.append(f"정제 행 수 : {len(df):,}   ← 행을 삭제하지 않았으므로 동일해야 정상")
lines.append("")
lines.append("  ※ 거래 데이터는 한 컬럼이 깨져도 다른 컬럼은 분석에 쓸 수 있다.")
lines.append("     날짜가 없는 주문도 '어떤 고객이 어떤 상품을 샀는가'는 유효하다.")
lines.append("")

lines.append("-" * 80)
lines.append("[컬럼별 정제 결과]")
lines.append("-" * 80)
for col in ["order_amount", "order_date", "quantity", "payment_method", "status"]:
    n_null = int(df[col].isna().sum())
    lines.append(f"  {col:<16} 사용 가능 {len(df)-n_null:>8,}건 / "
                 f"NULL {n_null:>7,}건 ({n_null/len(df)*100:>4.1f}%)")
lines.append("")

lines.append("-" * 80)
lines.append("[NULL 처리 사유별 건수]")
lines.append("-" * 80)
for col in ["amount_flag", "date_flag", "quantity_flag", "payment_flag", "status_flag"]:
    counts = df[col].value_counts(dropna=True)
    lines.append(f"\n  ■ {col}")
    if len(counts) == 0:
        lines.append("      없음 — 전량 정상 처리")
    for k, v in counts.items():
        lines.append(f"      {k:<32} {v:>8,}건")
lines.append("")

lines.append("-" * 80)
lines.append("[정제 후 범주형 분포]")
lines.append("-" * 80)
for col in ["payment_method", "status", "quantity"]:
    lines.append(f"\n  ■ {col}")
    for k, v in df[col].value_counts(dropna=False).sort_index().items():
        label = "(NULL)" if pd.isna(k) else str(k)
        lines.append(f"      {label:<12} {v:>8,}건  ({v/len(df)*100:>4.1f}%)")
lines.append("")

lines.append("-" * 80)
lines.append("[정제 후 금액·날짜 요약]")
lines.append("-" * 80)
amt = df["order_amount"].dropna()
dt = pd.to_datetime(df["order_date"].dropna())
lines.append(f"  금액 건수    : {len(amt):,}")
lines.append(f"  금액 최소/최대 : {amt.min():,.2f} / {amt.max():,.2f}")
lines.append(f"  금액 평균/중앙 : {amt.mean():,.2f} / {amt.median():,.2f}")
lines.append(f"  날짜 건수    : {len(dt):,}")
lines.append(f"  날짜 범위    : {dt.min().date()} ~ {dt.max().date()}")
lines.append(f"  주문이 있는 날 : {dt.dt.date.nunique():,}일")
lines.append("")

lines.append("-" * 80)
lines.append("[원본 값 보존]")
lines.append("-" * 80)
lines.append("  NULL 처리 건이 많으므로 정제 전 값을 같은 행에 보관한다.")
lines.append("  order_amount_raw / order_date_raw / quantity_raw")
lines.append("")
lines.append("  SQL 예시 — 날짜가 비워진 주문의 원본값 확인:")
lines.append("    SELECT date_flag, order_date_raw, COUNT(*)")
lines.append("    FROM   orders")
lines.append("    WHERE  order_date IS NULL")
lines.append("    GROUP  BY 1, 2;")

with open(os.path.join(REPORT_DIR, "정제로그_orders.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print()
print("\n".join(lines))
