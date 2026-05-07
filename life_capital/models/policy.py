"""支出政策資料模型

定義 expense_policy.yaml 的資料結構。
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from life_capital.models.base import VersionedModel


class RatioBase(str, Enum):
    """占比基準"""

    INCOME = "income"
    EXPENSE = "expense"


class UncategorizedHandling(str, Enum):
    """未分類處理方式"""

    WARN = "warn"
    ERROR = "error"
    IGNORE = "ignore"


class PolicyMetadata(BaseModel):
    """政策元資料"""

    ratio_base: RatioBase = RatioBase.INCOME
    allow_partial: bool = False  # 是否允許總和 < 100%


class CategoryGroup(BaseModel):
    """類別群組

    包含多個支出類別及其占比。
    """

    categories: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ratios(self) -> "CategoryGroup":
        for name, ratio in self.categories.items():
            if ratio < 0 or ratio > 1:
                raise ValueError(f"類別 '{name}' 的占比 ({ratio}) 必須在 0-1 之間")
        return self


class Flexibility(BaseModel):
    """彈性設定

    定義各群組的容忍度。
    """

    tolerances: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_tolerances(self) -> "Flexibility":
        for name, tolerance in self.tolerances.items():
            if tolerance < 0 or tolerance > 0.3:
                raise ValueError(f"群組 '{name}' 的容忍度 ({tolerance}) 必須在 0-0.3 之間")
        return self


class ExpensePolicy(VersionedModel):
    """支出政策主模型

    對應 expense_policy.yaml
    """

    metadata: PolicyMetadata = Field(default_factory=PolicyMetadata)
    categories: dict[str, dict[str, float]] = Field(default_factory=dict)
    flexibility: dict[str, float] = Field(default_factory=dict)
    uncategorized_handling: UncategorizedHandling = UncategorizedHandling.WARN

    @model_validator(mode="after")
    def validate_total_ratio(self) -> "ExpensePolicy":
        """驗證所有比例總和"""
        total = 0.0
        for group_name, group_categories in self.categories.items():
            for category_name, ratio in group_categories.items():
                if ratio < 0 or ratio > 1:
                    raise ValueError(
                        f"類別 '{group_name}.{category_name}' 的占比 ({ratio}) 必須在 0-1 之間"
                    )
                total += ratio

        if not self.metadata.allow_partial:
            if abs(total - 1.0) > 0.001:  # 容許小誤差
                raise ValueError(f"所有類別占比總和 ({total:.4f}) 必須等於 1.0")

        return self

    def get_all_categories(self) -> set[str]:
        """取得所有類別名稱"""
        all_cats = set()
        for group_categories in self.categories.values():
            all_cats.update(group_categories.keys())
        return all_cats

    def get_category_ratio(self, category: str) -> Optional[float]:
        """取得指定類別的占比"""
        for group_categories in self.categories.values():
            if category in group_categories:
                return group_categories[category]
        return None

    def get_group_for_category(self, category: str) -> Optional[str]:
        """取得類別所屬的群組名稱"""
        for group_name, group_categories in self.categories.items():
            if category in group_categories:
                return group_name
        return None

    def get_tolerance(self, group: str) -> float:
        """取得群組的容忍度，預設 0.05"""
        return self.flexibility.get(group, 0.05)
