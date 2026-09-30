# =============================================================================
# 파일명 : 04_verify_product_catalog.py
# 단계   : 5단계 - 정제 결과 검증
#
# [목적]
#   4단계에서 만든 정제본이 정말 규칙을 지켰는지 기계적으로 확인한다.
#   "잘 된 것 같다"가 아니라 검사 항목별로 합격/불합격을 판정한다.
#
# [왜 필요한가]
#   정제 코드에 실수가 있어도 파일은 아무 일 없다는 듯이 만들어진다.
#   예를 들어 정규식을 잘못 써서 절반만 고쳐졌어도 에러는 나지 않는다.
#   그래서 "고친 뒤에 다시 검사하는" 단계가 반드시 필요하다.
#   이 단계를 통과해야 비로소 PostgreSQL에 적재할 수 있다.
#
# [입력]  01_raw/product_catalog_dirty_30pct.csv      (원본)
#         03_cleaned/product_catalog_cleaned.csv      (정제본)
# [출력]  04_reports/검증결과_product_catalog.txt      (합격/불합격 판정표)
#         04_reports/비교표_product_catalog.csv        (정제 전후 Before/After 비교)
#
# [검증 원칙]
#   플래그가 붙은 값(끝자리 숫자, 고가 이상치)은 '의도적으로 남긴 것'이므로
#   불합격 처리하지 않는다. 검증은 규칙 위반을 찾는 것이지,
#   우리가 내린 판단을 다시 뒤집는 것이 아니다.
# =============================================================================

import os
import re
import pandas as pd


# -----------------------------------------------------------------------------
# [공통 함수] 인코딩 안전 CSV 읽기
#
# [왜 필요한가]
#   우리 스크립트는 항상 UTF-8로 파일을 저장한다.
#   그런데 중간에 CSV를 엑셀로 열고 저장하면, 윈도우 엑셀이 파일을
#   CP949(윈도우 한글 인코딩)로 다시 써버린다.
#   그 상태에서 UTF-8로 읽으려 하면 아래 에러가 난다:
#       UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc0
#
#   0xc0 은 UTF-8에는 존재할 수 없는 바이트이고, CP949에서 한글을 표현할 때
#   나오는 값이다. 즉 "이 파일은 UTF-8이 아니다"라는 신호다.
#
# [해결]
#   UTF-8로 먼저 시도하고, 실패하면 CP949로 다시 시도한다.
#   어떤 인코딩으로 읽었는지 화면에 알려주어, 파일이 변조됐다는 사실을
#   사용자가 인지할 수 있게 한다.
# -----------------------------------------------------------------------------
def read_csv_safe(path, **kwargs):
    for encoding in ["utf-8-sig", "cp949", "utf-8"]:
        try:
            df = pd.read_csv(path, encoding=encoding, **kwargs)
            if encoding != "utf-8-sig":
                print(f"  [주의] 이 파일은 {encoding} 인코딩입니다: {os.path.basename(path)}")
                print(f"         엑셀로 열어 저장한 흔적입니다. 정제 스크립트를 다시 실행하면 UTF-8로 복구됩니다.")
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 판별할 수 없습니다: {path}")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

RAW_FILE = os.path.join(PROJECT_DIR, "01_raw", "product_catalog_dirty_30pct.csv")
CLEAN_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "product_catalog_cleaned.csv")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

VALID_CATEGORIES = [
    "automotive", "beauty", "clothing", "electronics",
    "home", "kitchen", "sports", "toys",
]
TYPO_DOUBLE = re.compile(r"(aa|ii|uu|jj|kk|vv|ww|yy|hh|qq|xx|zz)", re.IGNORECASE)
MISSING_SPACE = re.compile(r"[a-z][A-Z]")


# 원본은 문자열로, 정제본은 price만 숫자로 읽는다
raw = read_csv_safe(RAW_FILE, dtype=str, keep_default_na=True)
clean = read_csv_safe(CLEAN_FILE, dtype={"product_id": str, "product_name": str,
                                         "category": str, "price": float,
                                         "name_flag": str, "price_flag": str})

print(f"원본   : {len(raw)}행")
print(f"정제본 : {len(clean)}행")
print()


# -----------------------------------------------------------------------------
# 검사 결과를 담을 리스트
#   각 항목마다 (검사명, 기대값, 실제값, 합격여부)를 기록한다
# -----------------------------------------------------------------------------
checks = []

def check(name, expected, actual, passed):
    checks.append({
        "검사항목": name,
        "기대": expected,
        "실제": actual,
        "판정": "합격" if passed else "불합격",
    })


# =============================================================================
# [검사 1] 데이터 손실이 없는가
#   정제 과정에서 행이 사라지거나 상품이 바뀌면 안 된다.
#   특히 product_id는 orders 테이블이 참조하는 키이므로 절대 변하면 안 된다.
# =============================================================================
check("행 개수 보존", f"{len(raw)}행", f"{len(clean)}행", len(raw) == len(clean))

raw_ids = set(raw["product_id"])
clean_ids = set(clean["product_id"])
check("product_id 집합 일치",
      "원본과 동일",
      f"누락 {len(raw_ids - clean_ids)}건 / 추가 {len(clean_ids - raw_ids)}건",
      raw_ids == clean_ids)

check("product_id 중복 없음", "0건",
      f"{clean['product_id'].duplicated().sum()}건",
      clean["product_id"].duplicated().sum() == 0)


# =============================================================================
# [검사 2] category 규칙 준수
#   정상 8종 + unknown 외의 값이 하나라도 있으면 불합격
# =============================================================================
allowed = set(VALID_CATEGORIES) | {"unknown"}
actual_cats = set(clean["category"].dropna())
invalid_cats = actual_cats - allowed

check("category 허용값만 존재",
      "8종 + unknown",
      f"{len(actual_cats)}종" + (f" / 위반: {invalid_cats}" if invalid_cats else ""),
      len(invalid_cats) == 0)

check("category 결측 없음", "0건",
      f"{clean['category'].isna().sum()}건",
      clean["category"].isna().sum() == 0)


# =============================================================================
# [검사 3] product_name 규칙 준수
#   플래그 대상(끝자리 숫자)은 의도적으로 남긴 것이므로 검사에서 제외한다.
# =============================================================================
names = clean["product_name"].dropna()

space_bad = (names != names.str.strip()).sum()
check("상품명 앞뒤 공백 없음", "0건", f"{space_bad}건", space_bad == 0)

typo_bad = names.apply(lambda x: bool(TYPO_DOUBLE.search(x))).sum()
check("상품명 문자중복 오타 없음", "0건", f"{typo_bad}건", typo_bad == 0)

nospace_bad = names.apply(lambda x: bool(MISSING_SPACE.search(x))).sum()
check("상품명 단어사이 공백 정상", "0건", f"{nospace_bad}건", nospace_bad == 0)

# Title Case 확인 : 전부 대문자이거나 전부 소문자인 값이 없어야 한다
case_bad = names.apply(lambda x: x.isupper() or x.islower()).sum()
check("상품명 대소문자 통일", "0건", f"{case_bad}건", case_bad == 0)


# =============================================================================
# [검사 4] price 규칙 준수
#   NULL은 허용된다 (음수/0원을 의도적으로 NULL 처리했으므로).
#   단, NULL이 아닌 값은 반드시 0보다 커야 한다.
# =============================================================================
prices = clean["price"].dropna()

check("price 자료형 숫자", "float", str(clean["price"].dtype),
      pd.api.types.is_numeric_dtype(clean["price"]))

check("price 0 이하 없음", "0건", f"{(prices <= 0).sum()}건", (prices <= 0).sum() == 0)

# NULL 건수가 4단계에서 의도한 71건(음수26 + 0원19 + 원본결측26)과 맞는지
null_count = clean["price"].isna().sum()
check("price NULL 건수 일치", "71건 (음수26+0원19+결측26)",
      f"{null_count}건", null_count == 71)

# NULL인 행에는 반드시 사유(price_flag)가 기록돼 있어야 한다
null_without_flag = clean[clean["price"].isna() & clean["price_flag"].isna()]
check("NULL 가격에 사유 기록됨", "0건",
      f"사유 없는 NULL {len(null_without_flag)}건",
      len(null_without_flag) == 0)


# =============================================================================
# [검사 5] 플래그 현황 (판정이 아니라 확인용)
#   의도적으로 남긴 값이 몇 건인지 기록만 한다.
# =============================================================================
flag_name = clean["name_flag"].notna().sum()
flag_price = clean["price_flag"].notna().sum()


# =============================================================================
# [출력 1] 검증 결과 리포트
# =============================================================================
result_df = pd.DataFrame(checks)
all_passed = (result_df["판정"] == "합격").all()

lines = []
lines.append("=" * 78)
lines.append("product_catalog 정제 검증 결과 (5단계)")
lines.append("=" * 78)
lines.append("")
lines.append(f"{'검사항목':<28}{'기대':<24}{'실제':<20}{'판정'}")
lines.append("-" * 78)
for _, r in result_df.iterrows():
    lines.append(f"{r['검사항목']:<28}{r['기대']:<24}{str(r['실제']):<20}{r['판정']}")
lines.append("-" * 78)
lines.append("")
lines.append(f"종합 판정 : {'전체 합격 — PostgreSQL 적재 가능' if all_passed else '불합격 항목 있음 — 4단계 재확인 필요'}")
lines.append("")

lines.append("-" * 78)
lines.append("[의도적으로 남긴 값 (플래그)]")
lines.append("-" * 78)
lines.append(f"  name_flag  : {flag_name}건  — 상품명 끝자리 숫자, 실제 모델명일 수 있어 유지")
lines.append(f"  price_flag : {flag_price}건  — NULL 처리 사유 및 고가 이상치 표시")
lines.append("  ※ 이 값들은 규칙 위반이 아니라 '판단 보류'이므로 불합격 대상이 아니다.")


# =============================================================================
# [출력 2] Before / After 비교표
#   포트폴리오에서 성과를 한눈에 보여주는 핵심 자료다.
# =============================================================================
raw_price = pd.to_numeric(raw["price"].str.replace(",", "").str.strip(), errors="coerce")

compare = [
    {"지표": "전체 행 수",
     "정제 전": len(raw), "정제 후": len(clean)},
    {"지표": "category 값 종류",
     "정제 전": raw["category"].nunique(), "정제 후": clean["category"].nunique()},
    {"지표": "category 결측",
     "정제 전": raw["category"].isna().sum(), "정제 후": clean["category"].isna().sum()},
    {"지표": "상품명 앞뒤공백",
     "정제 전": (raw["product_name"] != raw["product_name"].str.strip()).sum(),
     "정제 후": space_bad},
    {"지표": "상품명 오타(문자중복)",
     "정제 전": raw["product_name"].apply(lambda x: bool(TYPO_DOUBLE.search(str(x)))).sum(),
     "정제 후": typo_bad},
    {"지표": "가격 음수",
     "정제 전": (raw_price < 0).sum(), "정제 후": (prices < 0).sum()},
    {"지표": "가격 0원",
     "정제 전": (raw_price == 0).sum(), "정제 후": (prices == 0).sum()},
    {"지표": "가격 사용 가능 건수",
     "정제 전": ((raw_price > 0)).sum(), "정제 후": len(prices)},
]

compare_df = pd.DataFrame(compare)
compare_df.to_csv(
    os.path.join(REPORT_DIR, "비교표_product_catalog.csv"),
    index=False, encoding="utf-8-sig"
)

lines.append("")
lines.append("-" * 78)
lines.append("[정제 전후 비교]")
lines.append("-" * 78)
lines.append(f"{'지표':<26}{'정제 전':>12}{'정제 후':>12}")
for _, r in compare_df.iterrows():
    lines.append(f"{r['지표']:<26}{r['정제 전']:>12}{r['정제 후']:>12}")

with open(os.path.join(REPORT_DIR, "검증결과_product_catalog.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print()
print("저장 완료 : 04_reports/검증결과_product_catalog.txt")
print("저장 완료 : 04_reports/비교표_product_catalog.csv")
