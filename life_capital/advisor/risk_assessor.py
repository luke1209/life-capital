"""風險評估器

分析決策的風險並生成評估報告。

使用方式:
    from life_capital.advisor.risk_assessor import assess_risk

    assessment = assess_risk(decision)
"""

from dataclasses import dataclass
from typing import Optional

from life_capital.advisor.shared.evaluability import (
    EvaluabilityLevel,
    evaluate_decision,
)
from life_capital.models.decisions import DecisionRecord


@dataclass(frozen=True)
class RiskAssessment:
    """風險評估結果"""

    decision_id: str
    risk_level: str  # "low" | "medium" | "high"
    risk_tags: list[str]
    risk_explanation: str
    warnings: list[str]  # 可評估性警告


def assess_risk(decision: DecisionRecord) -> Optional[RiskAssessment]:
    """評估決策風險

    Args:
        decision: 決策記錄

    Returns:
        RiskAssessment 或 None（若不可評估）
    """
    # 使用 shared evaluability 模組判定
    eval_result = evaluate_decision(decision.comparability_score)

    # 若不可評估，返回 None
    if eval_result.is_evaluable == EvaluabilityLevel.SKIP:
        return None

    # 計算風險等級（基於 risk_tags 數量）
    risk_tag_count = len(decision.risk_tags)
    if risk_tag_count >= 3:
        risk_level = "high"
    elif risk_tag_count >= 1:
        risk_level = "medium"
    else:
        risk_level = "low"

    warnings = []
    if eval_result.is_evaluable == EvaluabilityLevel.WARNING:
        warnings.append(eval_result.warning_message)

    return RiskAssessment(
        decision_id=decision.decision_id,
        risk_level=risk_level,
        risk_tags=list(decision.risk_tags),
        risk_explanation=decision.risk_explanation,
        warnings=warnings,
    )
