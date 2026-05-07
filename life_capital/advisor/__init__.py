"""Phase 5: AI 顧問系統

決策比較引擎，提供「2 個可比較方案 + 風險說明」的財務建議。

核心特徵:
- 規則驅動（無 LLM），決定論邏輯，完全可追蹤
- 永遠生成 2 個可比較方案
- 直接複用 Phase 2-3 計算結果
- 隱私優先：獨立 privacy/redaction/ 層
"""

from life_capital.advisor.schemas import (
    AdvisorProposalPayload,
    BlockingReasonDetail,
    DecisionOptionSchema,
    RequiredInputSchema,
)

__all__ = [
    "AdvisorProposalPayload",
    "DecisionOptionSchema",
    "RequiredInputSchema",
    "BlockingReasonDetail",
]
