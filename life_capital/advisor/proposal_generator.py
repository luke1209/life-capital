"""提案生成器

從 DecisionComparator 輸出生成 AdvisorProposalPayload。

設計原則:
- 單一職責：只負責組裝輸出 Schema
- 純函式：無 I/O，無副作用
- 追蹤性：自動生成 operation_id 與 input_hash

使用方式:
    generator = ProposalGenerator()
    payload = generator.generate(
        comparison_result=result,
        redacted_context=context,
        template_id="buying_house"
    )
"""

from typing import Optional

from life_capital.advisor.decision_comparator import (
    ComparisonResult,
    DecisionComparator,
)
from life_capital.advisor.schemas import (
    AdvisorProposalPayload,
    RequiredInputSchema,
    compute_input_hash,
    generate_operation_id,
)
from life_capital.privacy.redaction.decision_context import RedactedDecisionContext


class ProposalGenerator:
    """提案生成器

    從決策比較結果生成完整的 AdvisorProposalPayload。

    使用方式:
        generator = ProposalGenerator()
        payload = generator.generate(
            comparison_result=result,
            redacted_context=context,
            template_id="buying_house"
        )
    """

    def __init__(self, comparator_version: str = "1.0"):
        """初始化生成器

        Args:
            comparator_version: 比較器版本號
        """
        self.comparator_version = comparator_version

    def generate(
        self,
        comparison_result: ComparisonResult,
        redacted_context: RedactedDecisionContext,
        template_id: str,
        operation_id: Optional[str] = None,
    ) -> AdvisorProposalPayload:
        """生成提案 Payload

        Args:
            comparison_result: 決策比較結果
            redacted_context: 去識別化的決策上下文
            template_id: 使用的模板 ID
            operation_id: 可選的操作 ID（未提供則自動生成）

        Returns:
            完整的 AdvisorProposalPayload
        """
        # 生成 operation_id
        op_id = operation_id or generate_operation_id()

        # 計算 input_hash
        context_dict = self._context_to_dict(redacted_context)
        input_hash = compute_input_hash(
            redacted_context=context_dict,
            template_id=template_id,
            comparator_version=self.comparator_version,
        )

        # 轉換選項
        option_a = comparison_result.option_a.to_schema()
        option_b = comparison_result.option_b.to_schema()

        # 轉換阻擋詳情
        blocking_details = tuple(comparison_result.blocking_details)

        # 生成補件需求
        required_inputs = self._generate_required_inputs(
            comparison_result.weak_dimensions,
            template_id,
        )

        return AdvisorProposalPayload(
            operation_id=op_id,
            comparability_score=comparison_result.comparability_score,
            is_comparable=comparison_result.is_comparable,
            option_a=option_a,
            option_b=option_b,
            risk_tags=tuple(comparison_result.risk_tags),
            risk_explanation=comparison_result.risk_explanation,
            input_hash=input_hash,
            template_id=template_id,
            blocking_details=blocking_details,
            required_inputs=tuple(required_inputs),
            comparator_version=self.comparator_version,
        )

    def generate_from_context(
        self,
        redacted_context: RedactedDecisionContext,
        template_id: str = "default",
        operation_id: Optional[str] = None,
    ) -> AdvisorProposalPayload:
        """從上下文直接生成提案

        便捷方法，內部調用 DecisionComparator。

        Args:
            redacted_context: 去識別化的決策上下文
            template_id: 使用的模板 ID
            operation_id: 可選的操作 ID

        Returns:
            完整的 AdvisorProposalPayload
        """
        comparator = DecisionComparator()
        comparison_result = comparator.compare(redacted_context, template_id)

        return self.generate(
            comparison_result=comparison_result,
            redacted_context=redacted_context,
            template_id=template_id,
            operation_id=operation_id,
        )

    def _context_to_dict(self, context: RedactedDecisionContext) -> dict:
        """將上下文轉換為字典

        Args:
            context: 去識別化的決策上下文

        Returns:
            字典格式的上下文
        """
        return {
            "expense_distribution": context.expense_distribution,
            "deficit_month_count": context.deficit_month_count,
            "runway_months": context.runway_months,
            "consecutive_deficit_months": context.consecutive_deficit_months,
            "income_volatility": context.income_volatility,
            "savings_rate_band": context.savings_rate_band,
            "expense_trend": context.expense_trend,
            "field_provenance": context.field_provenance,
        }

    def _generate_required_inputs(
        self,
        weak_dimensions: list,
        template_id: str,
    ) -> list:
        """生成補件需求

        Args:
            weak_dimensions: 弱維度列表
            template_id: 模板 ID

        Returns:
            RequiredInputSchema 列表
        """
        inputs = []

        dimension_requirements = {
            "time_horizon": RequiredInputSchema(
                field="runway_months",
                reason="確認財務跑道以評估決策時間範圍",
                priority="required",
            ),
            "risk_tolerance": RequiredInputSchema(
                field="income_volatility",
                reason="評估收入穩定度以判斷風險承受能力",
                priority="required",
            ),
            "liquidity": RequiredInputSchema(
                field="savings_rate_band",
                reason="確認儲蓄率以評估流動性需求",
                priority="required",
            ),
            "capital_need": RequiredInputSchema(
                field="expense_distribution",
                reason="確認支出結構以評估資金需求",
                priority="optional",
            ),
        }

        for dim in weak_dimensions:
            if dim in dimension_requirements:
                inputs.append(dimension_requirements[dim])

        # 模板特定需求
        if template_id == "buying_house":
            if "time_horizon" in weak_dimensions:
                inputs.append(RequiredInputSchema(
                    field="target_downpayment",
                    reason="確認首付目標金額以規劃準備期",
                    priority="optional",
                ))
        elif template_id == "investment":
            if "risk_tolerance" in weak_dimensions:
                inputs.append(RequiredInputSchema(
                    field="investment_experience",
                    reason="確認投資經驗以評估風險承受度",
                    priority="optional",
                ))

        return inputs
