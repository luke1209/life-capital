"""測試可評估性模組

驗證 Recommendability 與 Evaluability 兩個維度的閾值判定。
"""


from life_capital.advisor.shared.evaluability import (
    EvaluabilityLevel,
    RecommendabilityLevel,
    evaluate_decision,
)


class TestRecommendability:
    """測試可推薦性判定"""

    def test_full_recommendable_ge_07(self):
        """≥0.7 為 FULL"""
        result = evaluate_decision(0.7)
        assert result.is_recommendable == RecommendabilityLevel.FULL

        result = evaluate_decision(0.85)
        assert result.is_recommendable == RecommendabilityLevel.FULL

        result = evaluate_decision(1.0)
        assert result.is_recommendable == RecommendabilityLevel.FULL

    def test_partial_recommendable_05_07(self):
        """0.5-0.7 為 PARTIAL"""
        result = evaluate_decision(0.5)
        assert result.is_recommendable == RecommendabilityLevel.PARTIAL

        result = evaluate_decision(0.6)
        assert result.is_recommendable == RecommendabilityLevel.PARTIAL

        result = evaluate_decision(0.69)
        assert result.is_recommendable == RecommendabilityLevel.PARTIAL

    def test_none_recommendable_lt_05(self):
        """<0.5 為 NONE"""
        result = evaluate_decision(0.49)
        assert result.is_recommendable == RecommendabilityLevel.NONE

        result = evaluate_decision(0.3)
        assert result.is_recommendable == RecommendabilityLevel.NONE

        result = evaluate_decision(0.0)
        assert result.is_recommendable == RecommendabilityLevel.NONE


class TestEvaluability:
    """測試可評估性判定"""

    def test_full_evaluable_ge_05(self):
        """≥0.5 為 FULL"""
        result = evaluate_decision(0.5)
        assert result.is_evaluable == EvaluabilityLevel.FULL

        result = evaluate_decision(0.7)
        assert result.is_evaluable == EvaluabilityLevel.FULL

        result = evaluate_decision(1.0)
        assert result.is_evaluable == EvaluabilityLevel.FULL

    def test_warning_evaluable_03_05(self):
        """0.3-0.5 為 WARNING"""
        result = evaluate_decision(0.3)
        assert result.is_evaluable == EvaluabilityLevel.WARNING

        result = evaluate_decision(0.4)
        assert result.is_evaluable == EvaluabilityLevel.WARNING

        result = evaluate_decision(0.49)
        assert result.is_evaluable == EvaluabilityLevel.WARNING

    def test_skip_evaluable_lt_03(self):
        """<0.3 為 SKIP"""
        result = evaluate_decision(0.29)
        assert result.is_evaluable == EvaluabilityLevel.SKIP

        result = evaluate_decision(0.1)
        assert result.is_evaluable == EvaluabilityLevel.SKIP

        result = evaluate_decision(0.0)
        assert result.is_evaluable == EvaluabilityLevel.SKIP


class TestWarningMessages:
    """測試警告訊息"""

    def test_warning_message_correct(self):
        """警告訊息正確"""
        result = evaluate_decision(0.7)
        assert result.warning_message is None

        result = evaluate_decision(0.6)
        assert result.warning_message == "部分可比：推薦結果僅供參考"

        result = evaluate_decision(0.4)
        assert result.warning_message == "低可比性：風險評估可能不準確"

        result = evaluate_decision(0.2)
        assert result.warning_message == "不可比：跳過風險與敏感度評估"


class TestBoundaries:
    """測試邊界值"""

    def test_boundary_070_is_full(self):
        """邊界 0.70 為 FULL"""
        result = evaluate_decision(0.70)
        assert result.is_recommendable == RecommendabilityLevel.FULL
        assert result.is_evaluable == EvaluabilityLevel.FULL
        assert result.warning_message is None

    def test_boundary_050_is_partial(self):
        """邊界 0.50 為 PARTIAL"""
        result = evaluate_decision(0.50)
        assert result.is_recommendable == RecommendabilityLevel.PARTIAL
        assert result.is_evaluable == EvaluabilityLevel.FULL
        assert result.warning_message == "部分可比：推薦結果僅供參考"

    def test_boundary_030_is_warning(self):
        """邊界 0.30 為 WARNING"""
        result = evaluate_decision(0.30)
        assert result.is_recommendable == RecommendabilityLevel.NONE
        assert result.is_evaluable == EvaluabilityLevel.WARNING
        assert result.warning_message == "低可比性：風險評估可能不準確"
