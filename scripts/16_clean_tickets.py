# =============================================================================
# 파일명 : 16_clean_tickets.py
# 단계   : 4단계 - 정제 규칙 적용 및 정제 파일 생성 (support_tickets)
#
# [목적]
#   2단계 규칙서(데이터사전_tickets.md)대로 값을 고치고 새 파일로 저장한다.
#
# [처리 순서]
#   ① 원본 값 보존 컬럼 생성
#   ② issue_type / sentiment 복원 (7단계 변환)
#   ③ 날짜 유효성 판정 → 계산 복원 → NULL 처리
#   ④ 담당자명 정규화 및 조건부 복원
#
#   ③이 이 파일의 핵심이다. 다른 파일들은 오염된 날짜를 버렸지만,
#   여기서는 resolution_time_hours 를 근거로 12,626건을 되살린다.
#
# [이 파일에서 처음 하는 일 — 값을 '만들어낸다']
#   지금까지는 있는 값을 고치거나 비웠다.
#   여기서는 원본에 없던 값을 계산해서 채운다.
#   근거가 있어도 원본은 아니므로, 반드시 두 가지를 지킨다:
#     - date_flag 에 '처리시간으로_복원' 을 기록한다
#     - 원본 값을 _raw 컬럼에 그대로 보존한다
#   그래야 나중에 "이 날짜는 실제 기록인가, 계산값인가"를 구분할 수 있다.
#
# [입력]  01_raw/support_tickets_30000_dirty.csv
# [출력]  03_cleaned/support_tickets_cleaned.csv
#         04_reports/정제로그_tickets.txt
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
CLEAN_DIR = os.path.join(PROJECT_DIR, "03_cleaned")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(CLEAN_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 2단계에서 확정한 규칙 상수
# -----------------------------------------------------------------------------
ISO_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
VALID_ISSUE = ["payment", "delay", "refund", "product"]
VALID_SENTIMENT = ["positive", "neutral", "negative"]
VOWEL_DOUBLE = re.compile(r"(aa|ii|uu|jj|kk|vv|ww|yy|hh|qq|xx|zz)", re.IGNORECASE)

# 출력 날짜 형식 (PostgreSQL의 TIMESTAMP 타입이 그대로 인식한다)
DT_FORMAT = "%Y-%m-%d %H:%M:%S"


raw = read_csv_safe(INPUT_FILE, dtype=str, keep_default_na=True)
print(f"원본 읽기 완료 : {len(raw):,}행")
print()
print("[처리 진행]")

df = raw.copy()


# =============================================================================
# ① 원본 값 보존
#    정제를 시작하기 전에 복사해야 한다. 시작한 뒤에 복사하면 이미 바뀐 값이 담긴다.
# =============================================================================
PRESERVE_COLS = ["ticket_created", "ticket_resolved", "support_agent"]
for col in PRESERVE_COLS:
    df[f"{col}_raw"] = raw[col]

print(f"  1. 원본 값 보존 컬럼 생성        {len(PRESERVE_COLS)}개")


# =============================================================================
# ② issue_type / sentiment 복원
#
#   변환 순서 (순서를 지켜야 겹친 오염이 벗겨진다)
#     ① 앞뒤 공백 제거
#     ② 소문자 변환
#     ③ 끝의 _ 또는 x 제거
#     ④ 숫자 3 → e 치환
#     ⑤ 정상값에 있으면 확정
#     ⑥ 없으면 역순으로 뒤집어 대조   ← 이 파일에서 새로 추가된 규칙
#     ⑦ 그래도 없으면 앞글자 매칭(축약형), 후보가 1개일 때만 복원
# =============================================================================
def build_mapper(valid_values):
    """정상값 목록을 받아, 오염된 값을 복원하는 함수를 만들어 반환한다.
    반환 함수는 (복원값, 플래그) 튜플을 준다."""

    def mapper(value):
        if value == "" or pd.isna(value):
            return None, "결측"

        work = str(value).strip().lower()          # ①②
        work = re.sub(r"[_x]$", "", work)          # ③
        work = work.replace("3", "e")              # ④

        if work in valid_values:                   # ⑤
            return work, None

        # ⑥ 역순 배열 : value[::-1] 은 문자열을 거꾸로 뒤집는 파이썬 문법
        #    뒤집었을 때 정상값과 '정확히' 일치할 때만 복원하므로 안전하다
        if work[::-1] in valid_values:
            return work[::-1], None

        # ⑦ 축약형 : 앞글자가 일치하는 후보가 정확히 1개일 때만 복원
        candidates = [v for v in valid_values if v.startswith(work)]
        if len(candidates) == 1:
            return candidates[0], None

        # 복원 근거가 없으면 원본을 유지하고 플래그를 남긴다
        return value, "복원불가"

    return mapper


for col, valid in [("issue_type", VALID_ISSUE), ("sentiment", VALID_SENTIMENT)]:
    mapper = build_mapper(valid)
    source = df[col].fillna("")

    # 값 종류가 수십 개뿐이므로 고유값에만 함수를 적용하고 매핑으로 되돌린다.
    # 3만 행에 함수를 직접 적용하는 것보다 빠르다.
    lookup = {v: mapper(v) for v in source.unique()}
    df[col] = source.map(lambda v: lookup[v][0])
    df[f"{col.split('_')[0]}_flag"] = source.map(lambda v: lookup[v][1])

    print(f"  2. {col:<12} 정제           {df[col].nunique()}종으로 통일")


# =============================================================================
# ③ 날짜 — 유효성 판정 → 계산 복원 → NULL 처리
# =============================================================================

# -----------------------------------------------------------------------------
# 3-1. 유효성 판정
#   형식이 ISO여도 시각이 28시 77분이면 무효다.
#   문자열 검사만으로는 걸러지지 않으므로 시/분/초 값을 직접 확인한다.
# -----------------------------------------------------------------------------
def is_real_datetime(value):
    if pd.isna(value):
        return False
    v = str(value).strip()
    if not ISO_SECOND.match(v):
        return False
    hh, mm, ss = map(int, v[11:].split(":"))
    return hh <= 23 and mm <= 59 and ss <= 59

valid_created = df["ticket_created"].map(is_real_datetime)
valid_resolved = df["ticket_resolved"].map(is_real_datetime)

# 유효한 값만 날짜로 변환한다. where() 로 무효값은 미리 비운다.
created = pd.to_datetime(df["ticket_created"].where(valid_created),
                         format="ISO8601", errors="coerce")
resolved = pd.to_datetime(df["ticket_resolved"].where(valid_resolved),
                          format="ISO8601", errors="coerce")

hours = pd.to_numeric(df["resolution_time_hours"], errors="coerce")
# to_timedelta : 숫자를 '시간 간격'으로 바꿔 날짜에 더하거나 뺄 수 있게 한다
delta = pd.to_timedelta(hours, unit="h")

# -----------------------------------------------------------------------------
# 3-2. 오염 사유를 먼저 기록한다 (복원 여부와 무관하게 원래 무엇이 문제였는지)
# -----------------------------------------------------------------------------
def classify_reason(series, valid_mask):
    reason = pd.Series([None] * len(series), index=series.index, dtype="object")
    text = series.fillna("").str.strip()
    reason[series.isna()] = "원본결측"
    reason[text.isin(["2024/31/01", "31-15-2023"])] = "상수값"
    reason[text == "2025-12-12T28:77:10"] = "시각범위초과"
    reason[text.str.contains("T") & text.str.contains(r"\.")] = "적재시각추정"
    reason[valid_mask] = None
    return reason

created_reason = classify_reason(df["ticket_created"], valid_created)
resolved_reason = classify_reason(df["ticket_resolved"], valid_resolved)

# -----------------------------------------------------------------------------
# 3-3. 계산 복원
#   유형 B : 접수 정상 + 해결 무효 → 해결 = 접수 + 처리시간
#   유형 C : 해결 정상 + 접수 무효 → 접수 = 해결 − 처리시간
#
#   이 관계식은 두 날짜가 모두 정상인 14,687건에서 오차 0으로 검증되었다.
#   (근거는 규칙서 2-2 참고)
# -----------------------------------------------------------------------------
can_fix_resolved = valid_created & ~valid_resolved & delta.notna()
can_fix_created = ~valid_created & valid_resolved & delta.notna()

resolved = resolved.where(~can_fix_resolved, created + delta)
created = created.where(~can_fix_created, resolved - delta)

df["date_flag"] = None
# 복원된 행은 '무엇이 문제였는지 + 어떻게 채웠는지'를 함께 남긴다
df.loc[can_fix_resolved, "date_flag"] = (
    "해결일시_복원(" + resolved_reason[can_fix_resolved].fillna("무효") + ")")
df.loc[can_fix_created, "date_flag"] = (
    "접수일시_복원(" + created_reason[can_fix_created].fillna("무효") + ")")

# 양쪽 다 무효 → 복원 불가
both_invalid = ~valid_created & ~valid_resolved
df.loc[both_invalid, "date_flag"] = "복원불가(양쪽무효)"

df["ticket_created"] = created.dt.strftime(DT_FORMAT)
df["ticket_resolved"] = resolved.dt.strftime(DT_FORMAT)

n_fixed = int(can_fix_resolved.sum() + can_fix_created.sum())
print(f"  3. 날짜 계산 복원              {n_fixed:,}건 복원 / "
      f"{int(both_invalid.sum()):,}건 NULL")


# =============================================================================
# ④ support_agent 정규화 및 조건부 복원
#
#   ① 공백 정리 → ② 접미사 @@ -- 제거 → ③ Title Case
#   ④ 글자 중복은 '정상형이 데이터에 존재할 때만' 복원
#
#   경칭(Jr./DDS/MD)은 제거하지 않는다.
#   2단계 검증 결과 경칭 유무로 이름이 갈라지는 사례가 0건이었고,
#   제거해도 합쳐지는 이름이 없어 이득이 없기 때문이다.
# =============================================================================
normalized = (df["support_agent"].fillna("")
              .str.replace(r"\s+", " ", regex=True)
              .str.strip()
              .str.replace(r"(@@|--)$", "", regex=True)
              .str.strip()
              .str.title())

# '데이터 자신'을 사전으로 쓴다.
# 같은 담당자가 여러 티켓에 등장하므로, 정상 표기가 데이터 안에 존재한다.
known_names = set(normalized.unique())

def restore_agent(name):
    if not VOWEL_DOUBLE.search(name):
        return name, None
    collapsed = VOWEL_DOUBLE.sub(lambda m: m.group(0)[0], name)
    if collapsed in known_names:
        return collapsed, None
    # 사전에 없으면 정상 이름으로 판단하고 그대로 둔다 (Aaron, Isaac 등)
    return name, "글자중복이나_정상이름(유지)"

agent_lookup = {n: restore_agent(n) for n in known_names}
df["support_agent"] = normalized.map(lambda n: agent_lookup[n][0])
df["agent_flag"] = normalized.map(lambda n: agent_lookup[n][1])

print(f"  4. support_agent 정제          "
      f"{df['support_agent'].nunique()}명으로 통일")


# =============================================================================
# [저장]
# =============================================================================
OUTPUT_COLS = [
    # --- 키 (변경 없음) ---
    "ticket_id", "customer_id",
    # --- 분석용 정제값 ---
    "issue_type", "sentiment",
    "ticket_created", "ticket_resolved", "resolution_time_hours",
    "support_agent",
    # --- 원본 보존 ---
    "ticket_created_raw", "ticket_resolved_raw", "support_agent_raw",
    # --- 처리 사유 ---
    "date_flag", "issue_flag", "sentiment_flag", "agent_flag",
]
df = df[OUTPUT_COLS]

output_path = os.path.join(CLEAN_DIR, "support_tickets_cleaned.csv")
df.to_csv(output_path, index=False, encoding="utf-8-sig")

print()
print(f"정제 파일 저장 : {output_path}")


# =============================================================================
# [정제 로그]
# =============================================================================
lines = []
lines.append("=" * 80)
lines.append("support_tickets_30000 정제 로그 (4단계)")
lines.append("=" * 80)
lines.append(f"원본 행 수 : {len(raw):,}")
lines.append(f"정제 행 수 : {len(df):,}   ← 행을 삭제하지 않았으므로 동일해야 정상")
lines.append("")

lines.append("-" * 80)
lines.append("[컬럼별 정제 결과]")
lines.append("-" * 80)
for col in ["issue_type", "sentiment", "ticket_created", "ticket_resolved",
            "resolution_time_hours", "support_agent"]:
    n_null = int(df[col].isna().sum())
    lines.append(f"  {col:<24} 사용 가능 {len(df)-n_null:>7,}건 / "
                 f"NULL {n_null:>6,}건 ({n_null/len(df)*100:>4.1f}%)")
lines.append("")

lines.append("-" * 80)
lines.append("[날짜 복원 결과 — 이 파일의 핵심]")
lines.append("-" * 80)
n_a = int((valid_created & valid_resolved).sum())
lines.append(f"  A. 원본 그대로 사용        : {n_a:>7,}건 ({n_a/len(df)*100:>4.1f}%)")
lines.append(f"  B. 해결일시를 계산으로 복원 : {int(can_fix_resolved.sum()):>7,}건 "
             f"({can_fix_resolved.sum()/len(df)*100:>4.1f}%)")
lines.append(f"  C. 접수일시를 계산으로 복원 : {int(can_fix_created.sum()):>7,}건 "
             f"({can_fix_created.sum()/len(df)*100:>4.1f}%)")
lines.append(f"  D. 복원 불가 (NULL)       : {int(both_invalid.sum()):>7,}건 "
             f"({both_invalid.sum()/len(df)*100:>4.1f}%)")
lines.append("-" * 52)
usable = len(df) - int(both_invalid.sum())
lines.append(f"  사용 가능 합계            : {usable:>7,}건 ({usable/len(df)*100:>4.1f}%)")
lines.append(f"  복원하지 않았다면          : {n_a:>7,}건 ({n_a/len(df)*100:>4.1f}%)")
lines.append("")
lines.append("  ※ resolution_time_hours 컬럼이 깨끗한 덕분에 사용 가능 데이터가 두 배가 됐다.")
lines.append("     복원된 날짜는 원본 기록이 아니라 계산값이므로 date_flag 로 구분된다.")
lines.append("")

lines.append("-" * 80)
lines.append("[처리 사유별 건수]")
lines.append("-" * 80)
for col in ["date_flag", "issue_flag", "sentiment_flag", "agent_flag"]:
    counts = df[col].value_counts(dropna=True)
    lines.append(f"\n  ■ {col}")
    if len(counts) == 0:
        lines.append("      없음 — 전량 정상 처리")
    for k, v in counts.items():
        lines.append(f"      {k:<36} {v:>7,}건")
lines.append("")

lines.append("-" * 80)
lines.append("[정제 후 범주형 분포]")
lines.append("-" * 80)
for col in ["issue_type", "sentiment"]:
    lines.append(f"\n  ■ {col}")
    for k, v in df[col].value_counts(dropna=False).items():
        lines.append(f"      {str(k):<12} {v:>7,}건  ({v/len(df)*100:>4.1f}%)")
lines.append("")

lines.append("-" * 80)
lines.append("[담당자 및 처리시간 요약]")
lines.append("-" * 80)
lines.append(f"  담당자 수(정제 전 표기 기준) : {raw['support_agent'].nunique():,}종")
lines.append(f"  담당자 수(정제 후)          : {df['support_agent'].nunique():,}명")
lines.append(f"  담당자당 평균 처리 건수      : "
             f"{len(df)/df['support_agent'].nunique():.1f}건")
res = pd.to_numeric(df["resolution_time_hours"], errors="coerce")
lines.append(f"  처리시간 최소/최대          : {res.min():.0f} ~ {res.max():.0f} 시간")
lines.append(f"  처리시간 평균/중앙값        : {res.mean():.1f} / {res.median():.1f} 시간")
lines.append("")

lines.append("-" * 80)
lines.append("[원본 값 보존]")
lines.append("-" * 80)
lines.append("  날짜 12,626건을 계산으로 채웠으므로, 원본과 계산값을 반드시 구분해야 한다.")
lines.append("  ticket_created_raw / ticket_resolved_raw / support_agent_raw")
lines.append("")
lines.append("  SQL 예시 — 계산으로 복원된 티켓만 조회:")
lines.append("    SELECT ticket_id, ticket_created_raw, ticket_created, date_flag")
lines.append("    FROM   support_tickets")
lines.append("    WHERE  date_flag LIKE '%복원%';")

with open(os.path.join(REPORT_DIR, "정제로그_tickets.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print()
print("\n".join(lines))
