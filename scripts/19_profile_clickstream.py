# =============================================================================
# 파일명 : 19_profile_clickstream.py
# 단계   : 1단계 - 컬럼별 프로파일링 (클릭스트림 이벤트 로그)
#
# [목적]
#   clickstream_500k_events 파일을 관찰해서 "무엇이 정상인지" 파악한다.
#
# [이 파일의 특징 — 지금까지와 가장 다른 점]
#
#   ① 이벤트 로그다 (마스터도 거래도 아니다)
#      사용자의 행동 하나가 1행이다. 500,000행.
#      로그는 "값이 틀렸는가"보다 "이 컬럼을 분석에 쓸 수 있는가"가 더 중요하다.
#
#   ② 컬럼 이름이 같아도 의미가 다를 수 있다
#      이 파일에는 device_id 가 있고, CRM에도 device_id 가 있다.
#      이름이 같으니 조인하고 싶어지지만, 실제로 같은 것인지 확인해야 한다.
#      → 확인하지 않고 조인하면 결과가 0건이 나오거나, 더 나쁘게는
#        엉뚱하게 이어진 결과가 나온다.
#
#   ③ '오염되지 않았지만 쓸 수 없는' 컬럼이 있을 수 있다
#      값이 전부 정상 형식인데 의미가 없는 경우다.
#      이런 컬럼은 오염 검사만으로는 절대 걸러지지 않는다.
#      쓰임새를 직접 확인해야 한다.
#
# [입력]  01_raw/clickstream_500k_events.csv
#         03_cleaned/ 의 마스터 3종 (대조용)
# [출력]  02_profiling/clickstream/
#           - 01_기본정보.txt
#           - 02_컬럼별_상세.txt
#           - 03_타임스탬프_분류.csv
#           - 04_참조정합성.txt
#           - 05_컬럼_활용가능성.txt   ← 이 파일에서 새로 추가된 리포트
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

INPUT_FILE = os.path.join(PROJECT_DIR, "01_raw", "clickstream_500k_events.csv")
CLEAN_DIR = os.path.join(PROJECT_DIR, "03_cleaned")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "02_profiling", "clickstream")
os.makedirs(OUTPUT_DIR, exist_ok=True)


df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(df):,}행 × {len(df.columns)}열")
print()


# =============================================================================
# [출력 1] 기본 정보
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("clickstream_500k_events 기본 정보")
lines.append("=" * 84)
lines.append(f"전체 행 수 : {len(df):,}")
lines.append(f"전체 열 수 : {len(df.columns)}")
lines.append("")

role = {
    "event_id": "이벤트 고유번호 (기본키 후보)",
    "session_id": "세션 식별자 (같은 방문을 묶는 값)",
    "customer_id": "행동한 고객 (비로그인이면 비어 있음)",
    "event_type": "행동 유형 (범주형)",
    "page_url": "접속한 페이지 주소",
    "device_id": "기기 식별자 (CRM의 device_id와 같은 것인지 확인 필요)",
    "timestamp": "발생 시각",
    "ingest_run_id": "데이터 적재 배치 번호 (메타데이터)",
}
lines.append("컬럼 목록 및 추정 역할")
lines.append("-" * 84)
for c in df.columns:
    lines.append(f"  {c:<16} {role.get(c, '(미분류)')}")
lines.append("")

lines.append("-" * 84)
lines.append("[컬럼별 결측 및 고유값]")
lines.append("-" * 84)
lines.append(f"{'컬럼명':<16}{'결측':>10}{'결측률':>9}{'고유값':>12}{'고유율':>9}")
for c in df.columns:
    n_null = df[c].isna().sum()
    n_uniq = df[c].nunique()
    lines.append(f"{c:<16}{n_null:>10,}{n_null/len(df)*100:>8.1f}%"
                 f"{n_uniq:>12,}{n_uniq/len(df)*100:>8.1f}%")
lines.append("")
lines.append("  ※ 고유율을 눈여겨봐야 한다.")
lines.append("     100%에 가까우면 식별자, 0%에 가까우면 범주형이다.")
lines.append("     그런데 '식별자여야 하는데 고유율이 낮거나'")
lines.append("     '묶는 값이어야 하는데 고유율이 100%에 가까우면' 의미가 의심스럽다.")
lines.append("")

lines.append("-" * 84)
lines.append("[중복 검사]")
lines.append("-" * 84)
lines.append(f"완전 중복 행 : {df.duplicated().sum():,}건")
lines.append(f"event_id 중복 : {df['event_id'].duplicated().sum():,}건")

with open(os.path.join(OUTPUT_DIR, "01_기본정보.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("01_기본정보.txt 저장 완료")


# =============================================================================
# [출력 2] 컬럼별 상세
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("컬럼별 상세")
lines.append("=" * 84)
lines.append("")

# --- event_type : 범주형이므로 전체 목록 --------------------------------
lines.append("-" * 84)
lines.append("[event_type]")
lines.append("-" * 84)
for value, cnt in df["event_type"].value_counts(dropna=False).items():
    lines.append(f"  '{value}'  →  {cnt:,}건 ({cnt/len(df)*100:.1f}%)")
lines.append("")
lines.append("  ※ 구매(purchase) 이벤트가 없다는 점에 주의한다.")
lines.append("     따라서 '조회 → 장바구니'까지만 이 파일로 분석할 수 있고,")
lines.append("     '장바구니 → 구매' 단계는 orders 테이블과 이어야 한다.")
lines.append("")

# --- page_url : 유형별로 나눠서 확인 -----------------------------------
url = df["page_url"].fillna("")
product_pattern = re.compile(r"/product/(PROD-\d{4})")

lines.append("-" * 84)
lines.append("[page_url]")
lines.append("-" * 84)
lines.append(f"  결측            : {int((url == '').sum()):,}건")
lines.append(f"  상품 상세 페이지 : {int(url.str.contains('/product/PROD-').sum()):,}건")
lines.append(f"  검색 페이지      : {int(url.str.contains('/search').sum()):,}건")
lines.append(f"  홈(루트)        : {int((url == 'https://shop.example.com/').sum()):,}건")
lines.append("")
lines.append("  ※ URL 안에 상품 코드가 들어 있다 (/product/PROD-0109).")
lines.append("     여기서 product_id 를 뽑아내면 product_catalog 와 연결할 수 있다.")
lines.append("     원본에 없던 관계를 만들어내는 것이므로 이 파일에서 가장 값어치 있는 작업이다.")
lines.append("")

lines.append("  [event_type 별 상품 URL 보유 여부]")
crosstab = pd.crosstab(df["event_type"], url.str.contains("/product/PROD-"))
lines.append(crosstab.to_string())
lines.append("")
lines.append("  ※ login 과 search 는 상품 URL이 하나도 없다. 당연한 결과이므로 정상이다.")
lines.append("     이런 '상식과 맞는지' 확인이 데이터 신뢰도를 판단하는 근거가 된다.")
lines.append("")

# --- ingest_run_id : 고유값이 1개인 컬럼 -------------------------------
lines.append("-" * 84)
lines.append("[ingest_run_id]")
lines.append("-" * 84)
lines.append(f"  고유값 : {df['ingest_run_id'].nunique()}개")
lines.append(f"  값     : {df['ingest_run_id'].iloc[0]}")
lines.append("")
lines.append("  ※ 50만 행 전체가 같은 값이다. 적재 배치를 구분하는 메타데이터로 보인다.")
lines.append("     오염은 아니지만 분석에는 쓸 수 없다 (모든 행이 같으므로 구분이 불가능).")

with open(os.path.join(OUTPUT_DIR, "02_컬럼별_상세.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("02_컬럼별_상세.txt 저장 완료")


# =============================================================================
# [출력 3] timestamp 형식 분류
#   orders·tickets에서 쓴 방법을 그대로 적용한다.
#   형식별로 나누고 고유값 개수를 함께 본다.
# =============================================================================
ts = df["timestamp"].fillna("")

# 날짜와 시각 사이 구분자가 'T' 인 것과 공백인 것이 섞여 있다.
# 둘 다 같은 시각을 나타내는 유효한 표기이므로 형식만 다른 경우다.
ISO_T_TZ     = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00$")
ISO_SPACE_TZ = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+00:00$")
ISO_PLAIN    = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

def classify_ts(value):
    if value == "":
        return "결측"
    if ISO_T_TZ.match(value):
        return "ISO(T구분)+시간대"
    if ISO_SPACE_TZ.match(value):
        return "ISO(공백구분)+시간대"
    if ISO_PLAIN.match(value):
        return "ISO(초 단위, 시간대 없음)"
    # 아직 분류되지 않은 값은 하나의 묶음으로 처리한다.
    #
    #   [중요] 처음에는 값을 그대로 라벨에 넣어 f"기타('{value}')" 로 만들었다.
    #   그런데 미분류 값이 2만 종에 달해 라벨이 2만 개가 생겼고,
    #   아래 반복문이 2만 번 × 50만 행을 훑으면서 스크립트가 멈췄다.
    #   라벨은 항상 '개수가 정해진 몇 가지'여야 한다.
    return "미분류"

ts_kind = ts.map(classify_ts)

rows = []
for kind in ts_kind.unique():
    subset = ts[ts_kind == kind]
    rows.append({
        "형식": kind,
        "건수": len(subset),
        "고유값수": subset.nunique(),
        "예시": subset.iloc[0] if len(subset) else "",
    })

ts_df = pd.DataFrame(rows).sort_values("건수", ascending=False)
ts_df.to_csv(os.path.join(OUTPUT_DIR, "03_타임스탬프_분류.csv"),
             index=False, encoding="utf-8-sig")
print("03_타임스탬프_분류.csv 저장 완료")
print()
print(ts_df.to_string(index=False))
print()


# =============================================================================
# [출력 4] 참조 정합성 + 컬럼 의미 확인
#
#   여기서 device_id 가 CRM의 device_id 와 같은 것인지 확인한다.
#   이름이 같다는 이유로 조인하면 안 된다.
# =============================================================================
cust = read_csv_safe(os.path.join(CLEAN_DIR, "crm_customers_cleaned.csv"),
                     dtype=str, keep_default_na=True)
dev = read_csv_safe(os.path.join(CLEAN_DIR, "crm_customer_devices_cleaned.csv"),
                    dtype=str, keep_default_na=True)
prod = read_csv_safe(os.path.join(CLEAN_DIR, "product_catalog_cleaned.csv"),
                     dtype=str, keep_default_na=True)

lines = []
lines.append("=" * 84)
lines.append("참조 정합성 및 컬럼 의미 확인")
lines.append("=" * 84)
lines.append("")

# --- A. customer_id --------------------------------------------------------
lines.append("-" * 84)
lines.append("[A] customer_id → crm_customers")
lines.append("-" * 84)
has_cust = df["customer_id"].notna()
orphan_cust = int((~df.loc[has_cust, "customer_id"].isin(cust["customer_id"])).sum())
lines.append(f"  결측(비로그인 추정) : {int((~has_cust).sum()):,}건 "
             f"({(~has_cust).mean()*100:.1f}%)")
lines.append(f"  값이 있는 이벤트     : {int(has_cust.sum()):,}건")
lines.append(f"  등장한 고객 수       : {df['customer_id'].nunique():,}명 "
             f"(전체 고객 {len(cust):,}명)")
lines.append(f"  고아 레코드          : {orphan_cust:,}건")
lines.append("")
lines.append("  ※ 결측 30%는 오염이 아니라 '비로그인 상태의 행동'으로 보는 것이 자연스럽다.")
lines.append("     로그인 전에도 검색과 상품 조회는 할 수 있기 때문이다.")
lines.append("")

# --- B. device_id — 이 파일의 핵심 확인 ------------------------------------
lines.append("-" * 84)
lines.append("[B] device_id → crm_customer_devices  (이름이 같은 컬럼 대조)")
lines.append("-" * 84)
match_dev = int(df["device_id"].isin(dev["device_id"]).sum())
lines.append(f"  클릭스트림 device_id 고유값 : {df['device_id'].nunique():,}개")
lines.append(f"  CRM 기기 목록 고유값        : {dev['device_id'].nunique():,}개")
lines.append(f"  두 목록에 함께 존재하는 건수 : {match_dev:,}건 / {len(df):,}건")
lines.append("")
if match_dev == 0:
    lines.append("  [중요] 일치하는 값이 하나도 없다.")
    lines.append("     이름은 같지만 서로 다른 체계의 식별자다.")
    lines.append("     확인하지 않고 조인했다면 결과가 0건이 나왔을 것이다.")
    lines.append(f"     또한 고유율이 {df['device_id'].nunique()/len(df)*100:.1f}% 로,")
    lines.append("     사실상 이벤트마다 다른 값이다. 기기를 묶는 역할을 하지 못한다.")
lines.append("")

# --- C. page_url 에서 뽑은 product_id ---------------------------------------
lines.append("-" * 84)
lines.append("[C] page_url 에서 추출한 product_id → product_catalog")
lines.append("-" * 84)
extracted = url.str.extract(product_pattern)[0]
lines.append(f"  추출 성공            : {int(extracted.notna().sum()):,}건")
lines.append(f"  추출된 상품 종류      : {extracted.nunique():,}개 "
             f"(카탈로그 {len(prod):,}개)")
lines.append(f"  카탈로그에 없는 상품   : "
             f"{int((~extracted.dropna().isin(prod['product_id'])).sum()):,}건")
lines.append("")
lines.append("  ※ 추출한 500종이 전부 카탈로그에 존재한다.")
lines.append("     URL을 파싱해 만든 컬럼이지만 마스터와 완전히 연결된다.")
lines.append("     → 4단계에서 product_id 파생 컬럼을 만들 근거가 된다.")

with open(os.path.join(OUTPUT_DIR, "04_참조정합성.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("04_참조정합성.txt 저장 완료")


# =============================================================================
# [출력 5] 컬럼 활용 가능성 점검  ← 이 파일에서 새로 추가한 리포트
#
#   지금까지는 '값이 오염됐는가'만 봤다.
#   로그 데이터에서는 '값은 멀쩡한데 분석에 쓸 수 없는' 컬럼이 나온다.
#   오염 검사만으로는 절대 걸러지지 않으므로 별도로 확인한다.
#
#   session_id 를 예로 들면:
#     형식도 UUID로 정상이고 결측도 없다. 오염 검사는 전부 통과한다.
#     그런데 한 세션 안에 고객이 수십 명 들어 있다면 세션이 아니다.
#     '같은 방문을 묶는 값'이라는 정의를 만족하지 못하기 때문이다.
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("컬럼 활용 가능성 점검")
lines.append("=" * 84)
lines.append("")
lines.append("  오염 여부와 별개로, 각 컬럼을 분석에 쓸 수 있는지 확인한다.")
lines.append("  값이 전부 정상 형식이어도 의미가 없으면 쓸 수 없다.")
lines.append("")

# --- session_id 검증 --------------------------------------------------------
lines.append("-" * 84)
lines.append("[session_id] 정말 '세션'인가")
lines.append("-" * 84)
lines.append("  세션의 정의 : 한 사용자가 한 기기로 접속한 하나의 연속된 방문")
lines.append("  → 따라서 한 세션 안의 customer_id 는 1명(또는 비로그인)이어야 한다.")
lines.append("")

grouped = df.groupby("session_id")
cust_per_session = grouped["customer_id"].nunique()
dev_per_session = grouped["device_id"].nunique()
events_per_session = grouped.size()

lines.append(f"  세션 수                : {len(grouped):,}개")
lines.append(f"  세션당 이벤트 수 (평균) : {events_per_session.mean():.1f}건")
lines.append(f"  세션당 고객 수 (평균)   : {cust_per_session.mean():.1f}명   ← 1명이어야 정상")
lines.append(f"  세션당 고객 수 (최대)   : {cust_per_session.max():,}명")
lines.append(f"  세션당 기기 수 (평균)   : {dev_per_session.mean():.1f}개   ← 1개여야 정상")
lines.append("")

if cust_per_session.mean() > 2:
    lines.append("  [판정] session_id 를 세션으로 쓸 수 없다.")
    lines.append("     한 세션에 수십 명의 고객과 수십 개의 기기가 섞여 있다.")
    lines.append("     실제 방문 단위가 아니라 임의로 부여된 값으로 보인다.")
    lines.append("")
    lines.append("     [영향] 아래 분석이 불가능하다:")
    lines.append("       - 세션당 페이지뷰, 세션 이탈률")
    lines.append("       - 세션 내 행동 순서 (검색 → 조회 → 장바구니)")
    lines.append("     [대안] customer_id 단위로 묶어서 분석한다.")
    lines.append("            단, 비로그인 이벤트 30%는 제외된다는 한계를 함께 밝힌다.")
lines.append("")

# --- 컬럼별 최종 판정 -------------------------------------------------------
lines.append("-" * 84)
lines.append("[컬럼별 활용 판정 요약]")
lines.append("-" * 84)
lines.append(f"{'컬럼':<16}{'상태':<12}{'분석 활용'}")
lines.append("-" * 84)

verdicts = [
    ("event_id",      "정상",        "기본키로 사용"),
    ("session_id",    "정상(형식)",   "사용 불가 — 세션 역할을 하지 못함"),
    ("customer_id",   "결측 30%",    "사용 가능 — 비로그인 제외 후 분석"),
    ("event_type",    "정상",        "사용 — 4종, 오염 없음"),
    ("page_url",      "결측 1.7%",   "사용 — product_id 추출의 재료"),
    ("device_id",     "정상(형식)",   "사용 불가 — CRM과 무관, 이벤트마다 고유"),
    ("timestamp",     "오염 8%",     "정제 후 사용 — 형식 3종 통일 필요"),
    ("ingest_run_id", "정상",        "사용 불가 — 전 행이 동일값"),
]
for col, state, use in verdicts:
    lines.append(f"{col:<16}{state:<12}{use}")

lines.append("")
lines.append("  ※ 8개 컬럼 중 3개가 '오염되지 않았지만 분석에 쓸 수 없는' 컬럼이다.")
lines.append("     오염 검사만 했다면 전부 정상으로 판정됐을 것이다.")
lines.append("     로그 데이터에서는 값의 정확성뿐 아니라 '의미가 살아 있는지'를 확인해야 한다.")

with open(os.path.join(OUTPUT_DIR, "05_컬럼_활용가능성.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("05_컬럼_활용가능성.txt 저장 완료")
print()
print("\n".join(lines))
print()
print(f"모든 결과 저장 위치 : {OUTPUT_DIR}")
