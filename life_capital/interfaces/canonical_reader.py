"""Canonical 資料讀取介面

定義 Phase 4 (Capture) 及後續模組唯一可依賴的介面。

版本: 1.0
Breaking changes 需要 major version bump。
參見: docs/contracts/interface_policy.md
"""

from decimal import Decimal
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class CanonicalReader(Protocol):
    """Phase 4+ 唯一可依賴的介面

    此 Protocol 定義了 capture/ 模組與核心系統的契約。
    capture/ 不可直接 import models/，只能透過此介面存取資料。

    Version: 1.0
    Breaking changes require major version bump.

    變更規則：
    - Breaking: 刪除方法、改變方法簽名、改變返回型別
    - Compatible: 新增方法（需提供 default）
    - Internal: 實作細節變更

    Examples
    --------
    >>> reader = get_canonical_reader(data_path)
    >>> categories = reader.get_categories()
    >>> policy = reader.get_expense_policy()
    """

    def get_categories(self) -> list[str]:
        """取得所有支出類別

        Returns
        -------
        list[str]
            支出類別名稱列表，如 ["housing", "food", "transportation"]
        """
        ...

    def get_expense_policy(self) -> dict[str, Decimal]:
        """取得支出政策比例

        Returns
        -------
        dict[str, Decimal]
            類別名稱對應的比例，如 {"housing": Decimal("0.30"), "food": Decimal("0.15")}
        """
        ...

    def get_monthly_income(self) -> Decimal:
        """取得月收入總額

        Returns
        -------
        Decimal
            月收入總額（TWD）
        """
        ...

    def save_proposal(self, proposal: dict, filename: str) -> Path:
        """儲存提案至 proposals/ 目錄

        Parameters
        ----------
        proposal : dict
            提案內容，將被序列化為 YAML
        filename : str
            檔案名稱（不含路徑，需含 .yaml 副檔名）

        Returns
        -------
        Path
            儲存的檔案路徑
        """
        ...

    # V1.0 新增方法（Compatible change，提供 default）
    def get_version(self) -> str:
        """取得介面版本

        Returns
        -------
        str
            版本號，如 "1.0"
        """
        return "1.0"  # default implementation for backwards compatibility


# 介面版本常數
INTERFACE_VERSION = "1.0"
