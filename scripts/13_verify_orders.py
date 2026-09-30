# =============================================================================
# 파일명 : 13_verify_orders.py
# 단계   : 5단계 - 정제 결과 검증 (orders)
#
# [목적]
#   4단계 정제본이 규칙을 지켰는지 기계적으로 확인한다.
#   이 단계를 통과해야 PostgreSQL에 적재할 수 있다.
#
# [orders 검증의 특징]
#   ① 행이 줄지 않아야 한다
#      마스터 데이터(crm)는 중복 제거로 행이 줄었지만,
#      거래 데이터는 행 삭제를 하지 않았으므로 300,000행 그대로여야 한다.
#      줄었다면 어딘가에서 데이터가 새고 있다는 뜻이다.
#
#   ② NULL과 플래그가 짝을 이뤄야 한다
#      값을 비웠으면 반드시 사유(플래그)가 있어야 하고,
#      반대로 사유가 있는데 값이 남아 있어도 안 된다.
#      이 둘이 어긋나면 "왜 비었는지 모르는 값"이 생긴다.
#
#   ③ 참조 정합성을 다시 확인한다
#      정제 과정에서 키를 건드리지 않았지만, 검증은 결과로 확인해야 한다.
#
# [입력]  01_raw/orders_300k_dirty.csv
#         03_cleaned/orders_cleaned.csv
#         03_cleaned/crm_customers_cleaned.csv
#         03_cleaned/product_catalog_cleaned.csv
# [출력]  04_reports/검증결과_orders.txt
#         04_reports/비교표_orders.csv
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

RAW_FILE = os.path.join(PROJECT_DIR, "01_raw", "orders_300k_dirty.csv")
CLEAN_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "orders_cleaned.csv")
CUST_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "crm_customers_cleaned.csv")
PROD_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "product_catalog_cleaned.csv")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

VALID_PAYMENT = ["card", "cash", "upi", "wallet"]
VALID_STATUS = ["success", "failed", "refunded"]
STANDARD_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 4단계에서 NULL 처리한 건수 (의도한 값과 실제가 맞는지 대조하기 위한 기준)
EXPECTED_DATE_NULL = 90000
EXPECTED_AMOUNT_NULL = 51525
EXPECTED_QTY_NULL = 44867


raw = read_csv_safe(RAW_FILE, dtype=str, keep_default_na=True)
clean = read_csv_safe(CLEAN_FILE, dtype=str, keep_default_na=True)
cust = read_csv_safe(CUST_FILE, dtype=str, keep_default_na=True)
prod = read_csv_safe(PROD_FILE, dtype=str, keep_default_na=True)

print(f"원본   : {len(raw):,}행")
print(f"정제본 : {len(clean):,}행")
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
#   거래 데이터는 행 삭제를 하지 않았으므로 행 수가 완전히 같아야 한다.
# =============================================================================
check("행 개수 보존", f"{len(raw):,}행", f"{len(clean):,}행", len(raw) == len(clean))

raw_ids = set(raw["order_id"])
clean_ids = set(clean["order_id"])
check("order_id 집합 일치", "원본과 동일",
      f"누락 {len(raw_ids - clean_ids):,} / 추가 {len(clean_ids - raw_ids):,}",
      raw_ids == clean_ids)

check("order_id 중복 없음", "0건",
      f"{clean['order_id'].duplicated().sum():,}건",
      clean["order_id"].duplicated().sum() == 0)


# =============================================================================
# [검사 2] 키 컬럼 불변 검증
#   정제 과정에서 키를 건드리지 않았음을 확인한다.
#   order_id 기준으로 원본과 정제본을 붙여서 값이 같은지 비교한다.
# =============================================================================
merged = raw[["order_id", "customer_id", "product_id"]].merge(
    clean[["order_id", "customer_id", "product_id"]],
    on="order_id", suffixes=("_raw", "_clean"))

for key in ["customer_id", "product_id"]:
    diff = (merged[f"{key}_raw"] != merged[f"{key}_clean"]).sum()
    check(f"{key} 값 불변", "0건 변경", f"{diff:,}건", diff == 0)


# =============================================================================
# [검사 3] 참조 정합성 (외래키)
#   마스터에 없는 키를 가리키는 주문이 있으면
#   PostgreSQL에서 FOREIGN KEY 제약 생성이 실패한다.
# =============================================================================
orphan_c = int((~clean["customer_id"].isin(cust["customer_id"])).sum())
orphan_p = int((~clean["product_id"].isin(prod["product_id"])).sum())

check("customer_id 참조 정합성", "고아 0건", f"{orphan_c:,}건", orphan_c == 0)
check("product_id 참조 정합성", "고아 0건", f"{orphan_p:,}건", orphan_p == 0)


# =============================================================================
# [검사 4] 범주형 컬럼 허용값
# =============================================================================
pay_bad = int((~clean["payment_method"].isin(VALID_PAYMENT)).sum())
check("payment_method 허용값", "0건 위반", f"{pay_bad:,}건", pay_bad == 0)
check("payment_method 종류 수", "4종", f"{clean['payment_method'].nunique()}종",
      clean["payment_method"].nunique() == 4)

st_bad = int((~clean["status"].isin(VALID_STATUS)).sum())
check("status 허용값", "0건 위반", f"{st_bad:,}건", st_bad == 0)
check("status 종류 수", "3종", f"{clean['status'].nunique()}종",
      clean["status"].nunique() == 3)


# =============================================================================
# [검사 5] order_amount
#   NULL은 허용된다(의도적으로 비웠으므로).
#   단, NULL이 아닌 값은 반드시 0보다 커야 한다.
# =============================================================================
amount = pd.to_numeric(clean["order_amount"], errors="coerce")
amount_null = int(clean["order_amount"].isna().sum())

check("금액 0 이하 없음", "0건", f"{int((amount <= 0).sum()):,}건",
      (amount <= 0).sum() == 0)
check("금액 NULL 건수 일치", f"{EXPECTED_AMOUNT_NULL:,}건", f"{amount_null:,}건",
      amount_null == EXPECTED_AMOUNT_NULL)

# 상수형 오염값이 정제본에 남아 있지 않은지 확인
amount_const_left = int(amount.isin([0, 1200, -50]).sum())
check("금액 상수값 잔존 없음", "0건", f"{amount_const_left:,}건", amount_const_left == 0)


# =============================================================================
# [검사 6] order_date
#   남은 날짜는 전부 표준 형식이어야 하고, 정상 범위 안에 있어야 한다.
# =============================================================================
date_str = clean["order_date"].fillna("")
non_null_date = date_str[date_str != ""]

bad_format = int((~non_null_date.str.match(STANDARD_DATE)).sum())
check("날짜 표준형식", "0건 위반", f"{bad_format:,}건", bad_format == 0)

parsed = pd.to_datetime(non_null_date, errors="coerce", format="%Y-%m-%d")
check("날짜 파싱 가능", "0건 실패", f"{int(parsed.isna().sum()):,}건",
      parsed.isna().sum() == 0)

today = pd.Timestamp.today().normalize()
check("미래 날짜 없음", "0건", f"{int((parsed > today).sum()):,}건",
      (parsed > today).sum() == 0)

date_null = int(clean["order_date"].isna().sum())
check("날짜 NULL 건수 일치", f"{EXPECTED_DATE_NULL:,}건", f"{date_null:,}건",
      date_null == EXPECTED_DATE_NULL)


# =============================================================================
# [검사 7] quantity
# =============================================================================
qty = pd.to_numeric(clean["quantity"], errors="coerce")
qty_valid = qty.dropna()

out_of_range = int(((qty_valid < 1) | (qty_valid > 5)).sum())
check("수량 범위(1~5)", "0건 위반", f"{out_of_range:,}건", out_of_range == 0)

non_integer = int((qty_valid != qty_valid.round()).sum())
check("수량 정수", "0건 위반", f"{non_integer:,}건", non_integer == 0)

qty_null = int(clean["quantity"].isna().sum())
check("수량 NULL 건수 일치", f"{EXPECTED_QTY_NULL:,}건", f"{qty_null:,}건",
      qty_null == EXPECTED_QTY_NULL)


# =============================================================================
# [검사 8] NULL과 플래그의 짝 검증
#
#   이 검사가 orders에서 가장 중요하다.
#   값을 비웠으면 반드시 사유가 있어야 하고,
#   사유가 있는데 값이 남아 있어도 안 된다.
#   둘이 어긋나면 "왜 비었는지 모르는 값"이나 "사유는 있는데 안 비워진 값"이 생긴다.
# =============================================================================
PAIRS = [
    ("order_amount", "amount_flag"),
    ("order_date", "date_flag"),
    ("quantity", "quantity_flag"),
]

for value_col, flag_col in PAIRS:
    # NULL인데 사유가 없는 경우
    null_no_flag = int((clean[value_col].isna() & clean[flag_col].isna()).sum())
    check(f"{value_col} NULL에 사유 있음", "0건 누락", f"{null_no_flag:,}건",
          null_no_flag == 0)

    # 사유가 있는데 값이 남아 있는 경우
    flag_with_value = int((clean[flag_col].notna() & clean[value_col].notna()).sum())
    check(f"{value_col} 사유 있으면 NULL", "0건 불일치", f"{flag_with_value:,}건",
          flag_with_value == 0)


# =============================================================================
# [검사 9] 원본 값 보존 검증
#   _raw 컬럼에 정말 원본값이 들어있는지 확인한다.
#   실수로 정제 후에 복사했다면 _raw에도 정제값이 들어가 보존이 무의미해진다.
# =============================================================================
PRESERVE_COLS = ["order_amount", "order_date", "quantity"]

raw_lookup = raw.set_index("order_id")
clean_indexed = clean.set_index("order_id")

for col in PRESERVE_COLS:
    raw_col = f"{col}_raw"
    exists = raw_col in clean.columns
    check(f"{raw_col} 컬럼 존재", "존재", "존재" if exists else "없음", exists)
    if not exists:
        continue

    # 원본 파일의 같은 order_id 값과 대조한다
    a = raw_lookup[col].reindex(clean_indexed.index).fillna("")
    b = clean_indexed[raw_col].fillna("")
    mismatch = int((a.values != b.values).sum())
    check(f"{raw_col} 원본 일치", "0건 불일치", f"{mismatch:,}건", mismatch == 0)


# =============================================================================
# [출력] 검증 결과 리포트
# =============================================================================
result_df = pd.DataFrame(checks)
all_passed = (result_df["판정"] == "합격").all()

lines = []
lines.append("=" * 84)
lines.append("orders_300k 정제 검증 결과 (5단계)")
lines.append("=" * 84)
lines.append("")
lines.append(f"{'검사항목':<32}{'기대':<20}{'실제':<20}{'판정'}")
lines.append("-" * 84)
for _, r in result_df.iterrows():
    lines.append(f"{r['검사항목']:<32}{r['기대']:<20}{str(r['실제']):<20}{r['판정']}")
lines.append("-" * 84)
lines.append("")
lines.append(f"검사 항목 {len(result_df)}개 중 합격 {(result_df['판정']=='합격').sum()}개")
lines.append(f"종합 판정 : "
             f"{'전체 합격 — PostgreSQL 적재 가능' if all_passed else '불합격 항목 있음 — 4단계 재확인 필요'}")
lines.append("")

lines.append("-" * 84)
lines.append("[NULL 처리 사유별 내역 — 의도적으로 비운 값]")
lines.append("-" * 84)
for value_col, flag_col in PAIRS:
    lines.append(f"\n  ■ {value_col}  (NULL {int(clean[value_col].isna().sum()):,}건)")
    for k, v in clean[flag_col].value_counts().items():
        lines.append(f"      {k:<32} {v:>8,}건")
lines.append("")
lines.append("  ※ NULL은 규칙 위반이 아니라 '값을 신뢰할 수 없어 비운 것'이다.")
lines.append("     모든 NULL에 사유가 기록되어 있고, 원본값은 _raw 컬럼에 보존되어 있다.")
lines.append("")

lines.append("-" * 84)
lines.append("[분석 가능 데이터 규모]")
lines.append("-" * 84)
lines.append(f"  전체 주문                : {len(clean):,}건")
lines.append(f"  금액 분석 가능           : {len(clean)-amount_null:,}건 "
             f"({(len(clean)-amount_null)/len(clean)*100:.1f}%)")
lines.append(f"  시계열(날짜) 분석 가능    : {len(clean)-date_null:,}건 "
             f"({(len(clean)-date_null)/len(clean)*100:.1f}%)")
lines.append(f"  수량 분석 가능           : {len(clean)-qty_null:,}건 "
             f"({(len(clean)-qty_null)/len(clean)*100:.1f}%)")
lines.append(f"  결제수단·상태 분석 가능   : {len(clean):,}건 (100.0%)")
lines.append("")
lines.append("  ※ 컬럼마다 분석 가능 규모가 다르다.")
lines.append("     7단계 SQL 분석에서 쿼리마다 모수가 달라지므로,")
lines.append("     결과를 제시할 때 '몇 건 기준인지'를 함께 표기해야 한다.")


# =============================================================================
# [출력] Before / After 비교표
# =============================================================================
raw_amount = pd.to_numeric(
    raw["order_amount"].fillna("").str.strip().str.replace(",", "", regex=False)
    .replace("", None), errors="coerce")
raw_date = raw["order_date"].fillna("").str.strip()
raw_qty = pd.to_numeric(raw["quantity"].fillna("").str.strip().replace("", None),
                        errors="coerce")

compare = [
    {"지표": "전체 행 수", "정제 전": len(raw), "정제 후": len(clean)},
    {"지표": "payment_method 종류", "정제 전": raw["payment_method"].nunique(),
     "정제 후": clean["payment_method"].nunique()},
    {"지표": "status 종류", "정제 전": raw["status"].nunique(),
     "정제 후": clean["status"].nunique()},
    {"지표": "quantity 종류", "정제 전": raw["quantity"].nunique(),
     "정제 후": int(clean["quantity"].nunique())},
    {"지표": "날짜 형식 종류", "정제 전": 5, "정제 후": 1},
    {"지표": "날짜 사용 가능 건수",
     "정제 전": int(raw_date.str.match(STANDARD_DATE).sum()),
     "정제 후": len(clean) - date_null},
    {"지표": "금액 음수 건수", "정제 전": int((raw_amount < 0).sum()),
     "정제 후": int((amount < 0).sum())},
    {"지표": "금액 0원 건수", "정제 전": int((raw_amount == 0).sum()),
     "정제 후": int((amount == 0).sum())},
    {"지표": "수량 비정상 건수",
     "정제 전": int(((raw_qty <= 0) | raw_qty.isna()).sum()),
     "정제 후": int(((qty_valid < 1) | (qty_valid > 5)).sum())},
    {"지표": "고아 레코드", "정제 전": 0, "정제 후": orphan_c + orphan_p},
]

compare_df = pd.DataFrame(compare)
compare_df.to_csv(os.path.join(REPORT_DIR, "비교표_orders.csv"),
                  index=False, encoding="utf-8-sig")

lines.append("")
lines.append("-" * 84)
lines.append("[정제 전후 비교]")
lines.append("-" * 84)
lines.append(f"{'지표':<28}{'정제 전':>14}{'정제 후':>14}")
for _, r in compare_df.iterrows():
    lines.append(f"{r['지표']:<28}{r['정제 전']:>14,}{r['정제 후']:>14,}")

with open(os.path.join(REPORT_DIR, "검증결과_orders.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print()
print("저장 완료 : 04_reports/검증결과_orders.txt")
print("저장 완료 : 04_reports/비교표_orders.csv")
