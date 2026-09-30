# =============================================================================
# 파일명 : 01_profile_product_catalog.py
# 단계   : 1단계 - 컬럼별 프로파일링 (정상 데이터 파악)
#
# [목적]
#   원본 데이터를 "고치기 전에" 먼저 관찰한다.
#   어떤 컬럼이 있고, 어떤 값들이 들어있고, 무엇이 정상인지를 눈으로 확인하는 단계다.
#   이 단계에서는 데이터를 절대 수정하지 않는다. 오직 읽고 요약만 한다.
#
# [입력]  01_raw/product_catalog_dirty_30pct.csv
# [출력]  02_profiling/product_catalog/ 폴더 안에
#           - 01_기본정보.txt            : 행/열 수, 컬럼명, 결측치 요약
#           - 02_컬럼별_고유값.txt        : 컬럼마다 어떤 값들이 있는지 전체 목록
#           - 03_category_값분포.csv      : category 컬럼 값별 개수
#           - 04_price_형식검사.csv       : price 컬럼에서 숫자로 안 읽히는 값 목록
#
# [중요]
#   모든 컬럼을 문자열(str)로 읽는다.
#   pandas가 알아서 숫자로 바꿔버리면 " 32309.95"의 앞 공백이나
#   "1,200"의 쉼표 같은 오염을 못 보고 지나치기 때문이다.
#   원본을 "있는 그대로" 봐야 오염을 찾을 수 있다.
# =============================================================================

import os
import re
import pandas as pd


# -----------------------------------------------------------------------------
# [설정] 경로 지정
#   이 스크립트가 scripts\ 폴더 안에 있다고 가정하고,
#   한 단계 위(project_1)를 기준으로 경로를 계산한다.
#   → 나중에 폴더를 통째로 옮겨도 코드를 안 고쳐도 된다.
# -----------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))   # scripts 폴더 경로
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)                 # project_1 폴더 경로

INPUT_FILE = os.path.join(PROJECT_DIR, "01_raw", "product_catalog_dirty_30pct.csv")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "02_profiling", "product_catalog")

# 결과를 저장할 폴더가 없으면 자동으로 만든다. (exist_ok=True → 이미 있으면 그냥 넘어감)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [1] 원본 파일 읽기
# -----------------------------------------------------------------------------
# dtype=str        : 모든 값을 문자열로 읽는다 (위 [중요] 설명 참고)
# keep_default_na  : 빈 칸만 결측(NaN)으로 처리하고, "NA"나 "null" 같은 글자는
#                    일단 글자 그대로 둔다. 그런 값이 있는지도 확인해야 하니까.
df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=True)

print(f"원본 파일을 읽었습니다: {INPUT_FILE}")
print(f"행 개수: {len(df)}  /  열 개수: {len(df.columns)}")
print()


# -----------------------------------------------------------------------------
# [2] 기본정보 리포트 만들기
#     - 전체 크기, 컬럼 목록, 결측치 개수와 비율
#     - 결측치란 값이 비어있는 칸을 말한다. 정제 방향을 정하는 첫 기준이 된다.
# -----------------------------------------------------------------------------
lines = []
lines.append("=" * 70)
lines.append("product_catalog 기본 정보")
lines.append("=" * 70)
lines.append(f"전체 행 수 : {len(df)}")
lines.append(f"전체 열 수 : {len(df.columns)}")
lines.append(f"컬럼 목록  : {list(df.columns)}")
lines.append("")

lines.append("-" * 70)
lines.append("[컬럼별 결측치 현황]")
lines.append("-" * 70)
lines.append(f"{'컬럼명':<20}{'결측 개수':>12}{'결측 비율':>12}{'고유값 수':>12}")

for col in df.columns:
    null_count = df[col].isna().sum()               # 빈 칸 개수
    null_pct = null_count / len(df) * 100           # 전체 대비 비율(%)
    unique_count = df[col].nunique()                # 서로 다른 값이 몇 종류인지
    lines.append(f"{col:<20}{null_count:>12}{null_pct:>11.1f}%{unique_count:>12}")

lines.append("")

# 완전히 똑같은 행이 중복으로 들어있는지 확인한다.
lines.append("-" * 70)
lines.append("[중복 검사]")
lines.append("-" * 70)
lines.append(f"모든 값이 동일한 완전 중복 행 : {df.duplicated().sum()} 건")
lines.append(f"product_id 중복 건수          : {df['product_id'].duplicated().sum()} 건")
lines.append("  ※ product_id는 상품을 구분하는 고유 키(PK)이므로 중복이 0이어야 정상이다.")

# 파일로 저장 (encoding='utf-8-sig' → 윈도우 메모장/엑셀에서 한글이 깨지지 않는다)
with open(os.path.join(OUTPUT_DIR, "01_기본정보.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("01_기본정보.txt 저장 완료")


# -----------------------------------------------------------------------------
# [3] 컬럼별 고유값 목록 만들기
#     "이 컬럼에 정상적으로 들어와야 할 값이 무엇인가"를 판단하려면
#     실제로 어떤 값들이 들어있는지 전부 봐야 한다.
#     - 고유값이 적은 컬럼(category 등) → 전체 목록을 본다
#     - 고유값이 많은 컬럼(product_name 등) → 앞부분 샘플만 본다
# -----------------------------------------------------------------------------
lines = []
lines.append("=" * 70)
lines.append("컬럼별 고유값 목록")
lines.append("=" * 70)
lines.append("")

for col in df.columns:
    uniques = sorted(df[col].dropna().unique())     # 결측 제외 + 가나다/알파벳순 정렬
    lines.append("-" * 70)
    lines.append(f"[{col}]  고유값 {len(uniques)}종")
    lines.append("-" * 70)

    if len(uniques) <= 100:
        # 종류가 적으면 전부 출력한다.
        # 정렬해두면 'beauty', 'beauty ', 'beauty_', 'b3auty'처럼
        # 비슷한 오타끼리 나란히 붙어서 오염이 한눈에 보인다.
        for v in uniques:
            lines.append(f"  '{v}'")     # 따옴표로 감싸야 앞뒤 공백이 눈에 보인다
    else:
        lines.append(f"  (종류가 많아 앞 50개만 표시)")
        for v in uniques[:50]:
            lines.append(f"  '{v}'")
    lines.append("")

with open(os.path.join(OUTPUT_DIR, "02_컬럼별_고유값.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("02_컬럼별_고유값.txt 저장 완료")


# -----------------------------------------------------------------------------
# [4] category 컬럼 값 분포 (값별로 몇 건씩 있는지)
#     개수를 함께 보면 "어느 것이 정상 표기이고 어느 것이 소수의 오타인지"
#     구분할 수 있다. 보통 건수가 압도적으로 많은 쪽이 정상 표기다.
# -----------------------------------------------------------------------------
category_counts = df["category"].value_counts(dropna=False).reset_index()
category_counts.columns = ["category_값", "건수"]

category_counts.to_csv(
    os.path.join(OUTPUT_DIR, "03_category_값분포.csv"),
    index=False, encoding="utf-8-sig"
)
print("03_category_값분포.csv 저장 완료")


# -----------------------------------------------------------------------------
# [5] price 컬럼 형식 검사
#     가격은 "숫자"여야 정상이다. 그런데 문자열로 읽어보면
#     앞뒤 공백, 천단위 쉼표, 음수, 0 같은 비정상 값이 섞여 있을 수 있다.
#     여기서는 '표준 형식(소수점 둘째 자리 숫자)'에 맞지 않는 값을 전부 뽑아낸다.
#
#     정규표현식 r'^\d+\.\d{2}$' 의 의미:
#       ^        문자열 시작
#       \d+      숫자 1개 이상
#       \.       마침표
#       \d{2}    숫자 정확히 2개
#       $        문자열 끝
#     → "32309.95"는 통과, " 32309.95"(앞 공백)나 "1,200"(쉼표)은 불통과
# -----------------------------------------------------------------------------
STANDARD_PRICE = re.compile(r"^\d+\.\d{2}$")

abnormal_rows = []
for idx, value in df["price"].items():
    if pd.isna(value):
        reason = "결측(빈 값)"
    elif STANDARD_PRICE.match(value):
        continue                                    # 정상이므로 기록하지 않고 넘어감
    else:
        # 왜 비정상인지 사유를 붙여준다. 3단계(유형 분류)에서 바로 쓰인다.
        reasons = []
        if value != value.strip():
            reasons.append("앞뒤 공백")
        if "," in value:
            reasons.append("천단위 쉼표")
        # strip 후 숫자로 변환이 되는지 확인
        try:
            num = float(value.replace(",", "").strip())
            if num < 0:
                reasons.append("음수")
            elif num == 0:
                reasons.append("0원")
            if "." not in value.strip() or len(value.strip().split(".")[-1]) != 2:
                reasons.append("소수점 자릿수 불일치")
        except ValueError:
            reasons.append("숫자로 변환 불가")
        reason = " / ".join(reasons) if reasons else "형식 불일치"

    abnormal_rows.append({
        "행번호(0부터)": idx,
        "product_id": df.loc[idx, "product_id"],
        "price_원본값": value,
        "의심사유": reason,
    })

price_report = pd.DataFrame(abnormal_rows)
price_report.to_csv(
    os.path.join(OUTPUT_DIR, "04_price_형식검사.csv"),
    index=False, encoding="utf-8-sig"
)

print(f"04_price_형식검사.csv 저장 완료 (의심 값 {len(price_report)}건)")
print()
print(f"모든 결과는 여기에 저장되었습니다:\n{OUTPUT_DIR}")
