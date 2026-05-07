"""CSV 到 Transaction 轉換模組 (Phase 1.3)

將 CSV 行轉換為 Transaction 模型，用於 apply 流程。

轉換規則：
- date → occurred_at
- amount → amount (Decimal)
- category → category
- payer → payer (預設 shared)
- note → note
- merchant → merchant
- 自動計算 dedupe_key
- 生成 stable_id
"""

import hashlib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from life_capital.io.registry import DEFAULT_DEDUPE_KEY_VERSION
from life_capital.models.transaction import SourceRowRef, Transaction


class CSVConversionError(Exception):
    """CSV 轉換錯誤"""

    def __init__(self, row_index: int, field: str, message: str):
        self.row_index = row_index
        self.field = field
        self.message = message
        super().__init__(f"Row {row_index}: {field} - {message}")


def parse_date(value: str) -> date:
    """解析日期字串

    支援格式：
    - YYYY-MM-DD
    - YYYY/MM/DD
    - DD-MM-YYYY
    - DD/MM/YYYY

    Args:
        value: 日期字串

    Returns:
        date 物件

    Raises:
        ValueError: 無法解析的日期格式
    """
    value = value.strip()

    # YYYY-MM-DD 或 YYYY/MM/DD
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    # DD-MM-YYYY 或 DD/MM/YYYY
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"無法解析日期: {value}")


def parse_amount(value: str) -> Decimal:
    """解析金額字串

    支援格式：
    - 123.45
    - -123.45
    - 1,234.56 (移除逗號)

    Args:
        value: 金額字串

    Returns:
        Decimal 物件

    Raises:
        ValueError: 無法解析的金額格式
    """
    value = value.strip().replace(",", "")

    try:
        amount = Decimal(value)
        if amount == 0:
            raise ValueError("金額不能為 0")
        return amount
    except InvalidOperation:
        raise ValueError(f"無法解析金額: {value}")


def normalize_payer(value: Optional[str]) -> str:
    """正規化支付者

    Args:
        value: 支付者字串

    Returns:
        正規化的支付者 (person_a, person_b, shared)
    """
    if not value:
        return "shared"

    value = value.strip().lower()

    if value in ("person_a", "a"):
        return "person_a"
    elif value in ("person_b", "b"):
        return "person_b"
    elif value in ("shared", "s", "both", ""):
        return "shared"
    else:
        # 未知值，預設 shared
        return "shared"


def compute_row_hash(row: dict[str, Any]) -> str:
    """計算 CSV 行的 SHA-256 hash

    用於 SourceRowRef.raw_hash，追溯原始資料。

    Args:
        row: CSV 行字典

    Returns:
        64 字元的 hex hash
    """
    # 排序鍵值以確保一致性
    canonical = "|".join(f"{k}={v}" for k, v in sorted(row.items()) if v)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def csv_row_to_transaction(
    row: dict[str, Any],
    source_id: UUID,
    row_index: int,
) -> Transaction:
    """將 CSV 行轉換為 Transaction

    Args:
        row: CSV 行字典（包含 date, amount, category 等）
        source_id: 來源檔案的 source_id (UUID)
        row_index: 原始行號（1-based）

    Returns:
        Transaction 實例

    Raises:
        CSVConversionError: 轉換失敗
    """
    # 必填欄位檢查
    if "date" not in row or not row["date"]:
        raise CSVConversionError(row_index, "date", "日期為必填欄位")

    if "amount" not in row or not row["amount"]:
        raise CSVConversionError(row_index, "amount", "金額為必填欄位")

    if "category" not in row or not row["category"]:
        raise CSVConversionError(row_index, "category", "分類為必填欄位")

    # 解析日期
    try:
        occurred_at = parse_date(str(row["date"]))
    except ValueError as e:
        raise CSVConversionError(row_index, "date", str(e))

    # 解析金額
    try:
        amount = parse_amount(str(row["amount"]))
    except ValueError as e:
        raise CSVConversionError(row_index, "amount", str(e))

    # 解析分類
    category = str(row["category"]).strip()
    if not category:
        raise CSVConversionError(row_index, "category", "分類不能為空")

    # 解析支付者
    payer = normalize_payer(row.get("payer"))

    # 可選欄位
    note = row.get("note")
    if note:
        note = str(note).strip() or None

    merchant = row.get("merchant")
    if merchant:
        merchant = str(merchant).strip() or None

    # 建立 SourceRowRef
    source_row_ref = SourceRowRef(
        source_id=source_id,
        row_index=row_index,
        raw_hash=compute_row_hash(row),
    )

    # 建立 Transaction
    return Transaction(
        occurred_at=occurred_at,
        amount=amount,
        category=category,
        payer=payer,
        note=note,
        merchant=merchant,
        source_row_ref=source_row_ref,
        dedupe_key_version=DEFAULT_DEDUPE_KEY_VERSION,
    )


def batch_csv_to_transactions(
    rows: list[dict[str, Any]],
    source_id: UUID,
    skip_errors: bool = False,
) -> tuple[list[Transaction], list[CSVConversionError]]:
    """批次轉換 CSV 行為 Transactions

    Args:
        rows: CSV 行字典列表
        source_id: 來源檔案的 source_id (UUID)
        skip_errors: 是否跳過錯誤繼續處理

    Returns:
        (成功轉換的 Transactions 列表, 錯誤列表)
    """
    transactions: list[Transaction] = []
    errors: list[CSVConversionError] = []

    for i, row in enumerate(rows, start=1):
        try:
            transaction = csv_row_to_transaction(row, source_id, i)
            transactions.append(transaction)
        except CSVConversionError as e:
            errors.append(e)
            if not skip_errors:
                break

    return transactions, errors
