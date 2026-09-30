# =============================================================================
# 파일명 : 17_verify_tickets.py
# 단계   : 5단계 - 정제 결과 검증 (support_tickets)
#
# [목적]
#   4단계 정제본이 규칙을 지켰는지 기계적으로 확인한다.
#
# [이 파일의 검증이 특별한 점]
#   다른 파일들은 '값을 고쳤는지'만 확인하면 됐다.
#   이 파일은 **원본에 없던 값을 12,626건 만들어냈다.**
#   그래서 검증 항목이 두 종류로 나뉜다.
#
#     ① 일반 검증 : 규칙대로 고쳐졌는가 (다른 파일과 동일)
#     ② 복원 검증 : 만들어낸 값이 타당한가  ← 이 파일에서 추가
#
#   복원 검증에서 확인할 것:
#     - 복원된 날짜가 관계식을 만족하는가
#     - 복원된 날짜가 원본 데이터의 시간 범위 안에 있는가
#       (계산이 틀리면 1970년이나 2050년 같은 값이 나온다)
#     - 복원 대상이 정말 원본에서 무효였는가
#       (멀쩡한 값을 덮어썼다면 데이터 훼손이다)
#
# [입력]  01_raw/support_tickets_30000_dirty.csv
#         03_cleaned/support_tickets_cleaned.csv
#         03_cleaned/crm_customers_cleaned.csv
# [출력]  04_reports/검증결과_tickets.txt
#         04_reports/비교표_tickets.csv
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

RAW_FILE = os.path.join(PROJECT_DIR, "01_raw", "support_tickets_30000_dirty.csv")
CLEAN_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "support_tickets_cleaned.csv")
CUST_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "crm_customers_cleaned.csv")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

ISO_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
VALID_ISSUE = ["payment", "delay", "refund", "product"]
VALID_SENTIMENT = ["positive", "neutral", "negative"]
VOWEL_DOUBLE = re.compile(r"(aa|ii|uu|jj|kk|vv|ww|yy|hh|qq|xx|zz)", re.IGNORECASE)

# 4단계에서 의도한 건수 (실제와 대조하기 위한 기준)
EXPECTED_DATE_NULL = 2687
EXPECTED_RESTORED = 12626


raw = read_csv_safe(RAW_FILE, dtype=str, keep_default_na=True)
clean = read_csv_safe(CLEAN_FILE, dtype=str, keep_default_na=True)
cust = read_csv_safe(CUST_FILE, dtype=str, keep_default_na=True)

print(f"원본   : {len(raw):,}행")
print(f"정제본 : {len(clean):,}행")
print()


checks = []
def check(name, expected, actual, passed):
    checks.append({
        "검사항목": name, "기대": expected, "실제": actual,
        "판정": "합격" if passed else "불합격",
    })


# =============================================================================
# [검사 1] 데이터 손실
# =============================================================================
check("행 개수 보존", f"{len(raw):,}행", f"{len(clean):,}행", len(raw) == len(clean))

raw_ids, clean_ids = set(raw["ticket_id"]), set(clean["ticket_id"])
check("ticket_id 집합 일치", "원본과 동일",
      f"누락 {len(raw_ids-clean_ids):,} / 추가 {len(clean_ids-raw_ids):,}",
      raw_ids == clean_ids)
check("ticket_id 중복 없음", "0건",
      f"{clean['ticket_id'].duplicated().sum():,}건",
      clean["ticket_id"].duplicated().sum() == 0)


# =============================================================================
# [검사 2] 키 불변 및 참조 정합성
# =============================================================================
merged = raw[["ticket_id", "customer_id"]].merge(
    clean[["ticket_id", "customer_id"]], on="ticket_id", suffixes=("_raw", "_clean"))
diff = int((merged["customer_id_raw"] != merged["customer_id_clean"]).sum())
check("customer_id 값 불변", "0건 변경", f"{diff:,}건", diff == 0)

orphan = int((~clean["customer_id"].isin(cust["customer_id"])).sum())
check("customer_id 참조 정합성", "고아 0건", f"{orphan:,}건", orphan == 0)

# resolution_time_hours 는 정제 대상이 아니었으므로 값이 변하면 안 된다
merged2 = raw[["ticket_id", "resolution_time_hours"]].merge(
    clean[["ticket_id", "resolution_time_hours"]], on="ticket_id",
    suffixes=("_raw", "_clean"))
diff2 = int((merged2["resolution_time_hours_raw"]
             != merged2["resolution_time_hours_clean"]).sum())
check("처리시간 값 불변", "0건 변경", f"{diff2:,}건", diff2 == 0)


# =============================================================================
# [검사 3] 범주형 허용값
# =============================================================================
issue_bad = int((~clean["issue_type"].isin(VALID_ISSUE)).sum())
check("issue_type 허용값", "0건 위반", f"{issue_bad:,}건", issue_bad == 0)
check("issue_type 종류 수", "4종", f"{clean['issue_type'].nunique()}종",
      clean["issue_type"].nunique() == 4)

sent_bad = int((~clean["sentiment"].isin(VALID_SENTIMENT)).sum())
check("sentiment 허용값", "0건 위반", f"{sent_bad:,}건", sent_bad == 0)
check("sentiment 종류 수", "3종", f"{clean['sentiment'].nunique()}종",
      clean["sentiment"].nunique() == 3)


# =============================================================================
# [검사 4] 날짜 형식 및 논리
# =============================================================================
created = pd.to_datetime(clean["ticket_created"], errors="coerce")
resolved = pd.to_datetime(clean["ticket_resolved"], errors="coerce")
hours = pd.to_numeric(clean["resolution_time_hours"], errors="coerce")

both = created.notna() & resolved.notna()

parse_fail = int((clean["ticket_created"].notna() & created.isna()).sum()
                 + (clean["ticket_resolved"].notna() & resolved.isna()).sum())
check("날짜 파싱 가능", "0건 실패", f"{parse_fail:,}건", parse_fail == 0)

reversed_time = int((resolved < created)[both].sum())
check("해결일시 ≥ 접수일시", "0건 위반", f"{reversed_time:,}건", reversed_time == 0)

today = pd.Timestamp.today().normalize()
future = int(((created > today) | (resolved > today)).sum())
check("미래 날짜 없음", "0건", f"{future:,}건", future == 0)

date_null = int(clean["ticket_created"].isna().sum())
check("날짜 NULL 건수 일치", f"{EXPECTED_DATE_NULL:,}건", f"{date_null:,}건",
      date_null == EXPECTED_DATE_NULL)

# 접수와 해결이 항상 함께 있거나 함께 없어야 한다.
# 한쪽만 있으면 복원 로직이 빠뜨린 케이스가 있다는 뜻이다.
one_sided = int((created.notna() != resolved.notna()).sum())
check("날짜 짝 일치(한쪽만 존재 없음)", "0건", f"{one_sided:,}건", one_sided == 0)


# =============================================================================
# [검사 5] 복원 검증 ① — 관계식 성립
#
#   해결일시 − 접수일시 = 처리시간 이 모든 행에서 성립해야 한다.
#   복원한 값은 이 식으로 계산했으므로 당연하지만,
#   원본 유지 건까지 포함해 전수 확인하는 것이 의미가 있다.
# =============================================================================
gap_hours = (resolved - created).dt.total_seconds() / 3600
max_error = float((gap_hours - hours)[both].abs().max())

check("관계식 오차 (전체)", "0.0", f"{max_error:.4f}", max_error < 0.001)


# =============================================================================
# [검사 6] 복원 검증 ② — 복원 값이 타당한 범위인가
#
#   계산이 잘못되면 1970년이나 2050년 같은 값이 나온다.
#   원본이 그대로 유지된 티켓의 시간 범위를 기준선으로 삼고,
#   복원된 값이 그 범위(±1일 여유) 안에 있는지 확인한다.
# =============================================================================
# [주의] '복원' 이라는 글자로 찾으면 '복원불가(양쪽무효)' 까지 걸린다.
#   실제로 그 실수를 해서 15,313건(= 12,626 + 2,687)이 나왔다.
#   접두어로 정확히 구분해야 한다.
is_restored = clean["date_flag"].fillna("").str.startswith(
    ("접수일시_복원", "해결일시_복원"))
is_original = clean["date_flag"].isna()

base_min = created[is_original].min()
base_max = resolved[is_original].max()
# 경계에서 몇 분 차이는 자연스러우므로 하루 여유를 둔다
tolerance = pd.Timedelta(days=1)

out_of_range = int((
    (created[is_restored] < base_min - tolerance) |
    (resolved[is_restored] > base_max + tolerance)
).sum())

check("복원 날짜 범위 타당성", "0건 이탈", f"{out_of_range:,}건", out_of_range == 0)

n_restored = int(is_restored.sum())
check("복원 건수 일치", f"{EXPECTED_RESTORED:,}건", f"{n_restored:,}건",
      n_restored == EXPECTED_RESTORED)


# =============================================================================
# [검사 7] 복원 검증 ③ — 멀쩡한 값을 덮어쓰지 않았는가
#
#   가장 중요한 검사다.
#   복원 대상이 정말 원본에서 무효였는지 확인한다.
#   원본이 유효했는데 계산값으로 덮어썼다면 데이터 훼손이다.
# =============================================================================
def is_real_datetime(value):
    if pd.isna(value):
        return False
    v = str(value).strip()
    if not ISO_SECOND.match(v):
        return False
    hh, mm, ss = map(int, v[11:].split(":"))
    return hh <= 23 and mm <= 59 and ss <= 59

# 복원 사유에 '접수일시_복원'이 있으면 원본 접수일시가 무효였어야 한다
restored_created = clean["date_flag"].fillna("").str.startswith("접수일시_복원")
restored_resolved = clean["date_flag"].fillna("").str.startswith("해결일시_복원")

was_valid_created = clean["ticket_created_raw"].map(is_real_datetime)
was_valid_resolved = clean["ticket_resolved_raw"].map(is_real_datetime)

overwrite_c = int((restored_created & was_valid_created).sum())
overwrite_r = int((restored_resolved & was_valid_resolved).sum())

check("유효 접수일시 덮어쓰기 없음", "0건", f"{overwrite_c:,}건", overwrite_c == 0)
check("유효 해결일시 덮어쓰기 없음", "0건", f"{overwrite_r:,}건", overwrite_r == 0)

# 반대 방향 : 복원하지 않은 건은 원본이 유효했어야 한다
kept_but_invalid = int((is_original & ~(was_valid_created & was_valid_resolved)).sum())
check("원본유지 건은 원본이 유효", "0건 모순", f"{kept_but_invalid:,}건",
      kept_but_invalid == 0)


# =============================================================================
# [검사 8] support_agent
# =============================================================================
agent = clean["support_agent"].fillna("")

check("담당자명 앞뒤공백 없음", "0건",
      f"{int((agent != agent.str.strip()).sum()):,}건",
      (agent != agent.str.strip()).sum() == 0)
check("담당자명 접미사(@@ --) 없음", "0건",
      f"{int(agent.str.contains(r'(@@|--)', regex=True).sum()):,}건",
      agent.str.contains(r"(@@|--)", regex=True).sum() == 0)
check("담당자명 대소문자 통일", "0건 위반",
      f"{int((agent.str.isupper() | agent.str.islower()).sum()):,}건",
      (agent.str.isupper() | agent.str.islower()).sum() == 0)

# 글자중복이 남은 이름 검사
#
#   [처음 잘못 만든 검사]
#     "글자중복이 남았으면 반드시 플래그가 있어야 한다" 로 검사했더니 20건이 걸렸다.
#     확인해보니 이런 경우였다:
#         'Aaaron Mcpherson'(a 3개) → 'Aaron Mcpherson' 으로 정상 복원됨
#         'Isaaaac Graant'          → 'Isaac Grant' 으로 정상 복원됨
#     복원된 결과 이름에 'aa'가 남아 있지만 그것이 올바른 이름이다.
#     즉 '결과에 글자중복이 있다'는 것 자체는 오류가 아니다.
#
#   [올바른 검사]
#     잔여 글자중복 이름을 한 번 더 줄였을 때,
#     그 형태가 데이터에 담당자로 존재하면 → 복원을 놓친 것이다.
#     존재하지 않으면 → 정상 이름이므로 문제없다.
known_final = set(agent.unique())

def missed_restoration(name):
    if not VOWEL_DOUBLE.search(name):
        return False
    collapsed = VOWEL_DOUBLE.sub(lambda m: m.group(0)[0], name)
    return collapsed in known_final and collapsed != name

missed = int(agent.map(missed_restoration).sum())
check("복원 누락 없음(글자중복)", "0건", f"{missed:,}건", missed == 0)

# 참고 : 결과에 글자중복이 남은 이름 목록 (정상 이름이어야 한다)
residual_names = sorted({v for v in known_final if VOWEL_DOUBLE.search(v)})


# =============================================================================
# [검사 9] 원본 값 보존
# =============================================================================
PRESERVE_COLS = ["ticket_created", "ticket_resolved", "support_agent"]
raw_lookup = raw.set_index("ticket_id")
clean_indexed = clean.set_index("ticket_id")

for col in PRESERVE_COLS:
    raw_col = f"{col}_raw"
    exists = raw_col in clean.columns
    check(f"{raw_col} 컬럼 존재", "존재", "존재" if exists else "없음", exists)
    if not exists:
        continue
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
lines.append("=" * 88)
lines.append("support_tickets_30000 정제 검증 결과 (5단계)")
lines.append("=" * 88)
lines.append("")
lines.append(f"{'검사항목':<34}{'기대':<18}{'실제':<20}{'판정'}")
lines.append("-" * 88)
for _, r in result_df.iterrows():
    lines.append(f"{r['검사항목']:<34}{r['기대']:<18}{str(r['실제']):<20}{r['판정']}")
lines.append("-" * 88)
lines.append("")
lines.append(f"검사 항목 {len(result_df)}개 중 합격 {(result_df['판정']=='합격').sum()}개")
lines.append(f"종합 판정 : "
             f"{'전체 합격 — PostgreSQL 적재 가능' if all_passed else '불합격 항목 있음 — 4단계 재확인 필요'}")
lines.append("")

lines.append("-" * 88)
lines.append("[복원 검증 상세 — 이 파일에서만 필요한 검사]")
lines.append("-" * 88)
lines.append(f"  복원한 날짜             : {n_restored:,}건")
lines.append(f"  관계식 오차 최댓값       : {max_error:.4f} 시간")
lines.append(f"  원본 유지 건의 시간 범위  : {base_min} ~ {base_max}")
lines.append(f"  복원 건의 시간 범위      : "
             f"{created[is_restored].min()} ~ {resolved[is_restored].max()}")
lines.append(f"  범위 이탈               : {out_of_range:,}건")
lines.append("")
lines.append("  ※ 복원은 '원본에 없던 값을 만들어내는' 작업이므로 검증이 더 중요하다.")
lines.append("     특히 '멀쩡한 값을 덮어쓰지 않았는가'를 양방향으로 확인했다:")
lines.append(f"       유효한 원본을 덮어쓴 건 : {overwrite_c + overwrite_r:,}건")
lines.append(f"       원본이 무효인데 유지한 건 : {kept_but_invalid:,}건")
lines.append("")

lines.append("-" * 88)
lines.append("[담당자명 잔여 글자중복 — 정상 이름으로 판단한 목록]")
lines.append("-" * 88)
for name in residual_names:
    n = int((agent == name).sum())
    lines.append(f"  {name:<28} {n:>7,}건")
lines.append("")
lines.append("  ※ 이 이름들은 'aa'를 포함하지만 실제 이름이다.")
lines.append("     한 번 더 줄인 형태가 담당자 목록에 존재하지 않으므로 복원 누락이 아니다.")
lines.append("     원본이 'Aaaron'(a 3개) 이었던 건은 'Aaron' 으로 올바르게 복원되었다.")
lines.append("")

lines.append("-" * 88)
lines.append("[분석 가능 데이터 규모]")
lines.append("-" * 88)
usable_date = len(clean) - date_null
lines.append(f"  전체 티켓                : {len(clean):,}건")
lines.append(f"  유형·감정·처리시간 분석    : {len(clean):,}건 (100.0%)")
lines.append(f"  담당자 분석              : {len(clean):,}건 (100.0%)")
lines.append(f"  시계열(날짜) 분석         : {usable_date:,}건 "
             f"({usable_date/len(clean)*100:.1f}%)")
lines.append(f"    ├ 원본 날짜 기준        : {int(is_original.sum()):,}건 "
             f"({is_original.sum()/len(clean)*100:.1f}%)")
lines.append(f"    └ 복원 날짜 포함        : {usable_date:,}건 "
             f"({usable_date/len(clean)*100:.1f}%)")
lines.append("")
lines.append("  ※ 7단계 SQL 분석에서 시계열 결과를 제시할 때는")
lines.append("     '복원 날짜 포함 여부'를 함께 밝히는 것이 정확하다.")
lines.append("     date_flag IS NULL 조건으로 원본만 걸러 비교해볼 수 있다.")


# =============================================================================
# [출력] Before / After 비교표
# =============================================================================
def count_valid_dt(series):
    return int(series.map(is_real_datetime).sum())

compare = [
    {"지표": "전체 행 수", "정제 전": len(raw), "정제 후": len(clean)},
    {"지표": "issue_type 종류", "정제 전": raw["issue_type"].nunique(),
     "정제 후": clean["issue_type"].nunique()},
    {"지표": "sentiment 종류", "정제 전": raw["sentiment"].nunique(),
     "정제 후": clean["sentiment"].nunique()},
    {"지표": "담당자 표기 종류", "정제 전": raw["support_agent"].nunique(),
     "정제 후": clean["support_agent"].nunique()},
    {"지표": "접수일시 유효 건수", "정제 전": count_valid_dt(raw["ticket_created"]),
     "정제 후": int(created.notna().sum())},
    {"지표": "해결일시 유효 건수", "정제 전": count_valid_dt(raw["ticket_resolved"]),
     "정제 후": int(resolved.notna().sum())},
    {"지표": "두 날짜 모두 유효", "정제 전": int((raw["ticket_created"].map(is_real_datetime)
                                        & raw["ticket_resolved"].map(is_real_datetime)).sum()),
     "정제 후": int(both.sum())},
    {"지표": "날짜 형식 종류", "정제 전": 5, "정제 후": 1},
    {"지표": "고아 레코드", "정제 전": 0, "정제 후": orphan},
]

compare_df = pd.DataFrame(compare)
compare_df.to_csv(os.path.join(REPORT_DIR, "비교표_tickets.csv"),
                  index=False, encoding="utf-8-sig")

lines.append("")
lines.append("-" * 88)
lines.append("[정제 전후 비교]")
lines.append("-" * 88)
lines.append(f"{'지표':<26}{'정제 전':>14}{'정제 후':>14}")
for _, r in compare_df.iterrows():
    lines.append(f"{r['지표']:<26}{r['정제 전']:>14,}{r['정제 후']:>14,}")

with open(os.path.join(REPORT_DIR, "검증결과_tickets.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print()
print("저장 완료 : 04_reports/검증결과_tickets.txt")
print("저장 완료 : 04_reports/비교표_tickets.csv")
