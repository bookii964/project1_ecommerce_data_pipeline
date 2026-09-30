# =============================================================================
# 파일명 : 09_profile_orders.py
# 단계   : 1단계 - 컬럼별 프로파일링 (주문 거래 데이터)
#
# [목적]
#   orders_300k 파일을 관찰해서 "무엇이 정상인지" 파악한다.
#
# [앞선 두 파일과 달라진 점]
#
#   ① 거래(트랜잭션) 데이터다
#      product_catalog와 crm은 '마스터 데이터'였다. 상품 목록, 고객 명부처럼
#      대상 자체를 정의하는 데이터다.
#      orders는 '거래 데이터'다. 마스터를 참조해서 "누가 무엇을 샀는가"를 기록한다.
#      → 그래서 프로파일링 단계에서부터 마스터와 대조해야 한다.
#        존재하지 않는 고객이나 상품을 가리키는 주문(=고아 레코드)이 있으면
#        6단계에서 외래키 제약을 걸 때 적재가 실패한다.
#
#   ② 30만 행이다
#      메모리에 올릴 수는 있지만(약 50MB), 한 행씩 도는 방식은 매우 느리다.
#      CRM과 마찬가지로 전부 벡터 연산으로 처리한다.
#
#   ③ 날짜 형식이 여러 개 섞여 있다
#      단순히 "형식 위반 몇 건"으로 세면 안 되고,
#      어떤 형식이 몇 종류로 섞여 있는지를 분류해야 복원 방법을 정할 수 있다.
#
# [입력]  01_raw/orders_300k_dirty.csv
#         03_cleaned/crm_customers_cleaned.csv     (마스터 — 대조용)
#         03_cleaned/product_catalog_cleaned.csv   (마스터 — 대조용)
# [출력]  02_profiling/orders/
#           - 01_기본정보.txt        : 행/열, 결측, 고유값
#           - 02_범주형_값분포.txt    : payment_method / status / quantity 전체 목록
#           - 03_날짜형식_분류.csv    : order_date 형식별 건수와 특징
#           - 04_참조정합성.txt       : 마스터 테이블과의 대조 결과
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


df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(df):,}행 × {len(df.columns)}열")
print()


# =============================================================================
# [출력 1] 기본 정보
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("orders_300k 기본 정보")
lines.append("=" * 84)
lines.append(f"전체 행 수 : {len(df):,}")
lines.append(f"전체 열 수 : {len(df.columns)}")
lines.append("")

role = {
    "order_id": "주문 고유번호 (기본키 후보)",
    "customer_id": "주문한 고객 (crm_customers 참조 = 외래키)",
    "product_id": "주문한 상품 (product_catalog 참조 = 외래키)",
    "order_amount": "주문 금액",
    "order_date": "주문 일자",
    "payment_method": "결제 수단 (범주형)",
    "status": "주문 상태 (범주형)",
    "quantity": "주문 수량",
}
lines.append("컬럼 목록 및 역할")
lines.append("-" * 84)
for c in df.columns:
    lines.append(f"  {c:<16} {role.get(c, '(미분류)')}")
lines.append("")

lines.append("-" * 84)
lines.append("[컬럼별 결측 및 고유값]")
lines.append("-" * 84)
lines.append(f"{'컬럼명':<16}{'결측':>10}{'결측률':>10}{'고유값':>12}")
for c in df.columns:
    n_null = df[c].isna().sum()
    lines.append(f"{c:<16}{n_null:>10,}{n_null/len(df)*100:>9.1f}%{df[c].nunique():>12,}")
lines.append("")

lines.append("-" * 84)
lines.append("[중복 검사]")
lines.append("-" * 84)
lines.append(f"완전 중복 행     : {df.duplicated().sum():,}건")
lines.append(f"order_id 중복    : {df['order_id'].duplicated().sum():,}건")
lines.append("")
lines.append("  ※ 거래 데이터는 마스터와 달리 중복이 없는 것이 일반적이다.")
lines.append("     같은 주문이 두 번 기록되면 매출이 두 배로 집계되므로 반드시 확인한다.")

with open(os.path.join(OUTPUT_DIR, "01_기본정보.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("01_기본정보.txt 저장 완료")


# =============================================================================
# [출력 2] 범주형 컬럼 값 분포
#   payment_method, status, quantity는 값 종류가 적으므로 전체를 확인한다.
#   quantity는 숫자 컬럼이지만 고유값이 10개뿐이라 범주형처럼 관찰하는 편이 낫다.
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("범주형 컬럼 값 분포")
lines.append("=" * 84)
lines.append("")

for c in ["payment_method", "status", "quantity"]:
    counts = df[c].value_counts(dropna=False)
    lines.append("-" * 84)
    lines.append(f"[{c}]  고유값 {df[c].nunique()}종")
    lines.append("-" * 84)
    for value, cnt in counts.items():
        # 따옴표로 감싸야 앞뒤 공백이나 빈 문자열이 눈에 보인다
        lines.append(f"  '{value}'  →  {cnt:,}건")
    lines.append("")

with open(os.path.join(OUTPUT_DIR, "02_범주형_값분포.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("02_범주형_값분포.txt 저장 완료")


# =============================================================================
# [출력 3] order_date 형식 분류
#
#   날짜는 "형식 위반 몇 건"으로만 세면 복원 방법을 정할 수 없다.
#   어떤 형식이 섞여 있는지 분류해야 각각을 어떻게 되돌릴지 판단할 수 있다.
#
#   특히 중요한 확인 : 각 형식의 '고유값 개수'
#     고유값이 1개뿐이라면 그건 날짜가 아니라 '상수'다.
#     즉 시스템이 값을 못 채웠을 때 넣은 대체값일 가능성이 높다.
#     (product_catalog의 price -100이 26건 전부 같았던 것과 같은 패턴)
# =============================================================================
date_series = df["order_date"]

def classify_date(value):
    if pd.isna(value):
        return "결측"
    v = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return "YYYY-MM-DD (표준)"
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", v):
        return "YYYY/MM/DD (슬래시)"
    if re.fullmatch(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", v):
        return "YYYY/MM/DD HH:MM (슬래시+시각)"
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}", v):
        return "DD-MM-YYYY (일-월-년)"
    if "T" in v:
        return "ISO8601 (T구분+마이크로초)"
    return "기타"

date_type = date_series.map(classify_date)

rows = []
for fmt in date_type.unique():
    subset = date_series[date_type == fmt]
    n_unique = subset.nunique()
    rows.append({
        "형식": fmt,
        "건수": len(subset),
        "고유값수": n_unique,
        "판정": "상수(실질 결측 의심)" if n_unique == 1 else ("정상" if fmt.startswith("YYYY-MM-DD") else "형식변환 필요"),
        "예시": str(subset.dropna().iloc[0]) if len(subset.dropna()) else "",
    })

date_df = pd.DataFrame(rows).sort_values("건수", ascending=False)
date_df.to_csv(os.path.join(OUTPUT_DIR, "03_날짜형식_분류.csv"),
               index=False, encoding="utf-8-sig")
print("03_날짜형식_분류.csv 저장 완료")
print()
print(date_df.to_string(index=False))
print()


# =============================================================================
# [출력 4] 참조 정합성 — 마스터 테이블과 대조
#
#   거래 데이터의 핵심 검사다.
#   주문에 적힌 customer_id / product_id가 마스터에 실제로 존재해야 한다.
#   존재하지 않으면 '고아 레코드'라고 부르며, 다음 문제가 생긴다:
#     - PostgreSQL에서 FOREIGN KEY 제약 생성이 실패한다
#     - 조인 시 해당 주문이 통째로 사라져 매출이 과소 집계된다
# =============================================================================
cust = read_csv_safe(CUST_FILE, dtype=str, keep_default_na=True)
prod = read_csv_safe(PROD_FILE, dtype=str, keep_default_na=True)

lines = []
lines.append("=" * 84)
lines.append("참조 정합성 검사 (마스터 테이블 대조)")
lines.append("=" * 84)
lines.append("")

lines.append("-" * 84)
lines.append("[customer_id → crm_customers]")
lines.append("-" * 84)
orphan_cust = ~df["customer_id"].isin(cust["customer_id"])
lines.append(f"  마스터 고객 수          : {len(cust):,}명")
lines.append(f"  주문에 등장한 고객 수    : {df['customer_id'].nunique():,}명")
lines.append(f"  고아 주문(고객 없음)     : {int(orphan_cust.sum()):,}건")
lines.append(f"  주문이 없는 고객         : {len(set(cust['customer_id']) - set(df['customer_id'])):,}명")
lines.append("")
lines.append("  ※ '주문이 없는 고객'은 오류가 아니다. 가입만 하고 구매하지 않은 고객이다.")
lines.append("     오히려 분석 대상이 된다 (미구매 고객 특성 분석).")
lines.append("")

lines.append("-" * 84)
lines.append("[product_id → product_catalog]")
lines.append("-" * 84)
orphan_prod = ~df["product_id"].isin(prod["product_id"])
lines.append(f"  마스터 상품 수          : {len(prod):,}개")
lines.append(f"  주문에 등장한 상품 수    : {df['product_id'].nunique():,}개")
lines.append(f"  고아 주문(상품 없음)     : {int(orphan_prod.sum()):,}건")
lines.append("")

lines.append("-" * 84)
lines.append("[주문 금액 vs 상품 단가 — 계산 검증 가능성 확인]")
lines.append("-" * 84)
lines.append("  주문 금액이 '단가 × 수량'과 맞는지 확인하면, 금액 오류를 잡아낼 수 있다.")
lines.append("  실제로 계산이 성립하는지 먼저 검증했다.")
lines.append("")

merged = df.merge(prod[["product_id", "price"]], on="product_id", how="left")
amount = pd.to_numeric(merged["order_amount"].str.strip(), errors="coerce")
price = pd.to_numeric(merged["price"], errors="coerce")
qty = pd.to_numeric(merged["quantity"].str.strip(), errors="coerce")

valid = amount.notna() & price.notna() & (amount > 0)
corr = amount[valid].corr(price[valid])

both = valid & qty.notna() & (qty > 0)
ratio = (amount / (price * qty))[both]
match_rate = ((ratio - 1).abs() < 0.01).mean()

lines.append(f"  주문금액과 상품단가의 상관계수     : {corr:.4f}")
lines.append(f"  주문금액 = 단가 × 수량 인 비율    : {match_rate*100:.2f}%")
lines.append("")
lines.append("  → 상관계수가 0에 가깝고 일치율도 0%대다.")
lines.append("     주문 금액은 상품 단가와 아무 관계가 없다는 뜻이다.")
lines.append("     따라서 '단가 × 수량'으로 금액 오류를 검증하거나 복원할 수 없다.")
lines.append("     (검증 방법을 시도했으나 데이터가 뒷받침하지 않아 기각한 사례)")

with open(os.path.join(OUTPUT_DIR, "04_참조정합성.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("04_참조정합성.txt 저장 완료")
print()
print("\n".join(lines))
print()
print(f"모든 결과 저장 위치 : {OUTPUT_DIR}")
