"""集中管理檔名與路徑常數

此模組是所有檔案路徑與版本資訊的單一真相來源。
validate/migrate 指令只讀這裡的版本常數。
"""

# === 版本常數（集中管理）===
CURRENT_SCHEMA_VERSION = "1.2"  # YAML 檔案內容格式版本（V1.2: members 雙人結構）
DATA_LAYOUT_VERSION = "1.0"  # 資料夾/檔名結構版本

# === 檔名常數 ===
ASSUMPTIONS_FILE = "life_assumptions.yaml"
TARGETS_FILE = "lifetime_targets.yaml"
INCOME_FILE = "monthly_income.yaml"
POLICY_FILE = "expense_policy.yaml"
DECISIONS_FILE = "decisions.yaml"

# === 目錄常數 ===
EXPENSES_DIR = "expenses"

# === 預設資料目錄 ===
DEFAULT_DATA_DIR_NAME = ".life-capital"

# === 環境變數名稱 ===
ENV_DATA_DIR = "LIFE_CAPITAL_DATA_DIR"

# === CSV 欄位定義 ===
EXPENSE_CSV_REQUIRED_FIELDS = ["date", "amount", "category"]
EXPENSE_CSV_OPTIONAL_FIELDS = ["payer", "note", "merchant"]  # V1.1: 新增 payer 欄位
EXPENSE_CSV_ALL_FIELDS = EXPENSE_CSV_REQUIRED_FIELDS + EXPENSE_CSV_OPTIONAL_FIELDS

# === 檔名模式 ===
EXPENSE_FILE_PATTERN = "expenses_{year}_{month:02d}.csv"


def get_expense_filename(year: int, month: int) -> str:
    """生成支出檔案名稱

    Args:
        year: 年份 (e.g., 2024)
        month: 月份 (1-12)

    Returns:
        檔案名稱，如 "expenses_2024_12.csv"
    """
    return f"expenses_{year}_{month:02d}.csv"


# === Phase 0: 資料三層結構 ===
RAW_DIR = "raw"
CANONICAL_DIR = "canonical"
DERIVED_DIR = "derived"
PROPOSALS_DIR = "proposals"

# === Phase 0: Subdirectories ===
RAW_IMPORTS_DIR = "raw/imports"
RAW_MANUAL_DIR = "raw/manual"
CANONICAL_EXPENSES_DIR = "canonical/expenses"
CANONICAL_DECISIONS_DIR = "canonical/decisions"
DERIVED_REPORTS_DIR = "derived/reports"
DERIVED_SCENARIOS_DIR = "derived/scenarios"
PROPOSALS_PENDING_DIR = "proposals/pending"

# === Phase 0: Operation & Provenance ===
OPERATION_LOG_FILE = "canonical/.operation_log.jsonl"
MIGRATION_LOG_DIR = "canonical/.migrations"

# === Phase 1: Dedupe 策略常數 ===
AUTO_MERGE_THRESHOLD = 0.95  # ≥95% 自動合併
MANUAL_REVIEW_THRESHOLD = 0.70  # 70-95% 需人工裁決
WINDOW_OCCURRED_DAYS = 1  # occurred_at ±1 天
WINDOW_POSTED_DAYS = 7  # posted_at ±7 天（跨月緩衝）

# === Phase 1: 允許的 dedupe_key 版本集合 ===
ALLOWED_DEDUPE_KEY_VERSIONS: set[str] = {"v1", "v2"}  # 可擴展
DEFAULT_DEDUPE_KEY_VERSION = "v1"

# === Phase 1: Raw Manifest ===
RAW_MANIFEST_FILE = "raw/raw_manifest.json"

# === Phase 2: Scenario 模組常數 ===
CALC_VERSION = "2.0"  # 計算邏輯版本（Phase 2: Scenario 核心）
SCENARIOS_DIR = "derived/scenarios"
DEFAULT_PROJECTION_MONTHS = 24
MIN_PROJECTION_MONTHS = 10
MAX_PROJECTION_MONTHS = 60
DEFAULT_HISTORICAL_MONTHS = 6

# === Phase 3: Generation 模組常數 ===
GENERATION_VERSION = "1.0"  # 生成邏輯版本（Phase 3: Report Generation）
REPORTS_DIR = DERIVED_REPORTS_DIR  # "derived/reports" (沿用 Phase 0 定義)
REPORT_HASH_LEN = 12  # 報表檔名 hash 長度（統一 12 位）
REPORT_PROVENANCE_SUFFIX = ".meta.json"  # Sidecar provenance 檔案後綴

# === Phase 3: CLI Type Mapping ===
CLI_TYPE_MAPPING = {
    "all": ["monthly_summary", "projection_table", "scenario_comparison"],
    "monthly": ["monthly_summary"],
    "projection": ["projection_table"],
    "comparison": ["scenario_comparison"],
}

# === Phase 5: Advisor 模組常數 ===
ADVISOR_VERSION = "1.0"  # Advisor 邏輯版本
DECISIONS_SCHEMA_VERSION = "1.0"  # 決策記憶 schema 版本

# Phase 5: 路徑常數（唯一來源）
ADVISOR_PROPOSALS_DIR = "proposals/pending"  # advisor 輸出位置
ADVISOR_AUDIT_LOG = "derived/logs/advisor_audit.jsonl"  # 審計日誌
ADVISOR_DERIVED_DIR = "derived/advisor"  # Stage 3 衍生物目錄

# Phase 5: 可比較性閾值
COMPARABILITY_THRESHOLD = 0.6  # >= 0.6 為可比較

# Phase 5 Stage 3: Canonicalization 與 Provenance
CANONICALIZATION_VERSION = "1.0"  # 正規化版本
ADVISOR_PROVENANCE_VERSION = "1.0"  # Provenance schema 版本
