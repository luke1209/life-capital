"""Projection 計算模組測試

測試 Phase 2 核心預測邏輯，包含：
- PrecisionConfig 精度控制
- estimate_monthly_expenses 歷史估算
- calculate_projection 核心預測
- compute_input_hash 確定性 hash
"""

from decimal import Decimal

import pytest

# 直接從 projection 導入，避免觸發 calculators/__init__.py 循環導入
# (與 test_lifetime.py 使用相同模式)
from life_capital.calculators.projection import (
    PrecisionConfig,
    calculate_projection,
    compute_input_hash,
    estimate_monthly_expenses,
    is_depleted,
    next_month,
    quantize_internal,
    quantize_output,
)
from life_capital.models.expense import ExpenseRecord, MonthlyExpenses
from life_capital.models.scenario import OneTimeExpense, ProjectionInput

# =============================================================================
# PrecisionConfig Tests (V6 Final Contract 4)
# =============================================================================


class TestPrecisionConfig:
    """V6 Final Contract 4: 精度控制測試"""

    def test_internal_scale_is_2(self):
        """內部計算精度為 2 位小數"""
        assert PrecisionConfig.INTERNAL_SCALE == 2

    def test_output_scale_is_0(self):
        """輸出精度為 0 位小數（整數元）"""
        assert PrecisionConfig.OUTPUT_SCALE == 0

    def test_quantize_internal_rounds_to_2_decimals(self):
        """quantize_internal 四捨五入至 2 位小數"""
        assert quantize_internal(Decimal("123.456")) == Decimal("123.46")
        assert quantize_internal(Decimal("123.454")) == Decimal("123.45")
        assert quantize_internal(Decimal("123.455")) == Decimal("123.46")  # ROUND_HALF_UP

    def test_quantize_output_rounds_to_integer(self):
        """quantize_output 四捨五入至整數"""
        assert quantize_output(Decimal("123.4")) == Decimal("123")
        assert quantize_output(Decimal("123.5")) == Decimal("124")
        assert quantize_output(Decimal("123.6")) == Decimal("124")


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestNextMonth:
    """next_month 輔助函式測試"""

    def test_normal_month(self):
        """一般月份遞增"""
        assert next_month(2024, 1) == (2024, 2)
        assert next_month(2024, 6) == (2024, 7)
        assert next_month(2024, 11) == (2024, 12)

    def test_year_rollover(self):
        """跨年處理"""
        assert next_month(2024, 12) == (2025, 1)
        assert next_month(2025, 12) == (2026, 1)


class TestIsDepleted:
    """is_depleted 輔助函式測試"""

    def test_positive_balance(self):
        """正餘額不算耗盡"""
        assert is_depleted(Decimal("100")) is False
        assert is_depleted(Decimal("0.01")) is False

    def test_zero_balance(self):
        """零餘額不算耗盡"""
        assert is_depleted(Decimal("0")) is False

    def test_negative_balance(self):
        """負餘額算耗盡"""
        assert is_depleted(Decimal("-1")) is True
        assert is_depleted(Decimal("-0.01")) is True


# =============================================================================
# Expense Estimation Tests
# =============================================================================


class TestEstimateMonthlyExpenses:
    """歷史支出估算策略測試"""

    @pytest.fixture
    def sample_expenses(self) -> list[MonthlyExpenses]:
        """建立測試用歷史支出資料"""
        return [
            MonthlyExpenses(
                year=2024,
                month=1,
                records=[
                    ExpenseRecord(
                        date="2024-01-15",
                        amount=Decimal("10000"),
                        category="food",
                    ),
                ],
            ),
            MonthlyExpenses(
                year=2024,
                month=2,
                records=[
                    ExpenseRecord(
                        date="2024-02-15",
                        amount=Decimal("20000"),
                        category="food",
                    ),
                ],
            ),
            MonthlyExpenses(
                year=2024,
                month=3,
                records=[
                    ExpenseRecord(
                        date="2024-03-15",
                        amount=Decimal("12000"),
                        category="food",
                    ),
                ],
            ),
        ]

    def test_average_strategy(self, sample_expenses):
        """平均值策略"""
        result = estimate_monthly_expenses(sample_expenses, "average")
        # (10000 + 20000 + 12000) / 3 = 14000
        assert result == Decimal("14000.00")

    def test_median_strategy(self, sample_expenses):
        """中位數策略"""
        result = estimate_monthly_expenses(sample_expenses, "median")
        assert result == Decimal("12000.00")

    def test_max_strategy(self, sample_expenses):
        """最大值策略（保守估計）"""
        result = estimate_monthly_expenses(sample_expenses, "max")
        assert result == Decimal("20000.00")

    def test_latest_strategy(self, sample_expenses):
        """最新月份策略"""
        result = estimate_monthly_expenses(sample_expenses, "latest")
        assert result == Decimal("12000.00")

    def test_empty_history_raises_error(self):
        """空歷史資料應報錯"""
        with pytest.raises(ValueError, match="需要至少一個月"):
            estimate_monthly_expenses([], "average")

    def test_invalid_strategy_raises_error(self, sample_expenses):
        """無效策略應報錯"""
        with pytest.raises(ValueError, match="不支援的估算策略"):
            estimate_monthly_expenses(sample_expenses, "invalid")


# =============================================================================
# Input Hash Tests (V6 Final Contract 3)
# =============================================================================


class TestComputeInputHash:
    """確定性 hash 測試"""

    @pytest.fixture
    def basic_input(self) -> ProjectionInput:
        """基本測試輸入"""
        return ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
        )

    def test_same_input_same_hash(self, basic_input):
        """相同輸入產生相同 hash"""
        hash1 = compute_input_hash(basic_input)
        hash2 = compute_input_hash(basic_input)
        assert hash1 == hash2

    def test_different_input_different_hash(self, basic_input):
        """不同輸入產生不同 hash"""
        modified_input = ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000001"),  # 差 1 元
            projection_months=12,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
        )
        hash1 = compute_input_hash(basic_input)
        hash2 = compute_input_hash(modified_input)
        assert hash1 != hash2

    def test_calc_version_affects_hash(self, basic_input):
        """calc_version 變更會產生不同 hash"""
        hash_v1 = compute_input_hash(basic_input, calc_version="1.0")
        hash_v2 = compute_input_hash(basic_input, calc_version="2.0")
        assert hash_v1 != hash_v2

    def test_hash_is_sha256_hex(self, basic_input):
        """hash 格式為 SHA-256 hex"""
        result = compute_input_hash(basic_input)
        assert len(result) == 64  # SHA-256 hex 長度
        assert all(c in "0123456789abcdef" for c in result)


# =============================================================================
# Core Projection Tests
# =============================================================================


class TestCalculateProjection:
    """核心預測邏輯測試"""

    @pytest.fixture
    def simple_input(self) -> ProjectionInput:
        """簡單測試輸入：月收入 100k，月支出 80k，初始儲蓄 1M"""
        return ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
        )

    def test_basic_projection(self, simple_input):
        """基本預測計算"""
        result = calculate_projection(simple_input)

        # 驗證結構
        assert len(result.monthly_projections) == 12
        assert result.deficit_months == []  # 無赤字月份
        assert result.first_deficit_month is None
        assert result.asset_depletion_month is None

        # 驗證累計：每月淨現金流 +20000，12 個月累計 +240000
        # 初始 1000000 + 240000 = 1240000
        assert result.final_cumulative_savings == Decimal("1240000")

    def test_monthly_breakdown(self, simple_input):
        """月度明細驗證"""
        result = calculate_projection(simple_input)

        first_month = result.monthly_projections[0]
        assert first_month.year == 2024
        assert first_month.month == 1
        assert first_month.income == Decimal("100000")
        assert first_month.regular_expenses == Decimal("80000")
        assert first_month.net_cashflow == Decimal("20000")
        assert first_month.cumulative_savings == Decimal("1020000")

    def test_deficit_detection(self):
        """赤字月份偵測"""
        deficit_input = ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("100000"),
            projection_months=6,
            income_override=Decimal("50000"),
            expense_override=Decimal("80000"),  # 月虧 30000
        )
        result = calculate_projection(deficit_input)

        assert len(result.deficit_months) == 6  # 全部月份都是赤字
        assert result.first_deficit_month == (2024, 1)

    def test_asset_depletion(self):
        """資產耗盡偵測"""
        depletion_input = ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("50000"),
            projection_months=6,
            income_override=Decimal("10000"),
            expense_override=Decimal("30000"),  # 月虧 20000
        )
        result = calculate_projection(depletion_input)

        # 初始 50000，每月 -20000
        # 第 1 月：50000 - 20000 = 30000
        # 第 2 月：30000 - 20000 = 10000
        # 第 3 月：10000 - 20000 = -10000 ← 耗盡
        assert result.asset_depletion_month == (2024, 3)

    def test_one_time_expenses(self):
        """一次性支出處理"""
        input_with_one_time = ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=3,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
            one_time_expenses=[
                OneTimeExpense(
                    year=2024,
                    month=2,
                    amount=Decimal("50000"),
                    description="裝修費",
                    category="housing",
                ),
            ],
        )
        result = calculate_projection(input_with_one_time)

        # 第 2 月應有一次性支出
        month2 = result.monthly_projections[1]
        assert month2.one_time_expenses == Decimal("50000")
        assert month2.total_expenses == Decimal("130000")  # 80000 + 50000
        assert month2.net_cashflow == Decimal("-30000")  # 100000 - 130000

    def test_input_hash_in_result(self, simple_input):
        """結果包含 input_hash"""
        result = calculate_projection(simple_input)
        assert result.input_hash is not None
        assert len(result.input_hash) == 64

    def test_calculation_timestamp_in_result(self, simple_input):
        """結果包含 calculation_timestamp"""
        result = calculate_projection(simple_input)
        assert result.calculation_timestamp is not None
        from datetime import datetime
        datetime.fromisoformat(result.calculation_timestamp)  # 可解析即為合法 ISO 格式

    def test_missing_income_raises_error(self):
        """缺少收入來源應報錯"""
        invalid_input = ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            expense_override=Decimal("80000"),
            # 缺少 income 和 income_override
        )
        with pytest.raises(ValueError, match="必須提供 income 或 income_override"):
            calculate_projection(invalid_input)

    def test_missing_expense_raises_error(self):
        """缺少支出來源應報錯"""
        invalid_input = ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            income_override=Decimal("100000"),
            # 缺少 expense_override 和 historical_expenses
        )
        with pytest.raises(ValueError, match="必須提供 expense_override 或 historical_expenses"):
            calculate_projection(invalid_input)


# =============================================================================
# Determinism Tests (V6 Final Contract 3)
# =============================================================================


class TestProjectionDeterminism:
    """確定性測試：相同輸入必須產生相同結果（除 timestamp）"""

    def test_identical_results_for_same_input(self):
        """相同輸入產生相同結果"""
        inputs = ProjectionInput(
            start_year=2024,
            start_month=1,
            initial_savings=Decimal("1000000"),
            projection_months=12,
            income_override=Decimal("100000"),
            expense_override=Decimal("80000"),
        )

        result1 = calculate_projection(inputs)
        result2 = calculate_projection(inputs)

        # 比較關鍵欄位（不比較 timestamp）
        assert result1.input_hash == result2.input_hash
        assert result1.total_income == result2.total_income
        assert result1.total_expenses == result2.total_expenses
        assert result1.final_cumulative_savings == result2.final_cumulative_savings
        assert result1.deficit_months == result2.deficit_months
        assert result1.first_deficit_month == result2.first_deficit_month
        assert result1.asset_depletion_month == result2.asset_depletion_month

        # 比較月度明細
        for m1, m2 in zip(result1.monthly_projections, result2.monthly_projections):
            assert m1.year == m2.year
            assert m1.month == m2.month
            assert m1.income == m2.income
            assert m1.total_expenses == m2.total_expenses
            assert m1.cumulative_savings == m2.cumulative_savings
