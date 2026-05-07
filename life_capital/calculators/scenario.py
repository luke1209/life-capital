"""情境分析計算模組

Phase 2 情境分析邏輯，負責：
- 情境預設值模板
- 情境套用與比較
- 基準線對照分析

遵循 V6 Final 契約：
- Contract 2: 明確 --baseline 參數（用於情境比較）
- Contract 3: input_hash 確定性
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from life_capital.calculators.projection import (
    calculate_projection,
    compute_input_hash,
    quantize_output,
)
from life_capital.io.registry import CALC_VERSION
from life_capital.models.scenario import (
    DerivedProvenance,
    ProjectionInput,
    ProjectionResult,
    ScenarioAssumption,
    ScenarioComparisonResult,
    ScenarioPreset,
    ScenarioResult,
    ScenarioType,
)

# =============================================================================
# Scenario Preset Templates
# =============================================================================

def get_preset_assumption(preset: ScenarioPreset, name: str = "") -> ScenarioAssumption:
    """根據預設值取得情境假設

    Args:
        preset: 情境預設類型
        name: 情境名稱（可選，預設使用預設值名稱）

    Returns:
        ScenarioAssumption 情境假設
    """
    if preset == ScenarioPreset.CONSERVATIVE:
        return ScenarioAssumption(
            name=name or "保守情境",
            scenario_type=ScenarioType.COMBINED,
            income_change_percent=Decimal("-0.10"),  # 收入減少 10%
            income_change_start_month=1,
            expense_change_percent=Decimal("0.10"),  # 支出增加 10%
            one_time_expenses=[],
            description="保守估計：收入下降 10%，支出上升 10%",
        )
    elif preset == ScenarioPreset.BASELINE:
        return ScenarioAssumption(
            name=name or "基準情境",
            scenario_type=ScenarioType.COMBINED,
            income_change_percent=Decimal("0"),
            income_change_start_month=1,
            expense_change_percent=Decimal("0"),
            one_time_expenses=[],
            description="維持現狀：收入與支出不變",
        )
    elif preset == ScenarioPreset.OPTIMISTIC:
        return ScenarioAssumption(
            name=name or "樂觀情境",
            scenario_type=ScenarioType.COMBINED,
            income_change_percent=Decimal("0.10"),  # 收入增加 10%
            income_change_start_month=1,
            expense_change_percent=Decimal("-0.05"),  # 支出減少 5%
            one_time_expenses=[],
            description="樂觀估計：收入上升 10%，支出下降 5%",
        )
    else:
        raise ValueError(f"不支援的預設類型: {preset}")


# =============================================================================
# Scenario Application
# =============================================================================

def apply_scenario(
    base_input: ProjectionInput,
    scenario: ScenarioAssumption,
) -> ProjectionInput:
    """將情境假設套用至基礎輸入

    Args:
        base_input: 基礎預測輸入
        scenario: 情境假設

    Returns:
        套用情境後的 ProjectionInput
    """
    # 計算調整後的收入
    new_income_override = None
    if base_input.income_override is not None:
        if scenario.income_change_percent != Decimal("0"):
            adjusted = base_input.income_override * (Decimal("1") + scenario.income_change_percent)
            new_income_override = quantize_output(adjusted)
        else:
            new_income_override = base_input.income_override
    elif base_input.income is not None:
        base_income = Decimal(str(base_input.income.total_monthly()))
        if scenario.income_change_percent != Decimal("0"):
            adjusted = base_income * (Decimal("1") + scenario.income_change_percent)
            new_income_override = quantize_output(adjusted)

    # 計算調整後的支出
    new_expense_override = None
    if base_input.expense_override is not None:
        if scenario.expense_change_percent != Decimal("0"):
            adjusted = base_input.expense_override * (
                Decimal("1") + scenario.expense_change_percent
            )
            new_expense_override = quantize_output(adjusted)
        else:
            new_expense_override = base_input.expense_override

    # 合併一次性支出
    combined_one_time = list(base_input.one_time_expenses) + list(scenario.one_time_expenses)

    # 建立新的輸入（使用 dataclass replace）
    return ProjectionInput(
        start_year=base_input.start_year,
        start_month=base_input.start_month,
        initial_savings=base_input.initial_savings,
        projection_months=base_input.projection_months,
        assumptions=base_input.assumptions,
        income=base_input.income,
        historical_expenses=base_input.historical_expenses,
        income_override=(
            new_income_override if new_income_override else base_input.income_override
        ),
        expense_override=(
            new_expense_override if new_expense_override else base_input.expense_override
        ),
        one_time_expenses=combined_one_time,
        expense_estimation_strategy=base_input.expense_estimation_strategy,
    )


# =============================================================================
# Scenario Calculation
# =============================================================================

def calculate_scenario(
    base_input: ProjectionInput,
    scenario: ScenarioAssumption,
    baseline: Optional[ProjectionResult] = None,
) -> ScenarioResult:
    """計算單一情境結果

    V6 Final Contract 2: 明確 baseline 參數

    Args:
        base_input: 基礎預測輸入
        scenario: 情境假設
        baseline: 基準預測結果（用於計算差異）

    Returns:
        ScenarioResult 情境結果
    """
    # 套用情境
    scenario_input = apply_scenario(base_input, scenario)

    # 執行預測
    projection = calculate_projection(scenario_input)

    # 計算與基準線的差異
    baseline_diff_savings = None
    baseline_diff_months = None

    if baseline is not None:
        baseline_diff_savings = quantize_output(
            projection.final_cumulative_savings - baseline.final_cumulative_savings
        )

        # 計算資產耗盡月份差異
        if projection.asset_depletion_month and baseline.asset_depletion_month:
            scenario_months = _months_to_depletion(projection)
            baseline_months = _months_to_depletion(baseline)
            if scenario_months is not None and baseline_months is not None:
                baseline_diff_months = scenario_months - baseline_months

    return ScenarioResult(
        scenario=scenario,
        projection=projection,
        baseline_diff_savings=baseline_diff_savings,
        baseline_diff_months_to_depletion=baseline_diff_months,
    )


def _months_to_depletion(result: ProjectionResult) -> Optional[int]:
    """計算從起始到資產耗盡的月數"""
    if result.asset_depletion_month is None:
        return None

    if not result.monthly_projections:
        return None

    start = result.monthly_projections[0]
    depletion = result.asset_depletion_month

    start_total = start.year * 12 + start.month
    depletion_total = depletion[0] * 12 + depletion[1]

    return depletion_total - start_total


# =============================================================================
# Scenario Comparison
# =============================================================================

def compare_scenarios(
    base_input: ProjectionInput,
    scenarios: list[ScenarioAssumption],
    baseline_name: str = "基準",
) -> ScenarioComparisonResult:
    """比較多個情境

    V6 Final Contract 2: 使用第一個情境作為 baseline

    Args:
        base_input: 基礎預測輸入
        scenarios: 情境假設列表
        baseline_name: 基準情境名稱

    Returns:
        ScenarioComparisonResult 比較結果
    """
    if not scenarios:
        raise ValueError("至少需要一個情境")

    # 建立基準預測（使用原始輸入，不套用任何情境）
    baseline_input = ProjectionInput(
        start_year=base_input.start_year,
        start_month=base_input.start_month,
        initial_savings=base_input.initial_savings,
        projection_months=base_input.projection_months,
        assumptions=base_input.assumptions,
        income=base_input.income,
        historical_expenses=base_input.historical_expenses,
        income_override=base_input.income_override,
        expense_override=base_input.expense_override,
        one_time_expenses=[],  # 基準不含一次性支出
        expense_estimation_strategy=base_input.expense_estimation_strategy,
    )
    baseline_projection = calculate_projection(baseline_input)

    # 計算各情境
    scenario_results = []
    for scenario in scenarios:
        result = calculate_scenario(base_input, scenario, baseline_projection)
        scenario_results.append(result)

    # 建立比較表
    comparison_table = _build_comparison_table(baseline_projection, scenario_results)

    # 計算整體 input_hash
    input_hash = compute_input_hash(base_input)

    return ScenarioComparisonResult(
        baseline_name=baseline_name,
        scenarios=scenario_results,
        comparison_table=comparison_table,
        input_hash=input_hash,
    )


def _build_comparison_table(
    baseline: ProjectionResult,
    scenarios: list[ScenarioResult],
) -> dict:
    """建立情境比較表格"""
    table = {
        "baseline": {
            "final_savings": str(baseline.final_cumulative_savings),
            "deficit_months": baseline.deficit_months,
            "asset_depletion": baseline.asset_depletion_month,
        },
        "scenarios": [],
    }

    for result in scenarios:
        scenario_data = {
            "name": result.scenario.name,
            "final_savings": str(result.projection.final_cumulative_savings),
            "diff_savings": (
                str(result.baseline_diff_savings) if result.baseline_diff_savings else None
            ),
            "deficit_months": result.projection.deficit_months,
            "asset_depletion": result.projection.asset_depletion_month,
            "diff_depletion_months": result.baseline_diff_months_to_depletion,
        }
        table["scenarios"].append(scenario_data)

    return table


# =============================================================================
# Provenance Generation
# =============================================================================

def create_scenario_provenance(
    canonical_sources: list[str],
    calc_version: str = CALC_VERSION,
    input_hash: str = "",
) -> DerivedProvenance:
    """建立情境分析的 provenance 記錄

    Args:
        canonical_sources: 使用的 canonical 檔案列表
        calc_version: 計算邏輯版本
        input_hash: 輸入資料 hash

    Returns:
        DerivedProvenance 記錄
    """
    return DerivedProvenance(
        calc_version=f"scenario_{calc_version}",
        input_hash=input_hash,
        canonical_sources=canonical_sources,
        generated_at=datetime.now().isoformat(),
    )
