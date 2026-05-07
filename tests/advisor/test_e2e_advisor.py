"""Advisor E2E 整合測試（M9）

測試完整的 advisor 決策建議工作流程：
1. 原始財務資料 → ContextBuilder → RedactedDecisionContext
2. RedactedDecisionContext → DecisionComparator → ComparisonResult
3. ComparisonResult → ProposalGenerator → AdvisorProposalPayload
4. AdvisorProposalPayload → decisions_handler → canonical/decisions/

設計原則:
- 端對端驗證：模擬真實使用場景
- 5 模板 × 3 場景 = 15 個核心測試案例
- 覆蓋可比較、不可比較、極端風險三種情境

驗收標準（plan.md 7.1 節）:
- 每模板 9 案例：3 可比成功 + 3 不可比 + 3 極端風險
- 合計：5 模板 × 9 = 45 場景（此測試檔案覆蓋核心路徑）
"""

from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

import pytest

from life_capital.advisor.decision_comparator import ComparisonResult, DecisionComparator
from life_capital.advisor.proposal_generator import ProposalGenerator
from life_capital.advisor.schemas import (
    ADVISOR_SCHEMA_VERSION,
    AdvisorProposalPayload,
)
from life_capital.io.decisions_handler import (
    DecisionsHandler,
)
from life_capital.models.decisions import (
    ConfidenceLevel,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
    generate_decision_id,
)
from life_capital.models.operation import Operation, OperationType
from life_capital.privacy.redaction.decision_context import (
    RedactedDecisionContext,
    RedactedPresentationView,
)
from life_capital.privacy.redaction.engine import RedactionEngine

# === Test Fixtures ===

@pytest.fixture
def redaction_engine():
    """Redaction 引擎"""
    return RedactionEngine()


@pytest.fixture
def comparator():
    """決策比較器"""
    return DecisionComparator()


@pytest.fixture
def generator():
    """提案生成器"""
    return ProposalGenerator()


@pytest.fixture
def data_path(tmp_path):
    """臨時資料目錄"""
    return tmp_path


@pytest.fixture
def decisions_handler(data_path):
    """決策處理器"""
    return DecisionsHandler(data_path)


def make_operation(
    operation_type: OperationType = OperationType.APPLY,
    description: str = "E2E 測試操作",
) -> Operation:
    """建立測試用 Operation"""
    return Operation(
        operation_id=uuid4(),
        operation_type=operation_type,
        actor="e2e_test",
        target_path="canonical/decisions/decisions.yaml",
        description=description,
        created_at=datetime.now(),
    )


# === 財務資料 Fixtures ===

@pytest.fixture
def healthy_financial_data():
    """健康財務狀況（低風險）"""
    return {
        "monthly_income": 200000,
        "monthly_expense": 100000,  # 33% 儲蓄率
        "current_savings": 1200000,  # 12 個月跑道
        "expense_categories": {
            "food": 20000,
            "housing": 40000,
            "transport": 20000,
            "entertainment": 10000,
            "other": 10000,
        },
        "income_history": [145000, 200000, 148000, 152000, 200000, 155000],
        "monthly_balances": [50000, 45000, 48000, 52000, 50000, 55000],
        "consecutive_deficit_months": 0,
    }


@pytest.fixture
def moderate_financial_data():
    """中等財務狀況（中風險）"""
    return {
        "monthly_income": 100000,
        "monthly_expense": 60000,  # 15% 儲蓄率
        "current_savings": 300000,  # ~3.5 個月跑道
        "expense_categories": {
            "food": 20000,
            "housing": 35000,
            "transport": 12000,
            "entertainment": 8000,
            "other": 5000,
        },
        "income_history": [95000, 100000, 98000, 105000, 100000, 102000],
        "monthly_balances": [20000, 12000, 13000, 20000, 20000, 17000],
        "consecutive_deficit_months": 1,
    }


@pytest.fixture
def risky_financial_data():
    """高風險財務狀況"""
    return {
        "monthly_income": 80000,
        "monthly_expense": 90000,  # 赤字
        "current_savings": 100000,  # ~1 個月跑道
        "expense_categories": {
            "food": 30000,
            "housing": 35000,
            "transport": 20000,
            "entertainment": 5000,
            "other": 5000,
        },
        "income_history": [75000, 80000, 70000, 60000, 75000, 80000],  # 高波動
        "monthly_balances": [-10000, -5000, -20000, -2000, -8000, -10000],
        "consecutive_deficit_months": 3,
    }


# === E2E 工作流程測試 ===

class TestE2EWorkflow:
    """端對端工作流程測試"""

    def test_full_workflow_healthy_buying_house(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        healthy_financial_data: Dict[str, Any],
    ):
        """健康財務狀況 + 買房決策的完整流程"""
        # Step 1: Redaction
        redaction_result = redaction_engine.redact(healthy_financial_data)
        context = redaction_result.context

        # 驗證：隱私已保護
        assert isinstance(context, RedactedDecisionContext)
        assert "200000" not in str(context)

        # Step 2: Compare
        comparison = comparator.compare(context, template_id="buying_house")

        # 驗證：產生可比較結果
        assert isinstance(comparison, ComparisonResult)
        assert comparison.is_comparable is True
        assert comparison.comparability_score >= 0.6
        assert comparison.option_a.status == "comparable"
        assert comparison.option_b.status == "comparable"

        # Step 3: Generate Proposal
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="buying_house",
        )

        # 驗證：Payload 完整
        assert isinstance(payload, AdvisorProposalPayload)
        assert payload.schema_version == ADVISOR_SCHEMA_VERSION
        assert payload.source == "advisor"
        assert payload.is_comparable is True
        assert payload.option_a.direction == "conservative"
        assert payload.option_b.direction == "aggressive"
        assert len(payload.operation_id) > 0
        assert len(payload.input_hash) == 16

    def test_full_workflow_risky_investment(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        risky_financial_data: Dict[str, Any],
    ):
        """高風險財務狀況 + 投資決策的完整流程"""
        # Step 1: Redaction
        redaction_result = redaction_engine.redact(risky_financial_data)
        context = redaction_result.context

        # Step 2: Compare
        comparison = comparator.compare(context, template_id="investment")

        # 驗證：高風險應有風險標籤
        assert len(comparison.risk_tags) > 0
        assert any("deficit" in tag or "runway" in tag for tag in comparison.risk_tags)

        # Step 3: Generate Proposal
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="investment",
        )

        # 驗證：仍產生 2 選項
        assert payload.option_a is not None
        assert payload.option_b is not None
        assert len(payload.risk_explanation) > 0

    def test_workflow_with_decisions_handler(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        decisions_handler: DecisionsHandler,
        healthy_financial_data: Dict[str, Any],
    ):
        """完整流程 + 決策記錄寫入"""
        # Step 1-3: 生成 Payload
        redaction_result = redaction_engine.redact(healthy_financial_data)
        context = redaction_result.context
        comparison = comparator.compare(context, template_id="buying_house")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="buying_house",
        )

        # Step 4: 轉換為 DecisionRecord 並寫入
        record = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=payload.operation_id,
            created_at=datetime.now().isoformat(),
            template_id=payload.template_id,
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.HIGH if payload.is_comparable else ConfidenceLevel.LOW,
            comparability_score=payload.comparability_score,
            input_hash=payload.input_hash,
            option_a=DecisionOption(
                direction=payload.option_a.direction,
                label=payload.option_a.label,
                recommendation=payload.option_a.recommendation,
                score=payload.option_a.score,
                status=payload.option_a.status,
            ),
            option_b=DecisionOption(
                direction=payload.option_b.direction,
                label=payload.option_b.label,
                recommendation=payload.option_b.recommendation,
                score=payload.option_b.score,
                status=payload.option_b.status,
            ),
            risk_tags=list(payload.risk_tags),
            risk_explanation=payload.risk_explanation,
        )

        operation = make_operation()
        decision_id = decisions_handler.write_decision(record, operation)

        # 驗證：可讀取
        loaded = decisions_handler.get_by_decision_id(decision_id)
        assert loaded is not None
        assert loaded.template_id == "buying_house"
        assert loaded.comparability_score == payload.comparability_score


# === 5 模板 × 3 場景測試 ===

class TestTemplateScenarios:
    """5 模板 × 3 場景測試"""

    TEMPLATES = ["buying_house", "investment", "car_purchase", "travel", "savings_target"]

    @pytest.mark.parametrize("template_id", TEMPLATES)
    def test_comparable_scenario(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        healthy_financial_data: Dict[str, Any],
        template_id: str,
    ):
        """可比較場景（健康財務）"""
        # 執行流程
        context = redaction_engine.redact(healthy_financial_data).context
        comparison = comparator.compare(context, template_id=template_id)
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id=template_id,
        )

        # 驗證
        assert comparison.is_comparable is True
        assert comparison.option_a.status == "comparable"
        assert comparison.option_b.status == "comparable"
        assert payload.option_a.recommendation is not None
        assert payload.option_b.recommendation is not None

    @pytest.mark.parametrize("template_id", TEMPLATES)
    def test_moderate_risk_scenario(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        moderate_financial_data: Dict[str, Any],
        template_id: str,
    ):
        """中等風險場景"""
        # 執行流程
        context = redaction_engine.redact(moderate_financial_data).context
        comparison = comparator.compare(context, template_id=template_id)
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id=template_id,
        )

        # 驗證：仍產生 2 選項
        assert payload.option_a is not None
        assert payload.option_b is not None
        # 驗證：模板 ID 正確
        assert payload.template_id == template_id

    @pytest.mark.parametrize("template_id", TEMPLATES)
    def test_extreme_risk_scenario(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        risky_financial_data: Dict[str, Any],
        template_id: str,
    ):
        """極端風險場景"""
        # 執行流程
        context = redaction_engine.redact(risky_financial_data).context
        comparison = comparator.compare(context, template_id=template_id)
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id=template_id,
        )

        # 驗證：仍產生 2 選項（核心契約）
        assert payload.option_a is not None
        assert payload.option_b is not None
        assert payload.option_a.direction == "conservative"
        assert payload.option_b.direction == "aggressive"

        # 驗證：有風險說明
        assert len(payload.risk_tags) > 0 or len(payload.risk_explanation) > 0


# === 契約驗證測試 ===

class TestOutputContractCompliance:
    """驗證輸出符合 plan.md 定義的契約"""

    def test_always_two_options(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
    ):
        """永遠輸出 2 個選項"""
        # 測試各種資料
        test_cases = [
            {"monthly_income": 100000, "monthly_expense": 80000},  # 正常
            {"monthly_income": 50000, "monthly_expense": 80000},   # 赤字
            {},  # 空資料
        ]

        for data in test_cases:
            context = redaction_engine.redact(data).context
            comparison = comparator.compare(context, template_id="default")
            payload = generator.generate(
                comparison_result=comparison,
                redacted_context=context,
                template_id="default",
            )

            # 核心契約：永遠 2 選項
            assert payload.option_a is not None
            assert payload.option_b is not None
            assert payload.option_a.direction == "conservative"
            assert payload.option_b.direction == "aggressive"

    def test_option_status_values(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        healthy_financial_data: Dict[str, Any],
    ):
        """選項狀態值符合契約"""
        context = redaction_engine.redact(healthy_financial_data).context
        comparison = comparator.compare(context, template_id="buying_house")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="buying_house",
        )

        # 狀態值必須是定義的列舉
        valid_statuses = {"comparable", "not_comparable", "partial"}
        assert payload.option_a.status in valid_statuses
        assert payload.option_b.status in valid_statuses

    def test_comparability_threshold(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        healthy_financial_data: Dict[str, Any],
    ):
        """可比較性閾值為 0.6"""
        context = redaction_engine.redact(healthy_financial_data).context
        comparison = comparator.compare(context, template_id="buying_house")

        # 契約：score >= 0.6 → is_comparable = True
        if comparison.comparability_score >= 0.6:
            assert comparison.is_comparable is True
        else:
            assert comparison.is_comparable is False

    def test_blocking_details_structure(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        risky_financial_data: Dict[str, Any],
    ):
        """阻擋詳情結構正確"""
        context = redaction_engine.redact(risky_financial_data).context
        comparison = comparator.compare(context, template_id="buying_house")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="buying_house",
        )

        # 若有阻擋詳情，結構應正確
        for detail in payload.blocking_details:
            assert hasattr(detail, "code")
            assert hasattr(detail, "message")
            assert hasattr(detail, "severity")
            assert detail.severity in ("blocking", "warning")

    def test_input_hash_format(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        healthy_financial_data: Dict[str, Any],
    ):
        """input_hash 格式為 16 字元"""
        context = redaction_engine.redact(healthy_financial_data).context
        comparison = comparator.compare(context, template_id="buying_house")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="buying_house",
        )

        assert len(payload.input_hash) == 16
        # 應為十六進位字元
        assert all(c in "0123456789abcdef" for c in payload.input_hash)

    def test_operation_id_format(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        healthy_financial_data: Dict[str, Any],
    ):
        """operation_id 為非空字串"""
        context = redaction_engine.redact(healthy_financial_data).context
        comparison = comparator.compare(context, template_id="buying_house")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="buying_house",
        )

        assert len(payload.operation_id) > 0
        assert isinstance(payload.operation_id, str)


# === 隱私保護驗證 ===

class TestPrivacyInE2E:
    """E2E 流程中的隱私保護驗證"""

    def test_no_pii_in_final_output(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
    ):
        """最終輸出不包含 PII"""
        data_with_pii = {
            "user_name": "王小明",
            "email": "wang@example.com",
            "phone": "0912345678",
            "monthly_income": 100000,
            "monthly_expense": 80000,
        }

        context = redaction_engine.redact(data_with_pii).context
        comparison = comparator.compare(context, template_id="default")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="default",
        )

        # 轉為字典檢查
        payload_dict = payload.to_dict()
        payload_str = str(payload_dict)

        assert "王小明" not in payload_str
        assert "wang@example.com" not in payload_str
        assert "0912345678" not in payload_str

    def test_no_exact_amounts_in_output(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
    ):
        """最終輸出不包含精確金額"""
        data = {
            "monthly_income": 123456,
            "monthly_expense": 98765,
            "savings": 987654,
        }

        context = redaction_engine.redact(data).context
        comparison = comparator.compare(context, template_id="default")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="default",
        )

        payload_str = str(payload.to_dict())

        assert "123456" not in payload_str
        assert "98765" not in payload_str
        assert "987654" not in payload_str


# === 決策記憶整合測試 ===

class TestDecisionMemoryIntegration:
    """決策記憶整合測試"""

    def test_write_and_read_decision(
        self,
        decisions_handler: DecisionsHandler,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        healthy_financial_data: Dict[str, Any],
    ):
        """寫入並讀取決策記錄"""
        # 生成 Payload
        context = redaction_engine.redact(healthy_financial_data).context
        comparison = comparator.compare(context, template_id="buying_house")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="buying_house",
        )

        # 轉換並寫入
        record = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=payload.operation_id,
            created_at=datetime.now().isoformat(),
            template_id=payload.template_id,
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.HIGH,
            comparability_score=payload.comparability_score,
            input_hash=payload.input_hash,
            option_a=DecisionOption(
                direction=payload.option_a.direction,
                label=payload.option_a.label,
            ),
            option_b=DecisionOption(
                direction=payload.option_b.direction,
                label=payload.option_b.label,
            ),
            risk_tags=list(payload.risk_tags),
            risk_explanation=payload.risk_explanation,
        )

        operation = make_operation()
        decision_id = decisions_handler.write_decision(record, operation)

        # 讀取驗證
        loaded = decisions_handler.get_by_decision_id(decision_id)
        assert loaded is not None
        assert loaded.template_id == "buying_house"
        assert loaded.option_a.direction == "conservative"
        assert loaded.option_b.direction == "aggressive"

    def test_multiple_decisions_query(
        self,
        decisions_handler: DecisionsHandler,
    ):
        """多筆決策記錄查詢"""
        # 寫入多筆記錄
        templates = ["buying_house", "investment", "car_purchase"]

        for template_id in templates:
            record = DecisionRecord(
                decision_id=generate_decision_id(),
                operation_id=str(uuid4()),
                created_at=datetime.now().isoformat(),
                template_id=template_id,
                status=DecisionStatus.APPLIED,
                confidence=ConfidenceLevel.MEDIUM,
                comparability_score=0.75,
                input_hash="abc123def456gh",
                option_a=DecisionOption(direction="conservative", label="A"),
                option_b=DecisionOption(direction="aggressive", label="B"),
                risk_tags=[],
                risk_explanation="",
            )
            decisions_handler.write_decision(record, make_operation())

        # 查詢
        all_records = decisions_handler.read_all()
        assert len(all_records) == 3

        buying_house = decisions_handler.get_by_template("buying_house")
        assert len(buying_house) == 1

    def test_decision_revert_workflow(
        self,
        decisions_handler: DecisionsHandler,
    ):
        """決策回滾工作流程"""
        # 寫入決策
        record = DecisionRecord(
            decision_id=generate_decision_id(),
            operation_id=str(uuid4()),
            created_at=datetime.now().isoformat(),
            template_id="investment",
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.HIGH,
            comparability_score=0.8,
            input_hash="revert_test_123",
            option_a=DecisionOption(direction="conservative", label="A"),
            option_b=DecisionOption(direction="aggressive", label="B"),
            risk_tags=[],
            risk_explanation="",
        )
        operation = make_operation()
        decision_id = decisions_handler.write_decision(record, operation)

        # 回滾
        revert_operation = make_operation(
            operation_type=OperationType.UNDO,
            description="回滾投資決策",
        )
        reverted = decisions_handler.mark_reverted(decision_id, revert_operation)

        # 驗證：append-only
        all_records = decisions_handler.read_all()
        assert len(all_records) == 2  # 原記錄 + 回滾記錄

        # 驗證：回滾記錄狀態
        assert reverted.status == DecisionStatus.REVERTED
        assert reverted.reverted_at is not None

        # 驗證：原記錄仍可查詢
        original = decisions_handler.get_by_decision_id(decision_id)
        assert original is not None

        # 驗證：get_active_records 排除回滾
        active = decisions_handler.get_active_records()
        assert len(active) == 1  # 只有原記錄


# === Presentation View 測試 ===

class TestPresentationView:
    """Presentation View 生成測試"""

    def test_create_presentation_view(
        self,
        redaction_engine: RedactionEngine,
        healthy_financial_data: Dict[str, Any],
    ):
        """建立 Presentation View"""
        result = redaction_engine.redact(healthy_financial_data)
        view = redaction_engine.create_presentation_view(result.context)

        assert isinstance(view, RedactedPresentationView)
        assert len(view.summary_text) > 0
        assert view.context is not None

    def test_presentation_view_content(
        self,
        redaction_engine: RedactionEngine,
        risky_financial_data: Dict[str, Any],
    ):
        """Presentation View 內容正確"""
        result = redaction_engine.redact(risky_financial_data)
        view = redaction_engine.create_presentation_view(result.context)

        # 高風險應有相應描述
        assert "風險" in view.summary_text or "高" in view.summary_text


# === 邊界條件測試 ===

class TestEdgeCases:
    """邊界條件測試"""

    def test_empty_data_workflow(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
    ):
        """空資料的完整流程"""
        context = redaction_engine.redact({}).context
        comparison = comparator.compare(context, template_id="default")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="default",
        )

        # 仍應產生有效輸出
        assert payload.option_a is not None
        assert payload.option_b is not None

    def test_unknown_template_fallback(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        healthy_financial_data: Dict[str, Any],
    ):
        """未知模板應 fallback 到 default"""
        context = redaction_engine.redact(healthy_financial_data).context
        comparison = comparator.compare(context, template_id="unknown_template")
        payload = generator.generate(
            comparison_result=comparison,
            redacted_context=context,
            template_id="unknown_template",
        )

        # 仍應產生有效輸出
        assert payload.option_a is not None
        assert payload.option_b is not None
        assert payload.template_id == "unknown_template"

    def test_deterministic_output(
        self,
        redaction_engine: RedactionEngine,
        comparator: DecisionComparator,
        generator: ProposalGenerator,
        healthy_financial_data: Dict[str, Any],
    ):
        """相同輸入產生相同輸出（除時間戳）"""
        context = redaction_engine.redact(healthy_financial_data).context

        # 執行兩次
        comparison1 = comparator.compare(context, template_id="buying_house")
        comparison2 = comparator.compare(context, template_id="buying_house")

        # 比較核心欄位
        assert comparison1.comparability_score == comparison2.comparability_score
        assert comparison1.is_comparable == comparison2.is_comparable
        assert comparison1.option_a.direction == comparison2.option_a.direction
        assert comparison1.option_b.direction == comparison2.option_b.direction
        assert comparison1.risk_tags == comparison2.risk_tags
