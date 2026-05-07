"""資料取得模組

提供從 canonical 目錄取得歷史資料的功能，
用於情境分析與預測計算的輸入準備。
"""

import re
from typing import Optional

from life_capital.io.csv_handler import load_monthly_expenses
from life_capital.io.registry import (
    CANONICAL_EXPENSES_DIR,
    DEFAULT_HISTORICAL_MONTHS,
)
from life_capital.io.yaml_handler import load_model
from life_capital.models.expense import MonthlyExpenses
from life_capital.models.income import MonthlyIncome
from life_capital.utils.path_resolver import resolve_data_dir


def parse_expense_filename(filename: str) -> Optional[tuple[int, int]]:
    """解析支出檔名中的年月

    Args:
        filename: 檔名（如 expenses_2024_12.csv）

    Returns:
        (year, month) 或 None（無法解析）
    """
    match = re.match(r"expenses_(\d{4})_(\d{2})\.csv$", filename)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def list_expense_months(data_path: Optional[str] = None) -> list[tuple[int, int]]:
    """列出所有可用的支出月份

    Args:
        data_path: 資料目錄路徑

    Returns:
        [(year, month), ...] 按時間排序
    """
    data_dir = resolve_data_dir(data_path)
    expenses_dir = data_dir / CANONICAL_EXPENSES_DIR

    if not expenses_dir.exists():
        return []

    months = []
    for f in expenses_dir.glob("expenses_*.csv"):
        parsed = parse_expense_filename(f.name)
        if parsed:
            months.append(parsed)

    return sorted(months)


def fetch_historical_expenses(
    data_path: Optional[str] = None,
    months_back: int = DEFAULT_HISTORICAL_MONTHS,
    end_year: Optional[int] = None,
    end_month: Optional[int] = None,
) -> list[MonthlyExpenses]:
    """取得歷史支出資料

    從 canonical/expenses/ 目錄載入指定範圍的歷史支出資料。

    Args:
        data_path: 資料目錄路徑
        months_back: 往回取多少個月（預設 6 個月）
        end_year: 結束年份（預設為最新資料）
        end_month: 結束月份（預設為最新資料）

    Returns:
        MonthlyExpenses 列表，按時間升序排列

    Note:
        - 若指定範圍內沒有資料，回傳空列表
        - 若檔案載入失敗，該月份會被跳過（不中斷整體載入）
    """
    data_dir = resolve_data_dir(data_path)
    expenses_dir = data_dir / CANONICAL_EXPENSES_DIR

    if not expenses_dir.exists():
        return []

    # 列出所有可用月份
    available = list_expense_months(data_path)
    if not available:
        return []

    # 決定結束月份
    if end_year is None or end_month is None:
        end_year, end_month = available[-1]  # 使用最新資料

    # 計算起始月份
    start_year, start_month = _subtract_months(end_year, end_month, months_back - 1)

    # 篩選在範圍內的月份
    start_total = start_year * 12 + start_month
    end_total = end_year * 12 + end_month

    target_months = [
        (y, m)
        for y, m in available
        if start_total <= y * 12 + m <= end_total
    ]

    # 載入每個月的資料
    result = []
    for year, month in target_months:
        filepath = expenses_dir / f"expenses_{year}_{month:02d}.csv"
        if filepath.exists():
            try:
                expenses, _ = load_monthly_expenses(filepath, year, month)
                result.append(expenses)
            except Exception:
                # 載入失敗，跳過該月份
                pass

    return result


def fetch_expense_range(
    data_path: Optional[str] = None,
    start_year: Optional[int] = None,
    start_month: Optional[int] = None,
    end_year: Optional[int] = None,
    end_month: Optional[int] = None,
) -> list[MonthlyExpenses]:
    """取得指定範圍的支出資料

    Args:
        data_path: 資料目錄路徑
        start_year: 起始年份（None 表示從最早資料開始）
        start_month: 起始月份（None 表示從最早資料開始）
        end_year: 結束年份（None 表示到最新資料為止）
        end_month: 結束月份（None 表示到最新資料為止）

    Returns:
        MonthlyExpenses 列表，按時間升序排列
    """
    available = list_expense_months(data_path)
    if not available:
        return []

    # 設定預設邊界
    if start_year is None or start_month is None:
        start_year, start_month = available[0]

    if end_year is None or end_month is None:
        end_year, end_month = available[-1]

    # 計算回推月數
    start_total = start_year * 12 + start_month
    end_total = end_year * 12 + end_month
    months_count = end_total - start_total + 1

    return fetch_historical_expenses(
        data_path=data_path,
        months_back=months_count,
        end_year=end_year,
        end_month=end_month,
    )


def fetch_latest_income(
    data_path: Optional[str] = None,
) -> Optional[MonthlyIncome]:
    """取得月收入資料

    從 canonical/monthly_income.yaml 載入收入資料。

    Args:
        data_path: 資料目錄路徑

    Returns:
        MonthlyIncome 或 None（檔案不存在或載入失敗）
    """
    data_dir = resolve_data_dir(data_path)
    income_file = data_dir / "canonical" / "monthly_income.yaml"

    if not income_file.exists():
        # 嘗試舊路徑（相容性）
        income_file = data_dir / "monthly_income.yaml"
        if not income_file.exists():
            return None

    try:
        return load_model(income_file, MonthlyIncome)
    except Exception:
        return None


def _subtract_months(year: int, month: int, count: int) -> tuple[int, int]:
    """計算往回 N 個月的年月

    Args:
        year: 起始年份
        month: 起始月份 (1-12)
        count: 要減去的月數

    Returns:
        (year, month) 結果年月
    """
    total = year * 12 + month - 1 - count  # -1 是因為 month 是 1-based
    return total // 12, total % 12 + 1
