"""CanonicalReader Protocol 的具體實作

提供符合 CanonicalReader Protocol 的實作類別。
"""

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from life_capital.interfaces.canonical_reader import INTERFACE_VERSION

if TYPE_CHECKING:
    from life_capital.interfaces.canonical_reader import CanonicalReader


class CanonicalReaderImpl:
    """CanonicalReader Protocol 的具體實作

    此類別實作 CanonicalReader Protocol，提供對 canonical 資料的讀取功能。

    Parameters
    ----------
    data_path : Path
        資料目錄路徑（如 ~/.life-capital）

    Examples
    --------
    >>> reader = CanonicalReaderImpl(Path.home() / ".life-capital")
    >>> categories = reader.get_categories()
    >>> policy = reader.get_expense_policy()
    """

    def __init__(self, data_path: Path) -> None:
        self._data_path = Path(data_path)
        self._policy_cache: Optional[Dict[str, Decimal]] = None
        self._categories_cache: Optional[List[str]] = None

    def get_categories(self) -> List[str]:
        """取得所有支出類別"""
        if self._categories_cache is not None:
            return self._categories_cache

        from life_capital.io.registry import POLICY_FILE
        from life_capital.io.yaml_handler import load_model
        from life_capital.models.policy import ExpensePolicy

        policy_path = self._data_path / POLICY_FILE
        if not policy_path.exists():
            return []

        policy = load_model(policy_path, ExpensePolicy)
        self._categories_cache = list(policy.get_all_categories())
        return self._categories_cache

    def get_expense_policy(self) -> Dict[str, Decimal]:
        """取得支出政策比例"""
        if self._policy_cache is not None:
            return self._policy_cache

        from life_capital.io.registry import POLICY_FILE
        from life_capital.io.yaml_handler import load_model
        from life_capital.models.policy import ExpensePolicy

        policy_path = self._data_path / POLICY_FILE
        if not policy_path.exists():
            return {}

        policy = load_model(policy_path, ExpensePolicy)

        result: Dict[str, Decimal] = {}
        for group_categories in policy.categories.values():
            for category, ratio in group_categories.items():
                result[category] = Decimal(str(ratio))

        self._policy_cache = result
        return result

    def get_monthly_income(self) -> Decimal:
        """取得月收入總額"""
        from life_capital.io.registry import INCOME_FILE
        from life_capital.io.yaml_handler import load_model
        from life_capital.models.income import MonthlyIncome

        income_path = self._data_path / INCOME_FILE
        if not income_path.exists():
            return Decimal("0")

        income = load_model(income_path, MonthlyIncome)

        # 計算月收入總額（僅計算 monthly 頻率的來源）
        total = Decimal("0")
        for source in income.sources:
            if source.frequency.value == "monthly":
                total += Decimal(str(source.amount))

        return total

    def save_proposal(self, proposal: dict, filename: str) -> Path:
        """儲存提案至 proposals/ 目錄"""
        from life_capital.io.registry import PROPOSALS_PENDING_DIR
        from life_capital.io.yaml_handler import save_yaml

        proposals_dir = self._data_path / PROPOSALS_PENDING_DIR
        proposals_dir.mkdir(parents=True, exist_ok=True)

        proposal_path = proposals_dir / filename
        save_yaml(proposal_path, proposal)
        return proposal_path

    def get_version(self) -> str:
        """取得介面版本"""
        return INTERFACE_VERSION


def get_canonical_reader(data_path: Path) -> "CanonicalReader":
    """工廠函式：建立 CanonicalReader 實例

    Parameters
    ----------
    data_path : Path
        資料目錄路徑

    Returns
    -------
    CanonicalReader
        符合 Protocol 的實作
    """
    return CanonicalReaderImpl(data_path)
