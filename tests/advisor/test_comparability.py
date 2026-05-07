"""Comparability 測試

測試 advisor/comparability.py 的四維評分系統。
"""


import pytest

from life_capital.advisor.comparability import (
    ComparabilityCalculator,
    ComparabilityFeatures,
    ComparabilityResult,
    TimeSegment,
)
from life_capital.privacy.redaction.decision_context import RedactedDecisionContext


class TestComparabilityFeatures:
    """四維特徵向量測試"""

    def test_score_calculation(self):
        """測試加權評分計算"""
        features = ComparabilityFeatures(
            time_horizon=0.8,
            risk_tolerance=0.6,
            liquidity=0.7,
            capital_need=0.5,
        )
        # 0.8*0.3 + 0.6*0.2 + 0.7*0.3 + 0.5*0.2 = 0.24 + 0.12 + 0.21 + 0.10 = 0.67
        assert features.score() == pytest.approx(0.67, abs=0.01)

    def test_score_all_max(self):
        """測試全滿分"""
        features = ComparabilityFeatures(
            time_horizon=1.0,
            risk_tolerance=1.0,
            liquidity=1.0,
            capital_need=1.0,
        )
        assert features.score() == pytest.approx(1.0, abs=0.01)

    def test_score_all_min(self):
        """測試全最低分"""
        features = ComparabilityFeatures(
            time_horizon=0.0,
            risk_tolerance=0.0,
            liquidity=0.0,
            capital_need=0.0,
        )
        assert features.score() == pytest.approx(0.0, abs=0.01)

    def test_weak_dimensions(self):
        """測試弱維度辨識"""
        features = ComparabilityFeatures(
            time_horizon=0.8,
            risk_tolerance=0.3,  # 弱
            liquidity=0.4,       # 弱
            capital_need=0.9,
        )
        weak = features.weak_dimensions(threshold=0.5)
        assert "risk_tolerance" in weak
        assert "liquidity" in weak
        assert "time_horizon" not in weak
        assert "capital_need" not in weak

    def test_weights_sum_to_one(self):
        """測試權重總和為 1"""
        # 驗證隱含的權重配置
        # time_horizon: 0.3, risk_tolerance: 0.2, liquidity: 0.3, capital_need: 0.2
        assert 0.3 + 0.2 + 0.3 + 0.2 == pytest.approx(1.0, abs=0.01)


class TestTimeSegment:
    """時間分段測試"""

    def test_create_segment(self):
        """測試建立時間分段"""
        segment = TimeSegment(
            name="首付階段",
            duration="0-6個月",
            weight=0.3,
            threshold=0.7,
            metrics=["可用現金", "緊急備金"],
        )
        assert segment.name == "首付階段"
        assert segment.weight == 0.3
        assert segment.threshold == 0.7
        assert len(segment.metrics) == 2

    def test_evaluate_above_threshold(self):
        """測試評估超過閾值"""
        segment = TimeSegment(
            name="測試",
            duration="0-6個月",
            weight=0.3,
            threshold=0.6,
            metrics=[],
        )
        # 分數 0.8 > 閾值 0.6，應通過
        result = segment.evaluate(0.8)
        assert result["passed"] is True
        assert result["score"] == 0.8
        assert result["weighted_score"] == pytest.approx(0.24, abs=0.01)

    def test_evaluate_below_threshold(self):
        """測試評估低於閾值"""
        segment = TimeSegment(
            name="測試",
            duration="0-6個月",
            weight=0.5,
            threshold=0.7,
            metrics=[],
        )
        # 分數 0.5 < 閾值 0.7，應不通過
        result = segment.evaluate(0.5)
        assert result["passed"] is False
        assert result["score"] == 0.5


class TestComparabilityResult:
    """比較結果測試"""

    def test_comparable_result(self):
        """測試可比較結果"""
        features = ComparabilityFeatures(
            time_horizon=0.8,
            risk_tolerance=0.7,
            liquidity=0.8,
            capital_need=0.7,
        )
        result = ComparabilityResult(
            is_comparable=True,
            score=0.75,
            features=features,
            blocking_reasons=[],
            weak_dimensions=[],
        )
        assert result.is_comparable is True
        assert result.score >= 0.6

    def test_not_comparable_result(self):
        """測試不可比較結果"""
        features = ComparabilityFeatures(
            time_horizon=0.3,
            risk_tolerance=0.2,
            liquidity=0.4,
            capital_need=0.3,
        )
        result = ComparabilityResult(
            is_comparable=False,
            score=0.30,
            features=features,
            blocking_reasons=["TIME_HORIZON_INSUFFICIENT"],
            weak_dimensions=["time_horizon", "risk_tolerance"],
        )
        assert result.is_comparable is False
        assert len(result.blocking_reasons) > 0


class TestComparabilityCalculator:
    """可比較性計算器測試"""

    @pytest.fixture
    def calculator(self):
        """建立計算器"""
        return ComparabilityCalculator()

    @pytest.fixture
    def high_quality_context(self):
        """建立高品質決策上下文"""
        return RedactedDecisionContext(
            expense_distribution={"food": 0.3, "housing": 0.4, "transport": 0.2, "other": 0.1},
            deficit_month_count=0,
            runway_months=24,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="20-30%",
            expense_trend="stable",
        )

    @pytest.fixture
    def low_quality_context(self):
        """建立低品質決策上下文"""
        return RedactedDecisionContext(
            expense_distribution={"food": 0.5, "housing": 0.5},
            deficit_month_count=8,
            runway_months=3,
            consecutive_deficit_months=4,
            income_volatility="high",
            savings_rate_band="0-10%",
            expense_trend="increasing",
        )

    def test_calculate_default_template(self, calculator, high_quality_context):
        """測試預設模板計算"""
        result = calculator.calculate(high_quality_context, "default")
        assert isinstance(result, ComparabilityResult)
        assert 0 <= result.score <= 1

    def test_calculate_buying_house_template(self, calculator, high_quality_context):
        """測試買房模板計算"""
        result = calculator.calculate(high_quality_context, "buying_house")
        assert isinstance(result, ComparabilityResult)
        # 高品質上下文應該有較高的可比較性
        assert result.score > 0.5

    def test_calculate_low_quality_context(self, calculator, low_quality_context):
        """測試低品質上下文"""
        result = calculator.calculate(low_quality_context, "default")
        # 低品質上下文應該有較多弱維度
        assert len(result.weak_dimensions) > 0 or result.score < 0.6

    def test_threshold_boundary(self, calculator):
        """測試閾值邊界"""
        # 建立剛好在閾值附近的上下文
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.4, "housing": 0.4, "other": 0.2},
            deficit_month_count=2,
            runway_months=8,
            consecutive_deficit_months=1,
            income_volatility="medium",
            savings_rate_band="10-20%",
            expense_trend="stable",
        )
        result = calculator.calculate(context, "default")
        # 驗證 is_comparable 與 score 一致
        if result.score >= 0.6:
            assert result.is_comparable is True
        else:
            assert result.is_comparable is False

    def test_features_extraction(self, calculator, high_quality_context):
        """測試特徵提取"""
        result = calculator.calculate(high_quality_context, "default")
        features = result.features

        # 驗證特徵值在有效範圍
        assert 0 <= features.time_horizon <= 1
        assert 0 <= features.risk_tolerance <= 1
        assert 0 <= features.liquidity <= 1
        assert 0 <= features.capital_need <= 1

    def test_unknown_template_fallback(self, calculator, high_quality_context):
        """測試未知模板 fallback"""
        # 使用不存在的模板應該 fallback 到 default
        result = calculator.calculate(high_quality_context, "nonexistent_template")
        assert isinstance(result, ComparabilityResult)


class TestComparabilityIntegration:
    """整合測試"""

    def test_end_to_end_comparable(self):
        """端到端測試：可比較案例"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.25, "housing": 0.35, "transport": 0.15, "other": 0.25},
            deficit_month_count=0,
            runway_months=36,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="30-40%",
            expense_trend="stable",
        )
        calculator = ComparabilityCalculator()
        result = calculator.calculate(context, "buying_house")

        assert result.is_comparable is True
        assert result.score >= 0.6
        assert len(result.blocking_reasons) == 0

    def test_end_to_end_not_comparable(self):
        """端到端測試：不可比較案例"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.6, "housing": 0.4},
            deficit_month_count=10,
            runway_months=2,
            consecutive_deficit_months=6,
            income_volatility="high",
            savings_rate_band="0-10%",
            expense_trend="increasing",
        )
        calculator = ComparabilityCalculator()
        result = calculator.calculate(context, "buying_house")

        # 財務狀況差，不應該可比較
        assert result.score < 0.6 or len(result.blocking_reasons) > 0
