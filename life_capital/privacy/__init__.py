"""Phase 5: 隱私保護基礎層

獨立於 advisor/ 的隱私保護模組，提供資料去識別化功能。

核心功能:
- Redaction 引擎：去除敏感資訊
- 規則定義：FORBIDDEN / SENSITIVE / COMPOSITION
- 分層輸出：DecisionContext (引擎) vs PresentationView (CLI)
"""

from life_capital.privacy.redaction import (
    REDACTION_PROFILE_V1_0,
    RedactedDecisionContext,
    RedactionEngine,
)

__all__ = [
    "RedactionEngine",
    "RedactedDecisionContext",
    "REDACTION_PROFILE_V1_0",
]
