# =============================================================================
# 파일명 : 14_profile_tickets.py
# 단계   : 1단계 - 컬럼별 프로파일링 (고객 지원 티켓)
#
# [목적]
#   support_tickets_30000 파일을 관찰해서 "무엇이 정상인지" 파악한다.
#
# [이 파일의 특징 — 앞선 파일들과 다른 점]
#
#   ① 날짜 컬럼이 2개이고 서로 관계가 있다
#      ticket_created(접수) ≤ ticket_resolved(해결) 이어야 한다.
#      게다가 resolution_time_hours(처리시간)까지 있어서 3개가 서로 맞아야 한다.
#      → 세 컬럼을 교차 검증하면 어느 값이 틀렸는지 좁힐 수 있다.
#
#   ② 담당자명을 검증할 외부 기준이 없다
#      CRM에서는 이메일로 이름을 검증할 수 있었다.
#      여기에는 그런 참조 컬럼이 없다.
#      → 대신 '데이터 자신'을 사전으로 쓴다. 같은 담당자가 여러 티켓에 등장하므로,
#        오염된 표기를 고쳤을 때 정상 표기가 데이터 안에 이미 존재하는지로 판정한다.
#
#   ③ 새로운 오염 유형: 문자열 뒤집기
#      'tnemyap' = payment 를 거꾸로 쓴 것이다.
#      앞선 파일에는 없던 패턴이라 별도 검사가 필요하다.
#
# [입력]  01_raw/support_tickets_30000_dirty.csv
#         03_cleaned/crm_customers_cleaned.csv   (마스터 — 대조용)
# [출력]  02_profiling/tickets/
#           - 01_기본정보.txt
#           - 02_범주형_값분포.txt
#           - 03_날짜형식_분류.csv
#           - 04_교차검증.txt
#           - 05_담당자명_정규화시뮬레이션.csv
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

INPUT_FILE = os.path.join(PROJECT_DIR, "01_raw", "support_tickets_30000_dirty.csv")
CUST_FILE = os.path.join(PROJECT_DIR, "03_cleaned", "crm_customers_cleaned.csv")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "02_profiling", "tickets")
os.makedirs(OUTPUT_DIR, exist_ok=True)


df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(df):,}행 × {len(df.columns)}열")
print()


# =============================================================================
# [출력 1] 기본 정보
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("support_tickets_30000 기본 정보")
lines.append("=" * 84)
lines.append(f"전체 행 수 : {len(df):,}")
lines.append(f"전체 열 수 : {len(df.columns)}")
lines.append("")

role = {
    "ticket_id": "티켓 고유번호 (기본키 후보)",
    "customer_id": "문의한 고객 (crm_customers 참조 = 외래키)",
    "issue_type": "문의 유형 (범주형)",
    "ticket_created": "접수 일시",
    "ticket_resolved": "해결 일시",
    "resolution_time_hours": "처리 소요 시간(시간)",
    "sentiment": "고객 감정 (범주형)",
    "support_agent": "담당 상담원",
}
lines.append("컬럼 목록 및 역할")
lines.append("-" * 84)
for c in df.columns:
    lines.append(f"  {c:<24} {role.get(c, '(미분류)')}")
lines.append("")

lines.append("-" * 84)
lines.append("[컬럼별 결측 및 고유값]")
lines.append("-" * 84)
lines.append(f"{'컬럼명':<24}{'결측':>10}{'결측률':>10}{'고유값':>12}")
for c in df.columns:
    n_null = df[c].isna().sum()
    lines.append(f"{c:<24}{n_null:>10,}{n_null/len(df)*100:>9.1f}%{df[c].nunique():>12,}")
lines.append("")

lines.append("-" * 84)
lines.append("[중복 검사]")
lines.append("-" * 84)
lines.append(f"완전 중복 행    : {df.duplicated().sum():,}건")
lines.append(f"ticket_id 중복  : {df['ticket_id'].duplicated().sum():,}건")
lines.append("")
lines.append("  ※ 한 고객이 여러 번 문의할 수 있으므로 customer_id 중복은 정상이다.")
lines.append(f"     문의한 고객 수 : {df['customer_id'].nunique():,}명")
lines.append(f"     고객당 평균 문의 : {len(df)/df['customer_id'].nunique():.2f}건")

with open(os.path.join(OUTPUT_DIR, "01_기본정보.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("01_기본정보.txt 저장 완료")


# =============================================================================
# [출력 2] 범주형 컬럼 값 분포
#
#   issue_type과 sentiment는 값 종류가 적으므로 전체를 확인한다.
#   여기서 새로운 오염 유형인 '문자열 뒤집기'가 발견된다.
# =============================================================================
lines = []
lines.append("=" * 84)
lines.append("범주형 컬럼 값 분포")
lines.append("=" * 84)
lines.append("")

for c in ["issue_type", "sentiment"]:
    counts = df[c].value_counts(dropna=False)
    lines.append("-" * 84)
    lines.append(f"[{c}]  고유값 {df[c].nunique()}종")
    lines.append("-" * 84)
    for value, cnt in counts.items():
        # 따옴표로 감싸야 앞뒤 공백이 눈에 보인다
        lines.append(f"  '{value}'  →  {cnt:,}건")
    lines.append("")

lines.append("-" * 84)
lines.append("[발견된 오염 패턴]")
lines.append("-" * 84)
lines.append("  앞선 파일들과 같은 패턴 : 앞뒤 공백 / 대문자 / 숫자치환(3→e) / 축약형 / 접미사(_ x)")
lines.append("")
lines.append("  새로운 패턴 : 문자열 뒤집기")
lines.append("    'tnemyap' ← payment 를 거꾸로")
lines.append("    'yaled'   ← delay")
lines.append("    'tcudorp' ← product")
lines.append("    'dnufer'  ← refund")
lines.append("  → 글자를 역순으로 배열한 형태다. 앞선 파일에는 없던 유형이므로")
lines.append("     2단계에서 별도 복원 규칙을 만들어야 한다.")

with open(os.path.join(OUTPUT_DIR, "02_범주형_값분포.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("02_범주형_값분포.txt 저장 완료")


# =============================================================================
# [출력 3] 날짜 형식 분류
#
#   orders에서 쓴 방법을 그대로 적용한다.
#   형식별로 나누고 '고유값 개수'를 함께 본다. 고유값이 1개면 상수(대체값)다.
#
#   이 파일에는 orders에 없던 유형이 하나 더 있다:
#     ISO 형식인데 시각이 불가능한 값 (예: 28:77:10)
#     날짜 부분은 멀쩡한데 시:분:초가 범위를 벗어난다.
# =============================================================================
ISO_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

def classify_datetime(value):
    if pd.isna(value):
        return "결측"
    v = str(value).strip()
    if ISO_SECOND.match(v):
        hh, mm, ss = map(int, v[11:].split(":"))
        if hh > 23 or mm > 59 or ss > 59:
            return "ISO형식(시각 범위초과)"
        return "ISO형식(정상)"
    if "T" in v and "." in v:
        return "ISO형식(마이크로초=적재시각 추정)"
    return f"상수('{v}')"

rows = []
for col in ["ticket_created", "ticket_resolved"]:
    kinds = df[col].map(classify_datetime)
    for kind in kinds.unique():
        subset = df.loc[kinds == kind, col]
        rows.append({
            "컬럼": col,
            "형식": kind,
            "건수": len(subset),
            "고유값수": subset.nunique(),
            "예시": str(subset.dropna().iloc[0]) if len(subset.dropna()) else "",
        })

date_df = pd.DataFrame(rows).sort_values(["컬럼", "건수"], ascending=[True, False])
date_df.to_csv(os.path.join(OUTPUT_DIR, "03_날짜형식_분류.csv"),
               index=False, encoding="utf-8-sig")
print("03_날짜형식_분류.csv 저장 완료")
print()
print(date_df.to_string(index=False))
print()


# =============================================================================
# [출력 4] 교차 검증
# =============================================================================
cust = read_csv_safe(CUST_FILE, dtype=str, keep_default_na=True)

lines = []
lines.append("=" * 84)
lines.append("교차 검증")
lines.append("=" * 84)
lines.append("")

# --- A. 참조 정합성 ---------------------------------------------------------
lines.append("-" * 84)
lines.append("[A] customer_id → crm_customers 참조 정합성")
lines.append("-" * 84)
orphan = int((~df["customer_id"].isin(cust["customer_id"])).sum())
lines.append(f"  마스터 고객 수      : {len(cust):,}명")
lines.append(f"  문의한 고객 수      : {df['customer_id'].nunique():,}명")
lines.append(f"  고아 티켓(고객 없음) : {orphan:,}건")
lines.append("")

# --- B. 처리시간 vs 날짜 차이 ------------------------------------------------
#   resolution_time_hours 가 (해결일시 - 접수일시) 와 맞는지 확인한다.
#   맞는다면 처리시간을 이용해 날짜 오류를 판별할 수 있다.
lines.append("-" * 84)
lines.append("[B] resolution_time_hours vs (해결일시 - 접수일시)")
lines.append("-" * 84)

res_hours = pd.to_numeric(df["resolution_time_hours"], errors="coerce")
lines.append(f"  처리시간 결측       : {int(res_hours.isna().sum()):,}건")
lines.append(f"  처리시간 범위       : {res_hours.min():.0f} ~ {res_hours.max():.0f} 시간")
lines.append(f"  음수 / 0            : {int((res_hours<0).sum()):,}건 / {int((res_hours==0).sum()):,}건")
lines.append("")
lines.append("  → 처리시간 컬럼 자체는 깨끗하다. 결측도 이상값도 없다.")
lines.append("")

# format='ISO8601' : 마이크로초가 있든 없든 ISO 형식을 알아서 읽는다
created = pd.to_datetime(df["ticket_created"], errors="coerce", format="ISO8601")
resolved = pd.to_datetime(df["ticket_resolved"], errors="coerce", format="ISO8601")
diff_hours = (resolved - created).dt.total_seconds() / 3600

both_valid = created.notna() & resolved.notna()
match = ((diff_hours - res_hours).abs() < 1) & both_valid
negative = (diff_hours < 0) & both_valid

lines.append(f"  두 날짜가 모두 읽히는 티켓 : {int(both_valid.sum()):,}건")
lines.append(f"    ├ 처리시간과 일치(±1시간) : {int(match.sum()):,}건 "
             f"({match.sum()/both_valid.sum()*100:.1f}%)")
lines.append(f"    └ 해결일시 < 접수일시     : {int(negative.sum()):,}건  ← 논리 오류")
lines.append("")
lines.append("  ※ 일치율이 84%대라는 것은 세 컬럼이 대체로 정합적이라는 뜻이다.")
lines.append("     완벽히 일치하지 않는 이유는 날짜 컬럼 쪽에 오염이 섞여 있기 때문이다.")
lines.append("     처리시간 컬럼이 깨끗하므로, 2단계에서 이를 기준으로")
lines.append("     날짜 오류를 판별하는 방법을 검토할 수 있다.")
lines.append("")

# --- C. 담당자명 ------------------------------------------------------------
lines.append("-" * 84)
lines.append("[C] support_agent 표기 오염")
lines.append("-" * 84)

agent = df["support_agent"].fillna("")
lines.append(f"  고유값(원본)        : {agent.nunique():,}종")
lines.append(f"  앞뒤 공백           : {int((agent != agent.str.strip()).sum()):,}건")
lines.append(f"  전부 소문자         : {int(agent.str.strip().str.islower().sum()):,}건")
lines.append(f"  전부 대문자         : {int(agent.str.strip().str.isupper().sum()):,}건")
lines.append(f"  접미사 '@@' 부착    : {int(agent.str.contains('@@').sum()):,}건")
lines.append(f"  접미사 '--' 부착    : {int(agent.str.contains('--').sum()):,}건")
lines.append("")
lines.append(f"  경칭(Jr./DDS/MD) 포함 : {int(agent.str.contains(r'(Jr\\.|Sr\\.|DDS|MD|PhD|DVM)', regex=True).sum()):,}건")
lines.append("")
lines.append("  ※ 이름 뒤의 Jr. / DDS / MD 는 오염이 아니라 실제 경칭이다.")
lines.append("     같은 사람이 경칭 유무로 갈려서 기록되는지 확인한 결과 0건이었으므로")
lines.append("     제거하지 않는다. (근거는 2단계 규칙서 3-3 참고)")

with open(os.path.join(OUTPUT_DIR, "04_교차검증.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))
print("04_교차검증.txt 저장 완료")


# =============================================================================
# [출력 5] 담당자명 정규화 시뮬레이션
#
#   CRM에서는 이메일로 이름을 검증했다. 여기에는 참조 컬럼이 없다.
#   대신 '데이터 자신'을 사전으로 쓴다.
#
#   원리: 같은 담당자가 평균 40여 건의 티켓에 등장한다.
#         오염된 표기를 고쳤을 때 그 이름이 데이터 안에 이미 존재한다면,
#         그것이 정상 표기라는 증거가 된다.
#
#   이 방법이 필요한 이유는 'Isaac', 'Aaron' 처럼
#   'aa'가 정상인 이름을 망가뜨리지 않기 위해서다.
# =============================================================================
VOWEL_DOUBLE = re.compile(r"(aa|ii|uu|jj|kk|vv|ww|yy|hh|qq|xx|zz)", re.IGNORECASE)

# ① 표기 정규화 : 공백 정리 → 접미사(@@ --) 제거 → Title Case
#
#   [주의] 경칭(Jr. / DDS / MD)은 제거하지 않는다.
#     오염이 아니라 이름의 일부이기 때문이다.
#     검증 결과, 같은 사람이 경칭 유무로 갈려서 기록된 사례가 0건이었다.
#     (모든 이름의 경칭 상태가 1가지씩 — 제거해도 합쳐지는 이름이 없다)
#     제거하면 이득 없이 동명이인 충돌 위험만 생기므로 그대로 둔다.
normalized = (agent
              .str.replace(r"\s+", " ", regex=True)
              .str.strip()
              .str.replace(r"(@@|--)$", "", regex=True)
              .str.strip()
              .str.title())

known_names = set(normalized.unique())

# ② 글자 중복 복원 후보 검사
sim_rows = []
for name in sorted(known_names):
    if not VOWEL_DOUBLE.search(name):
        continue
    collapsed = VOWEL_DOUBLE.sub(lambda m: m.group(0)[0], name)
    sim_rows.append({
        "원본표기": name,
        "중복제거시": collapsed,
        "데이터에_존재": "예" if collapsed in known_names else "아니오",
        "판정": "복원 가능" if collapsed in known_names else "정상 이름으로 판단 → 유지",
        "건수": int((normalized == name).sum()),
    })

sim_df = pd.DataFrame(sim_rows)
sim_df.to_csv(os.path.join(OUTPUT_DIR, "05_담당자명_정규화시뮬레이션.csv"),
              index=False, encoding="utf-8-sig")

n_fix = int((sim_df["판정"] == "복원 가능").sum())
n_keep = int((sim_df["판정"] != "복원 가능").sum())

print("05_담당자명_정규화시뮬레이션.csv 저장 완료")
print()
print("[담당자명 정규화 시뮬레이션 결과]")
print(f"  원본 고유값                    : {agent.nunique():,}종")
print(f"  표기 정규화 후(경칭 유지)      : {len(known_names):,}종")
print(f"  글자중복 포함 이름             : {len(sim_df):,}종")
print(f"    ├ 복원 가능(정상형이 존재)    : {n_fix:,}종")
print(f"    └ 유지(정상 이름으로 판단)    : {n_keep:,}종")
if n_keep:
    print(f"       예: {', '.join(sim_df.loc[sim_df['판정']!='복원 가능','원본표기'].head(4))}")
print()
print(f"모든 결과 저장 위치 : {OUTPUT_DIR}")
