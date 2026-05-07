"""Advisor Schemas 測試

測試 advisor/schemas.py 的 DTO 結構與契約驗證。
"""


import pytest

from life_capital.advisor.schemas import (
    ADVISOR_SCHEMA_VERSION,
    AdvisorProposalPayload,
    BlockingReasonDetail,
    DecisionOptionSchema,
    RequiredInputSchema,
    compute_input_hash,
    extract_schema_fields,
    generate_operation_id,
)


class TestDecisionOptionSchema:
    """DecisionOptionSchema 測試"""

    def test_create_comparable_option(self):
        """測試建立可比較選項"""
        option = DecisionOptionSchema(
            direction="conservative",
            label="方案 A：延後購房",
            recommendation="建議延後 6 個月",
            score=0.75,
            status="comparable",
        )
        assert option.direction == "conservative"
        assert option.status == "comparable"
        assert option.score == 0.75

    def test_create_not_comparable_option(self):
        """測試建立不可比較選項"""
        option = DecisionOptionSchema(
            direction="aggressive",
            label="方案 B：現在購房",
            status="not_comparable",
            to_comparable_guidance="需補充收入資料",
        )
        assert option.status == "not_comparable"
        assert option.score is None
        assert option.to_comparable_guidance is not None

    def test_direction_values(self):
        """測試方向值限制"""
        for direction in ["conservative", "aggressive"]:
            option = DecisionOptionSchema(
                direction=direction,
                label="Test",
                status="comparable",
            )
            assert option.direction == direction

    def test_status_values(self):
        """測試狀態值限制"""
        for status in ["comparable", "not_comparable", "partial"]:
            option = DecisionOptionSchema(
                direction="conservative",
                label="Test",
                status=status,
            )
            assert option.status == status


class TestBlockingReasonDetail:
    """BlockingReasonDetail 測試"""

    def test_create_blocking_reason(self):
        """測試建立阻擋原因"""
        reason = BlockingReasonDetail(
            code="TIME_HORIZON_INSUFFICIENT",
            message="財務跑道不足",
            severity="blocking",
            affected_segments=["首付階段"],
        )
        assert reason.code == "TIME_HORIZON_INSUFFICIENT"
        assert reason.severity == "blocking"
        assert len(reason.affected_segments) == 1

    def test_warning_severity(self):
        """測試警告級別"""
        reason = BlockingReasonDetail(
            code="SEGMENT_WARNING",
            message="時段評估偏低",
            severity="warning",
        )
        assert reason.severity == "warning"


class TestRequiredInputSchema:
    """RequiredInputSchema 測試"""

    def test_create_required_input(self):
        """測試建立必要輸入"""
        req = RequiredInputSchema(
            field="monthly_income",
            reason="計算貸款承受力",
            priority="required",
        )
        assert req.field == "monthly_income"
        assert req.priority == "required"

    def test_optional_priority(self):
        """測試可選優先級"""
        req = RequiredInputSchema(
            field="bonus_income",
            reason="更精確的收入估算",
            priority="optional",
        )
        assert req.priority == "optional"


class TestAdvisorProposalPayload:
    """AdvisorProposalPayload 測試"""

    @pytest.fixture
    def sample_options(self):
        """建立範例選項"""
        option_a = DecisionOptionSchema(
            direction="conservative",
            label="方案 A",
            status="comparable",
            score=0.7,
        )
        option_b = DecisionOptionSchema(
            direction="aggressive",
            label="方案 B",
            status="comparable",
            score=0.6,
        )
        return option_a, option_b

    def test_create_comparable_payload(self, sample_options):
        """測試建立可比較的 payload"""
        option_a, option_b = sample_options
        payload = AdvisorProposalPayload(
            operation_id=generate_operation_id(),
            comparability_score=0.75,
            is_comparable=True,
            option_a=option_a,
            option_b=option_b,
            risk_tags=["short_runway"],
            risk_explanation="緊急備用金約 5 個月",
            input_hash=compute_input_hash({"test": "data"}, "buying_house"),
            template_id="buying_house",
        )
        assert payload.is_comparable is True
        assert payload.schema_version == ADVISOR_SCHEMA_VERSION
        assert len(payload.blocking_reasons) == 0

    def test_create_not_comparable_payload(self, sample_options):
        """測試建立不可比較的 payload"""
        option_a, option_b = sample_options
        blocking = [
            BlockingReasonDetail(
                code="MISSING_DATA",
                message="缺少收入資料",
                severity="blocking",
            )
        ]
        payload = AdvisorProposalPayload(
            operation_id=generate_operation_id(),
            comparability_score=0.4,
            is_comparable=False,
            option_a=option_a,
            option_b=option_b,
            risk_tags=[],
            risk_explanation="",
            blocking_details=blocking,
            required_inputs=[
                RequiredInputSchema(
                    field="income",
                    reason="計算",
                    priority="required",
                )
            ],
            input_hash=compute_input_hash({}, "default"),
            template_id="default",
        )
        assert payload.is_comparable is False
        assert len(payload.blocking_reasons) == 1
        assert len(payload.required_inputs) == 1


class TestHelperFunctions:
    """輔助函式測試"""

    def test_compute_input_hash_deterministic(self):
        """測試 input_hash 確定性"""
        data = {"income": 100000, "expenses": 80000}
        template = "buying_house"

        hash1 = compute_input_hash(data, template)
        hash2 = compute_input_hash(data, template)

        assert hash1 == hash2
        assert len(hash1) == 16

    def test_compute_input_hash_different_data(self):
        """測試不同輸入產生不同 hash"""
        data1 = {"income": 100000}
        data2 = {"income": 120000}

        hash1 = compute_input_hash(data1, "default")
        hash2 = compute_input_hash(data2, "default")

        assert hash1 != hash2

    def test_generate_operation_id_format(self):
        """測試 operation_id 格式"""
        op_id = generate_operation_id()

        # 應為 26 字元的 ULID 格式
        assert len(op_id) == 26
        assert op_id.isalnum()

    def test_generate_operation_id_unique(self):
        """測試 operation_id 唯一性"""
        ids = [generate_operation_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_extract_schema_fields(self):
        """測試 schema 欄位抽取"""
        fields = extract_schema_fields(AdvisorProposalPayload)

        assert "schema_version" in fields["required_fields"]
        assert "operation_id" in fields["required_fields"]
        assert "option_a" in fields["required_fields"]
        assert "option_b" in fields["required_fields"]
