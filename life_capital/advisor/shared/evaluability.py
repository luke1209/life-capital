"""決策可評估性判定模組

定義 Recommendability 與 Evaluability 兩個維度的分層邏輯。

使用方式:
    from life_capital.advisor.shared.evaluability import evaluate_decision

    eval_result = evaluate_decision(0.65)
    if eval_result.is_evaluable == EvaluabilityLevel.SKIP:
        return None  # 跳過評估
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RecommendabilityLevel(Enum):
    """可推薦程度"""

    FULL = "full"  # ≥0.7: 完整 A/B 排序與推薦
    PARTIAL = "partial"  # 0.5-0.7: 可推薦但需標註
    NONE = "none"  # <0.5: 不可推薦


class EvaluabilityLevel(Enum):
    """可評估程度（風險/敏感度）"""

    FULL = "full"  # ≥0.5: 完整評估
    WARNING = "warning"  # 0.3-0.5: 可評估但強制加警告
    SKIP = "skip"  # <0.3: 跳過評估


@dataclass(frozen=True)
class DecisionEvaluability:
    """決策的可評估性判定結果"""

    comparability_score: float
    is_recommendable: RecommendabilityLevel
    is_evaluable: EvaluabilityLevel
    warning_message: Optional[str]


def evaluate_decision(comparability_score: float) -> DecisionEvaluability:
    """判定決策的可評估性

    Args:
        comparability_score: 可比較性分數 (0.0-1.0)

    Returns:
        DecisionEvaluability 實例
    """
    # 判定 Recommendability
    if comparability_score >= 0.7:
        is_recommendable = RecommendabilityLevel.FULL
        is_evaluable = EvaluabilityLevel.FULL
        warning = None
    elif 0.5 <= comparability_score < 0.7:
        is_recommendable = RecommendabilityLevel.PARTIAL
        is_evaluable = EvaluabilityLevel.FULL
        warning = "部分可比：推薦結果僅供參考"
    elif 0.3 <= comparability_score < 0.5:
        is_recommendable = RecommendabilityLevel.NONE
        is_evaluable = EvaluabilityLevel.WARNING
        warning = "低可比性：風險評估可能不準確"
    else:  # < 0.3
        is_recommendable = RecommendabilityLevel.NONE
        is_evaluable = EvaluabilityLevel.SKIP
        warning = "不可比：跳過風險與敏感度評估"

    return DecisionEvaluability(
        comparability_score=comparability_score,
        is_recommendable=is_recommendable,
        is_evaluable=is_evaluable,
        warning_message=warning,
    )
