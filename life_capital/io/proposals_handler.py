"""Proposals 處理模組

提供 proposal 建立與管理功能，用於 raw → proposals → canonical 的資料流程。

Proposal 是待審核的變更請求，包含：
- operation: 操作追蹤資訊（operation_id, type, target_path）
- data: 實際資料內容

使用方式：
    lc dedupe --write-proposals  # 從 raw/imports/ 建立 proposals
    lc apply --confirm           # 從 proposals/pending/ 套用到 canonical/
"""

import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from life_capital.io.registry import (
    CANONICAL_EXPENSES_DIR,
    CURRENT_SCHEMA_VERSION,
    PROPOSALS_PENDING_DIR,
)
from life_capital.models.expense import ExpenseRecord, MonthlyExpenses
from life_capital.models.operation import Operation, OperationType


class ProposalError(Exception):
    """Proposal 處理錯誤"""

    pass


def create_expense_proposals(
    records: list[ExpenseRecord],
    source_file: Path,
    actor: str,
    base_dir: Optional[Path] = None,
) -> list[Path]:
    """從 ExpenseRecord 列表建立 proposals

    將記錄按月份分組，每個月份建立一個 proposal。

    Args:
        records: ExpenseRecord 列表
        source_file: 來源檔案路徑（用於描述）
        actor: 操作者（用於 operation 記錄）
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        建立的 proposal 檔案路徑列表

    Raises:
        ProposalError: 建立失敗
    """
    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    if not records:
        return []

    # 按年月分組
    grouped: dict[tuple[int, int], list[ExpenseRecord]] = defaultdict(list)
    for record in records:
        key = (record.date.year, record.date.month)
        grouped[key].append(record)

    # 確保 proposals/pending/ 目錄存在
    pending_dir = base_dir / PROPOSALS_PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)

    proposal_files: list[Path] = []

    try:
        for (year, month), month_records in sorted(grouped.items()):
            # 建立 MonthlyExpenses（驗證 records，無副作用以外用途）
            MonthlyExpenses(
                year=year,
                month=month,
                records=month_records,
            )

            # 建立 Operation
            operation = Operation(
                operation_id=uuid4(),
                created_at=datetime.now(),
                actor=actor,
                operation_type=OperationType.APPLY,
                target_path=Path(CANONICAL_EXPENSES_DIR) / f"expenses_{year}_{month:02d}.yaml",
                description=f"Import {len(month_records)} records from {source_file.name}",
                metadata={
                    "source_file": str(source_file),
                    "record_count": len(month_records),
                    "year": year,
                    "month": month,
                },
            )

            # 組合 proposal 資料
            proposal_data = {
                "operation": _serialize_operation(operation),
                "data": {
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "year": year,
                    "month": month,
                    "records": [_serialize_record(r) for r in month_records],
                },
            }

            # 生成檔案名稱
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(operation.operation_id)[:8]
            filename = f"{timestamp}_{unique_id}_expenses_{year}_{month:02d}.json"
            proposal_path = pending_dir / filename

            # 原子寫入
            _atomic_write_json(proposal_data, proposal_path)

            proposal_files.append(proposal_path)

        return proposal_files

    except Exception as e:
        raise ProposalError(f"建立 proposal 失敗: {e}")


def list_pending_proposals(base_dir: Optional[Path] = None) -> list[Path]:
    """列出待確認的 proposals

    Args:
        base_dir: 資料目錄根路徑（預設使用環境變數）

    Returns:
        待確認 proposal 檔案路徑列表（按時間戳排序）
    """
    if base_dir is None:
        from life_capital.utils.path_resolver import resolve_data_dir

        base_dir = resolve_data_dir()

    pending_dir = base_dir / PROPOSALS_PENDING_DIR

    if not pending_dir.exists():
        return []

    # 列出所有 JSON 檔案
    files = [f for f in pending_dir.glob("*.json") if f.is_file()]

    # 按檔案名稱排序（包含時間戳）
    files.sort()

    return files


def load_proposal(proposal_path: Path) -> dict[str, Any]:
    """載入 proposal 內容

    Args:
        proposal_path: Proposal 檔案路徑

    Returns:
        Proposal 資料字典

    Raises:
        ProposalError: 讀取失敗
        FileNotFoundError: 檔案不存在
    """
    if not proposal_path.exists():
        raise FileNotFoundError(f"Proposal 檔案不存在: {proposal_path}")

    try:
        with open(proposal_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ProposalError(f"Proposal JSON 解析失敗: {e}")
    except Exception as e:
        raise ProposalError(f"讀取 proposal 失敗: {e}")


def get_proposal_summary(proposal_path: Path) -> dict[str, Any]:
    """取得 proposal 摘要資訊

    Args:
        proposal_path: Proposal 檔案路徑

    Returns:
        摘要字典，包含 operation_id, type, target, description, record_count
    """
    data = load_proposal(proposal_path)

    operation = data.get("operation", {})
    proposal_data = data.get("data", {})

    return {
        "operation_id": operation.get("operation_id", "N/A")[:8],
        "operation_type": operation.get("operation_type", "N/A"),
        "target_path": operation.get("target_path", "N/A"),
        "description": operation.get("description", "N/A"),
        "record_count": len(proposal_data.get("records", [])),
        "year": proposal_data.get("year"),
        "month": proposal_data.get("month"),
        "created_at": operation.get("created_at", "N/A"),
    }


def delete_proposal(proposal_path: Path) -> None:
    """刪除 proposal

    Args:
        proposal_path: Proposal 檔案路徑

    Raises:
        FileNotFoundError: 檔案不存在
    """
    if not proposal_path.exists():
        raise FileNotFoundError(f"Proposal 檔案不存在: {proposal_path}")

    proposal_path.unlink()


def count_pending_proposals(base_dir: Optional[Path] = None) -> int:
    """計算待確認 proposals 數量

    Args:
        base_dir: 資料目錄根路徑

    Returns:
        待確認 proposals 數量
    """
    return len(list_pending_proposals(base_dir))


# === 內部輔助函式 ===


def _serialize_operation(operation: Operation) -> dict[str, Any]:
    """序列化 Operation 為 JSON 相容格式"""
    return {
        "operation_id": str(operation.operation_id),
        "created_at": operation.created_at.isoformat(),
        "actor": operation.actor,
        "operation_type": operation.operation_type.value,
        "target_path": str(operation.target_path),
        "description": operation.description,
        "metadata": operation.metadata,
    }


def _serialize_record(record: ExpenseRecord) -> dict[str, Any]:
    """序列化 ExpenseRecord 為 JSON 相容格式"""
    return {
        "date": record.date.isoformat(),
        "amount": str(record.amount),  # Decimal → str
        "category": record.category,
        "payer": record.payer,
        "note": record.note,
        "merchant": record.merchant,
    }


def _atomic_write_json(data: dict[str, Any], target_path: Path) -> None:
    """原子寫入 JSON 檔案

    使用臨時檔案確保寫入的原子性。

    Args:
        data: 資料字典
        target_path: 目標路徑
    """
    # 使用臨時檔案
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        prefix=".tmp_",
        dir=target_path.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # 原子重命名
        os.replace(tmp_path, target_path)
    except Exception:
        # 清理臨時檔案
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
