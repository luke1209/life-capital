"""Redaction 子模組

提供資料去識別化的核心功能。

模組結構:
- rules.py: 規則定義（FORBIDDEN/SENSITIVE/COMPOSITION）
- engine.py: Redaction 引擎
- decision_context.py: RedactedDecisionContext 資料結構
"""

from life_capital.privacy.redaction.decision_context import (
    RedactedDecisionContext,
    RedactedPresentationView,
)
from life_capital.privacy.redaction.engine import RedactionEngine
from life_capital.privacy.redaction.rules import (
    COMPOSITION_RULES,
    FORBIDDEN_FIELDS,
    REDACTION_PROFILE_V1_0,
    SENSITIVE_FIELDS,
    RedactionProfile,
)

__all__ = [
    # 規則
    "FORBIDDEN_FIELDS",
    "SENSITIVE_FIELDS",
    "COMPOSITION_RULES",
    "REDACTION_PROFILE_V1_0",
    "RedactionProfile",
    # 資料結構
    "RedactedDecisionContext",
    "RedactedPresentationView",
    # 引擎
    "RedactionEngine",
]
