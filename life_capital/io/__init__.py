"""I/O 層 - 資料存取與檔案處理

注意：csv_handler 延遲導入以避免循環導入問題
（csv_handler → models.expense → models.base → io.registry → io.__init__）
"""

# Errors 共用例外（無循環依賴）
from life_capital.io.errors import (
    CSVError,
    CSVParseError,
    RawFileExistsError,
    RawHandlerError,
    YAMLError,
    YAMLParseError,
    YAMLValidationError,
)

# Raw handler 可直接導入（無循環依賴）
from life_capital.io.raw_handler import (
    list_raw_files,
    read_raw,
    write_raw,
)

# Registry 可直接導入（無循環依賴）
from life_capital.io.registry import (
    ASSUMPTIONS_FILE,
    CURRENT_SCHEMA_VERSION,
    DATA_LAYOUT_VERSION,
    EXPENSES_DIR,
    INCOME_FILE,
    POLICY_FILE,
    TARGETS_FILE,
    get_expense_filename,
)

# YAML handler 可直接導入（無循環依賴）
from life_capital.io.yaml_handler import (
    load_model,
    load_yaml,
    save_model,
    save_yaml,
    validate_version,
)


# CSV handler 與 data_fetcher 延遲導入（避免循環依賴）
def __getattr__(name: str):
    """延遲導入 csv_handler 與 data_fetcher 相關符號"""
    csv_exports = {
        "DedupeMode",
        "load_csv",
        "load_monthly_expenses",
        "save_csv",
    }
    if name in csv_exports:
        from life_capital.io import csv_handler
        return getattr(csv_handler, name)

    # Data fetcher exports
    fetcher_exports = {
        "fetch_historical_expenses",
        "fetch_expense_range",
        "fetch_latest_income",
        "list_expense_months",
        "parse_expense_filename",
    }
    if name in fetcher_exports:
        from life_capital.io import data_fetcher
        return getattr(data_fetcher, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Registry
    "CURRENT_SCHEMA_VERSION",
    "DATA_LAYOUT_VERSION",
    "ASSUMPTIONS_FILE",
    "TARGETS_FILE",
    "INCOME_FILE",
    "POLICY_FILE",
    "EXPENSES_DIR",
    "get_expense_filename",
    # YAML
    "YAMLError",
    "YAMLParseError",
    "YAMLValidationError",
    "load_yaml",
    "save_yaml",
    "load_model",
    "save_model",
    "validate_version",
    # CSV
    "CSVError",
    "CSVParseError",
    "DedupeMode",
    "load_csv",
    "save_csv",
    "load_monthly_expenses",
    # Raw Handler
    "RawHandlerError",
    "RawFileExistsError",
    "write_raw",
    "read_raw",
    "list_raw_files",
    # Data Fetcher
    "fetch_historical_expenses",
    "fetch_expense_range",
    "fetch_latest_income",
    "list_expense_months",
    "parse_expense_filename",
]
