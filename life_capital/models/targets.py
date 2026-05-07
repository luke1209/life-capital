"""終身目標資料模型

定義 lifetime_targets.yaml 的資料結構。
MVP 只支援一次性目標 (lump-sum)。
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from life_capital.models.base import VersionedModel


class Priority(str, Enum):
    """目標優先級"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TargetCategory(str, Enum):
    """目標類別"""

    HOUSING = "housing"
    CHILDREN = "children"
    RETIREMENT = "retirement"
    TRANSPORTATION = "transportation"
    EDUCATION = "education"
    HEALTH = "health"
    TRAVEL = "travel"
    OTHER = "other"


class Target(BaseModel):
    """單一目標

    amount 永遠是 base_year 幣值。
    """

    name: str = Field(min_length=1)
    category: Optional[TargetCategory] = None
    priority: Priority = Priority.MEDIUM
    amount: float = Field(gt=0)  # 必須為正數，以 base_year 幣值計算
    target_year: int = Field(ge=2000)
    notes: Optional[str] = None

    @field_validator("target_year")
    @classmethod
    def validate_target_year_range(cls, v: int) -> int:
        current_year = datetime.now().year
        if v < current_year:
            raise ValueError(f"target_year ({v}) 不能小於當前年份 ({current_year})")
        if v > current_year + 100:
            raise ValueError(f"target_year ({v}) 超出合理範圍")
        return v


class LifetimeTargets(VersionedModel):
    """終身目標主模型

    對應 lifetime_targets.yaml
    """

    targets: list[Target] = Field(default_factory=list)

    def validate_against_assumptions(
        self,
        base_year: int,
        expected_lifespan: int,
        current_age: int,
    ) -> list[str]:
        """根據 assumptions 驗證目標

        Args:
            base_year: 基準年
            expected_lifespan: 預期壽命
            current_age: 當前年齡

        Returns:
            錯誤訊息列表
        """
        errors = []
        max_year = base_year + (expected_lifespan - current_age)

        for i, target in enumerate(self.targets):
            # 驗證 target_year > base_year (至少 1 年準備期)
            if target.target_year <= base_year:
                errors.append(
                    f"targets[{i}] ({target.name}): target_year ({target.target_year}) "
                    f"必須大於 base_year ({base_year})，至少需要 1 年準備期"
                )

            # 驗證不超過預期壽命
            if target.target_year > max_year:
                errors.append(
                    f"targets[{i}] ({target.name}): target_year ({target.target_year}) "
                    f"超過預期壽命年份 ({max_year})"
                )

        return errors

    def get_by_priority(self, priority: Priority) -> list[Target]:
        """依優先級篩選目標"""
        return [t for t in self.targets if t.priority == priority]

    def get_by_category(self, category: TargetCategory) -> list[Target]:
        """依類別篩選目標"""
        return [t for t in self.targets if t.category == category]

    def total_amount(self) -> float:
        """計算目標總額（base_year 幣值）"""
        return sum(t.amount for t in self.targets)
