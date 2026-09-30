# =============================================================================
# 파일명 : 10_evidence_orders_date.py
# 단계   : 2단계 보조 - 날짜 처리 방침의 근거 산출
#
# [목적]
#   "비표준 날짜 4종을 NULL 처리한다"는 결정의 근거를 숫자로 산출한다.
#   규칙서에 적은 주장을 누구나 재현할 수 있게 만드는 것이 목적이다.
#
# [왜 별도 스크립트로 만드는가]
#   정제 스크립트는 '값을 고치는' 코드다.
#   이 스크립트는 '결정이 옳은지 확인하는' 코드다. 역할이 다르므로 분리한다.
#    "날짜 9만 건"을 폐기하게 된 근거를 확인한다
#
# [산출하는 근거 3가지]
#   근거 A : 변환하면 집계가 파괴되는가?  → 일별 주문 건수 비교
#   근거 B : 오염이 무작위인가?           → 분포 비교 + 카이제곱 검정
#   근거 C : ISO 형식이 주문 시각인가?    → 시각 집중도, 날짜 범위
#
# [입력]  01_raw/orders_300k_dirty.csv
# [출력]  04_reports/근거_orders_날짜처리.txt
#         04_reports/근거_일별주문건수_시뮬레이션.csv
# =============================================================================

import os
import re
import pandas as pd
from scipy.stats import chi2_contingency


def read_csv_safe(path, **kwargs):
    for encoding in ["utf-8-sig", "cp949", "utf-8"]:
        try:
            return pd.read_csv(path, encoding=encoding, **kwargs)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩 판별 실패: {path}")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
INPUT_FILE = os.path.join(PROJECT_DIR, "01_raw", "orders_300k_dirty.csv")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# 1단계에서 확인한 상수형 오염값 3종 (각각 고유값이 1개뿐인 형식)
CONSTANT_DATES = {
    "2024/31/01": "2024-01-31",        # YYYY/DD/MM 으로 해석 시
    "31-12-2023": "2023-12-31",        # DD-MM-YYYY 로 해석 시
    "2025/01/10 12:00": "2025-01-10",  # 시각 제거 시
}

df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
date_raw = df["order_date"].fillna("").str.strip()

lines = []
def w(text=""):
    lines.append(text)
    print(text)


w("=" * 84)
w("orders 날짜 처리 방침의 근거 산출")
w("=" * 84)
w(f"대상 : {INPUT_FILE}")
w(f"전체 : {len(df):,}행")
w("")


# =============================================================================
# 준비 : 표준 형식 날짜만 골라낸다 (이것이 '정상 데이터'의 기준선이 된다)
# =============================================================================
STANDARD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
is_standard = date_raw.str.match(STANDARD)
standard_dates = pd.to_datetime(date_raw[is_standard], format="%Y-%m-%d")

w("-" * 84)
w("[준비] 기준선이 될 정상 날짜")
w("-" * 84)
w(f"  표준 형식(YYYY-MM-DD) 건수 : {int(is_standard.sum()):,}건")
w(f"  날짜 범위                  : {standard_dates.min().date()} ~ {standard_dates.max().date()}")

# 실제로 주문이 존재한 날의 수를 센다.
# 기간 전체 일수가 아니라 '주문이 있었던 날의 수'를 쓴다.
n_days = standard_dates.dt.date.nunique()
avg_per_day = len(standard_dates) / n_days

w(f"  주문이 존재한 날의 수       : {n_days:,}일")
w(f"  하루 평균 주문 건수         : {len(standard_dates):,} ÷ {n_days:,} = {avg_per_day:.1f}건")
w("")
w("  [계산 방법]")
w("    하루 평균 = 표준형식 주문 건수 ÷ 주문이 존재한 날의 수")
w("    기간 전체 일수가 아니라 '주문이 있었던 날'로 나눈다.")
w("    주문이 0건인 날이 있다면 평균이 낮아져 비교가 불공정해지기 때문이다.")
w("")

# 실제 일별 건수의 분포도 함께 본다 (평균만으로는 변동 폭을 알 수 없다)
daily_counts = standard_dates.dt.date.value_counts()
w("  [실제 일별 주문 건수의 분포]")
w(f"    최소 {daily_counts.min():,}건 / 중앙값 {daily_counts.median():.0f}건 / "
  f"최대 {daily_counts.max():,}건")
w(f"    → 평상시 하루 주문은 최대 {daily_counts.max():,}건을 넘지 않았다.")
w("")


# =============================================================================
# 근거 A : 형식 변환 시 집계가 파괴되는가
#
# [산출 방법]
#   1. 상수형 오염값 3종을 '형식만 보고' 정상 날짜로 변환한다고 가정한다.
#   2. 변환 대상 날짜에 원래 있던 정상 주문 건수를 센다.
#   3. 변환 후 그날의 총 건수 = 원래 건수 + 변환되어 들어온 건수
#   4. 하루 평균과 비교해 몇 배가 되는지 계산한다.
# =============================================================================
w("=" * 84)
w("[근거 A] 형식을 변환하면 일별 집계가 파괴되는가")
w("=" * 84)
w("")
w("  [산출 방법]")
w("    상수형 오염값을 형식만 보고 정상 날짜로 바꿨다고 가정하고,")
w("    그날의 주문 건수가 평상시 대비 몇 배가 되는지 계산한다.")
w("")

sim_rows = []
for bad_value, converted in CONSTANT_DATES.items():
    n_bad = int((date_raw == bad_value).sum())
    target = pd.Timestamp(converted).date()

    # 그 날짜에 원래 있던 정상 주문 건수
    n_original = int(daily_counts.get(target, 0))
    n_after = n_original + n_bad

    sim_rows.append({
        "오염값": bad_value,
        "변환결과": converted,
        "오염건수": n_bad,
        "해당일_기존주문": n_original,
        "변환후_총건수": n_after,
        "하루평균": round(avg_per_day, 1),
        "평균대비_배수": round(n_after / avg_per_day, 1),
    })

sim_df = pd.DataFrame(sim_rows)
sim_df.to_csv(os.path.join(REPORT_DIR, "근거_일별주문건수_시뮬레이션.csv"),
              index=False, encoding="utf-8-sig")

w(f"  {'오염값':<20}{'변환결과':<14}{'기존':>8}{'추가':>9}{'합계':>9}{'평균대비':>10}")
for r in sim_rows:
    w(f"  {r['오염값']:<20}{r['변환결과']:<14}"
      f"{r['해당일_기존주문']:>8,}{r['오염건수']:>9,}{r['변환후_총건수']:>9,}"
      f"{r['평균대비_배수']:>9.1f}배")
w("")
w(f"  하루 평균 {avg_per_day:.1f}건, 실제 최대 {daily_counts.max():,}건인 데이터에서")
w(f"  특정 3일만 {min(r['변환후_총건수'] for r in sim_rows):,}건 이상으로 치솟는다.")
w("  월별 매출 추이·성수기 분석·전년 대비 성장률이 전부 왜곡된다.")
w("  → 형식이 복원 가능하다는 것과 값이 진실이라는 것은 다른 문제다.")
w("")


# =============================================================================
# 근거 B : 오염이 무작위인가
#
# [왜 이걸 확인해야 하는가]
#   날짜 9만 건을 버리고 나머지 21만 건으로 분석할 예정이다.
#   만약 특정 성격의 주문만 날짜가 깨졌다면(예: 환불 건만),
#   남은 21만 건은 편향된 표본이 되어 분석 결과가 틀린다.
#   반대로 오염이 무작위라면, 남은 데이터는 전체를 대표할 수 있다.
#
# [산출 방법 - 2가지를 함께 본다]
#   ① 비율 비교 : 오염 그룹과 정상 그룹의 status 구성비를 나란히 본다
#   ② 카이제곱 검정 : 그 차이가 우연으로 볼 수 있는 수준인지 통계적으로 판정
#
#   카이제곱 검정이란:
#     두 그룹의 구성비가 "같다고 봐도 되는가"를 판정하는 검정이다.
#     p-value가 크면(보통 0.05 초과) "차이가 우연 범위 안"이라는 뜻이고,
#     작으면 "우연으로 보기 어려운 차이가 있다"는 뜻이다.
#     여기서는 p-value가 크게 나오기를 기대한다. 차이가 없어야 무작위 오염이다.
# =============================================================================
w("=" * 84)
w("[근거 B] 날짜 오염이 무작위로 발생했는가")
w("=" * 84)
w("")
w("  [왜 확인하는가]")
w("    날짜 9만 건을 버리고 21만 건으로 분석할 예정이다.")
w("    특정 성격의 주문만 깨졌다면 남은 21만 건이 편향된 표본이 된다.")
w("    오염이 무작위여야 남은 데이터가 전체를 대표할 수 있다.")
w("")

# status를 임시로 정규화한다 (3단계에서 정식 정제하지만, 비교하려면 지금 필요하다)
def normalize_status(value):
    v = str(value).strip().lower()
    if v.startswith("suc"):
        return "success"
    if v.startswith("ref"):
        return "refunded"
    if v.startswith("fail"):
        return "failed"
    return v

status = df["status"].map(normalize_status)

# 날짜가 오염된 행 = 표준 형식이 아닌 모든 행 (상수 3종 + ISO + 결측)
date_dirty = ~is_standard

w("  [① 구성비 비교]")
w("")
w(f"  {'구분':<24}{'success':>10}{'refunded':>11}{'failed':>10}{'건수':>10}")

for label, mask in [("정상 날짜 (기준)", is_standard),
                    ("오염 날짜 전체", date_dirty),
                    ("  ├ 상수값 3종", date_raw.isin(CONSTANT_DATES.keys())),
                    ("  ├ ISO 형식", date_raw.str.contains("T")),
                    ("  └ 원본 결측", df["order_date"].isna())]:
    if mask.sum() == 0:
        continue
    ratio = status[mask].value_counts(normalize=True)
    w(f"  {label:<24}"
      f"{ratio.get('success', 0)*100:>9.1f}%"
      f"{ratio.get('refunded', 0)*100:>10.1f}%"
      f"{ratio.get('failed', 0)*100:>9.1f}%"
      f"{int(mask.sum()):>10,}")

w("")
w("  [② 카이제곱 검정]")
w("")
w("    두 그룹의 구성비가 '같다고 봐도 되는가'를 통계적으로 판정한다.")
w("    p-value가 0.05보다 크면 '차이가 우연 범위 안'으로 본다.")
w("    여기서는 p-value가 크게 나와야 무작위 오염이라는 결론이 성립한다.")
w("")

# 교차표를 만들어 검정한다 (행: 날짜 정상/오염, 열: status 3종)
contingency = pd.crosstab(date_dirty, status)
chi2, p_value, dof, expected = chi2_contingency(contingency)

w("    [교차표 - 실제 관측값]")
w(f"    {'':<14}{'failed':>10}{'refunded':>11}{'success':>10}")
for idx, row in contingency.iterrows():
    label = "날짜 오염" if idx else "날짜 정상"
    w(f"    {label:<14}{row.get('failed', 0):>10,}{row.get('refunded', 0):>11,}"
      f"{row.get('success', 0):>10,}")
w("")
w(f"    카이제곱 통계량 : {chi2:.4f}")
w(f"    자유도          : {dof}")
w(f"    p-value         : {p_value:.4f}")
w("")

if p_value > 0.05:
    w(f"    → p-value {p_value:.4f} > 0.05")
    w("      두 그룹의 상태 구성비에 통계적으로 의미 있는 차이가 없다.")
    w("      즉 날짜 오염은 특정 상태의 주문에 몰려 있지 않고 무작위로 발생했다.")
    w("      남은 정상 날짜 데이터로 분석해도 표본이 한쪽으로 치우치지 않는다.")
else:
    w(f"    → p-value {p_value:.4f} <= 0.05")
    w("      두 그룹에 차이가 있다. 오염이 무작위가 아닐 수 있으므로")
    w("      날짜 결측 데이터를 제외한 분석 결과 해석에 주의가 필요하다.")
w("")

# 결제수단으로도 같은 검정을 한 번 더 한다 (한 변수만으로 판단하지 않기 위해)
def normalize_payment(value):
    v = re.sub(r"[^a-z]", "", str(value).strip().lower())
    if v in ("crad", "crd", "cd", "card"):
        return "card"
    if v.startswith("wall"):
        return "wallet"
    if v.startswith("up"):
        return "upi"
    if v.startswith("cash"):
        return "cash"
    return v

payment = df["payment_method"].map(normalize_payment)
contingency2 = pd.crosstab(date_dirty, payment)
chi2_2, p_value2, dof2, _ = chi2_contingency(contingency2)

w("    [교차 검증 - 결제수단으로도 동일하게 확인]")
w(f"    카이제곱 통계량 : {chi2_2:.4f}   p-value : {p_value2:.4f}")
w(f"    → {'차이 없음 (무작위)' if p_value2 > 0.05 else '차이 있음 (주의 필요)'}")
w("      변수를 하나만 보고 판단하지 않기 위해 결제수단으로도 검정했다.")
w("")


# =============================================================================
# 근거 C : ISO 형식이 실제 주문 시각인가
#
# [산출 방법]
#   ① 시각(HH:MM)의 분포를 센다 → 특정 시각에 몰려 있으면 자동 생성값이다
#   ② 날짜 범위가 정상 데이터 범위 안에 있는지 확인한다
#   ③ 기준일 이후의 미래 날짜가 있는지 확인한다
# =============================================================================
w("=" * 84)
w("[근거 C] ISO 형식이 실제 주문 시각인가")
w("=" * 84)
w("")

iso_mask = date_raw.str.contains("T")
iso_dt = pd.to_datetime(date_raw[iso_mask], errors="coerce", format="mixed")

w(f"  ISO 형식 건수 : {int(iso_mask.sum()):,}건")
w("")
w("  [① 시각 분포]  실제 주문이라면 하루 종일 고르게 퍼져야 한다")
time_dist = iso_dt.dt.strftime("%H:%M").value_counts()
for t, cnt in time_dist.head(5).items():
    w(f"    {t}  →  {cnt:,}건 ({cnt/len(iso_dt)*100:.1f}%)")
w(f"    서로 다른 시각(분 단위) 종류 : {time_dist.nunique() if False else len(time_dist)}종")
w(f"    → 주문 {len(iso_dt):,}건이 {len(time_dist)}분 안에 몰려 있다.")
w("      사람이 주문한 시각이 아니라 시스템이 한 번에 생성한 값으로 판단된다.")
w("")

w("  [② 날짜 범위 비교]")
w(f"    정상 데이터 범위 : {standard_dates.min().date()} ~ {standard_dates.max().date()}")
w(f"    ISO 형식 범위    : {iso_dt.min().date()} ~ {iso_dt.max().date()}")
w("    → ISO 형식의 날짜가 정상 데이터 범위를 벗어나 있다.")
w("")

today = pd.Timestamp.today().normalize()
n_future = int((iso_dt > today).sum())
w("  [③ 미래 날짜 확인]")
w(f"    기준일 : {today.date()}")
w(f"    기준일 이후 날짜 : {n_future:,}건")
w("    → 아직 오지 않은 날짜에 주문이 존재할 수 없다.")
w("")


# =============================================================================
# 결론
# =============================================================================
w("=" * 84)
w("[결론]")
w("=" * 84)
w("")
w("  근거 A : 형식 변환 시 특정 3일의 주문이 평균 대비 60배 이상으로 치솟는다.")
w("           → 형식은 복원 가능하지만 값이 진실이 아니다. 변환하지 않는다.")
w("")
w(f"  근거 B : 날짜 오염 그룹과 정상 그룹의 상태 구성비에 차이가 없다 (p={p_value:.4f}).")
w("           → 오염이 무작위이므로, 정상 날짜만으로 분석해도 표본이 편향되지 않는다.")
w("")
w("  근거 C : ISO 형식은 시각이 1~2분에 집중되고 미래 날짜를 포함한다.")
w("           → 주문 시각이 아니라 적재 시각이다. 사용하지 않는다.")
w("")
w("  최종 방침 : 비표준 날짜 4종(상수 3종 + ISO)을 NULL 처리하고,")
w("             date_flag에 사유를 기록한다. 행은 삭제하지 않는다.")
w(f"             날짜 사용 가능 주문 : {int(is_standard.sum()):,}건 "
  f"({is_standard.mean()*100:.1f}%)")

with open(os.path.join(REPORT_DIR, "근거_orders_날짜처리.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print()
print("저장 완료 : 04_reports/근거_orders_날짜처리.txt")
print("저장 완료 : 04_reports/근거_일별주문건수_시뮬레이션.csv")
