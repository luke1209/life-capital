"""Scenario 情境分析模組測試

測試 Phase 2 情境分析邏輯，包含：
- ScenarioPreset 預設模板
- apply_scenario 情境套用
- calculate_scenario 情境計算
- compare_scenarios 情境比較
"""

from decimal import Decimal

import pytest

from life_capital.calculators.scenario import (
    apply_scenario,
    calculate_scenario,
    compare_scenarios,
    create_scenario_provenance,
    get_preset_assumption,
)
from life_capital.models.scenario import (
    OneTimeExpense,
    ProjectionInput,
    ScenarioAssumption,
    ScenarioPreset,
    ScenarioType,
)

# =============================================================================
# Preset Tests
# =============================================================================


class TestGetPresetAssumption:
    """情境預設模板測試"""

    def test_conservative_preset(self):
        """保守情境：收入減少，支出增加"""
        result = get_preset_assumption(ScenarioPreset.CONSERVATIVE)
        assert result.income_change_percent == Decimal("-0.10")
        assert result.expense_change_percent == Decimal("0.10")
        assert "保守" in result.name

    def test_baseline_preset(self):
        """基準情境：無變化"""
        result = get_preset_assumption(ScenarioPreset.BASELINE)
        assert result.income_change_percent == Decimal("0")
        assert result.expense_change_percent == Decimal("0")
        assert "基準" in result.name

    def test_optimistic_preset(self):
        """樂觀情境：收入增加，支出減少"""
        result = get_preset_assumption(ScenarioPreset.OPTIMISTIC)
        assert result.income_change_percent == Decimal("0.10")
        assert result.expense_change_percent == Decimal("-0.05")
        assert "樂觀" in result.name

    def test_custom_name(self):
        """自訂名稱覆蓋預設"""
        result = get_preset_assumption(ScenarioPreset.CONSERVATIVE, name="我的保守估計")
        assert result.name == "我的保守估計"


# =============================================================================
# Apply Scenario Tests
# =============================================================================


class TestApplyScenario:
    """情境套用測試"""

    @pytest.fixture
    def base_input(self) -> ProjectionInput:
        """基礎輸入"""
        return ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
        )

    def test_income_reduction(self, base_input):
        """收入減少 10%"""
        scenario = ScenarioAssumption(
            name="測試",
            scenario_type=ScenarioType.INCOME_CHANGE,
            income_change_percent=Decimal("-0.10"),
            expense_change_percent=Decimal("0"),
        )
        result = apply_scenario(base_input, scenario)
        assert result.income_override == Decimal("90000")  # 100000 * 0.9

    def test_expense_increase(self, base_input):
        """支出增加 20%"""
        scenario = ScenarioAssumption(
            name="測試",
            scenario_type=ScenarioType.LARGE_EXPENSE,
            income_change_percent=Decimal("0"),
            expense_change_percent=Decimal("0.20"),
        )
        result = apply_scenario(base_input, scenario)
        assert result.expense_override == Decimal("96000")  # 80000 * 1.2

    def test_combined_changes(self, base_input):
        """收入支出同時變化"""
        scenario = get_preset_assumption(ScenarioPreset.CONSERVATIVE)
        result = apply_scenario(base_input, scenario)
        assert result.income_override == Decimal("90000")  # -10%
        assert result.expense_override == Decimal("88000")  # +10%

    def test_one_time_expense_merged(self, base_input):
        """一次性支出合併"""
        base_input_with_ot = ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
            one_time_expenses=[
                OneTimeExpense(
                    year=2024,
                    month=6,
                    amount=Decimal("50000"),
                    description="原有支出",
                    category="other",
                ),
            ],
        )
        scenario = ScenarioAssumption(
            name="測試",
            scenario_type=ScenarioType.LARGE_EXPENSE,
            income_change_percent=Decimal("0"),
            expense_change_percent=Decimal("0"),
            one_time_expenses=[
                OneTimeExpense(
                    year=2024,
                    month=12,
                    amount=Decimal("100000"),
                    description="新增支出",
                    category="other",
                ),
            ],
        )
        result = apply_scenario(base_input_with_ot, scenario)
        assert len(result.one_time_expenses) == 2

    def test_no_change_preserves_values(self, base_input):
        """無變化時保留原值"""
        scenario = get_preset_assumption(ScenarioPreset.BASELINE)
        result = apply_scenario(base_input, scenario)
        assert result.income_override == base_input.income_override
        assert result.expense_override == base_input.expense_override


# =============================================================================
# Calculate Scenario Tests
# =============================================================================


class TestCalculateScenario:
    """情境計算測試"""

    @pytest.fixture
    def base_input(self) -> ProjectionInput:
        """基礎輸入"""
        return ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
        )

    def test_scenario_calculation(self, base_input):
        """情境計算結果"""
        scenario = get_preset_assumption(ScenarioPreset.CONSERVATIVE)
        result = calculate_scenario(base_input, scenario)

        assert result.scenario.name == "保守情境"
        assert result.projection is not None
        assert len(result.projection.monthly_projections) == 12

    def test_baseline_diff_calculation(self, base_input):
        """基準差異計算"""
        from life_capital.calculators.projection import calculate_projection

        # 先計算基準
        baseline = calculate_projection(base_input)

        # 計算保守情境
        scenario = get_preset_assumption(ScenarioPreset.CONSERVATIVE)
        result = calculate_scenario(base_input, scenario, baseline=baseline)

        # 保守情境應該比基準差
        assert result.baseline_diff_savings is not None
        assert result.baseline_diff_savings < Decimal("0")

    def test_without_baseline(self, base_input):
        """無基準時差異為 None"""
        scenario = get_preset_assumption(ScenarioPreset.CONSERVATIVE)
        result = calculate_scenario(base_input, scenario, baseline=None)

        assert result.baseline_diff_savings is None
        assert result.baseline_diff_months_to_depletion is None


# =============================================================================
# Compare Scenarios Tests
# =============================================================================


class TestCompareScenarios:
    """情境比較測試"""

    @pytest.fixture
    def base_input(self) -> ProjectionInput:
        """基礎輸入"""
        return ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
        )

    def test_compare_multiple_scenarios(self, base_input):
        """比較多個情境"""
        scenarios = [
            get_preset_assumption(ScenarioPreset.CONSERVATIVE),
            get_preset_assumption(ScenarioPreset.OPTIMISTIC),
        ]
        result = compare_scenarios(base_input, scenarios)

        assert result.baseline_name == "基準"
        assert len(result.scenarios) == 2
        assert result.comparison_table is not None

    def test_comparison_table_structure(self, base_input):
        """比較表結構"""
        scenarios = [get_preset_assumption(ScenarioPreset.CONSERVATIVE)]
        result = compare_scenarios(base_input, scenarios)

        table = result.comparison_table
        assert "baseline" in table
        assert "scenarios" in table
        assert len(table["scenarios"]) == 1
        assert "final_savings" in table["baseline"]

    def test_empty_scenarios_raises_error(self, base_input):
        """空情境列表應報錯"""
        with pytest.raises(ValueError, match="至少需要一個情境"):
            compare_scenarios(base_input, [])

    def test_input_hash_in_result(self, base_input):
        """結果包含 input_hash"""
        scenarios = [get_preset_assumption(ScenarioPreset.BASELINE)]
        result = compare_scenarios(base_input, scenarios)

        assert result.input_hash is not None
        assert len(result.input_hash) == 64


# =============================================================================
# Provenance Tests
# =============================================================================


class TestCreateScenarioProvenance:
    """Provenance 記錄測試"""

    def test_provenance_structure(self):
        """provenance 結構正確"""
        result = create_scenario_provenance(
            canonical_sources=["monthly_income.yaml", "expenses_2024_01.csv"],
            input_hash="abc123",
        )

        assert "scenario_" in result.calc_version
        assert result.input_hash == "abc123"
        assert len(result.canonical_sources) == 2
        assert result.generated_at is not None
