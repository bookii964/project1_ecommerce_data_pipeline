# =============================================================================
# 파일명 : 18_preflight_check.py
# 단계   : 6단계 보조 - 적재 전 사전 점검
#
# [목적]
#   CSV를 PostgreSQL에 넣기 전에, 파일이 테이블 구조와 맞는지 확인한다.
#
# [왜 필요한가]
#   적재 오류 메시지는 원인을 곧바로 알려주지 않는다.
#   예를 들어 컬럼 수가 부족하면 이런 메시지가 나온다:
#       오류: "name_flag" 칼럼의 자료가 비었습니다
#   값이 비었다는 뜻이 아니라 '읽을 필드가 도중에 끝났다'는 뜻이다.
#   미리 컬럼 수를 세어보면 이런 혼란을 피할 수 있다.
#
# [점검 항목 4가지]
#   ① 파일이 존재하는가
#   ② 인코딩이 UTF-8인가          (엑셀로 저장하면 CP949로 바뀐다)
#   ③ 컬럼 이름과 순서가 맞는가    (\copy 는 순서대로 넣으므로 순서도 중요하다)
#   ④ 행 수가 예상과 맞는가
#
# [입력]  03_cleaned/*.csv
# [출력]  화면 출력 + 04_reports/적재전_점검결과.txt
# =============================================================================

import os
import csv
import pandas as pd


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
CLEAN_DIR = os.path.join(PROJECT_DIR, "03_cleaned")
REPORT_DIR = os.path.join(PROJECT_DIR, "04_reports")
os.makedirs(REPORT_DIR, exist_ok=True)


# -----------------------------------------------------------------------------
# [설정] 테이블별 기대 구조
#   01_create_tables.sql 의 컬럼 순서와 정확히 같아야 한다.
#   \copy 는 컬럼 이름을 보지 않고 '순서대로' 값을 넣기 때문이다.
# -----------------------------------------------------------------------------
EXPECTED = {
    "product_catalog_cleaned.csv": {
        "테이블": "product_catalog",
        "행수": 500,
        "컬럼": ["product_id", "product_name", "category", "price",
                "name_flag", "price_flag"],
    },
    "crm_customers_cleaned.csv": {
        "테이블": "crm_customers",
        "행수": 48200,
        "컬럼": ["customer_id", "first_name", "last_name", "email",
                "phone_number", "phone_ext", "gender", "dob", "signup_date",
                "age_at_signup", "address", "city", "state", "country",
                "device_count", "source",
                "first_name_raw", "last_name_raw", "email_raw", "phone_number_raw",
                "name_flag", "email_flag", "phone_flag", "age_flag"],
    },
    "crm_customer_devices_cleaned.csv": {
        "테이블": "crm_customer_devices",
        "행수": 51854,
        "컬럼": ["customer_id", "device_id"],
    },
    "orders_cleaned.csv": {
        "테이블": "orders",
        "행수": 300000,
        "컬럼": ["order_id", "customer_id", "product_id", "order_amount",
                "order_date", "payment_method", "status", "quantity",
                "order_amount_raw", "order_date_raw", "quantity_raw",
                "amount_flag", "date_flag", "quantity_flag",
                "payment_flag", "status_flag"],
    },
    "support_tickets_cleaned.csv": {
        "테이블": "support_tickets",
        "행수": 30000,
        "컬럼": ["ticket_id", "customer_id", "issue_type", "sentiment",
                "ticket_created", "ticket_resolved", "resolution_time_hours",
                "support_agent",
                "ticket_created_raw", "ticket_resolved_raw", "support_agent_raw",
                "date_flag", "issue_flag", "sentiment_flag", "agent_flag"],
    },
}

# 적재 순서 (외래키 때문에 이 순서를 지켜야 한다)
LOAD_ORDER = [
    "product_catalog_cleaned.csv",
    "crm_customers_cleaned.csv",
    "crm_customer_devices_cleaned.csv",
    "orders_cleaned.csv",
    "support_tickets_cleaned.csv",
]


lines = []
def w(text=""):
    lines.append(text)
    print(text)


w("=" * 78)
w("적재 전 사전 점검")
w("=" * 78)
w(f"대상 폴더 : {CLEAN_DIR}")
w("")

all_ok = True

for idx, filename in enumerate(LOAD_ORDER, start=1):
    spec = EXPECTED[filename]
    path = os.path.join(CLEAN_DIR, filename)

    w("-" * 78)
    w(f"[{idx}] {spec['테이블']}  ←  {filename}")
    w("-" * 78)

    # --- ① 파일 존재 확인 -----------------------------------------------
    if not os.path.exists(path):
        w("  [실패] 파일이 없습니다.")
        w("         해당 정제 스크립트를 먼저 실행하세요.")
        all_ok = False
        w("")
        continue

    size_mb = os.path.getsize(path) / 1024 / 1024
    w(f"  파일 크기 : {size_mb:,.1f} MB")

    # --- ② 인코딩 확인 ---------------------------------------------------
    #   파일 앞 3바이트가 EF BB BF 면 UTF-8 BOM 이다 (우리 스크립트의 저장 방식).
    #   엑셀로 열어 저장하면 BOM이 사라지고 CP949로 바뀌는 경우가 많다.
    with open(path, "rb") as f:
        head = f.read(3)

    encoding_used = None
    for enc in ["utf-8-sig", "cp949"]:
        try:
            with open(path, encoding=enc) as f:
                f.readline()
            encoding_used = enc
            break
        except UnicodeDecodeError:
            continue

    if encoding_used == "utf-8-sig":
        w("  인코딩    : UTF-8  (정상)")
    elif encoding_used == "cp949":
        w("  인코딩    : CP949  [경고]")
        w("              엑셀로 열어 저장한 흔적입니다.")
        w("              정제 스크립트를 다시 실행해 UTF-8로 복구하세요.")
        all_ok = False
    else:
        w("  인코딩    : 판별 실패  [실패]")
        all_ok = False

    # --- ③ 컬럼 이름과 순서 확인 ------------------------------------------
    #   csv.reader 로 첫 줄만 읽는다. 파일 전체를 메모리에 올리지 않아 빠르다.
    with open(path, encoding=encoding_used or "utf-8-sig", newline="") as f:
        actual_cols = next(csv.reader(f))

    expected_cols = spec["컬럼"]

    w(f"  컬럼 수   : {len(actual_cols)}개 (기대 {len(expected_cols)}개)")

    if actual_cols == expected_cols:
        w("  컬럼 구성 : 이름·순서 모두 일치  (정상)")
    else:
        all_ok = False
        w("  컬럼 구성 : 불일치  [실패]")

        missing = [c for c in expected_cols if c not in actual_cols]
        extra = [c for c in actual_cols if c not in expected_cols]

        if missing:
            w(f"              CSV에 없는 컬럼 : {missing}")
            w("              → 정제 스크립트가 구버전입니다. 다시 실행하세요.")
        if extra:
            w(f"              CSV에만 있는 컬럼 : {extra}")
            w("              → DDL(01_create_tables.sql)을 확인하세요.")
        if not missing and not extra:
            # 이름은 같은데 순서가 다른 경우.
            # \copy 는 순서대로 값을 넣으므로 이대로 적재하면 값이 뒤섞인다.
            w("              이름은 같으나 순서가 다릅니다.")
            w("              → \\copy 는 순서대로 넣으므로 값이 뒤섞입니다.")
            for i, (a, e) in enumerate(zip(actual_cols, expected_cols)):
                if a != e:
                    w(f"                {i+1}번째: CSV '{a}' vs 기대 '{e}'")

    # --- ④ 행 수 확인 ----------------------------------------------------
    #   30만 행 파일도 있으므로 pandas 대신 줄 수만 센다 (훨씬 빠르고 가볍다).
    with open(path, "rb") as f:
        row_count = sum(1 for _ in f) - 1     # 헤더 1줄 제외

    if row_count == spec["행수"]:
        w(f"  행 수     : {row_count:,}행  (정상)")
    else:
        w(f"  행 수     : {row_count:,}행  (기대 {spec['행수']:,}행)  [경고]")
        w("              정제 스크립트를 다시 실행했다면 숫자가 달라질 수 있습니다.")

    w("")


# =============================================================================
# 종합 판정
# =============================================================================
w("=" * 78)
if all_ok:
    w("종합 판정 : 전체 정상 — 적재를 진행할 수 있습니다.")
    w("")
    w("  적재 순서 (외래키 때문에 반드시 이 순서로):")
    for idx, filename in enumerate(LOAD_ORDER, start=1):
        w(f"    {idx}) {EXPECTED[filename]['테이블']}")
else:
    w("종합 판정 : 문제 발견 — 위의 [실패] 항목을 해결한 뒤 적재하세요.")
w("=" * 78)

with open(os.path.join(REPORT_DIR, "적재전_점검결과.txt"), "w", encoding="utf-8-sig") as f:
    f.write("\n".join(lines))

print()
print("저장 완료 : 04_reports/적재전_점검결과.txt")

