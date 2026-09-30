# =============================================================================
# 파일명 : 03_clean_product_catalog.py
# 단계   : 4단계 - 정제 규칙 적용 및 정제 파일 생성
#
# [목적]
#   2단계 규칙서에서 정한 방침대로 값을 실제로 고치고, 새 파일로 저장한다.
#   1~3단계는 관찰만 했고, 값을 바꾸는 것은 이 단계가 처음이다.
#
# [절대 원칙]
#   원본 파일(01_raw)은 절대 수정하지 않는다.
#   원본을 읽어서 복사본을 고치고, 결과는 03_cleaned에 새 이름으로 저장한다.
#   → 정제가 잘못됐을 때 언제든 처음부터 다시 할 수 있어야 하기 때문이다.
#
# [입력]  01_raw/product_catalog_dirty_30pct.csv
# [출력]  03_cleaned/product_catalog_cleaned.csv   : 정제 완료 데이터
#         04_reports/변경이력_product_catalog.csv  : 무엇이 무엇으로 바뀌었는지 전수 기록
#         04_reports/정제로그_product_catalog.txt  : 처리 건수 요약
#
# [처리 방침 요약]  ← 2단계 규칙서 기준
#   자동수정   : 정답이 명확한 것 (공백/대소문자/특수문자/숫자치환/축약형/오타)
#   NULL처리   : 논리적으로 불가능한 값 (음수 가격, 0원)
#   대체값     : category 결측 → 'unknown'
#   유지+플래그: 정답을 알 수 없는 것 (상품명 끝 숫자, 고가 이상치)
#   행 삭제    : 하지 않음 (product_id를 orders가 참조하므로 삭제 시 조인이 깨짐)
# =============================================================================

import os
import re
import pandas as pd


# -----------------------------------------------------------------------------
# [설정] 경로
# -----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

INPUT_FILE = os.path.join(PROJECT_DIR, "01_raw", "product_catalog_dirty_30pct.csv")
CLEAN_DIR = os.path.join(PROJECT_DIR, "03_cleaned")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 규칙 상수 (3단계 스크립트와 동일하게 유지)
# -----------------------------------------------------------------------------
VALID_CATEGORIES = [
    "automotive", "beauty", "clothing", "electronics",
    "home", "kitchen", "sports", "toys",
]

# 오타로 판단할 문자 중복 (정상 영어 단어에 잘 안 나오는 조합만)
TYPO_DOUBLE = re.compile(r"(aa|ii|uu|jj|kk|vv|ww|yy|hh|qq|xx|zz)", re.IGNORECASE)

# 소문자 뒤 대문자 = 단어 사이 공백 누락
MISSING_SPACE = re.compile(r"([a-z])([A-Z])")

PRICE_OUTLIER_THRESHOLD = 82970.63


# 변경 이력을 담을 리스트 (어떤 값이 무엇으로 바뀌었는지 전부 기록)
changes = []

def log_change(pid, column, before, after, reason):
    """값이 바뀔 때마다 기록. 나중에 '왜 이렇게 바뀌었지?' 를 추적할 수 있게 한다."""
    changes.append({
        "product_id": pid,
        "컬럼": column,
        "변경전": before,
        "변경후": after,
        "처리사유": reason,
    })


# -----------------------------------------------------------------------------
# [정제 함수 1] product_name
#
#   처리 순서가 매우 중요하다:
#     ① 앞뒤 공백 제거
#     ② 단어 사이 공백 삽입   ← 반드시 ③보다 먼저!
#     ③ 문자 중복 오타 수정
#     ④ Title Case 통일
#
#   ②를 ④보다 먼저 해야 하는 이유:
#     'StartWear'를 먼저 Title Case로 바꾸면 'Startwear'가 되어
#     대문자 경계가 사라진다. 그러면 어디서 단어를 끊어야 할지 알 수 없게 된다.
#     반대로 공백을 먼저 넣으면 'Start Wear' → 'Start Wear' 로 잘 처리된다.
# -----------------------------------------------------------------------------
def clean_name(value, pid):
    if pd.isna(value):
        return value, None

    original = value
    flags = []

    # ① 앞뒤 공백 제거
    result = value.strip()

    # ② 단어 사이 공백 삽입 : 소문자와 대문자 사이에 공백을 넣는다
    #    r"\1 \2" 는 "앞글자 + 공백 + 뒷글자" 를 의미한다
    result = MISSING_SPACE.sub(r"\1 \2", result)

    # ③ 문자 중복 오타 수정 : 'aa' → 'a' 처럼 2글자를 1글자로 축소
    #    m.group(0)[0] 는 매칭된 두 글자 중 첫 글자만 가져온다는 뜻
    result = TYPO_DOUBLE.sub(lambda m: m.group(0)[0], result)

    # ④ Title Case : 각 단어의 첫 글자만 대문자로 통일
    result = result.title()

    # ⑤ 끝자리 숫자는 고치지 않고 표시만 (사용자 결정: 숫자 유지)
    if re.search(r"\d$", result):
        flags.append("숫자포함_확인필요")

    if result != original:
        log_change(pid, "product_name", original, result, "표기 표준화 및 오타 수정")

    return result, ("; ".join(flags) if flags else None)


# -----------------------------------------------------------------------------
# [정제 함수 2] category
#
#   2단계에서 확정한 5단계 변환을 순서대로 적용한다.
#   한 값에 여러 오염이 겹쳐 있으므로 한 겹씩 벗겨내야 한다.
#     예: ' KITCH3N ' → 'KITCH3N' → 'kitch3n' → 'kitch3n' → 'kitchen'
# -----------------------------------------------------------------------------
def clean_category(value, pid):
    # 결측 → 'unknown' (행을 살려야 orders 조인이 유지된다)
    if pd.isna(value):
        log_change(pid, "category", "(빈 값)", "unknown", "결측 → 대체값 입력")
        return "unknown"

    original = value

    result = value.strip()            # ① 앞뒤 공백
    result = result.lower()           # ② 소문자 통일
    result = result.rstrip("_-")      # ③ 끝의 특수문자 제거
    result = result.replace("3", "e")  # ④ 숫자 치환 복원 (3 → e)

    # ⑤ 아직 정상 8종에 없으면 축약형 → 앞글자로 복원
    if result not in VALID_CATEGORIES:
        candidates = [v for v in VALID_CATEGORIES if v.startswith(result)]
        if len(candidates) == 1:
            result = candidates[0]
        else:
            # 후보가 0개거나 2개 이상이면 임의로 정하지 않는다.
            # 잘못 복원하는 것보다 unknown이 안전하다.
            log_change(pid, "category", original, "unknown", "복원 불가 → unknown 처리")
            return "unknown"

    if result != original:
        log_change(pid, "category", original, result, "표기 정규화 및 축약형 복원")

    return result


# -----------------------------------------------------------------------------
# [정제 함수 3] price
#
#   반환값 2개 : (정제된 가격, 플래그)
#   가격은 숫자로 바꿔서 반환한다. 문자열로 두면 SQL에서 계산을 못 한다.
# -----------------------------------------------------------------------------
def clean_price(value, pid):
    if pd.isna(value):
        return None, "결측"

    original = value

    # ① 앞뒤 공백 제거 + ② 천단위 쉼표 제거
    cleaned = value.strip().replace(",", "")

    try:
        num = float(cleaned)
    except ValueError:
        log_change(pid, "price", original, "(빈 값)", "숫자 변환 불가 → NULL 처리")
        return None, "숫자변환불가"

    # ③ 음수 : -100이 26건 반복되므로 실제 가격이 아니라 시스템 대체값으로 판단
    if num < 0:
        log_change(pid, "price", original, "(빈 값)", "음수 대체값 → NULL 처리")
        return None, "음수대체값"

    # ④ 0원 : 판매가로 성립하지 않음
    if num == 0:
        log_change(pid, "price", original, "(빈 값)", "0원 → NULL 처리")
        return None, "0원"

    # ⑤ 소수점 2자리로 통일 (값은 그대로, 표기만 맞춤)
    result = round(num, 2)

    # ⑥ 고가 이상치 : 값은 그대로 두고 표시만 한다
    #    통계적으로 튄다는 것과 값이 틀렸다는 것은 다른 문제이므로 삭제하지 않는다.
    flag = "고가이상치_확인필요" if result > PRICE_OUTLIER_THRESHOLD else None

    if f"{result:.2f}" != original:
        log_change(pid, "price", original, f"{result:.2f}", "숫자 형식 표준화")

    return result, flag


# =============================================================================
# [실행] 원본 읽기 → 컬럼별 정제 → 저장
# =============================================================================
df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(df)}행")

# 정제 결과를 담을 새 표를 만든다. 원본 df는 건드리지 않는다.
cleaned_rows = []

for _, row in df.iterrows():
    pid = row["product_id"]

    name, name_flag = clean_name(row["product_name"], pid)
    category = clean_category(row["category"], pid)
    price, price_flag = clean_price(row["price"], pid)

    cleaned_rows.append({
        "product_id": pid,          # 기본키는 절대 변경하지 않는다
        "product_name": name,
        "category": category,
        "price": price,
        "name_flag": name_flag,     # 사람 확인이 필요한 상품명 사유
        "price_flag": price_flag,   # 사람 확인이 필요한 가격 사유
    })

clean_df = pd.DataFrame(cleaned_rows)


# -----------------------------------------------------------------------------
# 정제본 저장
#   float_format='%.2f' : 가격을 항상 소수점 2자리로 저장한다
# -----------------------------------------------------------------------------
output_path = os.path.join(CLEAN_DIR, "product_catalog_cleaned.csv")
clean_df.to_csv(output_path, index=False, encoding="utf-8-sig", float_format="%.2f")
print(f"정제 파일 저장 완료 : {output_path}")


# -----------------------------------------------------------------------------
# 변경 이력 저장
#   "어떤 상품의 어떤 값이 무엇으로 왜 바뀌었는지" 전수 기록.
#   나중에 결과에 의문이 생기면 이 파일에서 해당 product_id를 검색하면 된다.
# -----------------------------------------------------------------------------
change_df = pd.DataFrame(changes)
change_df.to_csv(
    os.path.join(REPORT_DIR, "변경이력_product_catalog.csv"),
    index=False, encoding="utf-8-sig"
)
print(f"변경 이력 저장 완료 : 총 {len(change_df)}건")


# -----------------------------------------------------------------------------
# 정제 로그 요약
# -----------------------------------------------------------------------------
lines = []
lines.append("=" * 70)
lines.append("product_catalog 정제 로그 (4단계)")
lines.append("=" * 70)
lines.append(f"원본 행 수   : {len(df)}")
lines.append(f"정제 행 수   : {len(clean_df)}   ← 행 삭제를 하지 않았으므로 동일해야 정상")
lines.append(f"값 변경 건수 : {len(change_df)}")
lines.append("")

lines.append("-" * 70)
lines.append("[처리 사유별 건수]")
lines.append("-" * 70)
for reason, cnt in change_df["처리사유"].value_counts().items():
    lines.append(f"  {reason:<32} {cnt:>5}건")
lines.append("")

lines.append("-" * 70)
lines.append("[정제 후 category 분포]  ← 8종 + unknown 만 나와야 정상")
lines.append("-" * 70)
for cat, cnt in clean_df["category"].value_counts().items():
    lines.append(f"  {cat:<15} {cnt:>5}건")
lines.append("")

lines.append("-" * 70)
lines.append("[정제 후 price 현황]")
lines.append("-" * 70)
valid_price = clean_df["price"].dropna()
lines.append(f"  유효 가격 건수 : {len(valid_price)}")
lines.append(f"  NULL 처리 건수 : {clean_df['price'].isna().sum()}")
lines.append(f"  최소 / 최대    : {valid_price.min():,.2f} / {valid_price.max():,.2f}")
lines.append(f"  평균 / 중앙값  : {valid_price.mean():,.2f} / {valid_price.median():,.2f}")
lines.append("")

lines.append("-" * 70)
lines.append("[플래그 현황]  ← 값을 고치지 않고 표시만 한 건")
lines.append("-" * 70)
for col in ["name_flag", "price_flag"]:
    lines.append(f"\n  ■ {col}")
    counts = clean_df[col].value_counts(dropna=True)
    if len(counts) == 0:
        lines.append("      없음")
    for k, v in counts.items():
        lines.append(f"      {k:<24} {v:>5}건")

with open(os.path.join(REPORT_DIR, "정제로그_product_catalog.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print()
print("\n".join(lines))
