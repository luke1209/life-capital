"""支出記錄資料模型

定義 CSV 支出記錄的資料結構。
"""

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from life_capital.models.base import VersionedModel

# 支付者類型定義
Payer = Literal["person_a", "person_b", "shared"]
VALID_PAYERS: set[str] = {"person_a", "person_b", "shared"}


class ExpenseRecord(BaseModel):
    """單筆支出記錄

    對應 expenses_YYYY_MM.csv 的單行資料。
    amount 允許負數代表退款/回饋。
    """

    date: date
    amount: Decimal  # 使用 Decimal 保持精度
    category: str = Field(min_length=1)
    payer: Payer = Field(default="shared")  # 支付者：person_a, person_b, shared
    note: Optional[str] = None
    merchant: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """驗證金額非零"""
        if v == 0:
            raise ValueError("amount 不能為 0")
        return v

    def is_refund(self) -> bool:
        """判斷是否為退款/回饋"""
        return self.amount < 0

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> "ExpenseRecord":
        """從 CSV 行建立記錄

        Args:
            row: CSV 行資料（dict 格式）

        Returns:
            ExpenseRecord 實例
        """
        # 解析 payer，預設為 shared（向後相容）
        payer_raw = row.get("payer", "shared").strip().lower()
        payer = payer_raw if payer_raw in VALID_PAYERS else "shared"

        return cls(
            date=date.fromisoformat(row["date"]),
            amount=Decimal(row["amount"].replace(",", "").replace("$", "")),
            category=row["category"],
            payer=payer,
            note=row.get("note") or None,
            merchant=row.get("merchant") or None,
        )

    def to_csv_row(self) -> dict[str, str]:
        """轉換為 CSV 行格式"""
        return {
            "date": self.date.isoformat(),
            "amount": str(self.amount),
            "category": self.category,
            "payer": self.payer,
            "note": self.note or "",
            "merchant": self.merchant or "",
        }


class MonthlyExpenses(VersionedModel):
    """月度支出集合

    繼承 VersionedModel 以包含 schema_version 欄位。
    """

    year: int
    month: int
    records: list[ExpenseRecord] = Field(default_factory=list)

    def total(self) -> Decimal:
        """計算月度總支出（扣除退款）"""
        return sum((r.amount for r in self.records), Decimal("0"))

    def by_category(self) -> dict[str, Decimal]:
        """依類別統計支出"""
        result: dict[str, Decimal] = {}
        for record in self.records:
            if record.category not in result:
                result[record.category] = Decimal("0")
            result[record.category] += record.amount
        return result

    def by_payer(self) -> dict[str, Decimal]:
        """依支付者統計支出"""
        result: dict[str, Decimal] = {}
        for record in self.records:
            if record.payer not in result:
                result[record.payer] = Decimal("0")
            result[record.payer] += record.amount
        return result

    def expense_count(self) -> int:
        """支出筆數（不含退款）"""
        return sum(1 for r in self.records if not r.is_refund())

    def refund_count(self) -> int:
        """退款筆數"""
        return sum(1 for r in self.records if r.is_refund())
