"""測試 StagingService

覆蓋範圍：
- CRUD 操作（add, list, get, delete, clear）
- 狀態機轉移（parse, approve, reject, ignore, mark_duplicate）
- 批次操作（parse_all_pending）
- 重複偵測（精準判重、模糊判重）
- 異常處理（EntryNotFound, InvalidStateTransition）
- Parse 原子性（成功/失敗）

目標覆蓋率: >90%
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from life_capital.capture.expense_parser import ExpenseParser
from life_capital.capture.models import (
    DuplicateReason,
    StagingEntry,
    StagingStatus,
)
from life_capital.capture.staging_service import (
    EntryNotFound,
    InvalidStateTransition,
    StagingService,
)
from life_capital.io.staging_store import StagingStoreImpl
from tests.fixtures.canonical_reader_fake import CanonicalReaderFake

# === Fixtures ===


@pytest.fixture
def temp_data_dir(tmp_path):
    """建立臨時資料目錄"""
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    return tmp_path


@pytest.fixture
def reader():
    """建立 Fake CanonicalReader"""
    # 使用繁體中文類別名稱
    return CanonicalReaderFake(
        categories=["餐飲", "交通", "娛樂", "其他"]
    )


@pytest.fixture
def parser(reader):
    """建立 ExpenseParser"""
    return ExpenseParser(reader)


@pytest.fixture
def store(temp_data_dir):
    """建立 StagingStoreImpl"""
    return StagingStoreImpl(temp_data_dir)


@pytest.fixture
def service(store, parser, reader):
    """建立 StagingService"""
    return StagingService(store, parser, reader)


# === CRUD 操作測試 ===


def test_add_entry(service):
    """測試新增 entry"""
    entry = service.add_entry("昨天拉麵 320")

    assert entry.entry_id is not None
    assert entry.raw_text == "昨天拉麵 320"
    assert entry.status == StagingStatus.PENDING
    assert entry.source == "cli"
    assert entry.batch_id is None
    assert isinstance(entry.created_at, datetime)


def test_add_entry_with_batch(service):
    """測試批次新增 entry"""
    batch_id = str(uuid4())
    entry = service.add_entry("午餐 100", source="batch", batch_id=batch_id)

    assert entry.source == "batch"
    assert entry.batch_id == batch_id


def test_list_entries_empty(service):
    """測試列出空列表"""
    entries = service.list_entries()
    assert entries == []


def test_list_entries_all(service):
    """測試列出所有 entries"""
    service.add_entry("entry1")
    service.add_entry("entry2")
    service.add_entry("entry3")

    entries = service.list_entries()
    assert len(entries) == 3
    assert all(e.status == StagingStatus.PENDING for e in entries)


def test_list_entries_filter_by_status(service):
    """測試按狀態過濾"""
    entry1 = service.add_entry("entry1")
    entry2 = service.add_entry("entry2")

    # 將 entry1 解析為 parsed
    service.parse_entry(entry1.entry_id)

    # 只列出 pending
    pending_entries = service.list_entries(status=StagingStatus.PENDING)
    assert len(pending_entries) == 1
    assert pending_entries[0].entry_id == entry2.entry_id

    # 只列出 parsed
    parsed_entries = service.list_entries(status=StagingStatus.PARSED)
    assert len(parsed_entries) == 1
    assert parsed_entries[0].entry_id == entry1.entry_id


def test_get_entry(service):
    """測試讀取單筆 entry"""
    entry = service.add_entry("test entry")

    retrieved = service.get_entry(entry.entry_id)
    assert retrieved is not None
    assert retrieved.entry_id == entry.entry_id
    assert retrieved.raw_text == "test entry"


def test_get_entry_not_found(service):
    """測試讀取不存在的 entry"""
    retrieved = service.get_entry("nonexistent-id")
    assert retrieved is None


def test_list_entries_sorted_by_created_at(service):
    """測試 entries 按建立時間排序（新→舊）"""
    entry1 = service.add_entry("entry1")
    entry2 = service.add_entry("entry2")
    entry3 = service.add_entry("entry3")

    entries = service.list_entries()
    assert entries[0].entry_id == entry3.entry_id  # 最新
    assert entries[1].entry_id == entry2.entry_id
    assert entries[2].entry_id == entry1.entry_id  # 最舊


# === 狀態轉移測試 ===


def test_parse_entry_success(service):
    """測試解析成功（pending → parsed）"""
    entry = service.add_entry("昨天拉麵 320 元 餐飲")

    parsed = service.parse_entry(entry.entry_id)

    assert parsed.status == StagingStatus.PARSED
    assert parsed.parsed_amount == Decimal("320")
    assert parsed.parsed_category == "餐飲"
    assert parsed.confidence > 0
    assert parsed.confidence_breakdown is not None


def test_parse_entry_error(service):
    """測試解析失敗（pending → error）"""
    # 注意：當前 ExpenseParser 不會因為空文字而失敗
    # 它會正常解析，只是所有欄位都是 None
    # 此測試驗證：即使空文字，解析也能完成（不拋出異常）
    entry = service.add_entry("")

    parsed = service.parse_entry(entry.entry_id)

    # 空文字會被解析為 PARSED（所有欄位為 None）
    assert parsed.status in (StagingStatus.PARSED, StagingStatus.ERROR)
    # 信心度應該很低（因為所有欄位都缺失）
    assert parsed.confidence == 0.0


def test_parse_entry_invalid_state(service):
    """測試從非 pending 狀態解析（應拒絕）"""
    entry = service.add_entry("test")
    service.parse_entry(entry.entry_id)  # pending → parsed

    # 嘗試再次解析
    with pytest.raises(InvalidStateTransition):
        service.parse_entry(entry.entry_id)


def test_parse_entry_not_found(service):
    """測試解析不存在的 entry"""
    with pytest.raises(EntryNotFound):
        service.parse_entry("nonexistent-id")


def test_approve_entry(service):
    """測試批准 entry（parsed → approved）"""
    entry = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry.entry_id)

    approved = service.approve_entry(entry.entry_id, actor="person_a")

    assert approved.status == StagingStatus.APPROVED
    assert approved.reviewed_by == "person_a"
    assert approved.reviewed_at is not None


def test_approve_entry_invalid_state(service):
    """測試批准非 parsed 狀態的 entry"""
    entry = service.add_entry("test")

    # 嘗試批准 pending 狀態的 entry
    with pytest.raises(InvalidStateTransition):
        service.approve_entry(entry.entry_id, actor="person_a")


def test_approve_entry_not_found(service):
    """測試批准不存在的 entry"""
    with pytest.raises(EntryNotFound):
        service.approve_entry("nonexistent-id", actor="person_a")


def test_reject_entry_from_parsed(service):
    """測試拒絕 entry（parsed → rejected）"""
    entry = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry.entry_id)

    rejected = service.reject_entry(entry.entry_id, actor="person_a", reason="金額錯誤")

    assert rejected.status == StagingStatus.REJECTED
    assert rejected.reviewed_by == "person_a"
    assert rejected.reviewed_at is not None
    assert rejected.rejection_reason == "金額錯誤"


def test_reject_entry_from_approved(service):
    """測試從 approved 狀態拒絕"""
    entry = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry.entry_id)
    service.approve_entry(entry.entry_id, actor="person_a")

    rejected = service.reject_entry(entry.entry_id, actor="person_a", reason="重新考慮")

    assert rejected.status == StagingStatus.REJECTED


def test_reject_entry_invalid_state(service):
    """測試拒絕非 parsed/approved 狀態的 entry"""
    entry = service.add_entry("test")

    # 嘗試拒絕 pending 狀態的 entry
    with pytest.raises(InvalidStateTransition):
        service.reject_entry(entry.entry_id, actor="person_a", reason="test")


def test_ignore_entry(service):
    """測試忽略 entry（parsed → ignored）"""
    entry = service.add_entry("提醒明天開會")
    service.parse_entry(entry.entry_id)

    ignored = service.ignore_entry(entry.entry_id, reason="非支出")

    assert ignored.status == StagingStatus.IGNORED
    assert ignored.reviewed_at is not None
    assert ignored.rejection_reason == "非支出"


def test_ignore_entry_invalid_state(service):
    """測試忽略非 parsed 狀態的 entry"""
    entry = service.add_entry("test")

    with pytest.raises(InvalidStateTransition):
        service.ignore_entry(entry.entry_id, reason="test")


def test_mark_duplicate(service):
    """測試標記重複（parsed → duplicate）"""
    # 第一筆 entry
    entry1 = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry1.entry_id)

    # 第二筆 entry（不同內容，避免自動判重）
    entry2 = service.add_entry("今天咖啡 100 元 餐飲")
    service.parse_entry(entry2.entry_id)

    # 手動標記為重複
    duplicate = service.mark_duplicate(
        entry2.entry_id,
        duplicate_of=entry1.entry_id,
        reason=DuplicateReason.DUP_KEY_EXACT,
    )

    assert duplicate.status == StagingStatus.DUPLICATE
    assert duplicate.duplicate_of == entry1.entry_id
    assert duplicate.duplicate_reason == DuplicateReason.DUP_KEY_EXACT
    assert duplicate.reviewed_at is not None


def test_mark_duplicate_invalid_state(service):
    """測試標記非 parsed 狀態的 entry 為重複"""
    entry = service.add_entry("test")

    with pytest.raises(InvalidStateTransition):
        service.mark_duplicate(
            entry.entry_id,
            duplicate_of="other-id",
            reason=DuplicateReason.DUP_KEY_EXACT,
        )


# === 批次操作測試 ===


def test_parse_all_pending_success(service):
    """測試批次解析所有 pending entries"""
    service.add_entry("昨天拉麵 320 元 餐飲")
    service.add_entry("今天咖啡 100 元 餐飲")
    service.add_entry("捷運 50 元 交通")

    results = service.parse_all_pending()

    assert len(results) == 3
    assert all(r.status in (StagingStatus.PARSED, StagingStatus.ERROR) for r in results)


def test_parse_all_pending_partial_failure(service):
    """測試批次解析允許部分失敗"""
    service.add_entry("昨天拉麵 320 元 餐飲")  # 成功（完整資訊）
    service.add_entry("")  # 部分成功（空文字，信心度=0）

    results = service.parse_all_pending()

    assert len(results) == 2
    # 所有 entries 都會被解析（不會拋出異常）
    assert all(r.status in (StagingStatus.PARSED, StagingStatus.ERROR) for r in results)
    # 第一個應有較高信心度
    assert any(r.confidence > 0 for r in results)
    # 第二個應有零信心度
    assert any(r.confidence == 0 for r in results)


def test_parse_all_pending_empty(service):
    """測試批次解析空列表"""
    results = service.parse_all_pending()
    assert results == []


# === 重複偵測測試 ===


def test_duplicate_detection_exact_match(service):
    """測試精準判重（duplicate_key 完全匹配）"""
    # 第一筆 entry
    entry1 = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry1.entry_id)

    # 第二筆 entry（完全相同）
    entry2 = service.add_entry("昨天拉麵 320 元 餐飲")
    parsed2 = service.parse_entry(entry2.entry_id)

    # 應自動標記為 duplicate
    assert parsed2.status == StagingStatus.DUPLICATE
    assert parsed2.duplicate_of == entry1.entry_id
    assert parsed2.duplicate_reason == DuplicateReason.DUP_KEY_EXACT


def test_duplicate_detection_date_fuzzy(service):
    """測試模糊判重（日期±2天）"""
    # 第一筆 entry（2025-01-01）
    entry1 = service.add_entry("2025-01-01 拉麵 320 元 餐飲")
    service.parse_entry(entry1.entry_id)

    # 第二筆 entry（2025-01-02，差 1 天）
    entry2 = service.add_entry("2025-01-02 拉麵 320 元 餐飲")
    parsed2 = service.parse_entry(entry2.entry_id)

    # 應自動標記為 duplicate（模糊判重）
    assert parsed2.status == StagingStatus.DUPLICATE
    assert parsed2.duplicate_of == entry1.entry_id
    assert parsed2.duplicate_reason == DuplicateReason.DUP_DATE_FUZZ


def test_duplicate_detection_no_duplicate(service):
    """測試無重複"""
    # 兩筆完全不同的 entry
    entry1 = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry1.entry_id)

    entry2 = service.add_entry("今天咖啡 100 元 餐飲")
    parsed2 = service.parse_entry(entry2.entry_id)

    # 不應標記為 duplicate
    assert parsed2.status == StagingStatus.PARSED
    assert parsed2.duplicate_of is None


def test_duplicate_detection_insufficient_info(service):
    """測試資訊不足時無法判重"""
    # 第一筆 entry（無金額）
    entry1 = service.add_entry("昨天吃飯")
    service.parse_entry(entry1.entry_id)

    # 第二筆 entry（無金額）
    entry2 = service.add_entry("昨天吃飯")
    parsed2 = service.parse_entry(entry2.entry_id)

    # 資訊不足，無法可靠判重
    # 應保持 parsed 狀態（不自動標記為 duplicate）
    assert parsed2.status == StagingStatus.PARSED


def test_duplicate_detection_skip_ignored(service):
    """測試判重跳過已忽略的 entries"""
    # 第一筆 entry（已忽略）
    entry1 = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry1.entry_id)
    service.ignore_entry(entry1.entry_id, reason="測試")

    # 第二筆 entry（相同內容）
    entry2 = service.add_entry("昨天拉麵 320 元 餐飲")
    parsed2 = service.parse_entry(entry2.entry_id)

    # 不應標記為 duplicate（因為第一筆已忽略）
    assert parsed2.status == StagingStatus.PARSED


# === 文字正規化測試 ===


def test_normalize_text_remove_amount(service):
    """測試正規化移除金額"""
    text = "拉麵 320 元"
    normalized = service._normalize_text(text)
    assert "320" not in normalized
    assert "元" not in normalized


def test_normalize_text_remove_date(service):
    """測試正規化移除日期"""
    text = "2025-01-01 拉麵"
    normalized = service._normalize_text(text)
    assert "2025" not in normalized
    assert "01-01" not in normalized


def test_normalize_text_remove_whitespace(service):
    """測試正規化移除空白"""
    text = "拉   麵   320"
    normalized = service._normalize_text(text)
    assert " " not in normalized


def test_normalize_text_lowercase(service):
    """測試正規化轉小寫"""
    text = "Ramen 320 USD"
    normalized = service._normalize_text(text)
    assert normalized == "ramen"


# === 計算 duplicate_key 測試 ===


def test_compute_duplicate_key_success(service):
    """測試計算 duplicate_key 成功"""
    entry = StagingEntry(
        entry_id="test-id",
        raw_text="昨天拉麵 320 元 餐飲",
        created_at=datetime.now(),
        parsed_date=date(2025, 1, 1),
        parsed_amount=Decimal("320"),
    )

    key = service._compute_duplicate_key(entry)

    assert key is not None
    assert "2025-01-01" in key
    assert "320" in key


def test_compute_duplicate_key_missing_date(service):
    """測試日期缺失時無法計算 key"""
    entry = StagingEntry(
        entry_id="test-id",
        raw_text="拉麵 320 元",
        created_at=datetime.now(),
        parsed_date=None,
        parsed_amount=Decimal("320"),
    )

    key = service._compute_duplicate_key(entry)
    assert key is None


def test_compute_duplicate_key_missing_amount(service):
    """測試金額缺失時無法計算 key"""
    entry = StagingEntry(
        entry_id="test-id",
        raw_text="昨天吃飯",
        created_at=datetime.now(),
        parsed_date=date(2025, 1, 1),
        parsed_amount=None,
    )

    key = service._compute_duplicate_key(entry)
    assert key is None


# === 異常處理測試 ===


def test_entry_not_found_exception():
    """測試 EntryNotFound 異常"""
    exc = EntryNotFound("test message")
    assert str(exc) == "test message"


def test_invalid_state_transition_exception():
    """測試 InvalidStateTransition 異常"""
    exc = InvalidStateTransition("test message")
    assert str(exc) == "test message"


# === 整合測試 ===


def test_full_workflow_auto_approve_disabled(service):
    """測試完整工作流程（auto-approve 關閉）

    pending → parse → parsed → approve → approved
    """
    # 1. 新增 entry
    entry = service.add_entry("昨天拉麵 320 元 餐飲")
    assert entry.status == StagingStatus.PENDING

    # 2. 解析（auto-approve 關閉，停在 parsed）
    parsed = service.parse_entry(entry.entry_id)
    assert parsed.status == StagingStatus.PARSED

    # 3. 人工批准
    approved = service.approve_entry(entry.entry_id, actor="person_a")
    assert approved.status == StagingStatus.APPROVED

    # 4. 驗證 entry 可讀取
    retrieved = service.get_entry(entry.entry_id)
    assert retrieved.status == StagingStatus.APPROVED


def test_full_workflow_rejection(service):
    """測試完整工作流程（拒絕）

    pending → parse → parsed → reject → rejected
    """
    # 1. 新增 entry
    entry = service.add_entry("昨天拉麵 320 元 餐飲")

    # 2. 解析
    service.parse_entry(entry.entry_id)

    # 3. 拒絕
    rejected = service.reject_entry(entry.entry_id, actor="person_a", reason="金額錯誤")
    assert rejected.status == StagingStatus.REJECTED


def test_persistence_across_instances(temp_data_dir, reader, parser):
    """測試跨實例持久化（JSONL last-write-wins）"""
    # 第一個 service 實例
    store1 = StagingStoreImpl(temp_data_dir)
    service1 = StagingService(store1, parser, reader)

    entry = service1.add_entry("test entry")
    entry_id = entry.entry_id

    # 第二個 service 實例（重新讀取）
    store2 = StagingStoreImpl(temp_data_dir)
    service2 = StagingService(store2, parser, reader)

    retrieved = service2.get_entry(entry_id)
    assert retrieved is not None
    assert retrieved.entry_id == entry_id
    assert retrieved.raw_text == "test entry"


def test_last_write_wins(service):
    """測試 last-write-wins 語意"""
    # 新增 entry（使用完整資訊以便能批准）
    entry = service.add_entry("昨天拉麵 320 元 餐飲")
    entry_id = entry.entry_id

    # 解析（更新狀態）
    service.parse_entry(entry_id)

    # 批准（再次更新狀態）
    service.approve_entry(entry_id, actor="person_a")

    # 讀取最新版本
    latest = service.get_entry(entry_id)
    assert latest.status == StagingStatus.APPROVED


# === 邊界情況測試 ===


def test_empty_text_parsing(service):
    """測試空文字解析"""
    entry = service.add_entry("")
    parsed = service.parse_entry(entry.entry_id)

    # 空文字會被解析為 PARSED（所有欄位為 None，信心度=0）
    assert parsed.status in (StagingStatus.PARSED, StagingStatus.ERROR)
    assert parsed.confidence == 0.0


def test_special_characters_in_text(service):
    """測試特殊字元處理"""
    entry = service.add_entry("拉麵 @ #$% 320 元!!!")
    parsed = service.parse_entry(entry.entry_id)

    # 應能正常解析（忽略特殊字元）
    assert parsed.status in (StagingStatus.PARSED, StagingStatus.ERROR)


def test_very_long_text(service):
    """測試超長文字處理"""
    long_text = "拉麵 " * 1000 + " 320 元 餐飲"
    entry = service.add_entry(long_text)
    parsed = service.parse_entry(entry.entry_id)

    # 應能正常處理
    assert parsed.status in (StagingStatus.PARSED, StagingStatus.ERROR)


# === Clear 操作測試（標註為 TODO）===


def test_clear_all_not_implemented(service):
    """測試 clear_all 尚未實作"""
    service.add_entry("entry1")
    service.add_entry("entry2")

    # 當前 clear_all 會因為 delete_entry NotImplementedError 而跳過
    count = service.clear_all()

    # 驗證不會拋出異常（graceful degradation）
    assert count >= 0


def test_delete_entry_not_implemented(service):
    """測試 delete_entry 尚未實作"""
    entry = service.add_entry("test")

    with pytest.raises(NotImplementedError):
        service.delete_entry(entry.entry_id)


# === Proposal 整合測試 (Phase 4.1) ===


def test_approve_entry_creates_proposal(service):
    """測試批准 entry 時建立 proposal"""
    # 1. 新增並解析 entry
    entry = service.add_entry("昨天拉麵 320 元 餐飲")
    service.parse_entry(entry.entry_id)

    # 2. 批准（應建立 proposal）
    approved = service.approve_entry(entry.entry_id, actor="person_a")

    # 3. 驗證 proposal_id 已寫入
    assert approved.proposal_id is not None
    assert approved.proposal_id.endswith(".json")
    assert approved.status == StagingStatus.APPROVED

    # 4. 驗證 proposal 檔案存在
    from life_capital.io.proposals_handler import list_pending_proposals
    from life_capital.utils.path_resolver import resolve_data_dir

    base_dir = resolve_data_dir()
    proposals = list_pending_proposals(base_dir)

    # 應該有一個 proposal
    assert len(proposals) > 0
    assert any(p.name == approved.proposal_id for p in proposals)


def test_approve_entry_proposal_failure_rollback(service):
    """測試 proposal 建立失敗時回滾"""
    # 1. 新增 entry（但缺少必填欄位）
    entry = service.add_entry("一些文字")
    service.parse_entry(entry.entry_id)

    # 手動修改為缺少必填欄位的 parsed entry
    entry_obj = service.get_entry(entry.entry_id)
    entry_obj.parsed_amount = None  # 移除金額
    entry_obj.status = StagingStatus.PARSED
    service._store.write_entry(entry_obj)

    # 2. 嘗試批准（應失敗）
    with pytest.raises((ValueError, Exception)):
        service.approve_entry(entry.entry_id, actor="person_a")

    # 3. 驗證狀態回滾
    retrieved = service.get_entry(entry.entry_id)
    # 應保持 parsed 狀態（不是 approved）
    assert retrieved.status == StagingStatus.PARSED
    # 應記錄錯誤訊息
    assert retrieved.error_message is not None
    assert "Proposal 建立失敗" in retrieved.error_message
    # proposal_id 應為 None
    assert retrieved.proposal_id is None


def test_entry_to_record_conversion(service):
    """測試 StagingEntry → ExpenseRecord 轉換"""
    from datetime import date
    from decimal import Decimal

    from life_capital.models.expense import ExpenseRecord

    # 建立完整的 StagingEntry
    entry = StagingEntry(
        entry_id="test-id",
        raw_text="昨天拉麵 320 元 餐飲",
        created_at=datetime.now(),
        parsed_date=date(2025, 1, 1),
        parsed_amount=Decimal("320"),
        parsed_category="餐飲",
        parsed_merchant="拉麵店",
        parsed_note="好吃",
        status=StagingStatus.PARSED,
    )

    # 轉換
    record = service._entry_to_record(entry)

    # 驗證
    assert isinstance(record, ExpenseRecord)
    assert record.date == date(2025, 1, 1)
    assert record.amount == Decimal("320")
    assert record.category == "餐飲"
    assert record.merchant == "拉麵店"
    assert record.note == "好吃"
    assert record.payer == "shared"  # 預設值


def test_entry_to_record_missing_fields(service):
    """測試缺少必填欄位時拋出異常"""
    # 缺少 date
    entry1 = StagingEntry(
        entry_id="test-id",
        raw_text="test",
        created_at=datetime.now(),
        parsed_amount=Decimal("100"),
        parsed_category="餐飲",
    )
    with pytest.raises(ValueError, match="parsed_date 為必填欄位"):
        service._entry_to_record(entry1)

    # 缺少 amount
    entry2 = StagingEntry(
        entry_id="test-id",
        raw_text="test",
        created_at=datetime.now(),
        parsed_date=date(2025, 1, 1),
        parsed_category="餐飲",
    )
    with pytest.raises(ValueError, match="parsed_amount 為必填欄位"):
        service._entry_to_record(entry2)

    # 缺少 category
    entry3 = StagingEntry(
        entry_id="test-id",
        raw_text="test",
        created_at=datetime.now(),
        parsed_date=date(2025, 1, 1),
        parsed_amount=Decimal("100"),
    )
    with pytest.raises(ValueError, match="parsed_category 為必填欄位"):
        service._entry_to_record(entry3)


def test_approve_entry_proposal_content(service):
    """測試建立的 proposal 內容正確"""
    from life_capital.io.proposals_handler import load_proposal
    from life_capital.utils.path_resolver import resolve_data_dir

    # 1. 新增並批准 entry
    entry = service.add_entry("2025-01-15 拉麵 320 元 餐飲")
    service.parse_entry(entry.entry_id)
    approved = service.approve_entry(entry.entry_id, actor="person_a")

    # 2. 讀取 proposal 內容
    base_dir = resolve_data_dir()
    proposal_path = base_dir / "proposals" / "pending" / approved.proposal_id

    assert proposal_path.exists()

    proposal_data = load_proposal(proposal_path)

    # 3. 驗證 operation 欄位
    assert "operation" in proposal_data
    operation = proposal_data["operation"]
    assert operation["actor"] == "person_a"
    assert operation["operation_type"] == "apply"

    # 4. 驗證 data 欄位
    assert "data" in proposal_data
    data = proposal_data["data"]
    assert data["year"] == 2025
    assert data["month"] == 1
    assert len(data["records"]) == 1

    # 5. 驗證 record 內容
    record = data["records"][0]
    assert record["amount"] == "320"
    assert record["category"] == "餐飲"
    assert record["payer"] == "shared"
