"""月收入資料模型

定義 monthly_income.yaml 的資料結構。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from life_capital.models.base import VersionedModel

# 收入擁有者類型定義（與 expense.py 的 Payer 保持一致）
Owner = Literal["person_a", "person_b", "shared"]


class IncomeSource(BaseModel):
    """收入來源"""

    name: str = Field(min_length=1)
    amount: float = Field(ge=0)  # 允許 0（如暫時無收入）
    frequency: str = Field(default="monthly")  # monthly, yearly, one-time
    owner: Owner = Field(default="shared")  # 收入擁有者：person_a, person_b, shared
    notes: Optional[str] = None


class MonthlyIncome(VersionedModel):
    """月收入主模型

    對應 monthly_income.yaml
    """

    sources: list[IncomeSource] = Field(default_factory=list)

    def total_monthly(self) -> float:
        """計算月收入總額"""
        total = 0.0
        for source in self.sources:
            if source.frequency == "monthly":
                total += source.amount
            elif source.frequency == "yearly":
                total += source.amount / 12
        return total

    def total_yearly(self) -> float:
        """計算年收入總額"""
        total = 0.0
        for source in self.sources:
            if source.frequency == "monthly":
                total += source.amount * 12
            elif source.frequency == "yearly":
                total += source.amount
        return total

    def by_owner(self) -> dict[str, float]:
        """依擁有者統計月收入"""
        result: dict[str, float] = {}
        for source in self.sources:
            if source.owner not in result:
                result[source.owner] = 0.0
            if source.frequency == "monthly":
                result[source.owner] += source.amount
            elif source.frequency == "yearly":
                result[source.owner] += source.amount / 12
        return result
