"""支出分析計算

按類別統計支出，並依 expense_policy.yaml 比對占比。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from life_capital.models.expense import MonthlyExpenses
from life_capital.models.income import MonthlyIncome
from life_capital.models.policy import ExpensePolicy, RatioBase


@dataclass(frozen=True)
class BudgetCategoryResult:
    category: str
    group: str | None
    amount: Decimal
    actual_ratio: Decimal | None
    target_ratio: Decimal | None
    delta_ratio: Decimal | None
    status: str  # ok/over/under/unknown


@dataclass(frozen=True)
class BudgetCheckResult:
    base: RatioBase
    base_amount: Decimal
    total_expenses: Decimal
    categories: List[BudgetCategoryResult]


def _decimal_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator


def check_budget(
    *,
    expenses: MonthlyExpenses,
    policy: ExpensePolicy,
    income: MonthlyIncome | None = None,
) -> BudgetCheckResult:
    """產出支出占比檢查結果。"""
    total_expenses = expenses.total()

    if policy.metadata.ratio_base == RatioBase.INCOME:
        if income is None:
            raise ValueError("policy.metadata.ratio_base=income 需要提供 monthly_income.yaml")
        base_amount = Decimal(str(income.total_monthly()))
    else:
        base_amount = total_expenses

    by_category = expenses.by_category()
    allowed = policy.get_all_categories()

    results: list[BudgetCategoryResult] = []
    for category, amount in sorted(by_category.items(), key=lambda kv: kv[0]):
        group = policy.get_group_for_category(category)
        target_ratio_float = policy.get_category_ratio(category)

        actual_ratio = _decimal_ratio(amount, base_amount)
        target_ratio = (
            Decimal(str(target_ratio_float)) if target_ratio_float is not None else None
        )
        delta_ratio = (
            (actual_ratio - target_ratio)
            if (actual_ratio is not None and target_ratio is not None)
            else None
        )

        if category not in allowed or target_ratio is None or group is None:
            results.append(
                BudgetCategoryResult(
                    category=category,
                    group=group,
                    amount=amount,
                    actual_ratio=actual_ratio,
                    target_ratio=target_ratio,
                    delta_ratio=delta_ratio,
                    status="unknown",
                )
            )
            continue

        tolerance = Decimal(str(policy.get_tolerance(group)))
        lower = target_ratio - tolerance
        upper = target_ratio + tolerance

        status = "ok"
        if actual_ratio is None:
            status = "unknown"
        elif actual_ratio > upper:
            status = "over"
        elif actual_ratio < lower:
            status = "under"

        results.append(
            BudgetCategoryResult(
                category=category,
                group=group,
                amount=amount,
                actual_ratio=actual_ratio,
                target_ratio=target_ratio,
                delta_ratio=delta_ratio,
                status=status,
            )
        )

    return BudgetCheckResult(
        base=policy.metadata.ratio_base,
        base_amount=base_amount,
        total_expenses=total_expenses,
        categories=results,
    )

