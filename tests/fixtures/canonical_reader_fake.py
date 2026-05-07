"""
Fake CanonicalReader for testing

提供 CanonicalReader Protocol 的測試實作，用於 capture 模組的單元測試。
"""

from decimal import Decimal
from pathlib import Path
from typing import Optional


class CanonicalReaderFake:
    """
    CanonicalReader Protocol 的測試實作

    預設資料：
    - categories: ["food", "transportation", "housing", "entertainment"]
    - expense_policy: {"food": 0.3, "transportation": 0.2, "housing": 0.4, "entertainment": 0.1}
    - monthly_income: 100000
    """

    def __init__(
        self,
        categories: Optional[list[str]] = None,
        expense_policy: Optional[dict[str, Decimal]] = None,
        monthly_income: Optional[Decimal] = None,
    ):
        """
        初始化 Fake

        Args:
            categories: 自訂類別清單（可選）
            expense_policy: 自訂支出政策（可選）
            monthly_income: 自訂月收入（可選）
        """
        self._categories = categories or [
            "food",
            "transportation",
            "housing",
            "entertainment",
        ]
        self._expense_policy = expense_policy or {
            "food": Decimal("0.3"),
            "transportation": Decimal("0.2"),
            "housing": Decimal("0.4"),
            "entertainment": Decimal("0.1"),
        }
        self._monthly_income = monthly_income or Decimal("100000")

    def get_categories(self) -> list[str]:
        """取得所有支出類別"""
        return self._categories.copy()

    def get_expense_policy(self) -> dict[str, Decimal]:
        """取得支出政策比例"""
        return self._expense_policy.copy()

    def get_monthly_income(self) -> Decimal:
        """取得月收入總額"""
        return self._monthly_income

    def save_proposal(self, proposal: dict, filename: str) -> Path:
        """儲存提案（測試實作不實際寫入）"""
        return Path("/tmp") / filename

    def get_version(self) -> str:
        """取得介面版本"""
        return "1.0"
