"""Canonical 資料讀寫唯一入口模組

提供唯一入口強制與 operation_id 追蹤機制，
確保所有 canonical/ 資料變更都經過追蹤。

Phase 1 V4.1: 使用 __all__ 限制暴露 API，禁止直接 open() 寫入。
"""

# === API 防線：只暴露安全的公開介面 ===
__all__ = [
    # 讀取函式
    "read_canonical",
    "read_operation_log",
    "read_canonical_jsonl",
    # 寫入函式（唯一入口）
    "write_canonical",
    "append_canonical_jsonl",
    "append_operation_log",
    # 偵測函式
    "detect_bypass",
    # 錯誤類型
    "CanonicalError",
    "MissingOperationIDError",
    "BypassDetectedError",
]

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

from life_capital.io.registry import CANONICAL_DIR, OPERATION_LOG_FILE
from life_capital.models.operation import (
    Operation,
    OperationLogEntry,
    OperationType,
)


class CanonicalError(Exception):
    """Canonical 操作錯誤"""

    pass


class MissingOperationIDError(CanonicalError):
    """缺少 operation_id 錯誤"""

    def __init__(self, message: str = "write_canonical() 必須提供 operation_id"):
        super().__init__(message)


class BypassDetectedError(CanonicalError):
    """偵測到繞過寫入錯誤"""

    def __init__(self, paths: list[Path]):
        path_list = "\n  - ".join(str(p) for p in paths)
        super().__init__(f"偵測到繞過 canonical_handler 的直接修改:\n  - {path_list}")


def write_canonical(
    data: BaseModel,
    target_path: Path,
    operation: Operation,
    log_path: Optional[Path] = None,
) -> str:
    """寫入 canonical/ 資料（唯一入口）

    Args:
        data: Pydantic 模型實例
        target_path: 目標路徑（絕對路徑或相對路徑）
        operation: 操作追蹤資訊（必須包含 operation_id）
        log_path: 自訂 log 路徑（測試用，預設使用 OPERATION_LOG_FILE）

    Returns:
        operation_id (UUID 字串)

    Raises:
        MissingOperationIDError: 未提供 operation_id
        CanonicalError: 寫入失敗
    """
    # 護欄 1: 強制檢查 operation_id
    if operation.operation_id is None:
        raise MissingOperationIDError()

    # 護欄 2: 確保目標路徑在 canonical/ 內
    # 將路徑轉為相對路徑或檢查路徑部分
    path_parts = target_path.parts
    canonical_index = -1
    for i, part in enumerate(path_parts):
        if part == "canonical":
            canonical_index = i
            break

    if canonical_index == -1:
        raise CanonicalError(
            f"write_canonical() 只能寫入 canonical/ 內的檔案: {target_path}"
        )

    # 確保父目錄存在
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用臨時檔案進行原子寫入
    fd, tmp_path = tempfile.mkstemp(
        suffix=".yaml" if target_path.suffix == ".yaml" else ".json",
        prefix=".tmp_",
        dir=target_path.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if target_path.suffix == ".yaml":
                # YAML 格式
                yaml_data = data.model_dump(mode="json")
                yaml.dump(
                    yaml_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )
            else:
                # JSON 格式
                f.write(data.model_dump_json(indent=2))

        # 原子重命名
        os.replace(tmp_path, target_path)

        # 記錄 operation log
        log_entry = OperationLogEntry(operation=operation)
        append_operation_log(log_entry, log_path=log_path)

        return str(operation.operation_id)

    except Exception as e:
        # 清理臨時檔案
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise CanonicalError(f"寫入失敗 ({target_path}): {e}")


def read_canonical(file_path: Path, model_class: type[BaseModel]) -> BaseModel:
    """讀取 canonical/ 資料

    Args:
        file_path: 檔案路徑（相對於資料根目錄）
        model_class: Pydantic 模型類別

    Returns:
        解析後的模型實例

    Raises:
        FileNotFoundError: 檔案不存在
        CanonicalError: 讀取或解析失敗
    """
    if not file_path.exists():
        raise FileNotFoundError(f"檔案不存在: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            if file_path.suffix == ".yaml":
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        return model_class.model_validate(data)

    except Exception as e:
        raise CanonicalError(f"讀取失敗 ({file_path}): {e}")


def append_operation_log(
    entry: OperationLogEntry, log_path: Optional[Path] = None
) -> None:
    """追加 operation log

    Args:
        entry: 操作日誌條目
        log_path: 自訂 log 路徑（測試用，預設使用 OPERATION_LOG_FILE）

    Raises:
        CanonicalError: 寫入失敗
    """
    if log_path is None:
        log_path = Path(OPERATION_LOG_FILE)

    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")
    except Exception as e:
        raise CanonicalError(f"寫入 operation log 失敗: {e}")


def read_operation_log(
    since: Optional[datetime] = None,
    operation_type: Optional[OperationType] = None,
    log_path: Optional[Path] = None,
) -> list[OperationLogEntry]:
    """讀取 operation log

    Args:
        since: 過濾時間（只返回此時間之後的記錄）
        operation_type: 過濾操作類型
        log_path: 自訂 log 路徑（測試用，預設使用 OPERATION_LOG_FILE）

    Returns:
        操作日誌條目列表

    Raises:
        CanonicalError: 讀取失敗
    """
    if log_path is None:
        log_path = Path(OPERATION_LOG_FILE)

    if not log_path.exists():
        return []

    entries = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = OperationLogEntry.from_jsonl(line)

                    # 時間過濾
                    if since and entry.operation.created_at < since:
                        continue

                    # 操作類型過濾
                    if operation_type and entry.operation.operation_type != operation_type:
                        continue

                    entries.append(entry)

                except Exception as e:
                    # 記錄解析錯誤但不中斷
                    print(f"警告: 跳過無效的 log 條目: {e}")
                    continue

        return entries

    except Exception as e:
        raise CanonicalError(f"讀取 operation log 失敗: {e}")


def append_canonical_jsonl(
    data: BaseModel,
    target_path: Path,
    operation: Operation,
    log_path: Optional[Path] = None,
) -> str:
    """追加記錄到 canonical/ JSONL 檔案（唯一入口）

    用於交易記錄等需要逐筆追加的場景。

    Args:
        data: Pydantic 模型實例（如 Transaction）
        target_path: 目標 JSONL 檔案路徑
        operation: 操作追蹤資訊（必須包含 operation_id）
        log_path: 自訂 log 路徑（測試用，預設使用 OPERATION_LOG_FILE）

    Returns:
        operation_id (UUID 字串)

    Raises:
        MissingOperationIDError: 未提供 operation_id
        CanonicalError: 寫入失敗
    """
    # 護欄 1: 強制檢查 operation_id
    if operation.operation_id is None:
        raise MissingOperationIDError()

    # 護欄 2: 確保目標路徑在 canonical/ 內
    path_parts = target_path.parts
    canonical_index = -1
    for i, part in enumerate(path_parts):
        if part == "canonical":
            canonical_index = i
            break

    if canonical_index == -1:
        raise CanonicalError(
            f"append_canonical_jsonl() 只能寫入 canonical/ 內的檔案: {target_path}"
        )

    # 護欄 3: 確保是 .jsonl 檔案
    if target_path.suffix != ".jsonl":
        raise CanonicalError(
            f"append_canonical_jsonl() 只支援 .jsonl 檔案: {target_path}"
        )

    # 確保父目錄存在
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 追加模式寫入
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(data.model_dump_json() + "\n")

        # 記錄 operation log
        log_entry = OperationLogEntry(operation=operation)
        append_operation_log(log_entry, log_path=log_path)

        return str(operation.operation_id)

    except Exception as e:
        raise CanonicalError(f"追加失敗 ({target_path}): {e}")


def read_canonical_jsonl(
    file_path: Path, model_class: type[BaseModel]
) -> list[BaseModel]:
    """讀取 canonical/ JSONL 檔案

    Args:
        file_path: 檔案路徑
        model_class: Pydantic 模型類別

    Returns:
        解析後的模型實例列表

    Raises:
        FileNotFoundError: 檔案不存在
        CanonicalError: 讀取或解析失敗
    """
    if not file_path.exists():
        raise FileNotFoundError(f"檔案不存在: {file_path}")

    if file_path.suffix != ".jsonl":
        raise CanonicalError(f"read_canonical_jsonl() 只支援 .jsonl 檔案: {file_path}")

    records = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    record = model_class.model_validate(data)
                    records.append(record)
                except Exception as e:
                    raise CanonicalError(
                        f"解析失敗 ({file_path}, 第 {line_num} 行): {e}"
                    )

        return records

    except CanonicalError:
        raise
    except Exception as e:
        raise CanonicalError(f"讀取失敗 ({file_path}): {e}")


def detect_bypass(
    data_root: Path, log_path: Optional[Path] = None
) -> list[Path]:
    """偵測繞過寫入

    檢查 canonical/ 內的檔案修改時間與 operation log 的一致性，
    偵測可能的直接修改（繞過 canonical_handler）。

    Args:
        data_root: 資料根目錄
        log_path: 自訂 log 路徑（測試用，預設使用 OPERATION_LOG_FILE）

    Returns:
        疑似繞過的檔案列表

    Raises:
        CanonicalError: 讀取失敗
    """
    canonical_dir = data_root / CANONICAL_DIR
    if not canonical_dir.exists():
        return []

    # 讀取 operation log
    if log_path is None:
        log_path = data_root / OPERATION_LOG_FILE

    try:
        log_entries = read_operation_log(log_path=log_path)
    except CanonicalError:
        # operation log 不存在或損壞，無法驗證
        return []

    # 建立 operation log 中記錄的檔案修改時間表
    logged_paths: dict[Path, datetime] = {}
    for entry in log_entries:
        target_path = data_root / entry.operation.target_path
        logged_paths[target_path] = entry.operation.created_at

    # 檢查 canonical/ 內所有檔案
    bypass_files = []
    for file_path in canonical_dir.rglob("*"):
        # 跳過目錄和隱藏檔案（如 .operation_log.jsonl）
        if file_path.is_dir() or file_path.name.startswith("."):
            continue

        # 取得檔案實際修改時間
        actual_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

        # 檢查是否在 operation log 中
        if file_path not in logged_paths:
            # 檔案存在但未在 log 中記錄 → 疑似繞過
            bypass_files.append(file_path)
            continue

        # 檢查修改時間是否一致（允許 5 秒誤差）
        logged_time = logged_paths[file_path]
        time_diff = abs((actual_mtime - logged_time).total_seconds())
        if time_diff > 5:
            # 修改時間不一致 → 疑似繞過
            bypass_files.append(file_path)

    return bypass_files
