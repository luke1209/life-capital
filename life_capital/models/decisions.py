"""決策記憶資料模型

Phase 5 決策追蹤與記憶系統，記錄決策建議及其假設快照。

設計原則:
- append-only: 決策記錄只能新增，不可修改（回滾以 reverted 標記）
- 可追溯: 每個決策都有 operation_id 連結
- 快照隔離: 假設快照在決策時刻凍結，不受後續變更影響

版本歷程:
- V1.0 (2025-12-29): 初版
- V1.1 (2025-12-29): 新增 decision_rationale 與 reverted_from_decision_id
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from life_capital.io.registry import DECISIONS_SCHEMA_VERSION


class DecisionStatus(str, Enum):
    """決策狀態"""

    PENDING = "pending"  # 待確認（在 proposals/ 中）
    APPLIED = "applied"  # 已套用（進入 canonical/decisions/）
    REVERTED = "reverted"  # 已回滾（標記但不刪除）
    EXPIRED = "expired"  # 已過期（超過有效期限）


class ConfidenceLevel(str, Enum):
    """決策信心度等級"""

    HIGH = "high"  # 資料完整，可比較性 >= 0.8
    MEDIUM = "medium"  # 資料部分缺失，可比較性 0.6-0.8
    LOW = "low"  # 資料不足，可比較性 < 0.6


@dataclass(frozen=True)
class AssumptionSnapshot:
    """假設快照

    記錄決策時刻的關鍵假設，用於後續對帳與學習。

    Attributes:
        snapshot_version: 快照版本（如 "1.0"）
        created_at: 快照時間
        inflation_rate: 通膨率假設
        investment_return: 投資報酬率假設
        income_growth: 收入成長率假設
        expense_growth: 支出成長率假設
        custom_assumptions: 自訂假設（鍵值對）
    """

    snapshot_version: str
    created_at: str  # ISO 8601
    inflation_rate: Optional[float] = None
    investment_return: Optional[float] = None
    income_growth: Optional[float] = None
    expense_growth: Optional[float] = None
    custom_assumptions: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PreferenceWeights:
    """多目標權重

    記錄用戶偏好的多目標權重設定。

    Attributes:
        liquidity: 流動性權重（0-1）
        growth: 成長性權重（0-1）
        safety: 安全性權重（0-1）
        flexibility: 彈性權重（0-1）
    """

    liquidity: float = 0.25
    growth: float = 0.25
    safety: float = 0.25
    flexibility: float = 0.25

    def __post_init__(self):
        """驗證權重總和為 1.0"""
        total = self.liquidity + self.growth + self.safety + self.flexibility
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"權重總和必須為 1.0，目前為 {total}")


@dataclass(frozen=True)
class DecisionOption:
    """決策選項

    記錄單一決策選項的詳細資訊。

    Attributes:
        direction: 方向（保守/進取）
        label: 選項標籤（如 "方案 A：延後購房"）
        recommendation: 建議內容
        score: 評分（可比較時）
        status: 選項狀態（可比較/不可比較/部分）
        to_comparable_guidance: 如何變成可比較的指引
    """

    direction: Literal["conservative", "aggressive"]
    label: str
    recommendation: Optional[str] = None
    score: Optional[float] = None
    status: Literal["comparable", "not_comparable", "partial"] = "comparable"
    to_comparable_guidance: Optional[str] = None


@dataclass(frozen=True)
class DecisionRecord:
    """決策記錄

    完整的決策記錄，包含決策 ID、操作 ID、假設快照等。

    Attributes:
        decision_id: 決策唯一識別碼（格式: dec_<ULID>）
        operation_id: 關聯的操作 ID（ULID 格式）
        created_at: 建立時間（ISO 8601）
        template_id: 決策模板 ID
        status: 決策狀態
        confidence: 信心度等級
        comparability_score: 可比較性分數（0-1）
        input_hash: 輸入內容 hash（SHA-256 前 16 字元）
        option_a: 保守方案
        option_b: 進取方案
        risk_tags: 風險標籤列表
        risk_explanation: 風險說明
        blocking_reasons: 阻擋原因列表（若不可比較）
        assumption_snapshot: 假設快照
        preference_weights: 多目標權重
        reverted_at: 回滾時間（若已回滾）
        reverted_by: 回滾操作的 operation_id
        schema_version: Schema 版本
        decision_rationale: 決策理由說明（V1.1 新增）
        reverted_from_decision_id: 回滾來源決策 ID（V1.1 新增）
    """

    decision_id: str
    operation_id: str
    created_at: str
    template_id: str
    status: DecisionStatus
    confidence: ConfidenceLevel
    comparability_score: float
    input_hash: str
    option_a: DecisionOption
    option_b: DecisionOption
    risk_tags: List[str]
    risk_explanation: str
    blocking_reasons: List[str] = field(default_factory=list)
    assumption_snapshot: Optional[AssumptionSnapshot] = None
    preference_weights: Optional[PreferenceWeights] = None
    reverted_at: Optional[str] = None
    reverted_by: Optional[str] = None
    schema_version: str = DECISIONS_SCHEMA_VERSION
    # V1.1 新增欄位
    decision_rationale: Optional[str] = None
    reverted_from_decision_id: Optional[str] = None

    def is_applied(self) -> bool:
        """檢查是否已套用"""
        return self.status == DecisionStatus.APPLIED

    def is_reverted(self) -> bool:
        """檢查是否已回滾"""
        return self.status == DecisionStatus.REVERTED

    def is_comparable(self) -> bool:
        """檢查是否可比較"""
        return self.comparability_score >= 0.6


@dataclass
class DecisionMemory:
    """決策記憶庫

    管理所有決策記錄，支援查詢與版本追蹤。

    Attributes:
        records: 決策記錄列表（時間順序）
        version: 記憶庫版本
        last_updated: 最後更新時間
    """

    records: List[DecisionRecord] = field(default_factory=list)
    version: str = DECISIONS_SCHEMA_VERSION
    last_updated: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )

    def add_record(self, record: DecisionRecord) -> None:
        """新增決策記錄（append-only）"""
        self.records.append(record)
        self.last_updated = datetime.now().isoformat()

    def get_by_decision_id(self, decision_id: str) -> Optional[DecisionRecord]:
        """根據決策 ID 查詢記錄"""
        for record in self.records:
            if record.decision_id == decision_id:
                return record
        return None

    def get_by_operation_id(self, operation_id: str) -> Optional[DecisionRecord]:
        """根據操作 ID 查詢記錄"""
        for record in self.records:
            if record.operation_id == operation_id:
                return record
        return None

    def get_active_records(self) -> List[DecisionRecord]:
        """取得所有有效記錄（非回滾、非過期）"""
        return [
            r for r in self.records
            if r.status in (DecisionStatus.PENDING, DecisionStatus.APPLIED)
        ]

    def get_by_template(self, template_id: str) -> List[DecisionRecord]:
        """根據模板 ID 查詢記錄"""
        return [r for r in self.records if r.template_id == template_id]

    def mark_reverted(
        self,
        decision_id: str,
        reverted_by: str
    ) -> bool:
        """標記決策為已回滾

        注意：此方法會建立新記錄而非修改既有記錄（append-only）。
        實際實作中應在 handler 層處理此邏輯。

        Args:
            decision_id: 要回滾的決策 ID
            reverted_by: 執行回滾的操作 ID

        Returns:
            是否成功找到並標記
        """
        # 在 append-only 架構中，此方法僅作為查詢輔助
        # 實際回滾應透過 decisions_handler 建立新的 reverted 記錄
        record = self.get_by_decision_id(decision_id)
        return record is not None


def generate_decision_id() -> str:
    """生成決策 ID

    格式: dec_<ULID>

    Returns:
        唯一的決策 ID 字串
    """
    try:
        import ulid
        return f"dec_{ulid.new().str}"
    except ImportError:
        # Fallback: 使用 UUID
        from uuid import uuid4
        return f"dec_{uuid4().hex[:26].upper()}"
