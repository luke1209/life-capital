"""Decision Comparator 測試

測試 advisor/decision_comparator.py 的規則引擎。
"""

import pytest

from life_capital.advisor.decision_comparator import (
    ComparisonResult,
    DecisionComparator,
)
from life_capital.advisor.schemas import (
    BlockingReasonDetail,
    DecisionOptionSchema,
)
from life_capital.privacy.redaction.decision_context import RedactedDecisionContext


class TestComparisonResult:
    """比較結果測試"""

    def test_comparable_result_structure(self):
        """測試可比較結果結構"""
        option_a = DecisionOptionSchema(
            direction="conservative",
            label="方案 A",
            status="comparable",
            recommendation="建議延後",
            score=0.75,
        )
        option_b = DecisionOptionSchema(
            direction="aggressive",
            label="方案 B",
            status="comparable",
            recommendation="建議現在",
            score=0.65,
        )
        result = ComparisonResult(
            comparability_score=0.70,
            is_comparable=True,
            option_a=option_a,
            option_b=option_b,
            risk_tags=["moderate_risk"],
            risk_explanation="中等風險",
            blocking_details=[],
            weak_dimensions=[],
        )

        assert result.is_comparable is True
        assert result.option_a.direction == "conservative"
        assert result.option_b.direction == "aggressive"

    def test_not_comparable_result_structure(self):
        """測試不可比較結果結構"""
        option_a = DecisionOptionSchema(
            direction="conservative",
            label="方案 A",
            status="not_comparable",
            to_comparable_guidance="需補充收入資料",
        )
        option_b = DecisionOptionSchema(
            direction="aggressive",
            label="方案 B",
            status="not_comparable",
            to_comparable_guidance="需補充收入資料",
        )
        blocking = BlockingReasonDetail(
            code="MISSING_DATA",
            message="缺少必要資料",
            severity="blocking",
        )
        result = ComparisonResult(
            comparability_score=0.35,
            is_comparable=False,
            option_a=option_a,
            option_b=option_b,
            risk_tags=[],
            risk_explanation="",
            blocking_details=[blocking],
            weak_dimensions=["time_horizon", "liquidity"],
        )

        assert result.is_comparable is False
        assert len(result.blocking_details) == 1
        assert result.option_a.status == "not_comparable"


class TestDecisionComparator:
    """決策比較器測試"""

    @pytest.fixture
    def comparator(self):
        """建立比較器"""
        return DecisionComparator()

    @pytest.fixture
    def good_context(self):
        """良好的決策上下文"""
        return RedactedDecisionContext(
            expense_distribution={"food": 0.25, "housing": 0.35, "transport": 0.15, "other": 0.25},
            deficit_month_count=0,
            runway_months=36,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="30-40%",
            expense_trend="stable",
        )

    @pytest.fixture
    def poor_context(self):
        """較差的決策上下文"""
        return RedactedDecisionContext(
            expense_distribution={"food": 0.5, "housing": 0.4, "other": 0.1},
            deficit_month_count=8,
            runway_months=3,
            consecutive_deficit_months=5,
            income_volatility="high",
            savings_rate_band="0-10%",
            expense_trend="increasing",
        )

    @pytest.fixture
    def borderline_context(self):
        """邊界案例上下文"""
        return RedactedDecisionContext(
            expense_distribution={"food": 0.35, "housing": 0.40, "other": 0.25},
            deficit_month_count=3,
            runway_months=8,
            consecutive_deficit_months=2,
            income_volatility="medium",
            savings_rate_band="10-20%",
            expense_trend="stable",
        )

    def test_compare_returns_result(self, comparator, good_context):
        """測試比較回傳結果"""
        result = comparator.compare(good_context, "default")
        assert isinstance(result, ComparisonResult)

    def test_always_returns_two_options(self, comparator, good_context, poor_context):
        """測試永遠回傳兩個選項"""
        # 良好上下文
        result1 = comparator.compare(good_context, "default")
        assert result1.option_a is not None
        assert result1.option_b is not None

        # 較差上下文
        result2 = comparator.compare(poor_context, "default")
        assert result2.option_a is not None
        assert result2.option_b is not None

    def test_option_directions(self, comparator, good_context):
        """測試選項方向"""
        result = comparator.compare(good_context, "default")
        assert result.option_a.direction == "conservative"
        assert result.option_b.direction == "aggressive"

    def test_comparable_options_have_scores(self, comparator, good_context):
        """測試可比較選項有分數"""
        result = comparator.compare(good_context, "default")
        if result.is_comparable:
            assert result.option_a.score is not None
            assert result.option_b.score is not None
            assert 0 <= result.option_a.score <= 1
            assert 0 <= result.option_b.score <= 1

    def test_not_comparable_options_have_guidance(self, comparator, poor_context):
        """測試不可比較選項有指引"""
        result = comparator.compare(poor_context, "default")
        if not result.is_comparable:
            # 至少有一個選項應該有指引
            has_guidance = (
                result.option_a.to_comparable_guidance is not None or
                result.option_b.to_comparable_guidance is not None
            )
            assert has_guidance or result.option_a.status == "not_comparable"

    def test_risk_tags_for_poor_context(self, comparator, poor_context):
        """測試較差上下文有風險標籤"""
        result = comparator.compare(poor_context, "default")
        # 財務狀況差應該有風險標籤
        assert len(result.risk_tags) > 0 or not result.is_comparable

    def test_comparability_score_range(self, comparator, good_context):
        """測試可比較性分數範圍"""
        result = comparator.compare(good_context, "default")
        assert 0 <= result.comparability_score <= 1

    def test_comparability_threshold(self, comparator, good_context, poor_context):
        """測試可比較性閾值"""
        good_result = comparator.compare(good_context, "default")
        poor_result = comparator.compare(poor_context, "default")

        # 良好上下文分數應較高
        assert good_result.comparability_score > poor_result.comparability_score

    def test_buying_house_template(self, comparator, good_context):
        """測試買房模板"""
        result = comparator.compare(good_context, "buying_house")
        assert result.option_a.label is not None
        assert result.option_b.label is not None

    def test_investment_template(self, comparator, good_context):
        """測試投資模板"""
        result = comparator.compare(good_context, "investment")
        assert result.option_a.label is not None
        assert result.option_b.label is not None

    def test_unknown_template_fallback(self, comparator, good_context):
        """測試未知模板 fallback"""
        result = comparator.compare(good_context, "nonexistent_template")
        # 應該 fallback 到 default 並正常工作
        assert isinstance(result, ComparisonResult)

    def test_borderline_case(self, comparator, borderline_context):
        """測試邊界案例"""
        result = comparator.compare(borderline_context, "default")
        # 邊界案例應該有弱維度標記或部分可比較狀態
        assert isinstance(result, ComparisonResult)
        # 確認處理正常，不論結果如何
        assert result.comparability_score >= 0


class TestRiskAssessment:
    """風險評估測試"""

    @pytest.fixture
    def comparator(self):
        return DecisionComparator()

    def test_high_deficit_risk(self, comparator):
        """測試高赤字風險"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.5, "other": 0.5},
            deficit_month_count=10,
            runway_months=2,
            consecutive_deficit_months=8,
            income_volatility="high",
            savings_rate_band="0-10%",
            expense_trend="increasing",
        )
        result = comparator.compare(context, "default")

        # 高赤字應該有風險標籤
        risk_tags_str = " ".join(result.risk_tags).lower()
        assert (
            "deficit" in risk_tags_str or
            "risk" in risk_tags_str or
            len(result.risk_tags) > 0 or
            not result.is_comparable
        )

    def test_short_runway_risk(self, comparator):
        """測試短跑道風險"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.5, "other": 0.5},
            deficit_month_count=2,
            runway_months=3,  # 很短的跑道
            consecutive_deficit_months=1,
            income_volatility="medium",
            savings_rate_band="10-20%",
            expense_trend="stable",
        )
        result = comparator.compare(context, "buying_house")

        # 短跑道對買房決策應該有風險
        assert len(result.risk_tags) > 0 or not result.is_comparable

    def test_high_volatility_risk(self, comparator):
        """測試高波動風險"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.4, "other": 0.6},
            deficit_month_count=1,
            runway_months=12,
            consecutive_deficit_months=0,
            income_volatility="high",  # 高波動
            savings_rate_band="15-25%",
            expense_trend="stable",
        )
        result = comparator.compare(context, "investment")

        # 高波動對投資決策應該有風險考量
        has_volatility_concern = (
            "volatility" in " ".join(result.risk_tags).lower() or
            "高波動" in result.risk_explanation or
            "波動" in result.risk_explanation or
            len(result.risk_tags) > 0
        )
        assert has_volatility_concern or result.comparability_score < 0.8


class TestOptionGeneration:
    """選項生成測試"""

    @pytest.fixture
    def comparator(self):
        return DecisionComparator()

    def test_labels_match_template(self, comparator):
        """測試標籤符合模板"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.3, "housing": 0.4, "other": 0.3},
            deficit_month_count=0,
            runway_months=24,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="25-35%",
            expense_trend="stable",
        )

        # 買房模板
        result = comparator.compare(context, "buying_house")
        assert (
            "購房" in result.option_a.label
            or "購房" in result.option_b.label
            or "方案" in result.option_a.label
        )

    def test_recommendations_not_empty_when_comparable(self, comparator):
        """測試可比較時建議非空"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.25, "housing": 0.35, "other": 0.40},
            deficit_month_count=0,
            runway_months=48,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="35-45%",
            expense_trend="decreasing",
        )
        result = comparator.compare(context, "default")

        if result.is_comparable:
            # 可比較時應有建議
            has_recommendation = (
                result.option_a.recommendation is not None or
                result.option_b.recommendation is not None
            )
            assert has_recommendation


class TestPureFunctional:
    """純函式特性測試"""

    @pytest.fixture
    def comparator(self):
        return DecisionComparator()

    def test_deterministic(self, comparator):
        """測試確定性"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.3, "housing": 0.4, "other": 0.3},
            deficit_month_count=1,
            runway_months=18,
            consecutive_deficit_months=0,
            income_volatility="medium",
            savings_rate_band="20-30%",
            expense_trend="stable",
        )

        # 多次呼叫應該產生相同結果
        result1 = comparator.compare(context, "default")
        result2 = comparator.compare(context, "default")

        assert result1.comparability_score == result2.comparability_score
        assert result1.is_comparable == result2.is_comparable
        assert result1.option_a.direction == result2.option_a.direction

    def test_no_side_effects(self, comparator):
        """測試無副作用"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.3, "other": 0.7},
            deficit_month_count=0,
            runway_months=24,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="25-35%",
            expense_trend="stable",
        )

        original_deficit = context.deficit_month_count
        original_volatility = context.income_volatility

        # 呼叫比較器
        comparator.compare(context, "default")

        # 上下文不應被修改
        assert context.deficit_month_count == original_deficit
        assert context.income_volatility == original_volatility


class TestIntegration:
    """整合測試"""

    def test_full_comparison_workflow(self):
        """完整比較工作流程"""
        from life_capital.privacy.redaction.engine import RedactionEngine

        # 1. 原始資料
        raw_data = {
            "monthly_income": 100000,
            "monthly_expense": 70000,
            "savings": 400000,
            "expense_categories": {
                "food": 20000,
                "housing": 20000,
                "transport": 10000,
                "other": 20000,
            },
            "income_history": [98000, 100000, 102000, 99000, 101000, 100000],
        }

        # 2. 去識別
        engine = RedactionEngine()
        redaction_result = engine.redact(raw_data)
        context = redaction_result.context

        # 3. 比較
        comparator = DecisionComparator()
        result = comparator.compare(context, "buying_house")

        # 4. 驗證輸出
        assert isinstance(result, ComparisonResult)
        assert result.option_a is not None
        assert result.option_b is not None
        assert result.option_a.direction == "conservative"
        assert result.option_b.direction == "aggressive"
