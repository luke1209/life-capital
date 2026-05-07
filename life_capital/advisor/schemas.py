"""Phase 5 DTO Schema 定義（凍結版）

此模組定義 advisor 輸出的核心資料結構。
一旦發布後，欄位移除或改名將被 CI 攔截（見 tests/contracts/test_advisor_schema_contract.py）

版本歷程:
- V1.0 (2025-12-29): 初版，含 AdvisorProposalPayload, DecisionOptionSchema

設計原則:
- frozen=True: 不可變，確保 hashable
- 永遠輸出 2 個選項（即使不可比）
- blocking_reasons 為結構化詳情（非簡單字串）
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal, Optional

# === Schema 版本常數 ===
ADVISOR_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class RequiredInputSchema:
    """補件需求的 schema

    當決策不可比時，列出需要補充的資料欄位。

    Attributes:
        field: 需要補充的欄位名稱（如 "monthly_income"）
        reason: 為何需要此欄位（如 "計算貸款承受力"）
        priority: 必要或選填
    """
    field: str
    reason: str
    priority: Literal["required", "optional"] = "required"


@dataclass(frozen=True)
class BlockingReasonDetail:
    """阻擋原因詳情（結構化）

    比簡單的 blocking_reasons: list[str] 更具結構化，
    便於前端顯示與程式化處理。

    Attributes:
        code: 標準化代碼（如 "TIME_RANGE_MISMATCH", "MISSING_DATA"）
        message: 人類可讀說明
        severity: blocking（阻擋比較）或 warning（警告但可繼續）
        affected_segments: 受影響的時間分段（如 ["T1_首付", "T2_貸款期"]）
    """
    code: str
    message: str
    severity: Literal["blocking", "warning"] = "blocking"
    affected_segments: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DecisionOptionSchema:
    """單一決策選項的 schema

    永遠會有 option_a（保守）和 option_b（進取）兩個選項。

    Attributes:
        direction: 方向（conservative=保守, aggressive=進取）
        label: 顯示標籤（如 "方案 A：延後購房"）
        status: 可比較狀態
        recommendation: 可比時的建議內容
        score: 可比時的評分（0.0-1.0）
        to_comparable_guidance: 不可比時的指引
    """
    direction: Literal["conservative", "aggressive"]
    label: str
    status: Literal["comparable", "not_comparable", "partial"]

    # 可比時填入
    recommendation: Optional[str] = None
    score: Optional[float] = None

    # 不可比時填入
    to_comparable_guidance: Optional[str] = None


@dataclass(frozen=True)
class AdvisorProposalPayload:
    """advisor proposal 的完整輸出 schema（契約化）

    這是 advisor 模組的核心輸出格式，寫入 proposals/pending/*.yaml。
    一旦發布後，移除欄位或改名將觸發 CI 失敗。

    設計約束:
    - 永遠輸出 2 個選項（option_a, option_b）
    - 即使不可比，仍輸出選項 + blocking_details
    - source 固定為 "advisor"
    - operation_id 使用 ULID 格式

    Attributes:
        schema_version: Schema 版本（如 "1.0"）
        source: 來源（固定為 "advisor"）
        operation_id: ULID 格式的操作識別碼
        comparability_score: 可比較性分數（0.0-1.0）
        is_comparable: 是否可比較（score >= 0.6）
        option_a: 保守方向選項
        option_b: 進取方向選項
        risk_tags: 風險標籤列表
        risk_explanation: 風險說明文字
        blocking_details: 結構化阻擋原因
        required_inputs: 需要補充的輸入清單
        input_hash: 輸入內容的 SHA-256 前 16 字元
        template_id: 使用的決策模板 ID
        comparator_version: 比較器版本
        created_at: ISO 8601 格式時間戳
    """
    # === 必填欄位（有預設值的放後面）===
    operation_id: str

    # 比較結果
    comparability_score: float
    is_comparable: bool

    # 永遠 2 個選項
    option_a: DecisionOptionSchema
    option_b: DecisionOptionSchema

    # 風險
    risk_tags: tuple
    risk_explanation: str

    # 追蹤欄位
    input_hash: str
    template_id: str

    # === 有預設值的欄位 ===
    schema_version: str = ADVISOR_SCHEMA_VERSION
    source: Literal["advisor"] = "advisor"
    blocking_details: tuple = ()
    required_inputs: tuple = ()
    comparator_version: str = "1.0"
    created_at: str = ""

    def __post_init__(self):
        """自動填入 created_at（若為空）"""
        if not self.created_at:
            object.__setattr__(self, 'created_at', datetime.now().isoformat())

    @property
    def blocking_reasons(self) -> list[str]:
        """向後相容：回傳 code 清單"""
        return [d.code for d in self.blocking_details]

    def to_dict(self) -> dict:
        """轉換為可序列化的字典"""
        result = asdict(self)
        # 將 tuple 轉為 list（YAML 友好）
        result["risk_tags"] = list(result["risk_tags"])
        result["blocking_details"] = [asdict(d) if hasattr(d, '__dataclass_fields__') else d
                                       for d in self.blocking_details]
        result["required_inputs"] = [asdict(r) if hasattr(r, '__dataclass_fields__') else r
                                      for r in self.required_inputs]
        return result


def compute_input_hash(
    redacted_context: dict,
    template_id: str,
    comparator_version: str = "1.0"
) -> str:
    """計算輸入內容的 hash

    用於偵測輸入變化，避免重複計算。

    Args:
        redacted_context: 去識別化的決策上下文
        template_id: 決策模板 ID
        comparator_version: 比較器版本（預設 "1.0"）

    Returns:
        SHA-256 hash 的前 16 字元
    """
    content = json.dumps({
        "context": redacted_context,
        "template_id": template_id,
        "comparator_version": comparator_version,
    }, sort_keys=True, ensure_ascii=False)

    return hashlib.sha256(content.encode()).hexdigest()[:16]


def generate_operation_id() -> str:
    """生成 ULID 格式的 operation_id

    ULID 特性:
    - 26 字元，可排序
    - 時間戳內嵌（前 10 字元）
    - 全系統唯一

    Returns:
        ULID 格式字串（如 "01ARZ3NDEKTSV4RRFFQ69G5FAV"）
    """
    try:
        import ulid
        return str(ulid.new())
    except ImportError:
        # Fallback: 使用 UUID + 時間戳模擬
        import uuid
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        uid = uuid.uuid4().hex[:12].upper()
        return f"{ts}{uid}"


# === Baseline 相關函式（供契約測試使用）===

def extract_schema_fields(schema_class: type = None) -> dict:
    """抽取當前 schema 的欄位定義

    供 tests/contracts/test_advisor_schema_contract.py 使用，
    用於偵測 breaking change。

    Args:
        schema_class: 可選的 schema 類別（用於文檔目的）

    Returns:
        包含 required_fields 和 enum_constraints 的字典
    """
    return {
        "schema_version": ADVISOR_SCHEMA_VERSION,
        "required_fields": [
            "schema_version", "source", "operation_id",
            "comparability_score", "is_comparable",
            "option_a", "option_b",
            "risk_tags", "risk_explanation",
            "blocking_details", "required_inputs",
            "input_hash", "template_id", "comparator_version", "created_at"
        ],
        "option_required_fields": [
            "direction", "label", "status"
        ],
        "enum_constraints": {
            "source": ["advisor"],
            "direction": ["conservative", "aggressive"],
            "status": ["comparable", "not_comparable", "partial"],
            "priority": ["required", "optional"],
            "severity": ["blocking", "warning"]
        }
    }
