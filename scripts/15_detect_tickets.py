# =============================================================================
# 파일명 : 15_detect_tickets.py
# 단계   : 3단계 - 비정상 데이터 색출 및 유형 분류 (support_tickets)
#
# [목적]
#   2단계 규칙서(데이터사전_tickets.md)를 코드로 옮겨 규칙 위반 건을 전부 찾아낸다.
#   이 단계에서도 데이터를 고치지 않는다. 찾아서 기록만 한다.
#
# [이 파일의 3단계가 특별한 점]
#   날짜는 '오염 여부'만으로는 부족하다. '복원 가능한가'까지 분류해야 한다.
#
#     유형 A : 둘 다 정상          → 그대로 사용
#     유형 B : 접수만 정상          → 해결일시를 계산으로 복원 가능
#     유형 C : 해결만 정상          → 접수일시를 계산으로 복원 가능
#     유형 D : 둘 다 무효          → 복원 불가, NULL
#
#   같은 '오염'이라도 B/C는 살릴 수 있고 D는 못 살린다.
#   이 구분이 없으면 4단계에서 무엇을 복원할지 알 수 없다.
#
# [입력]  01_raw/support_tickets_30000_dirty.csv
#         03_cleaned/crm_customers_cleaned.csv   (마스터 — 대조용)
# [출력]  02_profiling/tickets/
#           - 06_이상데이터_상세.csv
#           - 07_유형별_집계.csv
#           - 08_진단요약.txt
#
# [분류 구분]
#   오염     : 값 자체가 틀림. 수정 또는 NULL 처리
#   표준화   : 값은 맞는데 표기만 다름
#   복원가능 : 오염이지만 다른 컬럼을 근거로 되살릴 수 있음
#   확인필요 : 정답을 알 수 없음
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


# -----------------------------------------------------------------------------
# [설정] 2단계에서 확정한 규칙 상수
# -----------------------------------------------------------------------------
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                          r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ISO_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

VALID_ISSUE = ["payment", "delay", "refund", "product"]
VALID_SENTIMENT = ["positive", "neutral", "negative"]

# 고유값이 1개뿐인 상수형 오염값
CONSTANT_DATETIMES = ["2024/31/01", "31-15-2023", "2025-12-12T28:77:10"]

VOWEL_DOUBLE = re.compile(r"(aa|ii|uu|jj|kk|vv|ww|yy|hh|qq|xx|zz)", re.IGNORECASE)


df = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
cust = read_csv_safe(CUST_FILE, dtype=str, keep_default_na=True)

print(f"원본 읽기 완료 : {len(df):,}행 × {len(df.columns)}열")
print()


issues = []

def add(mask, column, issue_type, kind):
    n = int(mask.sum())
    if n == 0:
        return
    sub = df.loc[mask, ["ticket_id"]].copy()
    sub["행번호"] = sub.index
    sub["컬럼"] = column
    sub["원본값"] = df.loc[mask, column].values
    sub["위반유형"] = issue_type
    sub["분류구분"] = kind
    issues.append(sub)
    print(f"  [{kind}] {column:<22} {issue_type:<30} {n:>7,}건")


# =============================================================================
# [검사 1] 키 컬럼 및 참조 정합성
# =============================================================================
print("[검사 1] 키 컬럼 및 참조 정합성")

add(df["ticket_id"].isna(), "ticket_id", "결측", "오염")
add(~df["ticket_id"].fillna("").str.match(UUID_PATTERN), "ticket_id", "UUID형식위반", "오염")
add(df["ticket_id"].duplicated(keep=False), "ticket_id", "중복", "오염")
add(df.duplicated(keep=False), "ticket_id", "완전중복행", "오염")

add(~df["customer_id"].fillna("").str.match(UUID_PATTERN),
    "customer_id", "UUID형식위반", "오염")
add(~df["customer_id"].isin(cust["customer_id"]),
    "customer_id", "고아레코드(고객없음)", "오염")

print("  (출력이 없으면 위반 0건 — 정상입니다)")
print()


# =============================================================================
# [검사 2] issue_type
#
#   한 겹씩 벗겨내며 어떤 오염이 걸려 있는지 전부 기록한다.
#   마지막에 '역순 배열'과 '축약형'을 구분해서 판정한다.
# =============================================================================
print("[검사 2] issue_type")

issue = df["issue_type"].fillna("")

add(df["issue_type"].isna(), "issue_type", "결측", "오염")
add(issue != issue.str.strip(), "issue_type", "앞뒤공백", "오염")

work = issue.str.strip()
add(work != work.str.lower(), "issue_type", "대문자표기", "오염")

work = work.str.lower()
add(work.str.match(r".*[_x]$") & ~work.isin(VALID_ISSUE),
    "issue_type", "접미사부착(_ 또는 x)", "오염")

work = work.str.replace(r"[_x]$", "", regex=True)
add(work.str.contains("3"), "issue_type", "숫자치환(3→e)", "오염")

work = work.str.replace("3", "e", regex=False)

# 위 처리를 거치고도 정상 4종에 없는 값을 분류한다
def classify_issue(value):
    if value in VALID_ISSUE or value == "":
        return None
    # ① 역순 배열 : 뒤집었을 때 정상값과 정확히 일치하는가
    #    value[::-1] 은 문자열을 거꾸로 뒤집는 파이썬 문법이다
    if value[::-1] in VALID_ISSUE:
        return f"역순배열(→{value[::-1]})"
    # ② 축약형 : 앞글자가 일치하는 정상값 후보가 1개인가
    candidates = [v for v in VALID_ISSUE if v.startswith(value)]
    if len(candidates) == 1:
        return f"축약형(→{candidates[0]})"
    return "복원불가_미확인값"

issue_class = work.map(classify_issue)
for label in sorted(issue_class.dropna().unique()):
    kind = "확인필요" if "복원불가" in label else "오염"
    add(issue_class == label, "issue_type", label, kind)
print()


# =============================================================================
# [검사 3] sentiment
#   issue_type과 같은 순서. 역순 패턴은 발견되지 않았으나 검사는 함께 수행한다.
# =============================================================================
print("[검사 3] sentiment")

sent = df["sentiment"].fillna("")

add(df["sentiment"].isna(), "sentiment", "결측", "오염")
add(sent != sent.str.strip(), "sentiment", "앞뒤공백", "오염")

work = sent.str.strip()
add(work != work.str.lower(), "sentiment", "대문자표기", "오염")

work = work.str.lower()
add(work.str.contains("3"), "sentiment", "숫자치환(3→e)", "오염")
work = work.str.replace("3", "e", regex=False)

def classify_sentiment(value):
    if value in VALID_SENTIMENT or value == "":
        return None
    if value[::-1] in VALID_SENTIMENT:
        return f"역순배열(→{value[::-1]})"
    candidates = [v for v in VALID_SENTIMENT if v.startswith(value)]
    if len(candidates) == 1:
        return f"축약형(→{candidates[0]})"
    return "복원불가_미확인값"

sent_class = work.map(classify_sentiment)
for label in sorted(sent_class.dropna().unique()):
    kind = "확인필요" if "복원불가" in label else "오염"
    add(sent_class == label, "sentiment", label, kind)
print()


# =============================================================================
# [검사 4] 날짜 — 오염 유형 분류
# =============================================================================
print("[검사 4] 날짜 오염 유형")

def is_real_datetime(value):
    """진짜 정상 ISO 일시인지 판정.
    형식이 맞아도 28시 77분처럼 시각이 불가능하면 False."""
    if pd.isna(value):
        return False
    v = str(value).strip()
    if not ISO_SECOND.match(v):
        return False
    hh, mm, ss = map(int, v[11:].split(":"))
    return hh <= 23 and mm <= 59 and ss <= 59

valid_created = df["ticket_created"].map(is_real_datetime)
valid_resolved = df["ticket_resolved"].map(is_real_datetime)

for col in ["ticket_created", "ticket_resolved"]:
    raw = df[col].fillna("").str.strip()

    add(df[col].isna(), col, "결측", "오염")

    for const in CONSTANT_DATETIMES:
        # 시각 범위초과 값은 사유를 따로 표기한다
        label = ("시각범위초과" if "T" in const else "상수값") + f"('{const}')"
        add(raw == const, col, label, "오염")

    # 마이크로초가 붙은 ISO = 적재 시점 타임스탬프
    add(raw.str.contains("T") & raw.str.contains(r"\."),
        col, "적재시각추정(마이크로초)", "오염")
print()


# =============================================================================
# [검사 5] 날짜 — 복원 가능성 분류 (이 파일의 핵심)
#
#   resolution_time_hours 가 깨끗하므로,
#   한쪽 날짜만 정상이어도 나머지를 계산으로 되살릴 수 있다.
#   그래서 '오염'을 다시 '복원 가능/불가'로 나눈다.
# =============================================================================
print("[검사 5] 날짜 복원 가능성")

res_hours = pd.to_numeric(df["resolution_time_hours"], errors="coerce")
has_hours = res_hours.notna()

# 유형 B : 접수만 정상 → 해결일시 복원 가능
type_b = valid_created & ~valid_resolved & has_hours
add(type_b, "ticket_resolved", "복원가능(접수+처리시간)", "복원가능")

# 유형 C : 해결만 정상 → 접수일시 복원 가능
type_c = ~valid_created & valid_resolved & has_hours
add(type_c, "ticket_created", "복원가능(해결−처리시간)", "복원가능")

# 유형 D : 둘 다 무효 → 복원 불가
type_d = ~valid_created & ~valid_resolved
add(type_d, "ticket_created", "복원불가(양쪽 무효)", "확인필요")
print()


# =============================================================================
# [검사 6] resolution_time_hours
#   2단계에서 '완전히 깨끗한 컬럼'으로 확인했다. 검증 차원에서 다시 검사한다.
# =============================================================================
print("[검사 6] resolution_time_hours")

add(df["resolution_time_hours"].isna(), "resolution_time_hours", "결측", "오염")
add(res_hours < 0, "resolution_time_hours", "음수", "오염")
add(res_hours == 0, "resolution_time_hours", "0시간", "오염")
print("  (출력이 없으면 위반 0건 — 이 컬럼이 날짜 복원의 기준이 된다)")
print()


# =============================================================================
# [검사 7] support_agent
# =============================================================================
print("[검사 7] support_agent")

agent = df["support_agent"].fillna("")

add(df["support_agent"].isna(), "support_agent", "결측", "오염")
add(agent != agent.str.strip(), "support_agent", "앞뒤공백", "표준화")

stripped = agent.str.strip()
add(stripped.str.isupper() & (stripped != ""), "support_agent", "전부대문자", "표준화")
add(stripped.str.islower() & (stripped != ""), "support_agent", "전부소문자", "표준화")
add(stripped.str.endswith("@@"), "support_agent", "접미사부착(@@)", "오염")
add(stripped.str.endswith("--"), "support_agent", "접미사부착(--)", "오염")

# 글자 중복 복원 가능 여부 판정
#   '데이터 자신'을 사전으로 쓴다. 중복을 줄인 형태가 사전에 있으면 복원 가능.
#   경칭(Jr./DDS/MD)은 제거하지 않는다 — 2단계 검증 결과 이름이 갈라지는 사례 0건.
normalized = (stripped
              .str.replace(r"\s+", " ", regex=True)
              .str.replace(r"(@@|--)$", "", regex=True)
              .str.strip()
              .str.title())
known_names = set(normalized.unique())

def classify_agent(name):
    if not VOWEL_DOUBLE.search(name):
        return None
    collapsed = VOWEL_DOUBLE.sub(lambda m: m.group(0)[0], name)
    if collapsed in known_names:
        return "글자중복_복원가능"
    return "글자중복이나_정상이름(유지)"

agent_class = normalized.map(classify_agent)
add(agent_class == "글자중복_복원가능", "support_agent", "글자중복_복원가능", "복원가능")
add(agent_class == "글자중복이나_정상이름(유지)", "support_agent",
    "글자중복이나_정상이름(유지)", "확인필요")
print()


# =============================================================================
# [출력 1] 이상 데이터 상세
# =============================================================================
issue_df = pd.concat(issues, ignore_index=True)
issue_df = issue_df[["행번호", "ticket_id", "컬럼", "원본값", "위반유형", "분류구분"]]
issue_df = issue_df.sort_values(["행번호", "컬럼"])

issue_df.to_csv(os.path.join(OUTPUT_DIR, "06_이상데이터_상세.csv"),
                index=False, encoding="utf-8-sig")
print(f"06_이상데이터_상세.csv 저장 완료 (총 {len(issue_df):,}건)")


# =============================================================================
# [출력 2] 유형별 집계
# =============================================================================
summary = (
    issue_df.groupby(["컬럼", "분류구분", "위반유형"])
    .size().reset_index(name="건수")
    .sort_values(["컬럼", "분류구분", "건수"], ascending=[True, True, False])
)
summary.to_csv(os.path.join(OUTPUT_DIR, "07_유형별_집계.csv"),
               index=False, encoding="utf-8-sig")
print("07_유형별_집계.csv 저장 완료")


# =============================================================================
# [출력 3] 진단 요약
# =============================================================================
lines = []
lines.append("=" * 80)
lines.append("support_tickets_30000 오염 진단 요약 (3단계)")
lines.append("=" * 80)
lines.append(f"전체 행 수        : {len(df):,}")
lines.append(f"위반 건수(누적)   : {len(issue_df):,}")

affected = issue_df["행번호"].nunique()
lines.append(f"위반이 있는 행 수 : {affected:,} / {len(df):,} ({affected/len(df)*100:.1f}%)")
lines.append("")

lines.append("-" * 80)
lines.append("[분류 구분별 건수]")
lines.append("-" * 80)
for kind, cnt in issue_df["분류구분"].value_counts().items():
    lines.append(f"  {kind:<10} : {cnt:>8,}건")
lines.append("")
lines.append("  오염     = 값이 틀림. 표기 규칙으로 수정")
lines.append("  표준화   = 값은 맞고 표기만 다름")
lines.append("  복원가능 = 오염이지만 다른 컬럼을 근거로 되살릴 수 있음")
lines.append("  확인필요 = 복원 근거가 없음")
lines.append("")

lines.append("-" * 80)
lines.append("[컬럼별 · 유형별 상세]")
lines.append("-" * 80)
for col in df.columns:
    sub = issue_df[issue_df["컬럼"] == col]
    lines.append(f"\n■ {col}  (총 {len(sub):,}건)")
    if len(sub) == 0:
        lines.append("    위반 없음 — 정상 컬럼")
        continue
    for (kind, itype), cnt in sub.groupby(["분류구분", "위반유형"]).size().items():
        lines.append(f"    [{kind}] {itype:<32} {cnt:>8,}건")

# -----------------------------------------------------------------------------
# 날짜 복원 가능성 요약 (이 파일의 핵심 지표)
# -----------------------------------------------------------------------------
type_a = valid_created & valid_resolved
lines.append("")
lines.append("-" * 80)
lines.append("[날짜 복원 가능성 — 이 파일의 핵심]")
lines.append("-" * 80)
lines.append(f"{'유형':<28}{'건수':>10}{'비율':>10}")
for label, mask in [("A. 둘 다 정상", type_a),
                    ("B. 접수만 정상 → 해결 복원", type_b),
                    ("C. 해결만 정상 → 접수 복원", type_c),
                    ("D. 둘 다 무효 → NULL", type_d)]:
    n = int(mask.sum())
    lines.append(f"{label:<28}{n:>10,}{n/len(df)*100:>9.1f}%")
usable = int((type_a | type_b | type_c).sum())
lines.append("-" * 48)
lines.append(f"{'복원 후 사용 가능':<28}{usable:>10,}{usable/len(df)*100:>9.1f}%")
lines.append(f"{'복원 없이 사용 가능':<28}{int(type_a.sum()):>10,}"
             f"{type_a.sum()/len(df)*100:>9.1f}%")
lines.append("")
lines.append("  ※ resolution_time_hours 컬럼이 깨끗한 덕분에")
lines.append("     사용 가능 티켓이 49.0% → 91.0% 로 늘어난다.")

lines.append("")
lines.append("-" * 80)
lines.append("[4단계 처리 예정]")
lines.append("-" * 80)
lines.append("  자동 수정 : issue_type 35종→4종, sentiment 18종→3종")
lines.append("  계산 복원 : 한쪽만 정상인 날짜 (유형 B + C)")
lines.append("  조건부 복원: 담당자명 글자중복 (정상형이 사전에 존재할 때만)")
lines.append("  NULL 처리 : 양쪽 날짜가 모두 무효인 유형 D")
lines.append("  처리 안 함 : 담당자 경칭(Jr./DDS/MD) — 검증 결과 처리 이득 없음")
lines.append("  행 삭제   : 없음")

with open(os.path.join(OUTPUT_DIR, "08_진단요약.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print("08_진단요약.txt 저장 완료")
print()
print("\n".join(lines))
