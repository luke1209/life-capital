"""路徑解析模組

處理 --path 參數和預設路徑解析。
支援環境變數 LIFE_CAPITAL_DATA_DIR 覆寫。
"""

import os
from pathlib import Path
from typing import Optional

from life_capital.io.registry import (
    ASSUMPTIONS_FILE,
    DEFAULT_DATA_DIR_NAME,
    ENV_DATA_DIR,
    EXPENSES_DIR,
    INCOME_FILE,
    POLICY_FILE,
    TARGETS_FILE,
    get_expense_filename,
)


def get_default_data_dir() -> Path:
    """取得預設資料目錄路徑

    優先順序:
    1. 環境變數 LIFE_CAPITAL_DATA_DIR
    2. ~/.life-capital/

    Returns:
        資料目錄的 Path 物件
    """
    env_path = os.environ.get(ENV_DATA_DIR)
    if env_path:
        return Path(env_path).expanduser().resolve()

    return Path.home() / DEFAULT_DATA_DIR_NAME


def resolve_data_dir(path: Optional[str] = None) -> Path:
    """解析資料目錄路徑

    Args:
        path: 使用者指定的路徑，可為 None 使用預設值

    Returns:
        解析後的絕對路徑

    Raises:
        ValueError: 路徑格式無效
    """
    if path:
        resolved = Path(path).expanduser().resolve()
        return resolved

    return get_default_data_dir()


def ensure_data_dir(path: Optional[str] = None) -> Path:
    """確保資料目錄存在，若不存在則建立

    Args:
        path: 使用者指定的路徑，可為 None 使用預設值

    Returns:
        資料目錄的 Path 物件

    Raises:
        PermissionError: 無法建立目錄
    """
    data_dir = resolve_data_dir(path)
    data_dir.mkdir(parents=True, exist_ok=True)

    # 建立 expenses 子目錄
    expenses_dir = data_dir / EXPENSES_DIR
    expenses_dir.mkdir(exist_ok=True)

    return data_dir


def data_file(filename: str, path: Optional[str] = None) -> Path:
    """取得資料檔案的完整路徑

    Args:
        filename: 檔案名稱
        path: 使用者指定的資料目錄，可為 None 使用預設值

    Returns:
        檔案的完整 Path 物件
    """
    data_dir = resolve_data_dir(path)
    return data_dir / filename


def assumptions_file(path: Optional[str] = None) -> Path:
    """取得 life_assumptions.yaml 的路徑"""
    return data_file(ASSUMPTIONS_FILE, path)


def targets_file(path: Optional[str] = None) -> Path:
    """取得 lifetime_targets.yaml 的路徑"""
    return data_file(TARGETS_FILE, path)


def income_file(path: Optional[str] = None) -> Path:
    """取得 monthly_income.yaml 的路徑"""
    return data_file(INCOME_FILE, path)


def policy_file(path: Optional[str] = None) -> Path:
    """取得 expense_policy.yaml 的路徑"""
    return data_file(POLICY_FILE, path)


def expenses_dir(path: Optional[str] = None) -> Path:
    """取得 expenses 目錄的路徑"""
    data_dir = resolve_data_dir(path)
    return data_dir / EXPENSES_DIR


def expenses_file(year: int, month: int, path: Optional[str] = None) -> Path:
    """取得特定月份支出檔案的路徑

    Args:
        year: 年份
        month: 月份 (1-12)
        path: 使用者指定的資料目錄

    Returns:
        支出檔案的完整路徑
    """
    exp_dir = expenses_dir(path)
    filename = get_expense_filename(year, month)
    return exp_dir / filename


def list_expense_files(path: Optional[str] = None) -> list[Path]:
    """列出所有支出檔案

    Args:
        path: 使用者指定的資料目錄

    Returns:
        所有 expenses_YYYY_MM.csv 檔案的路徑列表，按名稱排序
    """
    exp_dir = expenses_dir(path)
    if not exp_dir.exists():
        return []

    files = list(exp_dir.glob("expenses_*.csv"))
    return sorted(files)


def validate_data_dir(path: Optional[str] = None) -> tuple[bool, str]:
    """驗證資料目錄是否可用

    Args:
        path: 使用者指定的資料目錄

    Returns:
        (是否有效, 錯誤訊息或空字串)
    """
    try:
        data_dir = resolve_data_dir(path)

        # 檢查目錄是否存在
        if not data_dir.exists():
            return False, f"資料目錄不存在: {data_dir}"

        # 檢查是否為目錄
        if not data_dir.is_dir():
            return False, f"路徑不是目錄: {data_dir}"

        # 檢查寫入權限
        test_file = data_dir / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            return False, f"無寫入權限: {data_dir}"

        return True, ""

    except Exception as e:
        return False, f"驗證失敗: {e}"
