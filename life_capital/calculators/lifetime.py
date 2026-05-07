"""終身需求計算模組

實作 PMT (Payment) 與 FV (Future Value) 公式。
支援 nominal/real 兩種計算模式。
所有計算使用 Decimal 確保精度。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from life_capital.calculators.rounding import RoundingConfig, to_decimal
from life_capital.models.assumptions import LifeAssumptions, RatesMode
from life_capital.models.targets import Target

# === 核心公式 ===


def calculate_fv(
    pv: Decimal,
    rate: Decimal,
    periods: int,
) -> Decimal:
    """計算未來價值 (Future Value)

    FV = PV × (1 + r)^n

    Args:
        pv: 現值 (Present Value)
        rate: 每期利率
        periods: 期數

    Returns:
        未來價值

    Note:
        - 當 periods = 0 時，FV = PV
        - 當 rate = 0 時，FV = PV
    """
    if periods <= 0:
        return pv

    if rate == Decimal("0"):
        return pv

    # FV = PV × (1 + r)^n
    growth_factor = (Decimal("1") + rate) ** periods
    return pv * growth_factor


def calculate_pv(
    fv: Decimal,
    rate: Decimal,
    periods: int,
) -> Decimal:
    """計算現值 (Present Value)

    PV = FV / (1 + r)^n

    Args:
        fv: 未來價值
        rate: 每期利率
        periods: 期數

    Returns:
        現值
    """
    if periods <= 0:
        return fv

    if rate == Decimal("0"):
        return fv

    growth_factor = (Decimal("1") + rate) ** periods
    return fv / growth_factor


def calculate_pmt(
    fv: Decimal,
    rate: Decimal,
    periods: int,
) -> Decimal:
    """計算每期付款金額 (Payment)

    標準 PMT 公式（期末付款，求達到 FV 需要的定期儲蓄）：
    PMT = FV × r / ((1 + r)^n - 1)

    Args:
        fv: 目標未來價值
        rate: 每期利率（月利率 = 年利率 / 12）
        periods: 期數（月數）

    Returns:
        每期需儲蓄金額

    Special cases:
        - rate = 0: PMT = FV / periods
        - periods = 0: 無法計算，回傳 FV（需立即準備）
        - rate < 0: 正常計算（但會發出警告）
    """
    if periods <= 0:
        # 無準備期，需立即準備全額
        return fv

    if rate == Decimal("0"):
        # 零利率：簡單除法
        return fv / Decimal(periods)

    # 標準 PMT 公式
    # PMT = FV × r / ((1 + r)^n - 1)
    growth_factor = (Decimal("1") + rate) ** periods
    denominator = growth_factor - Decimal("1")

    if denominator == Decimal("0"):
        # 理論上不會發生（除非 rate 極小且 periods 極小）
        return fv / Decimal(periods)

    return fv * rate / denominator


def calculate_pmt_for_pv(
    pv: Decimal,
    rate: Decimal,
    periods: int,
) -> Decimal:
    """計算達到現值所需的每期付款（貸款場景）

    PMT = PV × r × (1 + r)^n / ((1 + r)^n - 1)

    Args:
        pv: 貸款本金（現值）
        rate: 每期利率
        periods: 期數

    Returns:
        每期還款金額
    """
    if periods <= 0:
        return pv

    if rate == Decimal("0"):
        return pv / Decimal(periods)

    growth_factor = (Decimal("1") + rate) ** periods
    numerator = pv * rate * growth_factor
    denominator = growth_factor - Decimal("1")

    if denominator == Decimal("0"):
        return pv / Decimal(periods)

    return numerator / denominator


# === 目標計算 ===


@dataclass
class TargetCalculation:
    """單一目標的計算結果"""

    target: Target
    years_to_goal: int
    months_to_goal: int

    # 金額（base_year 幣值）
    base_amount: Decimal

    # 未來價值（考慮通膨後，僅 nominal 模式有意義）
    future_value: Decimal

    # 每月需儲蓄金額
    monthly_payment: Decimal

    # 計算模式
    mode: RatesMode

    # 使用的報酬率
    investment_return: Decimal

    def __post_init__(self):
        """驗證計算結果"""
        if self.monthly_payment < Decimal("0"):
            raise ValueError(f"monthly_payment 不能為負數: {self.monthly_payment}")


@dataclass
class LifetimeCalculation:
    """終身需求計算結果"""

    # 計算參數
    mode: RatesMode
    base_year: int
    inflation_rate: Decimal
    investment_return: Decimal

    # 各目標計算結果
    target_results: list[TargetCalculation]

    # 彙總
    total_base_amount: Decimal  # 目標總額（base_year 幣值）
    total_future_value: Decimal  # 目標總額（未來幣值，nominal 模式）
    total_monthly_payment: Decimal  # 每月需儲蓄總額

    def get_by_priority(self, priority: str) -> list[TargetCalculation]:
        """依優先級篩選結果"""
        return [r for r in self.target_results if r.target.priority.value == priority]


def calculate_target(
    target: Target,
    base_year: int,
    inflation_rate: Decimal,
    investment_return: Decimal,
    mode: RatesMode,
) -> TargetCalculation:
    """計算單一目標的儲蓄需求

    Args:
        target: 目標資料
        base_year: 基準年
        inflation_rate: 年通膨率
        investment_return: 年投資報酬率（已根據 mode 選擇 nominal/real）
        mode: 計算模式

    Returns:
        TargetCalculation 計算結果
    """
    # 計算期數
    years_to_goal = target.target_year - base_year
    months_to_goal = years_to_goal * 12

    # 轉換為 Decimal
    base_amount = to_decimal(target.amount)

    # 計算未來價值
    if mode == RatesMode.NOMINAL:
        # 名目模式：通膨調整至目標年
        future_value = calculate_fv(base_amount, inflation_rate, years_to_goal)
    else:
        # 實質模式：不調整通膨
        future_value = base_amount

    # 計算每月儲蓄（使用月利率）
    monthly_rate = investment_return / Decimal("12")
    monthly_payment = calculate_pmt(future_value, monthly_rate, months_to_goal)

    return TargetCalculation(
        target=target,
        years_to_goal=years_to_goal,
        months_to_goal=months_to_goal,
        base_amount=base_amount,
        future_value=future_value,
        monthly_payment=monthly_payment,
        mode=mode,
        investment_return=investment_return,
    )


def calculate_lifetime_needs(
    targets: list[Target],
    assumptions: LifeAssumptions,
    rounding_config: Optional[RoundingConfig] = None,
) -> LifetimeCalculation:
    """計算終身財務需求

    Args:
        targets: 目標列表
        assumptions: 生活假設
        rounding_config: Rounding 設定（可選）

    Returns:
        LifetimeCalculation 完整計算結果
    """
    mode = assumptions.rates.mode
    base_year = assumptions.metadata.base_year
    inflation_rate = to_decimal(assumptions.rates.annual_inflation)

    # 根據 mode 選擇報酬率
    if mode == RatesMode.NOMINAL:
        investment_return = to_decimal(assumptions.rates.nominal_investment_return or 0)
    else:
        investment_return = to_decimal(assumptions.rates.real_investment_return or 0)

    # 計算各目標
    target_results: list[TargetCalculation] = []
    for target in targets:
        result = calculate_target(
            target=target,
            base_year=base_year,
            inflation_rate=inflation_rate,
            investment_return=investment_return,
            mode=mode,
        )
        target_results.append(result)

    # 彙總
    total_base = sum((r.base_amount for r in target_results), Decimal("0"))
    total_fv = sum((r.future_value for r in target_results), Decimal("0"))
    total_pmt = sum((r.monthly_payment for r in target_results), Decimal("0"))

    # 套用 rounding（如果有設定）
    if rounding_config:
        total_base = rounding_config.quantize(total_base)
        total_fv = rounding_config.quantize(total_fv)
        total_pmt = rounding_config.quantize(total_pmt)

    return LifetimeCalculation(
        mode=mode,
        base_year=base_year,
        inflation_rate=inflation_rate,
        investment_return=investment_return,
        target_results=target_results,
        total_base_amount=total_base,
        total_future_value=total_fv,
        total_monthly_payment=total_pmt,
    )


# === 輔助函式 ===


def years_between(start_year: int, end_year: int) -> int:
    """計算兩年份之間的年數"""
    return max(0, end_year - start_year)


def months_between(start_year: int, end_year: int) -> int:
    """計算兩年份之間的月數"""
    return years_between(start_year, end_year) * 12


def annual_to_monthly_rate(annual_rate: Decimal) -> Decimal:
    """將年利率轉換為月利率（簡單除法）

    Note: 這是簡化計算。精確轉換應為 (1 + r_annual)^(1/12) - 1
    """
    return annual_rate / Decimal("12")


def monthly_to_annual_rate(monthly_rate: Decimal) -> Decimal:
    """將月利率轉換為年利率（簡單乘法）"""
    return monthly_rate * Decimal("12")
