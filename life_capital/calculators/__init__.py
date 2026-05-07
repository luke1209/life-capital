"""計算邏輯 - 全部使用 Decimal

注意：projection 模組因循環導入問題，需直接導入：
    from life_capital.calculators.projection import calculate_projection
"""

from life_capital.calculators.lifetime import (
    LifetimeCalculation,
    TargetCalculation,
    annual_to_monthly_rate,
    calculate_fv,
    calculate_lifetime_needs,
    calculate_pmt,
    calculate_pmt_for_pv,
    calculate_pv,
    calculate_target,
    monthly_to_annual_rate,
    months_between,
    years_between,
)
from life_capital.calculators.rounding import (
    RoundingConfig,
    ensure_decimal,
    quantize_amount,
    to_decimal,
)

__all__ = [
    # Rounding
    "RoundingConfig",
    "to_decimal",
    "ensure_decimal",
    "quantize_amount",
    # Lifetime calculations
    "calculate_fv",
    "calculate_pv",
    "calculate_pmt",
    "calculate_pmt_for_pv",
    "calculate_target",
    "calculate_lifetime_needs",
    "TargetCalculation",
    "LifetimeCalculation",
    # Utilities
    "years_between",
    "months_between",
    "annual_to_monthly_rate",
    "monthly_to_annual_rate",
    # Note: projection 模組需直接導入（循環導入限制）
]
