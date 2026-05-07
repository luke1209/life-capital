"""交易記錄資料模型 (Phase 1)

定義 canonical 層的交易記錄結構，支援：
- stable_id: 永久識別碼
- dedupe_key: 去重 hash
- source_row_ref: 原始資料追溯
"""

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from life_capital.io.registry import (
    CURRENT_SCHEMA_VERSION,
    DEFAULT_DEDUPE_KEY_VERSION,
)

if TYPE_CHECKING:
    from life_capital.models.expense import ExpenseRecord

# 支付者類型定義
Payer = Literal["person_a", "person_b", "shared"]
VALID_PAYERS: set[str] = {"person_a", "person_b", "shared"}

# 預設貨幣
DEFAULT_CURRENCY = "TWD"


class SourceRowRef(BaseModel):
    """原始資料追溯參考

    記錄交易記錄的原始來源，用於追溯資料血統。

    Attributes:
        source_id: raw 檔案的 source_id (UUID)
        row_index: 原始行號 (1-based)
        raw_hash: 原始行的 SHA-256 hash
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    source_id: UUID
    row_index: int = Field(ge=1)
    raw_hash: str = Field(min_length=64, max_length=64)


class Transaction(BaseModel):
    """交易記錄模型

    Phase 1 的核心交易模型，支援去重與追溯功能。

    Attributes:
        stable_id: 永久識別碼，建立後不可變
        dedupe_key: 去重 hash，允許策略更新
        dedupe_key_version: 去重策略版本（v1, v2, ...）
        occurred_at: 消費日（優先顯示）
        posted_at: 入帳日（可選）
        amount: 金額（Decimal）
        currency: 貨幣代碼
        category: 分類
        payer: 支付者
        note: 備註
        merchant: 商家
        is_transfer: 是否為轉帳
        reversal_of: 退款/沖正關聯的 stable_id
        source_row_ref: 原始資料追溯
        schema_version: Schema 版本
        created_at: 記錄建立時間
        updated_at: 記錄更新時間
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        json_encoders={
            Decimal: str,
            UUID: str,
            date: lambda v: v.isoformat(),
            datetime: lambda v: v.isoformat(),
        },
    )

    # 身份欄位
    stable_id: UUID = Field(default_factory=uuid4)
    dedupe_key: str = Field(default="")
    dedupe_key_version: str = Field(default=DEFAULT_DEDUPE_KEY_VERSION)

    # 時間欄位
    occurred_at: date
    posted_at: Optional[date] = None

    # 金額欄位
    amount: Decimal
    currency: str = Field(default=DEFAULT_CURRENCY, min_length=3, max_length=3)

    # 分類欄位
    category: str = Field(min_length=1)
    payer: Payer = Field(default="shared")

    # 描述欄位
    note: Optional[str] = None
    merchant: Optional[str] = None

    # 關聯欄位
    is_transfer: bool = Field(default=False)
    reversal_of: Optional[UUID] = None

    # 追蹤欄位
    source_row_ref: Optional[SourceRowRef] = None
    schema_version: str = Field(default=CURRENT_SCHEMA_VERSION)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """驗證金額非零"""
        if v == 0:
            raise ValueError("amount 不能為 0")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """正規化貨幣代碼為大寫"""
        return v.upper()

    @model_validator(mode="after")
    def compute_dedupe_key_if_empty(self) -> "Transaction":
        """若 dedupe_key 為空，自動計算"""
        if not self.dedupe_key:
            self.dedupe_key = self._compute_dedupe_key()
        return self

    def _compute_dedupe_key(self) -> str:
        """計算去重 key

        Key = occurred_at + amount + category + payer + merchant
        使用 SHA-256 hash。

        Returns:
            64 字元的 hex hash
        """
        # 正規化金額為固定 2 位小數
        amount_str = f"{self.amount:.2f}"

        # 組合 canonical 字串
        canonical = "|".join(
            [
                self.occurred_at.isoformat(),
                amount_str,
                self.category.strip().lower(),
                self.payer,
                (self.merchant or "").strip().lower(),
            ]
        )

        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def is_refund(self) -> bool:
        """判斷是否為退款/回饋"""
        return self.amount < 0

    def is_reversal(self) -> bool:
        """判斷是否為沖正記錄"""
        return self.reversal_of is not None

    def update_dedupe_key(self) -> str:
        """重新計算並更新 dedupe_key

        用於去重策略更新時重新計算。

        Returns:
            新的 dedupe_key
        """
        self.dedupe_key = self._compute_dedupe_key()
        self.updated_at = datetime.now()
        return self.dedupe_key

    def to_dict(self) -> dict:
        """轉換為字典格式（用於序列化）"""
        return self.model_dump(mode="json", exclude_none=True)

    @classmethod
    def from_expense_record(
        cls,
        record: "ExpenseRecord",  # 避免循環 import，使用字串
        source_row_ref: Optional[SourceRowRef] = None,
    ) -> "Transaction":
        """從 ExpenseRecord 建立 Transaction

        用於 Phase 1 migration。

        Args:
            record: ExpenseRecord 實例
            source_row_ref: 原始資料追溯（可選）

        Returns:
            Transaction 實例
        """
        # 延遲 import 避免循環依賴
        from life_capital.models.expense import ExpenseRecord as ER

        if not isinstance(record, ER):
            raise TypeError(f"Expected ExpenseRecord, got {type(record)}")

        return cls(
            occurred_at=record.date,
            amount=record.amount,
            category=record.category,
            payer=record.payer,
            note=record.note,
            merchant=record.merchant,
            source_row_ref=source_row_ref,
        )


class TransactionCollection(BaseModel):
    """交易記錄集合

    用於儲存一組交易記錄（如月度交易）。

    Attributes:
        transactions: 交易記錄列表
        schema_version: Schema 版本
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    transactions: list[Transaction] = Field(default_factory=list)
    schema_version: str = Field(default=CURRENT_SCHEMA_VERSION)

    def add(self, transaction: Transaction) -> None:
        """新增交易記錄"""
        self.transactions.append(transaction)

    def find_by_stable_id(self, stable_id: UUID) -> Optional[Transaction]:
        """依 stable_id 查找交易"""
        for t in self.transactions:
            if t.stable_id == stable_id:
                return t
        return None

    def find_by_dedupe_key(self, dedupe_key: str) -> list[Transaction]:
        """依 dedupe_key 查找交易（可能有多筆）"""
        return [t for t in self.transactions if t.dedupe_key == dedupe_key]

    def total(self) -> Decimal:
        """計算總金額"""
        return sum((t.amount for t in self.transactions), Decimal("0"))

    def by_category(self) -> dict[str, Decimal]:
        """依類別統計金額"""
        result: dict[str, Decimal] = {}
        for t in self.transactions:
            if t.category not in result:
                result[t.category] = Decimal("0")
            result[t.category] += t.amount
        return result

    def by_payer(self) -> dict[str, Decimal]:
        """依支付者統計金額"""
        result: dict[str, Decimal] = {}
        for t in self.transactions:
            if t.payer not in result:
                result[t.payer] = Decimal("0")
            result[t.payer] += t.amount
        return result

    def count(self) -> int:
        """交易筆數"""
        return len(self.transactions)
