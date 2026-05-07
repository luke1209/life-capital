"""測試風險矩陣生成器

驗證風險矩陣 JSON 輸出格式與統計正確性。
"""

import json

import pytest

from life_capital.generation.risk_matrix import (
    generate_risk_matrix,
    save_risk_matrix,
)
from life_capital.models.decisions import (
    ConfidenceLevel,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
)


def create_test_decision(
    decision_id: str,
    status: DecisionStatus,
    comparability_score: float,
    risk_tags: list[str],
) -> DecisionRecord:
    """建立測試用決策記錄"""
    return DecisionRecord(
        decision_id=decision_id,
        operation_id=f"op_{decision_id}",
        created_at="2024-12-29T10:00:00Z",
        template_id="tmpl_housing",
        status=status,
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


@pytest.fixture
def test_decisions():
    """建立測試用決策列表"""
    return [
        # High risk (3 tags, evaluated)
        create_test_decision(
            "dec_001",
            DecisionStatus.APPLIED,
            0.7,
            ["流動性風險", "市場風險", "信用風險"],
        ),
        # Medium risk (1 tag, evaluated)
        create_test_decision(
            "dec_002", DecisionStatus.PENDING, 0.6, ["流動性風險"]
        ),
        # Low risk (0 tags, evaluated)
        create_test_decision("dec_003", DecisionStatus.APPLIED, 0.8, []),
        # Skipped (score < 0.3)
        create_test_decision(
            "dec_004", DecisionStatus.PENDING, 0.2, ["流動性風險"]
        ),
        # Reverted (should be filtered out)
        create_test_decision(
            "dec_005", DecisionStatus.REVERTED, 0.7, ["市場風險"]
        ),
    ]


class TestMatrixStructure:
    """測試矩陣結構"""

    def test_matrix_has_required_keys(self, test_decisions, tmp_path):
        """包含必要鍵"""
        matrix = generate_risk_matrix(test_decisions, tmp_path)

        required_keys = [
            "generated_at",
            "total_decisions",
            "assessed_count",
            "skipped_count",
            "risk_distribution",
            "assessments",
        ]

        for key in required_keys:
            assert key in matrix

    def test_risk_distribution_correct(self, test_decisions, tmp_path):
        """統計正確"""
        matrix = generate_risk_matrix(test_decisions, tmp_path)

        # 預期: 1 high, 1 medium, 1 low
        assert matrix["risk_distribution"]["high"] == 1
        assert matrix["risk_distribution"]["medium"] == 1
        assert matrix["risk_distribution"]["low"] == 1

    def test_skipped_count_correct(self, test_decisions, tmp_path):
        """跳過計數正確"""
        matrix = generate_risk_matrix(test_decisions, tmp_path)

        # 預期: 4 個 active（排除 reverted）, 3 個評估, 1 個跳過
        assert matrix["total_decisions"] == 4
        assert matrix["assessed_count"] == 3
        assert matrix["skipped_count"] == 1


class TestAssessmentsList:
    """測試評估列表"""

    def test_assessments_list_valid(self, test_decisions, tmp_path):
        """assessments 列表合法"""
        matrix = generate_risk_matrix(test_decisions, tmp_path)

        assessments = matrix["assessments"]
        assert len(assessments) == 3

        for assessment in assessments:
            assert "decision_id" in assessment
            assert "risk_level" in assessment
            assert "risk_tags" in assessment
            assert "risk_explanation" in assessment
            assert "warnings" in assessment
            assert assessment["risk_level"] in ["low", "medium", "high"]


class TestSaveRiskMatrix:
    """測試儲存功能"""

    def test_save_risk_matrix_creates_file(self, test_decisions, tmp_path):
        """save 建立檔案"""
        data_path = tmp_path / "data"
        data_path.mkdir()
        (data_path / "canonical" / "decisions").mkdir(parents=True)
        (data_path / "derived" / "advisor").mkdir(parents=True)

        file_path = save_risk_matrix(test_decisions, data_path)

        assert file_path.exists()
        assert file_path.suffix == ".json"
        assert "risk_matrix" in file_path.name

    def test_save_risk_matrix_provenance(self, test_decisions, tmp_path):
        """Provenance 正確"""
        data_path = tmp_path / "data"
        data_path.mkdir()
        (data_path / "canonical" / "decisions").mkdir(parents=True)
        (data_path / "derived" / "advisor").mkdir(parents=True)

        file_path = save_risk_matrix(test_decisions, data_path)
        meta_path = file_path.with_suffix(".json.meta.json")

        assert meta_path.exists()

        with open(meta_path, "r") as f:
            provenance = json.load(f)

        assert provenance["artifact_type"] == "risk_matrix"
        assert provenance["calc_version"] == "risk_v1.0"
        assert len(provenance["input_hash"]) == 64
        assert len(provenance["content_hash"]) == 64
        assert "canonical/decisions/decisions.yaml" in provenance[
            "canonical_sources"
        ]
