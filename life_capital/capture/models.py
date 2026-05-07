"""
Phase 4 CAPTURE 核心資料模型

隔離規則：此檔案為 capture/ 內部模型，不可被外部 import
V4.1.1 規格：包含完整 Source enums + DuplicateReason + 終態追蹤欄位
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

# ===== Status Enums =====


class StagingStatus(str, Enum):
    """StagingEntry 狀態機（8 狀態）"""

    PENDING = "pending"  # 待解析
    PARSED = "parsed"  # 已解析，待確認
    ERROR = "error"  # 解析失敗
    APPROVED = "approved"  # 已批准，proposal 已建立
    REJECTED = "rejected"  # 已拒絕
    IGNORED = "ignored"  # 非支出
    DUPLICATE = "duplicate"  # 重複輸入
    APPLIED = "applied"  # 終態：已進入 canonical


# ===== Source Enums (V4.1.1) =====


class AmountSource(str, Enum):
    """金額抽取來源類型"""

    EXACT = "exact"  # 明確數字（320, 1200）
    RANGE = "range"  # 範圍取值（100-120 → 110）
    INFERRED = "inferred"  # 推斷（"約 120" → 120）
    MISSING = "missing"  # 無法抽取


class DateSource(str, Enum):
    """日期抽取來源類型"""

    BUILTIN_EXACT = "builtin_exact"  # 內建規則精確匹配（今天、昨天、YYYY-MM-DD）
    BUILTIN_INFERRED = "builtin_inferred"  # 內建規則推斷（不完整日期）
    DATEPARSER = "dateparser"  # dateparser fallback
    RELATIVE = "relative"  # 相對日期（上週、本月）
    MISSING = "missing"  # 無法抽取


class CategorySource(str, Enum):
    """類別抽取來源類型"""

    EXACT = "exact"  # 完全匹配 expense_policy
    FUZZY = "fuzzy"  # 模糊匹配
    MISSING = "missing"  # 無法抽取


# ===== Duplicate Reason Enum (V4.1.1) =====


class DuplicateReason(str, Enum):
    """判重原因"""

    DUP_KEY_EXACT = "exact_key_match"  # duplicate_key 精準匹配
    DUP_DATE_FUZZ = "date_fuzzy_match"  # 日期模糊匹配（±2天）
    DUP_AMOUNT_MISSING = "amount_missing_fuzzy"  # 金額缺失時的文字模糊匹配


# ===== Core Data Model =====


@dataclass
class StagingEntry:
    """
    Staging 待處理支出記錄

    V4.1.1 完整欄位：
    - 基本欄位：entry_id, raw_text, created_at
    - 版本追蹤：parser_version, batch_id, source
    - 解析結果：parsed_date, parsed_amount, parsed_category, parsed_merchant, parsed_note
    - 來源枚舉：amount_source, date_source, category_source
    - 狀態管理：status, confidence, confidence_breakdown, error_message
    - 決策記錄：reviewed_at, reviewed_by, rejection_reason
    - 判重欄位：duplicate_of, duplicate_reason
    - 終態追蹤：proposal_id, canonical_record_id
    - 稽核欄位：raw_locale
    """

    # === 基本欄位 ===
    entry_id: str  # UUID
    raw_text: str  # 原始輸入（不可變）
    created_at: datetime  # 建立時間

    # === 版本追蹤 ===
    parser_version: str = "1.0"  # 解析器版本
    batch_id: Optional[str] = None  # 批次匯入 ID
    source: str = "cli"  # 來源（cli/api/batch）

    # === 解析結果（Optional）===
    parsed_date: Optional[date] = None
    parsed_amount: Optional[Decimal] = None
    parsed_category: Optional[str] = None
    parsed_merchant: Optional[str] = None
    parsed_note: Optional[str] = None

    # === 來源枚舉（V4.1.1）===
    amount_source: AmountSource = AmountSource.MISSING
    date_source: DateSource = DateSource.MISSING
    category_source: CategorySource = CategorySource.MISSING

    # === 狀態與信心度 ===
    status: StagingStatus = StagingStatus.PENDING
    confidence: float = 0.0  # 0.0-1.0
    confidence_breakdown: Optional[dict] = None  # {"amount": 0.9, "date": 0.8, ...}
    error_message: Optional[str] = None  # 解析失敗原因

    # === 決策記錄 ===
    reviewed_at: Optional[datetime] = None  # approve/reject 時間
    reviewed_by: Optional[str] = None  # actor
    rejection_reason: Optional[str] = None  # 拒絕原因

    # === 判重欄位 ===
    duplicate_of: Optional[str] = None  # 重複的 entry_id
    duplicate_reason: Optional[DuplicateReason] = None  # 判重原因（V4.1.1）

    # === 終態追蹤（V4.1.1）===
    proposal_id: Optional[str] = None  # approved 時寫入
    canonical_record_id: Optional[str] = None  # applied 時寫入

    # === 稽核欄位 ===
    raw_locale: Optional[str] = None  # 輸入語系（zh-TW, en-US）

    def __post_init__(self):
        """資料驗證與型別轉換"""
        # 確保 Enum 型別
        if isinstance(self.status, str):
            self.status = StagingStatus(self.status)
        if isinstance(self.amount_source, str):
            self.amount_source = AmountSource(self.amount_source)
        if isinstance(self.date_source, str):
            self.date_source = DateSource(self.date_source)
        if isinstance(self.category_source, str):
            self.category_source = CategorySource(self.category_source)
        if self.duplicate_reason and isinstance(self.duplicate_reason, str):
            self.duplicate_reason = DuplicateReason(self.duplicate_reason)

        # 確保 Decimal 型別
        if self.parsed_amount is not None and not isinstance(
            self.parsed_amount, Decimal
        ):
            self.parsed_amount = Decimal(str(self.parsed_amount))

        # 確保 date 型別
        if self.parsed_date is not None and isinstance(self.parsed_date, str):
            self.parsed_date = date.fromisoformat(self.parsed_date)

        # 確保 datetime 型別
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)
        if self.reviewed_at is not None and isinstance(self.reviewed_at, str):
            self.reviewed_at = datetime.fromisoformat(self.reviewed_at)

    @property
    def amount_certain(self) -> bool:
        """金額是否確定（V4.1.1 derived property）"""
        return self.amount_source == AmountSource.EXACT

    @property
    def date_certain(self) -> bool:
        """日期是否確定（V4.1.1 derived property）"""
        return self.date_source == DateSource.BUILTIN_EXACT

    @property
    def category_certain(self) -> bool:
        """類別是否確定（V4.1.1 derived property）"""
        return self.category_source == CategorySource.EXACT

    @property
    def all_certain(self) -> bool:
        """三欄位是否全部確定（auto-approve 護欄）"""
        return self.amount_certain and self.date_certain and self.category_certain

    def to_dict(self) -> dict:
        """轉換為字典（用於 JSONL 序列化）"""
        return {
            # 基本欄位
            "entry_id": self.entry_id,
            "raw_text": self.raw_text,
            "created_at": self.created_at.isoformat(),
            # 版本追蹤
            "parser_version": self.parser_version,
            "batch_id": self.batch_id,
            "source": self.source,
            # 解析結果
            "parsed_date": self.parsed_date.isoformat() if self.parsed_date else None,
            "parsed_amount": str(self.parsed_amount)
            if self.parsed_amount
            else None,
            "parsed_category": self.parsed_category,
            "parsed_merchant": self.parsed_merchant,
            "parsed_note": self.parsed_note,
            # 來源枚舉
            "amount_source": self.amount_source.value,
            "date_source": self.date_source.value,
            "category_source": self.category_source.value,
            # 狀態與信心度
            "status": self.status.value,
            "confidence": self.confidence,
            "confidence_breakdown": self.confidence_breakdown,
            "error_message": self.error_message,
            # 決策記錄
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "rejection_reason": self.rejection_reason,
            # 判重欄位
            "duplicate_of": self.duplicate_of,
            "duplicate_reason": self.duplicate_reason.value
            if self.duplicate_reason
            else None,
            # 終態追蹤
            "proposal_id": self.proposal_id,
            "canonical_record_id": self.canonical_record_id,
            # 稽核欄位
            "raw_locale": self.raw_locale,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StagingEntry":
        """從字典建立實例（用於 JSONL 反序列化）"""
        # 移除不屬於 dataclass 的欄位（如 _seq）
        data = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**data)
