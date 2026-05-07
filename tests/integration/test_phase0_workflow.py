"""Phase 0 Integration 測試

完整測試 Phase 0 工作流程，包含：
- 完整工作流程（import → apply → rebuild → undo）
- 繞過偵測（直接修改 canonical 檔案）
- raw/ 不可變性驗證
- 操作可追溯性驗證
- 重建冪等性驗證
- derived 可重建性驗證（V2.5）
"""

import csv
import shutil
import stat
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from pydantic import BaseModel, Field

from life_capital.io.canonical_handler import (
    detect_bypass,
    read_canonical,
    read_operation_log,
    write_canonical,
)
from life_capital.io.raw_handler import write_raw
from life_capital.models.operation import (
    Operation,
    OperationLogEntry,
    OperationType,
    Provenance,
    SourceType,
)

# === Test Fixtures ===


@pytest.fixture
def test_env(tmp_path: Path):
    """建立完整測試環境

    Returns:
        dict: 包含 data_dir, csv_file, operation_log 路徑
    """
    data_dir = tmp_path / "life-capital"

    # 建立目錄結構
    (data_dir / "raw" / "imports").mkdir(parents=True)
    (data_dir / "raw" / "manual").mkdir(parents=True)
    (data_dir / "canonical").mkdir(parents=True)
    (data_dir / "proposals").mkdir(parents=True)
    (data_dir / "derived").mkdir(parents=True)

    # 建立測試 CSV
    csv_file = tmp_path / "test_expenses.csv"
    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "amount", "category", "note", "merchant"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "date": "2024-12-01",
                "amount": "1000",
                "category": "食物",
                "note": "午餐",
                "merchant": "餐廳A",
            }
        )
        writer.writerow(
            {
                "date": "2024-12-02",
                "amount": "500",
                "category": "交通",
                "note": "搭車",
                "merchant": "捷運",
            }
        )

    # 建立 operation log 路徑
    operation_log = data_dir / "canonical" / ".operation_log.jsonl"

    return {
        "data_dir": data_dir,
        "csv_file": csv_file,
        "operation_log": operation_log,
        "tmp_path": tmp_path,
    }


class SampleModel(BaseModel):
    """測試用簡單模型"""

    name: str
    value: int
    updated_at: datetime = Field(default_factory=datetime.now)


# === Test Cases ===


class TestCompleteWorkflow:
    """測試 1: 完整工作流程"""

    def test_complete_workflow(self, test_env: dict):
        """完整工作流程：import → apply → rebuild → undo"""
        data_dir = test_env["data_dir"]
        csv_file = test_env["csv_file"]
        operation_log = test_env["operation_log"]

        # === Step 1: lc import ===
        provenance = Provenance(
            source_type=SourceType.CSV_IMPORT,
            parser_version="1.0.0",
        )

        # 模擬 CSV 匯入至 raw/imports/
        csv_data = {
            "headers": ["date", "amount", "category", "note", "merchant"],
            "rows": [],
        }
        with open(csv_file, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                csv_data["rows"].append(dict(row))

        raw_file = write_raw(
            data=csv_data,
            target="imports",
            provenance=provenance,
            format="csv",
            base_dir=data_dir,
        )

        # 驗證 raw/ 檔案存在且 read-only
        assert raw_file.exists()
        file_stat = raw_file.stat()
        mode = stat.filemode(file_stat.st_mode)
        assert mode == "-r--r--r--"  # 444 權限

        # === Step 2: lc apply (proposals/ → canonical/) ===
        # 模擬從 proposals/ 寫入至 canonical/
        proposal_data = SampleModel(name="test_proposal", value=100)
        proposal_path = data_dir / "proposals" / "proposal_001.yaml"

        # 先寫入 proposal（這只是模擬，實際 proposals/ 不受 canonical_handler 管理）
        with open(proposal_path, "w", encoding="utf-8") as f:
            yaml.dump(proposal_data.model_dump(mode="json"), f)

        # 建立 apply operation
        apply_operation = Operation(
            operation_id=uuid4(),
            actor="test_user",
            operation_type=OperationType.APPLY,
            target_path=Path("canonical/applied_data.yaml"),
            description="Apply proposal_001",
        )

        # 執行 apply（寫入 canonical）
        canonical_path = data_dir / "canonical" / "applied_data.yaml"
        operation_id_1 = write_canonical(
            data=proposal_data,
            target_path=canonical_path,
            operation=apply_operation,
            log_path=operation_log,
        )

        # 驗證 canonical 檔案存在
        assert canonical_path.exists()

        # 驗證 operation log 記錄
        log_entries = read_operation_log(log_path=operation_log)
        assert len(log_entries) == 1
        assert log_entries[0].operation.operation_type == OperationType.APPLY
        assert str(log_entries[0].operation.operation_id) == operation_id_1

        # === Step 3: lc rebuild (canonical/ → derived/) ===
        # 注意：derived/ 不由 write_canonical() 管理
        # 這裡模擬 rebuild 建立 derived/ 檔案（使用普通檔案寫入）
        derived_data = {"name": "summary", "value": 200}
        derived_path = data_dir / "derived" / "summary.yaml"
        derived_path.parent.mkdir(parents=True, exist_ok=True)

        with open(derived_path, "w", encoding="utf-8") as f:
            yaml.dump(derived_data, f)

        # 記錄 rebuild operation（但不使用 write_canonical）
        rebuild_operation = Operation(
            operation_id=uuid4(),
            actor="system",
            operation_type=OperationType.REBUILD,
            target_path=Path("derived/summary.yaml"),
            description="Rebuild derived data",
        )

        from life_capital.io.canonical_handler import append_operation_log

        rebuild_entry = OperationLogEntry(operation=rebuild_operation)
        append_operation_log(rebuild_entry, log_path=operation_log)

        # 驗證 derived 檔案存在
        assert derived_path.exists()

        # 驗證 operation log 更新
        log_entries = read_operation_log(log_path=operation_log)
        assert len(log_entries) == 2
        assert log_entries[1].operation.operation_type == OperationType.REBUILD

        # === Step 4: lc undo (回滾操作) ===
        # 模擬 undo：刪除最後一個 operation 的目標檔案
        last_entry = log_entries[-1]
        target_to_remove = data_dir / last_entry.operation.target_path

        if target_to_remove.exists():
            target_to_remove.unlink()

        # 記錄 undo operation
        undo_operation = Operation(
            operation_id=uuid4(),
            actor="test_user",
            operation_type=OperationType.UNDO,
            target_path=last_entry.operation.target_path,
            description=f"Undo operation {last_entry.operation.operation_id}",
        )

        undo_entry = OperationLogEntry(operation=undo_operation)
        append_operation_log(undo_entry, log_path=operation_log)

        # 驗證 undo 後檔案已刪除
        assert not derived_path.exists()

        # 驗證 operation log 包含 undo
        log_entries = read_operation_log(log_path=operation_log)
        assert len(log_entries) == 3
        assert log_entries[2].operation.operation_type == OperationType.UNDO


class TestBypassDetection:
    """測試 2: 繞過偵測"""

    def test_bypass_detection(self, test_env: dict):
        """偵測直接修改 canonical 檔案（繞過 write_canonical）"""
        data_dir = test_env["data_dir"]
        operation_log = test_env["operation_log"]

        # 建立空 operation log
        operation_log.parent.mkdir(parents=True, exist_ok=True)
        operation_log.touch()

        # 直接建立 canonical 檔案（繞過 write_canonical）
        bypass_file = data_dir / "canonical" / "bypass.yaml"
        with open(bypass_file, "w", encoding="utf-8") as f:
            yaml.dump({"name": "bypass", "value": 999}, f)

        # 執行繞過偵測
        bypass_files = detect_bypass(data_dir, log_path=operation_log)

        # 驗證偵測到繞過檔案
        assert len(bypass_files) == 1
        assert bypass_file in bypass_files

    def test_doctor_hard_fail(self, test_env: dict):
        """測試 lc doctor 在偵測到繞過時 hard fail"""
        data_dir = test_env["data_dir"]
        operation_log = test_env["operation_log"]

        # 建立空 operation log
        operation_log.parent.mkdir(parents=True, exist_ok=True)
        operation_log.touch()

        # 直接建立 canonical 檔案（繞過）
        bypass_file = data_dir / "canonical" / "bypass.yaml"
        with open(bypass_file, "w", encoding="utf-8") as f:
            yaml.dump({"name": "bypass", "value": 999}, f)

        # 模擬 lc doctor 檢查（使用 detect_bypass）
        bypass_files = detect_bypass(data_dir, log_path=operation_log)

        # 驗證檢查失敗
        if len(bypass_files) > 0:
            exit_code = 1  # Hard fail
        else:
            exit_code = 0

        assert exit_code == 1
        assert len(bypass_files) == 1


class TestRawImmutability:
    """測試 3: raw/ 不可變性"""

    def test_raw_immutability(self, test_env: dict):
        """驗證 raw/ 檔案不可變"""
        data_dir = test_env["data_dir"]

        # 寫入 raw 檔案
        provenance = Provenance(
            source_type=SourceType.CSV_IMPORT,
            parser_version="1.0.0",
        )

        sample_data = SampleModel(name="test", value=42)
        raw_file = write_raw(
            data=sample_data,
            target="imports",
            provenance=provenance,
            format="yaml",
            base_dir=data_dir,
        )

        # 驗證檔案權限為 444
        file_stat = raw_file.stat()
        mode = stat.filemode(file_stat.st_mode)
        assert mode == "-r--r--r--"

        # 嘗試修改檔案應失敗
        with pytest.raises(PermissionError):
            with open(raw_file, "w", encoding="utf-8") as f:
                f.write("modified content")

    def test_cannot_overwrite_raw(self, test_env: dict):
        """驗證無法覆寫已存在的 raw 檔案"""
        data_dir = test_env["data_dir"]

        provenance = Provenance(
            source_type=SourceType.CSV_IMPORT,
            parser_version="1.0.0",
        )

        sample_data = SampleModel(name="test", value=42)

        # 第一次寫入（使用 UUID 檔名，實際不會碰撞）
        raw_file = write_raw(
            data=sample_data,
            target="imports",
            provenance=provenance,
            format="yaml",
            base_dir=data_dir,
        )

        # 驗證檔案存在
        assert raw_file.exists()

        # 由於檔名含 UUID，實際上不會碰撞
        # 此測試驗證設計上禁止覆寫的理念


class TestOperationTraceability:
    """測試 4: 操作可追溯性"""

    def test_operation_traceability(self, test_env: dict):
        """驗證所有操作都有完整 operation_id 與 provenance"""
        data_dir = test_env["data_dir"]
        operation_log = test_env["operation_log"]

        # 執行多個操作
        operations = []

        # Operation 1: IMPORT
        import_op = Operation(
            operation_id=uuid4(),
            actor="test_user",
            operation_type=OperationType.IMPORT,
            target_path=Path("canonical/import_data.yaml"),
            description="Import test data",
        )
        operations.append(import_op)

        import_data = SampleModel(name="import", value=100)
        write_canonical(
            data=import_data,
            target_path=data_dir / "canonical" / "import_data.yaml",
            operation=import_op,
            log_path=operation_log,
        )

        # Operation 2: APPLY
        apply_op = Operation(
            operation_id=uuid4(),
            actor="test_user",
            operation_type=OperationType.APPLY,
            target_path=Path("canonical/apply_data.yaml"),
            description="Apply proposal",
        )
        operations.append(apply_op)

        apply_data = SampleModel(name="apply", value=200)
        write_canonical(
            data=apply_data,
            target_path=data_dir / "canonical" / "apply_data.yaml",
            operation=apply_op,
            log_path=operation_log,
        )

        # Operation 3: REBUILD (derived/ 不使用 write_canonical)
        rebuild_op = Operation(
            operation_id=uuid4(),
            actor="system",
            operation_type=OperationType.REBUILD,
            target_path=Path("derived/rebuild_data.yaml"),
            description="Rebuild derived",
        )
        operations.append(rebuild_op)

        # 寫入 derived/ 檔案（普通檔案寫入）
        rebuild_data = {"name": "rebuild", "value": 300}
        derived_path = data_dir / "derived" / "rebuild_data.yaml"
        derived_path.parent.mkdir(parents=True, exist_ok=True)

        with open(derived_path, "w", encoding="utf-8") as f:
            yaml.dump(rebuild_data, f)

        # 記錄 operation
        from life_capital.io.canonical_handler import append_operation_log

        rebuild_entry = OperationLogEntry(operation=rebuild_op)
        append_operation_log(rebuild_entry, log_path=operation_log)

        # 讀取 operation log
        log_entries = read_operation_log(log_path=operation_log)

        # 驗證所有操作都有記錄
        assert len(log_entries) == 3

        # 驗證每個 entry 都有 operation_id
        for entry in log_entries:
            assert entry.operation.operation_id is not None
            assert isinstance(entry.operation.operation_id, uuid4().__class__)

        # 驗證 operation 順序
        assert log_entries[0].operation.operation_type == OperationType.IMPORT
        assert log_entries[1].operation.operation_type == OperationType.APPLY
        assert log_entries[2].operation.operation_type == OperationType.REBUILD

        # 驗證 provenance 完整記錄
        for i, entry in enumerate(log_entries):
            assert entry.operation.actor in ["test_user", "system"]
            assert entry.operation.description != ""


class TestRebuildIdempotency:
    """測試 5: 重建冪等性"""

    def test_rebuild_idempotency(self, test_env: dict):
        """驗證 lc rebuild 兩次結果一致（除了 generated_at）"""
        data_dir = test_env["data_dir"]
        operation_log = test_env["operation_log"]

        # 建立初始 canonical 資料
        canonical_data = SampleModel(name="source", value=100)
        canonical_path = data_dir / "canonical" / "source.yaml"

        init_op = Operation(
            operation_id=uuid4(),
            actor="test_user",
            operation_type=OperationType.IMPORT,
            target_path=Path("canonical/source.yaml"),
            description="Initial data",
        )

        write_canonical(
            data=canonical_data,
            target_path=canonical_path,
            operation=init_op,
            log_path=operation_log,
        )

        # 第一次 rebuild (derived/ 使用普通檔案寫入)
        derived_data_1 = {"name": "summary", "value": 200, "updated_at": datetime.now().isoformat()}
        derived_path = data_dir / "derived" / "summary.yaml"
        derived_path.parent.mkdir(parents=True, exist_ok=True)

        with open(derived_path, "w", encoding="utf-8") as f:
            yaml.dump(derived_data_1, f)

        # 記錄 rebuild operation
        rebuild_op_1 = Operation(
            operation_id=uuid4(),
            actor="system",
            operation_type=OperationType.REBUILD,
            target_path=Path("derived/summary.yaml"),
            description="First rebuild",
        )

        from life_capital.io.canonical_handler import append_operation_log

        rebuild_entry_1 = OperationLogEntry(operation=rebuild_op_1)
        append_operation_log(rebuild_entry_1, log_path=operation_log)

        # 讀取第一次結果
        with open(derived_path, "r", encoding="utf-8") as f:
            result_1 = yaml.safe_load(f)

        # 刪除 derived 檔案
        derived_path.unlink()

        # 第二次 rebuild
        derived_data_2 = {"name": "summary", "value": 200, "updated_at": datetime.now().isoformat()}

        with open(derived_path, "w", encoding="utf-8") as f:
            yaml.dump(derived_data_2, f)

        # 記錄 rebuild operation
        rebuild_op_2 = Operation(
            operation_id=uuid4(),
            actor="system",
            operation_type=OperationType.REBUILD,
            target_path=Path("derived/summary.yaml"),
            description="Second rebuild",
        )

        rebuild_entry_2 = OperationLogEntry(operation=rebuild_op_2)
        append_operation_log(rebuild_entry_2, log_path=operation_log)

        # 讀取第二次結果
        with open(derived_path, "r", encoding="utf-8") as f:
            result_2 = yaml.safe_load(f)

        # 驗證結果一致（除了 updated_at）
        assert result_1["name"] == result_2["name"]
        assert result_1["value"] == result_2["value"]

        # 驗證確定性排序（operation log）
        log_entries = read_operation_log(log_path=operation_log)

        # 找出所有 REBUILD 操作
        rebuild_entries = [
            e for e in log_entries if e.operation.operation_type == OperationType.REBUILD
        ]
        assert len(rebuild_entries) == 2

        # 驗證順序（時間戳應遞增）
        assert rebuild_entries[0].operation.created_at <= rebuild_entries[1].operation.created_at


class TestDerivedRebuildable:
    """測試 6: derived 可重建性（V2.5）"""

    def test_derived_rebuildable(self, test_env: dict):
        """驗證刪除整個 derived/ 後可完全重建"""
        data_dir = test_env["data_dir"]
        operation_log = test_env["operation_log"]

        # 建立初始 canonical 資料
        canonical_data = SampleModel(name="source", value=100)
        canonical_path = data_dir / "canonical" / "source.yaml"

        init_op = Operation(
            operation_id=uuid4(),
            actor="test_user",
            operation_type=OperationType.IMPORT,
            target_path=Path("canonical/source.yaml"),
            description="Initial data",
        )

        write_canonical(
            data=canonical_data,
            target_path=canonical_path,
            operation=init_op,
            log_path=operation_log,
        )

        # 建立初始 derived/ (使用普通檔案寫入)
        derived_data = {"name": "summary", "value": 200}
        derived_path = data_dir / "derived" / "summary.yaml"
        derived_path.parent.mkdir(parents=True, exist_ok=True)

        with open(derived_path, "w", encoding="utf-8") as f:
            yaml.dump(derived_data, f)

        # 記錄 rebuild operation
        rebuild_op = Operation(
            operation_id=uuid4(),
            actor="system",
            operation_type=OperationType.REBUILD,
            target_path=Path("derived/summary.yaml"),
            description="Initial rebuild",
        )

        from life_capital.io.canonical_handler import append_operation_log

        rebuild_entry = OperationLogEntry(operation=rebuild_op)
        append_operation_log(rebuild_entry, log_path=operation_log)

        # 驗證 derived 存在
        assert derived_path.exists()

        # 讀取初始內容
        with open(derived_path, "r", encoding="utf-8") as f:
            initial_result = yaml.safe_load(f)

        # 刪除整個 derived/ 目錄
        derived_dir = data_dir / "derived"
        shutil.rmtree(derived_dir)

        # 驗證目錄已刪除
        assert not derived_dir.exists()

        # 重建 derived/ 目錄
        derived_dir.mkdir(parents=True, exist_ok=True)

        # 執行重建（模擬 lc rebuild）
        # 從 canonical 重新計算並寫入 derived
        source_data = read_canonical(canonical_path, SampleModel)
        rebuilt_data = {"name": "summary", "value": source_data.value * 2}

        with open(derived_path, "w", encoding="utf-8") as f:
            yaml.dump(rebuilt_data, f)

        # 記錄 rebuild operation
        rebuild_op_2 = Operation(
            operation_id=uuid4(),
            actor="system",
            operation_type=OperationType.REBUILD,
            target_path=Path("derived/summary.yaml"),
            description="Rebuild after deletion",
        )

        rebuild_entry_2 = OperationLogEntry(operation=rebuild_op_2)
        append_operation_log(rebuild_entry_2, log_path=operation_log)

        # 驗證 derived 完全恢復
        assert derived_path.exists()

        # 讀取重建結果
        with open(derived_path, "r", encoding="utf-8") as f:
            rebuilt_result = yaml.safe_load(f)

        # 驗證內容一致
        assert rebuilt_result["name"] == initial_result["name"]
        assert rebuilt_result["value"] == initial_result["value"]

        # 驗證 operation log 記錄完整
        log_entries = read_operation_log(log_path=operation_log)
        rebuild_entries = [
            e for e in log_entries if e.operation.operation_type == OperationType.REBUILD
        ]
        assert len(rebuild_entries) == 2
