"""測試風險評估器

驗證風險等級計算與可評估性整合。
"""


from life_capital.advisor.risk_assessor import assess_risk
from life_capital.models.decisions import (
    ConfidenceLevel,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
)


def create_test_decision(
    comparability_score: float, risk_tags: list[str]
) -> DecisionRecord:
    """建立測試用決策記錄"""
    return DecisionRecord(
        decision_id="dec_TEST123",
        operation_id="op_TEST456",
        created_at="2024-12-29T10:00:00Z",
        template_id="tmpl_housing",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.MEDIUM,
        comparability_score=comparability_score,
        input_hash="abc123def456",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
            recommendation="保守建議",
        ),
        option_b=DecisionOption(
            direction="aggressive", label="方案 B", recommendation="進取建議"
        ),
        risk_tags=risk_tags,
        risk_explanation="測試風險說明",
    )


class TestRiskLevelCalculation:
    """測試風險等級計算"""

    def test_assess_risk_high_level(self):
        """≥3 tags 為 high"""
        decision = create_test_decision(
            0.7, ["流動性風險", "市場風險", "信用風險"]
        )
        assessment = assess_risk(decision)

        assert assessment is not None
        assert assessment.risk_level == "high"
        assert assessment.decision_id == "dec_TEST123"

    def test_assess_risk_medium_level(self):
        """1-2 tags 為 medium"""
        decision = create_test_decision(0.7, ["流動性風險"])
        assessment = assess_risk(decision)
        assert assessment is not None
        assert assessment.risk_level == "medium"

        decision = create_test_decision(0.7, ["流動性風險", "市場風險"])
        assessment = assess_risk(decision)
        assert assessment is not None
        assert assessment.risk_level == "medium"

    def test_assess_risk_low_level(self):
        """0 tags 為 low"""
        decision = create_test_decision(0.7, [])
        assessment = assess_risk(decision)

        assert assessment is not None
        assert assessment.risk_level == "low"


class TestEvaluabilityIntegration:
    """測試可評估性整合"""

    def test_assess_risk_skip_lt_03(self):
        """<0.3 返回 None"""
        decision = create_test_decision(0.2, ["流動性風險"])
        assessment = assess_risk(decision)

        assert assessment is None

    def test_assess_risk_warning_added(self):
        """WARNING 等級加警告"""
        decision = create_test_decision(0.4, ["流動性風險"])
        assessment = assess_risk(decision)

        assert assessment is not None
        assert len(assessment.warnings) == 1
        assert "低可比性" in assessment.warnings[0]

    def test_assess_risk_no_warning_full(self):
        """FULL 等級無警告"""
        decision = create_test_decision(0.7, ["流動性風險"])
        assessment = assess_risk(decision)

        assert assessment is not None
        assert len(assessment.warnings) == 0


class TestRiskAssessmentContent:
    """測試評估內容保留"""

    def test_risk_tags_preserved(self):
        """risk_tags 保留"""
        tags = ["流動性風險", "市場風險"]
        decision = create_test_decision(0.7, tags)
        assessment = assess_risk(decision)

        assert assessment is not None
        assert assessment.risk_tags == tags

    def test_risk_explanation_preserved(self):
        """risk_explanation 保留"""
        decision = create_test_decision(0.7, ["流動性風險"])
        assessment = assess_risk(decision)

        assert assessment is not None
        assert assessment.risk_explanation == "測試風險說明"
