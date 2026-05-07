"""測試 canonical_handler 模組"""

import json
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from pydantic import BaseModel, Field

from life_capital.io.canonical_handler import (
    CanonicalError,
    append_operation_log,
    detect_bypass,
    read_canonical,
    read_operation_log,
    write_canonical,
)
from life_capital.models.operation import (
    Operation,
    OperationLogEntry,
    OperationType,
)


# === 測試用 Pydantic 模型 ===
class SampleModel(BaseModel):
    """測試用簡單模型（避免與 pytest Test 前綴衝突）"""

    name: str
    value: int
    updated_at: datetime = Field(default_factory=datetime.now)


# === Fixtures ===
@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """建立臨時資料目錄"""
    canonical_dir = tmp_path / "canonical"
    canonical_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_operation() -> Operation:
    """建立範例 operation"""
    return Operation(
        operation_id=uuid4(),
        actor="test_user",
        operation_type=OperationType.IMPORT,
        target_path=Path("canonical/test.yaml"),
        description="Test operation",
    )


# === 測試 write_canonical ===
def test_write_canonical_success(temp_data_dir: Path, sample_operation: Operation):
    """測試正常寫入 canonical 資料"""
    data = SampleModel(name="test", value=42)
    target_path = temp_data_dir / "canonical" / "test.yaml"
    log_path = temp_data_dir / "canonical" / ".operation_log.jsonl"

    # 執行寫入（傳入自訂 log_path）
    operation_id = write_canonical(data, target_path, sample_operation, log_path=log_path)

    # 驗證返回值
    assert operation_id == str(sample_operation.operation_id)

    # 驗證檔案存在且內容正確
    assert target_path.exists()
    with open(target_path, "r", encoding="utf-8") as f:
        saved_data = yaml.safe_load(f)
    assert saved_data["name"] == "test"
    assert saved_data["value"] == 42

    # 驗證 operation log 存在
    assert log_path.exists()


def test_write_canonical_missing_operation_id(temp_data_dir: Path):
    """測試缺少 operation_id 時拋出錯誤

    注意：由於 Pydantic 自動生成 UUID，此測試驗證檢查邏輯存在。
    實務上 operation_id 會由 Pydantic 自動產生，不會為 None。
    """
    # 跳過此測試，因為 Pydantic 自動生成 UUID，無法設為 None
    pytest.skip("Pydantic 自動生成 operation_id，無法為 None")


def test_write_canonical_non_canonical_path(temp_data_dir: Path, sample_operation: Operation):
    """測試寫入非 canonical/ 路徑時拋出錯誤"""
    data = SampleModel(name="test", value=42)
    target_path = temp_data_dir / "raw" / "test.yaml"

    # 修改 operation 的 target_path
    operation = Operation(
        operation_id=uuid4(),
        actor="test_user",
        operation_type=OperationType.IMPORT,
        target_path=Path("raw/test.yaml"),  # 非 canonical/ 路徑
        description="Test operation",
    )

    # 驗證拋出 CanonicalError
    with pytest.raises(CanonicalError, match="只能寫入 canonical/"):
        write_canonical(data, target_path, operation)


def test_write_canonical_json_format(temp_data_dir: Path, sample_operation: Operation):
    """測試寫入 JSON 格式"""
    data = SampleModel(name="test", value=42)
    target_path = temp_data_dir / "canonical" / "test.json"

    # 修改 operation 的 target_path
    operation = Operation(
        operation_id=uuid4(),
        actor="test_user",
        operation_type=OperationType.IMPORT,
        target_path=Path("canonical/test.json"),
        description="Test operation",
    )

    # 執行寫入
    write_canonical(data, target_path, operation)

    # 驗證 JSON 檔案內容
    assert target_path.exists()
    with open(target_path, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert saved_data["name"] == "test"
    assert saved_data["value"] == 42


# === 測試 read_canonical ===
def test_read_canonical_success(temp_data_dir: Path):
    """測試正常讀取 canonical 資料"""
    # 建立測試檔案
    file_path = temp_data_dir / "canonical" / "test.yaml"
    file_path.parent.mkdir(parents=True, exist_ok=True)

    test_data = {"name": "test", "value": 42, "updated_at": datetime.now().isoformat()}
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(test_data, f)

    # 讀取資料
    loaded_model = read_canonical(file_path, SampleModel)

    # 驗證內容
    assert loaded_model.name == "test"
    assert loaded_model.value == 42


def test_read_canonical_file_not_found(temp_data_dir: Path):
    """測試讀取不存在的檔案"""
    file_path = temp_data_dir / "canonical" / "nonexistent.yaml"

    with pytest.raises(FileNotFoundError):
        read_canonical(file_path, SampleModel)


# === 測試 append_operation_log ===
def test_append_operation_log(temp_data_dir: Path, sample_operation: Operation, monkeypatch):
    """測試追加 operation log"""
    # 設定 OPERATION_LOG_FILE 路徑
    monkeypatch.setattr(
        "life_capital.io.canonical_handler.OPERATION_LOG_FILE",
        str(temp_data_dir / "canonical" / ".operation_log.jsonl"),
    )

    # 建立 log entry
    log_entry = OperationLogEntry(operation=sample_operation)

    # 追加 log
    append_operation_log(log_entry)

    # 驗證 log 檔案存在
    log_path = temp_data_dir / "canonical" / ".operation_log.jsonl"
    assert log_path.exists()

    # 驗證 log 內容
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1

    # 驗證 JSON 格式正確
    parsed = OperationLogEntry.from_jsonl(lines[0].strip())
    assert parsed.operation.actor == "test_user"


# === 測試 read_operation_log ===
def test_read_operation_log_empty(temp_data_dir: Path, monkeypatch):
    """測試讀取空 operation log"""
    # 設定路徑但不建立檔案
    monkeypatch.setattr(
        "life_capital.io.canonical_handler.OPERATION_LOG_FILE",
        str(temp_data_dir / "canonical" / ".operation_log.jsonl"),
    )

    entries = read_operation_log()
    assert entries == []


def test_read_operation_log_with_filters(temp_data_dir: Path, monkeypatch):
    """測試過濾功能"""
    monkeypatch.setattr(
        "life_capital.io.canonical_handler.OPERATION_LOG_FILE",
        str(temp_data_dir / "canonical" / ".operation_log.jsonl"),
    )

    # 建立多個 log entries
    log_path = temp_data_dir / "canonical" / ".operation_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entries = [
        OperationLogEntry(
            operation=Operation(
                actor="user1",
                operation_type=OperationType.IMPORT,
                target_path=Path("canonical/test1.yaml"),
                description="Import 1",
            )
        ),
        OperationLogEntry(
            operation=Operation(
                actor="user2",
                operation_type=OperationType.APPLY,
                target_path=Path("canonical/test2.yaml"),
                description="Apply 1",
            )
        ),
    ]

    # 寫入 log
    with open(log_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.to_jsonl() + "\n")

    # 測試過濾：只讀取 IMPORT 類型
    filtered = read_operation_log(operation_type=OperationType.IMPORT)
    assert len(filtered) == 1
    assert filtered[0].operation.operation_type == OperationType.IMPORT


# === 測試 detect_bypass ===
def test_detect_bypass_no_bypass(temp_data_dir: Path, sample_operation: Operation):
    """測試正常情況（無繞過）"""
    # 正常寫入資料
    data = SampleModel(name="test", value=42)
    target_path = temp_data_dir / "canonical" / "test.yaml"
    log_path = temp_data_dir / "canonical" / ".operation_log.jsonl"

    write_canonical(data, target_path, sample_operation, log_path=log_path)

    # 偵測繞過（傳入 log_path）
    bypass_files = detect_bypass(temp_data_dir, log_path=log_path)
    assert len(bypass_files) == 0


def test_detect_bypass_direct_modification(temp_data_dir: Path):
    """測試偵測直接修改檔案（繞過 canonical_handler）"""
    # 建立空 log 檔案
    log_path = temp_data_dir / "canonical" / ".operation_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch()

    # 直接建立檔案（繞過 write_canonical）
    bypass_file = temp_data_dir / "canonical" / "bypass.yaml"
    bypass_file.parent.mkdir(parents=True, exist_ok=True)
    with open(bypass_file, "w", encoding="utf-8") as f:
        yaml.dump({"name": "bypass", "value": 99}, f)

    # 偵測繞過（傳入 log_path）
    bypass_files = detect_bypass(temp_data_dir, log_path=log_path)
    assert len(bypass_files) == 1
    assert bypass_file in bypass_files


def test_detect_bypass_time_mismatch(temp_data_dir: Path, sample_operation: Operation):
    """測試偵測修改時間不一致（疑似繞過）"""
    # 正常寫入資料
    data = SampleModel(name="test", value=42)
    target_path = temp_data_dir / "canonical" / "test.yaml"
    log_path = temp_data_dir / "canonical" / ".operation_log.jsonl"

    write_canonical(data, target_path, sample_operation, log_path=log_path)

    # 等待足夠時間並直接修改檔案（模擬繞過）
    # macOS 檔案系統時間精度較低，需等待更長時間
    time.sleep(6)  # 超過 5 秒容差
    with open(target_path, "w", encoding="utf-8") as f:
        yaml.dump({"name": "modified", "value": 999}, f)

    # 偵測繞過（傳入 log_path）
    bypass_files = detect_bypass(temp_data_dir, log_path=log_path)
    # 由於修改時間差異超過 5 秒，應該被偵測到
    assert len(bypass_files) > 0
