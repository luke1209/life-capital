"""現金流預測計算模組

Phase 2 核心計算邏輯，負責月度現金流預測。

遵循 V6 Final 契約：
- Contract 3: input_hash = SHA-256(calc_version + sources_digest)
- Contract 4: Internal 2 digits, output 0 digits, ROUND_HALF_UP
"""

import hashlib
import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from life_capital.io.registry import CALC_VERSION
from life_capital.models.expense import MonthlyExpenses
from life_capital.models.scenario import (
    MonthlyProjection,
    OneTimeExpense,
    ProjectionInput,
    ProjectionResult,
)

# =============================================================================
# V6 Final Contract 4: PrecisionConfig
# =============================================================================

class PrecisionConfig:
    """精度配置（V6 Final Contract 4）

    - 內部計算: 2 位小數
    - 輸出結果: 0 位小數（整數元）
    - 捨入方法: ROUND_HALF_UP（四捨五入）
    """

    INTERNAL_SCALE = 2  # 內部計算精度
    OUTPUT_SCALE = 0    # 輸出精度
    ROUNDING = ROUND_HALF_UP

    _INTERNAL_EXP = Decimal("0.01")
    _OUTPUT_EXP = Decimal("1")

    @classmethod
    def quantize_internal(cls, value: Decimal) -> Decimal:
        """內部計算量化（2 位小數）"""
        return value.quantize(cls._INTERNAL_EXP, rounding=cls.ROUNDING)

    @classmethod
    def quantize_output(cls, value: Decimal) -> Decimal:
        """輸出量化（整數元）"""
        return value.quantize(cls._OUTPUT_EXP, rounding=cls.ROUNDING)


def quantize_internal(value: Decimal) -> Decimal:
    """內部計算量化（便捷函式）"""
    return PrecisionConfig.quantize_internal(value)


def quantize_output(value: Decimal) -> Decimal:
    """輸出量化（便捷函式）"""
    return PrecisionConfig.quantize_output(value)


# =============================================================================
# V6 Final Contract 3: Input Hash (Determinism)
# =============================================================================

def compute_input_hash(inputs: ProjectionInput, calc_version: str = CALC_VERSION) -> str:
    """計算輸入資料的確定性 hash

    V6 Final Contract 3: input_hash = SHA-256(calc_version + sources_digest)

    確保：
    - 相同輸入產生相同 hash
    - calc_version 變更會產生不同 hash
    - 使用 sort_keys=True 確保 JSON 序列化一致性

    Args:
        inputs: 預測輸入參數
        calc_version: 計算邏輯版本

    Returns:
        SHA-256 hash（hex 格式）
    """
    # 將 dataclass 轉為可序列化的 dict
    input_dict = _serialize_projection_input(inputs)

    # 組合 calc_version 和輸入資料
    hash_content = {
        "calc_version": calc_version,
        "inputs": input_dict,
    }

    # 確定性序列化：sort_keys=True, separators 固定
    json_str = json.dumps(
        hash_content,
        sort_keys=True,
        separators=(",", ":"),
        default=str,  # 處理 Decimal, date 等類型
    )

    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def _serialize_projection_input(inputs: ProjectionInput) -> dict:
    """序列化 ProjectionInput 為可 hash 的 dict"""
    result = {
        "start_year": inputs.start_year,
        "start_month": inputs.start_month,
        "initial_savings": str(inputs.initial_savings),
        "projection_months": inputs.projection_months,
        "expense_estimation_strategy": inputs.expense_estimation_strategy,
    }

    # 處理 assumptions（可能是 dataclass 或 dict）
    if inputs.assumptions is not None:
        if hasattr(inputs.assumptions, "model_dump"):
            result["assumptions"] = inputs.assumptions.model_dump()
        elif hasattr(inputs.assumptions, "__dict__"):
            result["assumptions"] = inputs.assumptions.__dict__
        else:
            result["assumptions"] = inputs.assumptions

    # 處理 income
    if inputs.income is not None:
        if hasattr(inputs.income, "model_dump"):
            result["income"] = inputs.income.model_dump()
        else:
            result["income"] = str(inputs.income)

    # 處理 historical_expenses
    if inputs.historical_expenses:
        result["historical_expenses"] = [
            {
                "year": exp.year,
                "month": exp.month,
                "total": str(exp.total()),
            }
            for exp in inputs.historical_expenses
        ]

    # 處理 overrides
    if inputs.income_override is not None:
        result["income_override"] = str(inputs.income_override)
    if inputs.expense_override is not None:
        result["expense_override"] = str(inputs.expense_override)

    # 處理 one_time_expenses
    if inputs.one_time_expenses:
        result["one_time_expenses"] = [
            ot.model_dump() for ot in inputs.one_time_expenses
        ]

    return result


# =============================================================================
# Helper Functions
# =============================================================================

def next_month(year: int, month: int) -> tuple[int, int]:
    """計算下一個月份

    Args:
        year: 年份
        month: 月份 (1-12)

    Returns:
        (year, month) 下一個月份
    """
    if month == 12:
        return (year + 1, 1)
    return (year, month + 1)


def is_depleted(ending_balance: Decimal) -> bool:
    """判斷資產是否耗盡

    Args:
        ending_balance: 期末餘額

    Returns:
        True 如果餘額 < 0
    """
    return ending_balance < Decimal("0")


# =============================================================================
# Expense Estimation Strategies
# =============================================================================

def estimate_monthly_expenses(
    historical: list[MonthlyExpenses],
    strategy: str = "average",
) -> Decimal:
    """根據歷史資料估算月度支出

    支援策略：
    - average: 歷史平均值
    - median: 中位數
    - max: 最大值（保守估計）
    - latest: 最近一個月

    Args:
        historical: 歷史支出資料列表
        strategy: 估算策略

    Returns:
        估算的月度支出金額

    Raises:
        ValueError: 無歷史資料或策略無效
    """
    if not historical:
        raise ValueError("需要至少一個月的歷史支出資料")

    # 計算每月總支出
    monthly_totals = [exp.total() for exp in historical]

    if strategy == "average":
        total = sum(monthly_totals, Decimal("0"))
        return quantize_internal(total / len(monthly_totals))

    elif strategy == "median":
        sorted_totals = sorted(monthly_totals)
        n = len(sorted_totals)
        if n % 2 == 0:
            median = (sorted_totals[n // 2 - 1] + sorted_totals[n // 2]) / 2
        else:
            median = sorted_totals[n // 2]
        return quantize_internal(median)

    elif strategy == "max":
        return quantize_internal(max(monthly_totals))

    elif strategy == "latest":
        # 按 (year, month) 排序，取最新
        sorted_historical = sorted(
            historical,
            key=lambda x: (x.year, x.month),
            reverse=True,
        )
        return quantize_internal(sorted_historical[0].total())

    else:
        raise ValueError(f"不支援的估算策略: {strategy}")


# =============================================================================
# Core Projection Logic
# =============================================================================

def calculate_projection(
    inputs: ProjectionInput,
) -> ProjectionResult:
    """執行現金流預測計算

    核心計算邏輯：
    1. 確定月收入（override 或 income 模型）
    2. 確定基本月支出（override 或歷史估算）
    3. 逐月計算：
       - 收入 - 支出 - 一次性支出 = 淨現金流
       - 累計儲蓄 = 前月累計 + 淨現金流
    4. 追蹤赤字月份與資產耗盡時點

    Args:
        inputs: 預測輸入參數（ProjectionInput）

    Returns:
        ProjectionResult 包含完整預測結果

    Raises:
        ValueError: 輸入參數無效
    """
    # 驗證輸入
    _validate_inputs(inputs)

    # 確定月收入
    monthly_income = _determine_monthly_income(inputs)

    # 確定基本月支出
    monthly_expense = _determine_monthly_expense(inputs)

    # 建立一次性支出查找表
    one_time_lookup = _build_one_time_lookup(inputs.one_time_expenses or [])

    # 初始化
    current_year = inputs.start_year
    current_month = inputs.start_month
    cumulative_savings = quantize_internal(inputs.initial_savings)

    monthly_projections: list[MonthlyProjection] = []
    total_income = Decimal("0")
    total_expenses = Decimal("0")
    deficit_months: list[tuple[int, int]] = []  # [(year, month), ...]
    first_deficit_month: Optional[tuple[int, int]] = None
    asset_depletion_month: Optional[tuple[int, int]] = None

    # 逐月計算
    for _ in range(inputs.projection_months):
        # 取得一次性支出
        one_time_list = one_time_lookup.get((current_year, current_month), [])
        one_time_total = sum(
            (ot.amount for ot in one_time_list),
            Decimal("0"),
        )

        # 計算當月
        month_total_expense = quantize_internal(monthly_expense + one_time_total)
        net_cashflow = quantize_internal(monthly_income - month_total_expense)
        cumulative_savings = quantize_internal(cumulative_savings + net_cashflow)

        # 判斷赤字
        is_deficit = net_cashflow < Decimal("0")
        if is_deficit:
            deficit_months.append((current_year, current_month))
            if first_deficit_month is None:
                first_deficit_month = (current_year, current_month)

        # 判斷資產耗盡
        if asset_depletion_month is None and is_depleted(cumulative_savings):
            asset_depletion_month = (current_year, current_month)

        # 建立月度預測記錄
        projection = MonthlyProjection(
            year=current_year,
            month=current_month,
            income=quantize_output(monthly_income),
            regular_expenses=quantize_output(monthly_expense),
            one_time_expenses=quantize_output(one_time_total),
            total_expenses=quantize_output(month_total_expense),
            net_cashflow=quantize_output(net_cashflow),
            cumulative_savings=quantize_output(cumulative_savings),
            is_deficit=is_deficit,
        )
        monthly_projections.append(projection)

        # 累計
        total_income += monthly_income
        total_expenses += month_total_expense

        # 下一個月
        current_year, current_month = next_month(current_year, current_month)

    # 計算平均月現金流
    avg_cashflow = quantize_internal(
        (total_income - total_expenses) / inputs.projection_months
    )

    # 計算 input_hash
    input_hash = compute_input_hash(inputs)

    return ProjectionResult(
        monthly_projections=monthly_projections,
        total_income=quantize_output(total_income),
        total_expenses=quantize_output(total_expenses),
        final_cumulative_savings=quantize_output(cumulative_savings),
        average_monthly_cashflow=quantize_output(avg_cashflow),
        deficit_months=deficit_months,
        first_deficit_month=first_deficit_month,
        asset_depletion_month=asset_depletion_month,
        input_hash=input_hash,
        calculation_timestamp=datetime.now().isoformat(),
    )


def _validate_inputs(inputs: ProjectionInput) -> None:
    """驗證輸入參數"""
    if inputs.projection_months < 1:
        raise ValueError("projection_months 必須 >= 1")

    if inputs.start_month < 1 or inputs.start_month > 12:
        raise ValueError("start_month 必須在 1-12 之間")

    if inputs.initial_savings < Decimal("0"):
        raise ValueError("initial_savings 不能為負數")

    # 必須有收入來源
    if inputs.income is None and inputs.income_override is None:
        raise ValueError("必須提供 income 或 income_override")

    # 必須有支出估算來源
    if (
        inputs.expense_override is None
        and not inputs.historical_expenses
    ):
        raise ValueError("必須提供 expense_override 或 historical_expenses")


def _determine_monthly_income(inputs: ProjectionInput) -> Decimal:
    """確定月收入金額"""
    if inputs.income_override is not None:
        return quantize_internal(inputs.income_override)

    if inputs.income is not None:
        # MonthlyIncome.total_monthly() 返回 float
        return quantize_internal(Decimal(str(inputs.income.total_monthly())))

    raise ValueError("無法確定月收入")


def _determine_monthly_expense(inputs: ProjectionInput) -> Decimal:
    """確定基本月支出金額"""
    if inputs.expense_override is not None:
        return quantize_internal(inputs.expense_override)

    if inputs.historical_expenses:
        return estimate_monthly_expenses(
            inputs.historical_expenses,
            inputs.expense_estimation_strategy,
        )

    raise ValueError("無法確定月支出")


def _build_one_time_lookup(
    one_time_expenses: list[OneTimeExpense],
) -> dict[tuple[int, int], list[OneTimeExpense]]:
    """建立一次性支出查找表"""
    lookup: dict[tuple[int, int], list[OneTimeExpense]] = {}
    for ot in one_time_expenses:
        key = (ot.year, ot.month)
        if key not in lookup:
            lookup[key] = []
        lookup[key].append(ot)
    return lookup
