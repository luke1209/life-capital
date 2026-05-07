"""Phase 4 CAPTURE - Staging Repair 測試

測試 staging repair 功能的 3 種不一致偵測與修復：
1. approved_without_proposal
2. proposal_without_approved
3. applied_without_canonical
"""

from decimal import Decimal
from pathlib import Path

import pytest

from life_capital.capture.models import StagingStatus
from life_capital.capture.staging_service import (
    InconsistencyReport,
    RepairResult,
    StagingService,
)
from life_capital.interfaces.canonical_reader import CanonicalReader


class CanonicalReaderFake(CanonicalReader):
    """Fake CanonicalReader for testing"""

    def get_categories(self) -> list[str]:
        return ["餐飲", "交通", "購物"]

    def get_expense_policy(self) -> dict:
        return {}

    def get_monthly_income(self) -> Decimal:
        return Decimal("0")

    def save_proposal(self, data: dict, operation: dict) -> Path:
        return Path("/fake/proposal")

    def get_version(self) -> str:
        return "1.1"


@pytest.fixture
def service_with_reader(tmp_path):
    """建立 StagingService with CanonicalReaderFake"""
    from life_capital.capture.expense_parser import ExpenseParser
    from life_capital.io.staging_store import StagingStoreImpl

    reader = CanonicalReaderFake()
    store = StagingStoreImpl(tmp_path)
    parser = ExpenseParser(reader)
    return StagingService(store, parser, reader)


# === 不一致偵測測試 ===


def test_detect_no_inconsistencies(service_with_reader):
    """測試：無不一致狀態"""
    service = service_with_reader

    # 建立正常 entry (pending → parsed)
    service.add_entry(text="餐飲 320", source="cli")

    # 偵測不一致
    reports = service.detect_inconsistencies()

    # 驗證：無不一致
    assert len(reports) == 0


def test_detect_approved_without_proposal(service_with_reader):
    """測試：偵測 approved_without_proposal"""
    service = service_with_reader

    # 建立 entry 並手動設為 approved（但無 proposal_id）
    entry = service.add_entry(text="餐飲 320", source="cli")
    entry.status = StagingStatus.APPROVED
    entry.proposal_id = None  # 問題：沒有 proposal_id
    service._store.write_entry(entry)

    # 偵測不一致
    reports = service.detect_inconsistencies()

    # 驗證：偵測到 1 筆不一致
    assert len(reports) == 1
    report = reports[0]
    assert report.entry_id == entry.entry_id
    assert report.inconsistency_type == "approved_without_proposal"
    assert report.current_status == "approved"
    assert "proposal_id=None" in report.description


def test_detect_proposal_without_approved(service_with_reader):
    """測試：偵測 proposal_without_approved"""
    service = service_with_reader

    # 建立 entry 並手動設置 proposal_id（但 status 為 pending）
    entry = service.add_entry(text="餐飲 320", source="cli")
    entry.proposal_id = "fake-proposal-id.yaml"  # 問題：有 proposal_id 但 status 不對
    service._store.write_entry(entry)

    # 偵測不一致
    reports = service.detect_inconsistencies()

    # 驗證：偵測到 1 筆不一致
    assert len(reports) == 1
    report = reports[0]
    assert report.entry_id == entry.entry_id
    assert report.inconsistency_type == "proposal_without_approved"
    assert "proposal_id 存在" in report.description


def test_detect_applied_without_canonical(service_with_reader):
    """測試：偵測 applied_without_canonical"""
    service = service_with_reader

    # 建立 entry 並手動設為 applied（但無 canonical_record_id）
    entry = service.add_entry(text="餐飲 320", source="cli")
    entry.status = StagingStatus.APPLIED
    entry.proposal_id = "fake-proposal-id.yaml"
    entry.canonical_record_id = None  # 問題：沒有 canonical_record_id
    service._store.write_entry(entry)

    # 偵測不一致
    reports = service.detect_inconsistencies()

    # 驗證：偵測到 1 筆不一致
    assert len(reports) == 1
    report = reports[0]
    assert report.entry_id == entry.entry_id
    assert report.inconsistency_type == "applied_without_canonical"
    assert "canonical_record_id=None" in report.description


def test_detect_multiple_inconsistencies(service_with_reader):
    """測試：偵測多筆不一致"""
    service = service_with_reader

    # 建立 3 筆不一致的 entries
    # 1. approved_without_proposal
    entry1 = service.add_entry(text="餐飲 320", source="cli")
    entry1.status = StagingStatus.APPROVED
    entry1.proposal_id = None
    service._store.write_entry(entry1)

    # 2. proposal_without_approved
    entry2 = service.add_entry(text="交通 100", source="cli")
    entry2.proposal_id = "fake-proposal-id.yaml"
    service._store.write_entry(entry2)

    # 3. applied_without_canonical
    entry3 = service.add_entry(text="購物 500", source="cli")
    entry3.status = StagingStatus.APPLIED
    entry3.proposal_id = "fake-proposal-id.yaml"
    entry3.canonical_record_id = None
    service._store.write_entry(entry3)

    # 偵測不一致
    reports = service.detect_inconsistencies()

    # 驗證：偵測到 3 筆不一致
    assert len(reports) == 3
    types = {r.inconsistency_type for r in reports}
    assert types == {
        "approved_without_proposal",
        "proposal_without_approved",
        "applied_without_canonical",
    }


# === 修復功能測試 ===


def test_repair_approved_without_proposal(service_with_reader):
    """測試：修復 approved_without_proposal → 降級為 parsed"""
    service = service_with_reader

    # 建立不一致 entry
    entry = service.add_entry(text="餐飲 320", source="cli")
    entry.status = StagingStatus.APPROVED
    entry.proposal_id = None
    service._store.write_entry(entry)

    # 執行修復
    results = service.repair_inconsistencies(dry_run=False)

    # 驗證：修復成功
    assert len(results) == 1
    result = results[0]
    assert result.entry_id == entry.entry_id
    assert result.inconsistency_type == "approved_without_proposal"
    assert result.success is True
    assert "降級為 parsed" in result.action_taken

    # 驗證：entry 狀態已更新
    repaired_entry = service.get_entry(entry.entry_id)
    assert repaired_entry.status == StagingStatus.PARSED
    assert repaired_entry.proposal_id is None


def test_repair_proposal_without_approved_proposal_not_exists(
    service_with_reader,
):
    """測試：修復 proposal_without_approved（proposal 不存在）→ 刪除 proposal_id"""
    service = service_with_reader

    # 建立不一致 entry（proposal 不存在）
    entry = service.add_entry(text="餐飲 320", source="cli")
    entry.proposal_id = "non-existent-proposal.yaml"
    service._store.write_entry(entry)

    # 執行修復
    results = service.repair_inconsistencies(dry_run=False)

    # 驗證：修復成功
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert "刪除 proposal_id" in result.action_taken
    assert "不存在" in result.action_taken

    # 驗證：proposal_id 已清除
    repaired_entry = service.get_entry(entry.entry_id)
    assert repaired_entry.proposal_id is None


def test_repair_proposal_without_approved_proposal_exists(
    service_with_reader, tmp_path
):
    """測試：修復 proposal_without_approved（proposal 存在）→ 升級為 approved"""
    service = service_with_reader

    # 建立 proposal 檔案
    proposals_dir = tmp_path / "proposals" / "pending"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    proposal_file = proposals_dir / "test-proposal.yaml"
    proposal_file.write_text("data: {}\noperation: {}", encoding="utf-8")

    # 建立不一致 entry（proposal 存在）
    entry = service.add_entry(text="餐飲 320", source="cli")
    entry.proposal_id = "test-proposal.yaml"
    service._store.write_entry(entry)

    # 執行修復
    results = service.repair_inconsistencies(dry_run=False)

    # 驗證：修復成功
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert "升級為 approved" in result.action_taken

    # 驗證：status 已升級
    repaired_entry = service.get_entry(entry.entry_id)
    assert repaired_entry.status == StagingStatus.APPROVED


def test_repair_applied_without_canonical(service_with_reader):
    """測試：修復 applied_without_canonical → 降級為 approved"""
    service = service_with_reader

    # 建立不一致 entry
    entry = service.add_entry(text="餐飲 320", source="cli")
    entry.status = StagingStatus.APPLIED
    entry.proposal_id = "fake-proposal-id.yaml"
    entry.canonical_record_id = None
    service._store.write_entry(entry)

    # 執行修復
    results = service.repair_inconsistencies(dry_run=False)

    # 驗證：修復成功
    assert len(results) == 1
    result = results[0]
    assert result.success is True
    assert "降級為 approved" in result.action_taken

    # 驗證：status 已降級
    repaired_entry = service.get_entry(entry.entry_id)
    assert repaired_entry.status == StagingStatus.APPROVED
    assert repaired_entry.canonical_record_id is None


def test_repair_dry_run_no_changes(service_with_reader):
    """測試：dry-run 模式不實際修改"""
    service = service_with_reader

    # 建立不一致 entry
    entry = service.add_entry(text="餐飲 320", source="cli")
    entry.status = StagingStatus.APPROVED
    entry.proposal_id = None
    service._store.write_entry(entry)

    # 執行 dry-run 修復
    results = service.repair_inconsistencies(dry_run=True)

    # 驗證：有修復結果
    assert len(results) == 1
    assert results[0].success is True

    # 驗證：entry 狀態未變更
    entry_after = service.get_entry(entry.entry_id)
    assert entry_after.status == StagingStatus.APPROVED  # 未變更


def test_repair_multiple_inconsistencies(service_with_reader):
    """測試：修復多筆不一致"""
    service = service_with_reader

    # 建立 3 筆不一致的 entries
    entry1 = service.add_entry(text="餐飲 320", source="cli")
    entry1.status = StagingStatus.APPROVED
    entry1.proposal_id = None
    service._store.write_entry(entry1)

    entry2 = service.add_entry(text="交通 100", source="cli")
    entry2.proposal_id = "non-existent.yaml"
    service._store.write_entry(entry2)

    entry3 = service.add_entry(text="購物 500", source="cli")
    entry3.status = StagingStatus.APPLIED
    entry3.proposal_id = "fake.yaml"
    entry3.canonical_record_id = None
    service._store.write_entry(entry3)

    # 執行修復
    results = service.repair_inconsistencies(dry_run=False)

    # 驗證：全部修復成功
    assert len(results) == 3
    assert all(r.success for r in results)

    # 驗證：entries 已修復
    assert service.get_entry(entry1.entry_id).status == StagingStatus.PARSED
    assert service.get_entry(entry2.entry_id).proposal_id is None
    assert service.get_entry(entry3.entry_id).status == StagingStatus.APPROVED


# === InconsistencyReport & RepairResult 資料結構測試 ===


def test_inconsistency_report_structure():
    """測試：InconsistencyReport 資料結構"""
    report = InconsistencyReport(
        entry_id="test-id",
        inconsistency_type="approved_without_proposal",
        current_status="approved",
        description="test description",
        suggested_fix="test fix",
    )

    assert report.entry_id == "test-id"
    assert report.inconsistency_type == "approved_without_proposal"
    assert report.current_status == "approved"
    assert report.description == "test description"
    assert report.suggested_fix == "test fix"


def test_repair_result_structure():
    """測試：RepairResult 資料結構"""
    result = RepairResult(
        entry_id="test-id",
        inconsistency_type="approved_without_proposal",
        action_taken="降級為 parsed",
        success=True,
    )

    assert result.entry_id == "test-id"
    assert result.inconsistency_type == "approved_without_proposal"
    assert result.action_taken == "降級為 parsed"
    assert result.success is True
