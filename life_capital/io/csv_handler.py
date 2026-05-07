"""CSV 讀寫模組

提供支出 CSV 的讀寫與去重功能。
支援 exact hash (SHA-256) 和 key-based 去重。
"""

import csv
import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from life_capital.io.errors import CSVError, CSVParseError
from life_capital.io.registry import (
    EXPENSE_CSV_ALL_FIELDS,
    EXPENSE_CSV_REQUIRED_FIELDS,
)
from life_capital.models.expense import VALID_PAYERS, ExpenseRecord, MonthlyExpenses

# 重新導出供向後相容
__all__ = [
    "CSVError",
    "CSVParseError",
    "DedupeMode",
    "load_csv",
    "save_csv",
    "load_monthly_expenses",
]


DedupeMode = Literal["exact", "key"]


def normalize_date(date_str: str) -> str:
    """正規化日期格式為 YYYY-MM-DD

    支援格式:
    - YYYY-MM-DD
    - YYYY/MM/DD
    - DD/MM/YYYY
    - MM/DD/YYYY
    """
    date_str = date_str.strip()

    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # YYYY/MM/DD
    if re.match(r"^\d{4}/\d{2}/\d{2}$", date_str):
        parts = date_str.split("/")
        return f"{parts[0]}-{parts[1]}-{parts[2]}"

    # DD/MM/YYYY or MM/DD/YYYY - 假設為 DD/MM/YYYY（較常見）
    if re.match(r"^\d{2}/\d{2}/\d{4}$", date_str):
        parts = date_str.split("/")
        # 假設 DD/MM/YYYY
        return f"{parts[2]}-{parts[1]}-{parts[0]}"

    raise ValueError(f"無法解析日期格式: {date_str}")


def normalize_amount(amount_str: str) -> str:
    """正規化金額格式

    - 移除千分位逗號
    - 移除貨幣符號
    - 處理括號負數表示法
    - 輸出固定 2 位小數（用於 canonical string）
    """
    amount_str = amount_str.strip()

    # 移除貨幣符號和空白
    amount_str = re.sub(r"[$￥¥€£\s]", "", amount_str)

    # 處理括號負數: (100) → -100
    if amount_str.startswith("(") and amount_str.endswith(")"):
        amount_str = "-" + amount_str[1:-1]

    # 移除千分位逗號
    amount_str = amount_str.replace(",", "")

    # 轉換為 Decimal 並格式化為固定 2 位小數
    try:
        decimal_val = Decimal(amount_str)
        return f"{decimal_val:.2f}"
    except InvalidOperation:
        raise ValueError(f"無法解析金額: {amount_str}")


def normalize_text(text: str) -> str:
    """正規化文字欄位

    - 去除前後空白
    - 合併連續空白
    - 處理 null/N/A
    """
    if not text:
        return ""

    text = text.strip()

    # null/N/A 視為空
    if text.lower() in ("null", "n/a", "none", "na"):
        return ""

    # 合併連續空白
    text = re.sub(r"\s+", " ", text)

    return text


def normalize_payer(payer_str: str) -> str:
    """正規化支付者欄位

    - 轉小寫
    - 驗證為有效值
    - 無效值回傳 "shared"
    """
    if not payer_str:
        return "shared"

    payer = payer_str.strip().lower()
    return payer if payer in VALID_PAYERS else "shared"


def compute_row_hash(row: dict[str, str]) -> str:
    """計算完整行的 SHA-256 hash

    用於 exact 去重模式。
    """
    # 按固定順序組合欄位（V1.1: 加入 payer）
    canonical = "|".join(
        [
            normalize_date(row.get("date", "")),
            normalize_amount(row.get("amount", "0")),
            normalize_text(row.get("category", "")),
            normalize_payer(row.get("payer", "")),
            normalize_text(row.get("note", "")),
            normalize_text(row.get("merchant", "")),
        ]
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_row_key(row: dict[str, str]) -> str:
    """計算行的去重 key

    用於 key-based 去重模式。
    Key = date + amount + category + payer + merchant（V1.1: 加入 payer）
    """
    canonical = "|".join(
        [
            normalize_date(row.get("date", "")),
            normalize_amount(row.get("amount", "0")),
            normalize_text(row.get("category", "")),
            normalize_payer(row.get("payer", "")),
            normalize_text(row.get("merchant", "")),  # 空也保留
        ]
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_amount(amount_str: str) -> Decimal:
    """解析金額字串為 Decimal"""
    amount_str = amount_str.strip()

    # 移除貨幣符號
    amount_str = re.sub(r"[$￥¥€£\s]", "", amount_str)

    # 處理括號負數
    if amount_str.startswith("(") and amount_str.endswith(")"):
        amount_str = "-" + amount_str[1:-1]

    # 移除千分位逗號
    amount_str = amount_str.replace(",", "")

    try:
        return Decimal(amount_str)
    except InvalidOperation:
        raise ValueError(f"無法解析金額: {amount_str}")


def parse_date(date_str: str) -> date:
    """解析日期字串"""
    normalized = normalize_date(date_str)
    return date.fromisoformat(normalized)


def load_csv(
    path: Path,
    dedupe: DedupeMode = "exact",
) -> tuple[list[ExpenseRecord], int]:
    """讀取支出 CSV

    Args:
        path: CSV 檔案路徑
        dedupe: 去重模式 - "exact" (完整 hash) 或 "key" (key-based)

    Returns:
        (記錄列表, 去重數量)

    Raises:
        FileNotFoundError: 檔案不存在
        CSVParseError: 解析失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"檔案不存在: {path}")

    records: list[ExpenseRecord] = []
    seen_hashes: set[str] = set()
    duplicates = 0

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        # 驗證必要欄位
        if reader.fieldnames is None:
            raise CSVParseError(path, 1, "CSV 檔案為空或無表頭")

        missing = set(EXPENSE_CSV_REQUIRED_FIELDS) - set(reader.fieldnames)
        if missing:
            raise CSVParseError(path, 1, f"缺少必要欄位: {missing}")

        for i, row in enumerate(reader, start=2):
            try:
                # 計算 hash/key
                if dedupe == "exact":
                    row_hash = compute_row_hash(row)
                else:
                    row_hash = compute_row_key(row)

                # 檢查重複
                if row_hash in seen_hashes:
                    duplicates += 1
                    continue

                seen_hashes.add(row_hash)

                # 解析記錄（V1.1: 加入 payer）
                record = ExpenseRecord(
                    date=parse_date(row["date"]),
                    amount=parse_amount(row["amount"]),
                    category=normalize_text(row["category"]),
                    payer=normalize_payer(row.get("payer", "")),
                    note=normalize_text(row.get("note", "")) or None,
                    merchant=normalize_text(row.get("merchant", "")) or None,
                )
                records.append(record)

            except Exception as e:
                raise CSVParseError(path, i, str(e))

    return records, duplicates


def save_csv(path: Path, records: list[ExpenseRecord]) -> None:
    """儲存支出記錄為 CSV

    Args:
        path: 目標路徑
        records: 支出記錄列表
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPENSE_CSV_ALL_FIELDS)
        writer.writeheader()

        for record in records:
            writer.writerow(record.to_csv_row())


def load_monthly_expenses(
    path: Path,
    year: int,
    month: int,
    dedupe: DedupeMode = "exact",
) -> tuple[MonthlyExpenses, int]:
    """讀取月度支出

    Args:
        path: CSV 檔案路徑
        year: 年份
        month: 月份
        dedupe: 去重模式

    Returns:
        (MonthlyExpenses, 去重數量)
    """
    records, duplicates = load_csv(path, dedupe)

    return MonthlyExpenses(year=year, month=month, records=records), duplicates
