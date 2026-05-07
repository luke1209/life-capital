"""資料模型 - Pydantic 模型 = Schema 唯一真相"""

from life_capital.models.assumptions import (
    Basic,
    Calculation,
    Child,
    Currency,
    Family,
    LifeAssumptions,
    Member,
    Metadata,
    Rates,
    RatesMode,
    RoundingMethod,
    RoundingStage,
)
from life_capital.models.base import VersionedModel
from life_capital.models.common import ALLOWED_MEMBER_IDS, DEFAULT_PRIMARY_MEMBER
from life_capital.models.expense import ExpenseRecord, MonthlyExpenses
from life_capital.models.income import IncomeSource, MonthlyIncome
from life_capital.models.policy import (
    ExpensePolicy,
    PolicyMetadata,
    RatioBase,
    UncategorizedHandling,
)
from life_capital.models.targets import LifetimeTargets, Priority, Target, TargetCategory

__all__ = [
    # Base
    "VersionedModel",
    # Assumptions
    "LifeAssumptions",
    "Metadata",
    "Basic",
    "Member",
    "Rates",
    "RatesMode",
    "Calculation",
    "RoundingMethod",
    "RoundingStage",
    "Family",
    "Child",
    "Currency",
    # Common
    "ALLOWED_MEMBER_IDS",
    "DEFAULT_PRIMARY_MEMBER",
    # Targets
    "LifetimeTargets",
    "Target",
    "Priority",
    "TargetCategory",
    # Income
    "MonthlyIncome",
    "IncomeSource",
    # Policy
    "ExpensePolicy",
    "PolicyMetadata",
    "RatioBase",
    "UncategorizedHandling",
    # Expense
    "ExpenseRecord",
    "MonthlyExpenses",
]
