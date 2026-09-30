# =============================================================================
# 파일명 : 02_detect_product_catalog.py
# 단계   : 3단계 - 비정상 데이터 색출 및 유형 분류
#
# [목적]
#   2단계에서 문서로 정한 규칙(데이터사전_product_catalog.md)을 코드로 옮겨서,
#   규칙을 위반한 값을 전부 찾아내고 "왜 위반인지" 사유를 붙인다.
#
# [매우 중요]
#   이 단계에서도 데이터를 고치지 않는다. 찾아서 기록만 한다.
#   고치는 것은 4단계다. 왜 나누는가?
#     → 먼저 전체 오염 현황을 숫자로 파악해야 정제 방향이 맞는지 검증할 수 있고,
#       "정제 전에 무엇이 얼마나 잘못돼 있었는지"가 포트폴리오의 핵심 근거가 되기 때문이다.
#
# [입력]  01_raw/product_catalog_dirty_30pct.csv
# [출력]  02_profiling/product_catalog/
#           - 05_이상데이터_상세.csv   : 위반 건 1건당 1행 (어떤 상품의 어떤 컬럼이 왜 위반인지)
#           - 06_유형별_집계.csv       : 컬럼×유형별 건수 요약
#           - 07_진단요약.txt          : 사람이 읽는 요약 리포트
#
# [분류 구분 3가지]  ← 2단계 규칙서에서 정한 개념
#   오염     : 값 자체가 틀림. 반드시 고쳐야 함  (예: 'KITCHEN', '3l3ctronics')
#   표준화   : 값은 맞는데 표기만 다름           (예: '2215.4' → '2215.40')
#   확인필요 : 맞는지 틀린지 알 수 없음. 사람 판단 필요 (예: 상품명 끝 숫자, 고가 이상치)
#   → 이 셋을 섞어서 세면 "오염 몇 건"이라는 리포트 숫자가 부정확해진다.
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
OUTPUT_DIR = os.path.join(PROJECT_DIR, "02_profiling", "product_catalog")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 2단계에서 확정한 규칙 상수
#   코드 여기저기에 값을 흩어놓지 않고 맨 위에 모아둔다.
#   규칙이 바뀌면 이 부분만 고치면 되므로 유지보수가 쉽다.
# -----------------------------------------------------------------------------

# category 허용값 8종
VALID_CATEGORIES = [
    "automotive", "beauty", "clothing", "electronics",
    "home", "kitchen", "sports", "toys",
]

# 영어에서 거의 나타나지 않는 문자 중복 → 오타로 판단
#   ll, ss, tt 같은 정상 자음 중복은 제외했다 (Small, Address 같은 정상 단어를 망가뜨리므로)
TYPO_DOUBLE = re.compile(r"(aa|ii|uu|jj|kk|vv|ww|yy|hh|qq|xx|zz)", re.IGNORECASE)

# 소문자 뒤에 바로 대문자가 오는 패턴 → 단어 사이 공백 누락 (예: StartWear)
MISSING_SPACE = re.compile(r"[a-z][A-Z]")

# 가격 표준 형식 : 숫자 + 마침표 + 숫자 2자리
STANDARD_PRICE = re.compile(r"^\d+\.\d{2}$")

# 고가 이상치 기준 : 1단계에서 계산한 IQR 상한 (Q3 + 1.5 * IQR)
#   ※ 이 값은 데이터로부터 계산된 것이며, 이 기준을 넘는다고 틀린 값은 아니다.
#      '통계적으로 튄다'는 표시일 뿐이므로 '확인필요'로 분류한다.
PRICE_OUTLIER_THRESHOLD = 82970.63


# -----------------------------------------------------------------------------
# [1] 원본 읽기 (1단계와 동일하게 전부 문자열로)
# -----------------------------------------------------------------------------
df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(df)}행")


# 위반 사항을 하나씩 담을 리스트.
# 최종적으로 "위반 1건 = 1행" 형태의 표가 된다.
# 한 상품이 여러 컬럼에서 위반하면 여러 행으로 기록된다.
issues = []

def record(row_idx, product_id, column, raw_value, issue_type, kind):
    """위반 사항 1건을 기록하는 함수.
    kind : '오염' / '표준화' / '확인필요' 중 하나
    """
    issues.append({
        "행번호": row_idx,
        "product_id": product_id,
        "컬럼": column,
        "원본값": raw_value,
        "위반유형": issue_type,
        "분류구분": kind,
    })


# -----------------------------------------------------------------------------
# [2] 컬럼별 검사
#   df.iterrows() 로 한 행씩 순회한다.
#   500행짜리 작은 파일이라 이 방식이 읽기 쉽고 충분히 빠르다.
#   (30만 행짜리 orders에서는 속도 때문에 다른 방식을 쓸 것이다)
# -----------------------------------------------------------------------------
for idx, row in df.iterrows():
    pid = row["product_id"]

    # ---------------------------------------------------------------------
    # 2-1. product_id 검사 : PROD-숫자4자리 형식인가
    # ---------------------------------------------------------------------
    if pd.isna(pid):
        record(idx, pid, "product_id", pid, "결측", "오염")
    elif not re.fullmatch(r"PROD-\d{4}", pid):
        record(idx, pid, "product_id", pid, "형식위반", "오염")

    # ---------------------------------------------------------------------
    # 2-2. product_name 검사
    # ---------------------------------------------------------------------
    name = row["product_name"]
    if pd.isna(name):
        record(idx, pid, "product_name", name, "결측", "오염")
    else:
        # ① 앞뒤 공백 : 원본과 공백 제거본이 다르면 공백이 있다는 뜻
        if name != name.strip():
            record(idx, pid, "product_name", name, "앞뒤공백", "표준화")

        stripped = name.strip()

        # ② 대소문자 불일치 : 전부 대문자이거나 전부 소문자면 Title Case 위반
        if stripped.isupper():
            record(idx, pid, "product_name", name, "전부대문자", "표준화")
        elif stripped.islower():
            record(idx, pid, "product_name", name, "전부소문자", "표준화")

        # ③ 단어 사이 공백 누락
        if MISSING_SPACE.search(stripped):
            record(idx, pid, "product_name", name, "단어사이_공백누락", "오염")

        # ④ 문자 중복 오타
        if TYPO_DOUBLE.search(stripped):
            record(idx, pid, "product_name", name, "문자중복_오타", "오염")

        # ⑤ 끝에 숫자 → 고치지 않고 표시만 (2단계에서 유지하기로 결정)
        if re.search(r"\d$", stripped):
            record(idx, pid, "product_name", name, "끝자리_숫자포함", "확인필요")

    # ---------------------------------------------------------------------
    # 2-3. category 검사
    #   오염 유형을 "한 번에 하나씩" 벗겨내면서 어떤 문제가 걸려 있는지 전부 기록한다.
    #   한 값에 공백+대문자+숫자치환이 동시에 있을 수 있으므로 if를 연달아 쓴다.
    # ---------------------------------------------------------------------
    cat = row["category"]
    if pd.isna(cat):
        record(idx, pid, "category", cat, "결측", "오염")
    else:
        # ① 앞뒤 공백
        if cat != cat.strip():
            record(idx, pid, "category", cat, "앞뒤공백", "오염")
        work = cat.strip()

        # ② 대문자 포함
        if work != work.lower():
            record(idx, pid, "category", cat, "대문자표기", "오염")
        work = work.lower()

        # ③ 끝에 특수문자 (- 또는 _)
        if work != work.rstrip("_-"):
            record(idx, pid, "category", cat, "끝_특수문자", "오염")
        work = work.rstrip("_-")

        # ④ 숫자 치환 (3 → e)
        if "3" in work:
            record(idx, pid, "category", cat, "숫자치환(3→e)", "오염")
        work = work.replace("3", "e")

        # ⑤ 위 처리를 다 하고도 정상 8종에 없으면 축약형
        if work not in VALID_CATEGORIES:
            # 앞글자가 일치하는 정상값 후보를 찾는다
            candidates = [v for v in VALID_CATEGORIES if v.startswith(work)]
            if len(candidates) == 1:
                record(idx, pid, "category", cat, f"축약형(→{candidates[0]})", "오염")
            else:
                # 후보가 0개거나 2개 이상이면 자동 복원 불가 → 사람 판단 필요
                record(idx, pid, "category", cat, "복원불가_미확인값", "확인필요")

    # ---------------------------------------------------------------------
    # 2-4. price 검사
    # ---------------------------------------------------------------------
    price = row["price"]
    if pd.isna(price):
        record(idx, pid, "price", price, "결측", "오염")
    else:
        # ① 앞뒤 공백
        if price != price.strip():
            record(idx, pid, "price", price, "앞뒤공백", "표준화")

        # ② 천단위 쉼표
        if "," in price:
            record(idx, pid, "price", price, "천단위_쉼표", "표준화")

        # 숫자로 바꿔서 값 자체의 문제를 검사한다
        cleaned = price.replace(",", "").strip()
        try:
            num = float(cleaned)

            # ③ 음수 : 판매가로 불가능. -100이 반복되므로 시스템 대체값으로 판단
            if num < 0:
                record(idx, pid, "price", price, "음수(대체값 추정)", "오염")
            # ④ 0원 : 판매가로 성립하지 않음
            elif num == 0:
                record(idx, pid, "price", price, "0원", "오염")
            else:
                # ⑤ 고가 이상치 : 값은 유효하나 통계적으로 튐 → 유지하고 표시만
                if num > PRICE_OUTLIER_THRESHOLD:
                    record(idx, pid, "price", price, "고가이상치", "확인필요")

            # ⑥ 소수점 자릿수 : 값은 맞는데 표기만 다른 경우 → 표준화
            #    (음수/0에도 해당될 수 있으나 그건 이미 오염으로 잡혔으므로 중복 기록해도 무방)
            if not STANDARD_PRICE.fullmatch(cleaned):
                record(idx, pid, "price", price, "소수점_자릿수불일치", "표준화")

        except ValueError:
            # 숫자로 아예 변환이 안 되는 값 (문자가 섞인 경우 등)
            record(idx, pid, "price", price, "숫자변환_불가", "오염")


# -----------------------------------------------------------------------------
# [3] 결과 1 : 이상 데이터 상세 목록 저장
# -----------------------------------------------------------------------------
issue_df = pd.DataFrame(issues)
issue_df.to_csv(
    os.path.join(OUTPUT_DIR, "05_이상데이터_상세.csv"),
    index=False, encoding="utf-8-sig"
)
print(f"05_이상데이터_상세.csv 저장 완료 (총 {len(issue_df)}건)")


# -----------------------------------------------------------------------------
# [4] 결과 2 : 컬럼 × 유형별 집계표 저장
#   groupby : 같은 조합끼리 묶어서 개수를 센다
# -----------------------------------------------------------------------------
summary = (
    issue_df.groupby(["컬럼", "분류구분", "위반유형"])
    .size()
    .reset_index(name="건수")
    .sort_values(["컬럼", "분류구분", "건수"], ascending=[True, True, False])
)
summary.to_csv(
    os.path.join(OUTPUT_DIR, "06_유형별_집계.csv"),
    index=False, encoding="utf-8-sig"
)
print("06_유형별_집계.csv 저장 완료")


# -----------------------------------------------------------------------------
# [5] 결과 3 : 사람이 읽는 요약 리포트
# -----------------------------------------------------------------------------
lines = []
lines.append("=" * 70)
lines.append("product_catalog 오염 진단 요약 (3단계)")
lines.append("=" * 70)
lines.append(f"전체 행 수        : {len(df)}")
lines.append(f"위반 건수(누적)   : {len(issue_df)}")

# 한 상품이 여러 위반을 가질 수 있으므로, '위반이 하나라도 있는 상품 수'를 따로 센다
affected = issue_df["product_id"].nunique()
lines.append(f"위반이 있는 상품 수 : {affected} / {len(df)} ({affected/len(df)*100:.1f}%)")
lines.append("")

lines.append("-" * 70)
lines.append("[분류 구분별 건수]")
lines.append("-" * 70)
for kind, cnt in issue_df["분류구분"].value_counts().items():
    lines.append(f"  {kind:<8} : {cnt:>5}건")
lines.append("")
lines.append("  오염     = 값이 틀림. 4단계에서 수정 대상")
lines.append("  표준화   = 값은 맞고 표기만 다름. 형식 통일 대상")
lines.append("  확인필요 = 정답을 알 수 없음. 수정하지 않고 플래그로 표시")
lines.append("")

lines.append("-" * 70)
lines.append("[컬럼별 · 유형별 상세]")
lines.append("-" * 70)
for col in ["product_id", "product_name", "category", "price"]:
    sub = issue_df[issue_df["컬럼"] == col]
    lines.append(f"\n■ {col}  (총 {len(sub)}건)")
    if len(sub) == 0:
        lines.append("    위반 없음 — 정상")
        continue
    for (kind, itype), cnt in sub.groupby(["분류구분", "위반유형"]).size().items():
        lines.append(f"    [{kind}] {itype:<22} {cnt:>4}건")

with open(os.path.join(OUTPUT_DIR, "07_진단요약.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("07_진단요약.txt 저장 완료")
print()
print("\n".join(lines))
