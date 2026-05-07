"""測試 DecisionsHandler V1.1 功能

測試 round-trip、向後相容、ID 重複檢查、狀態轉換驗證。
"""

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from life_capital.io.decisions_handler import (
    DecisionsHandler,
    DuplicateDecisionError,
    InvalidTransitionError,
)
from life_capital.models.decisions import (
    ConfidenceLevel,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
    generate_decision_id,
)
from life_capital.models.operation import Operation, OperationType


@pytest.fixture
def temp_data_path():
    """建立臨時資料目錄"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def handler(temp_data_path):
    """建立 handler 實例"""
    return DecisionsHandler(temp_data_path)


@pytest.fixture
def sample_operation():
    """建立範例 operation"""
    return Operation(
        operation_id=uuid4(),
        actor="test_user",
        operation_type=OperationType.APPLY,
        target_path=Path("/tmp/test"),
        description="Test operation",
    )


@pytest.fixture
def sample_record():
    """建立範例 record"""
    return DecisionRecord(
        decision_id=generate_decision_id(),
        operation_id="01JGTEST00000000000001",
        created_at="2025-12-29T10:00:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.8,
        input_hash="abc123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["test"],
        risk_explanation="測試風險",
    )


# === Round-trip 測試 ===


def test_roundtrip_with_rationale(handler, sample_operation):
    """含 decision_rationale 的 round-trip"""
    rationale = "基於市場分析的決策理由"

    record = DecisionRecord(
        decision_id=generate_decision_id(),
        operation_id="01JGTEST00000000000001",
        created_at="2025-12-29T10:00:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.85,
        input_hash="rationale123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["market"],
        risk_explanation="市場風險",
        decision_rationale=rationale,
    )

    # 寫入
    handler.write_decision(record, sample_operation)

    # 讀取
    loaded = handler.get_by_decision_id(record.decision_id)

    assert loaded is not None
    assert loaded.decision_rationale == rationale


def test_roundtrip_with_reverted_from(handler, sample_operation):
    """含 reverted_from_decision_id 的 round-trip"""
    original_id = "dec_original_001"

    record = DecisionRecord(
        decision_id=generate_decision_id(),
        operation_id="01JGTEST00000000000002",
        created_at="2025-12-29T10:05:00Z",
        template_id="default",
        status=DecisionStatus.REVERTED,
        confidence=ConfidenceLevel.MEDIUM,
        comparability_score=0.7,
        input_hash="reverted123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["test"],
        risk_explanation="測試",
        reverted_at="2025-12-29T10:05:00Z",
        reverted_by="01JGTEST00000000000002",
        reverted_from_decision_id=original_id,
    )

    # 寫入
    handler.write_decision(record, sample_operation)

    # 讀取
    loaded = handler.get_by_decision_id(record.decision_id)

    assert loaded is not None
    assert loaded.reverted_from_decision_id == original_id


def test_roundtrip_v11_full(handler, sample_operation):
    """完整 V1.1 欄位 round-trip"""
    rationale = "完整的決策理由說明"
    original_id = "dec_full_original_001"

    record = DecisionRecord(
        decision_id=generate_decision_id(),
        operation_id="01JGTEST00000000000003",
        created_at="2025-12-29T10:10:00Z",
        template_id="default",
        status=DecisionStatus.REVERTED,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.9,
        input_hash="full123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A：延後",
            recommendation="建議延後",
            score=0.75,
            status="comparable",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B：立即",
            recommendation="建議立即",
            score=0.92,
            status="comparable",
        ),
        risk_tags=["market", "timing"],
        risk_explanation="市場與時機風險",
        reverted_at="2025-12-29T10:10:00Z",
        reverted_by="01JGTEST00000000000003",
        decision_rationale=rationale,
        reverted_from_decision_id=original_id,
    )

    # 寫入
    handler.write_decision(record, sample_operation)

    # 讀取
    loaded = handler.get_by_decision_id(record.decision_id)

    assert loaded is not None
    assert loaded.decision_rationale == rationale
    assert loaded.reverted_from_decision_id == original_id
    assert loaded.status == DecisionStatus.REVERTED


# === 向後相容測試 ===


def test_read_v10_decisions_yaml(temp_data_path):
    """讀取 V1.0 決策檔案"""
    # 複製 V1.0 fixture 到測試目錄
    fixture_path = Path(__file__).parent.parent / "fixtures" / "decisions" / "v1.0_minimal.yaml"
    decisions_dir = temp_data_path / "canonical" / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    dest_path = decisions_dir / "decisions.yaml"

    shutil.copy(fixture_path, dest_path)

    handler = DecisionsHandler(temp_data_path)
    records = handler.read_all()

    assert len(records) == 1
    record = records[0]

    # V1.0 欄位正常讀取
    assert record.decision_id == "dec_01JGTEST00000000000001"
    assert record.status == DecisionStatus.PENDING

    # V1.1 新欄位為 None
    assert record.decision_rationale is None
    assert record.reverted_from_decision_id is None


def test_v10_missing_fields_default_none(temp_data_path):
    """V1.0 缺失欄位預設為 None"""
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "decisions" / "v1.0_with_reverts.yaml"
    )
    decisions_dir = temp_data_path / "canonical" / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    dest_path = decisions_dir / "decisions.yaml"

    shutil.copy(fixture_path, dest_path)

    handler = DecisionsHandler(temp_data_path)
    records = handler.read_all()

    assert len(records) == 2

    for record in records:
        # 所有 V1.0 記錄的新欄位應為 None
        assert record.decision_rationale is None
        assert record.reverted_from_decision_id is None


def test_write_v11_preserves_v10_fields(handler, sample_operation):
    """寫入 V1.1 保留 V1.0 欄位"""
    record = DecisionRecord(
        decision_id=generate_decision_id(),
        operation_id="01JGTEST00000000000004",
        created_at="2025-12-29T10:15:00Z",
        template_id="default",
        status=DecisionStatus.APPLIED,
        confidence=ConfidenceLevel.MEDIUM,
        comparability_score=0.65,
        input_hash="preserve123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["preserve"],
        risk_explanation="保留測試",
        # 不設定 V1.1 欄位
    )

    handler.write_decision(record, sample_operation)
    loaded = handler.get_by_decision_id(record.decision_id)

    # V1.0 欄位完整保留
    assert loaded.decision_id == record.decision_id
    assert loaded.status == DecisionStatus.APPLIED
    assert loaded.confidence == ConfidenceLevel.MEDIUM
    assert loaded.comparability_score == 0.65

    # V1.1 欄位為 None
    assert loaded.decision_rationale is None
    assert loaded.reverted_from_decision_id is None


# === ID 重複檢查測試 ===


def test_duplicate_decision_id_raises(handler, sample_operation):
    """重複 decision_id 拋出錯誤"""
    decision_id = "dec_duplicate_test_001"

    record1 = DecisionRecord(
        decision_id=decision_id,
        operation_id="01JGTEST00000000000005",
        created_at="2025-12-29T10:20:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.8,
        input_hash="dup123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["test"],
        risk_explanation="測試",
    )

    # 第一次寫入成功
    handler.write_decision(record1, sample_operation)

    record2 = DecisionRecord(
        decision_id=decision_id,  # 相同 ID
        operation_id="01JGTEST00000000000006",
        created_at="2025-12-29T10:25:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.MEDIUM,
        comparability_score=0.7,
        input_hash="dup456",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["test"],
        risk_explanation="測試",
    )

    # 第二次寫入應拋出錯誤
    with pytest.raises(DuplicateDecisionError) as exc_info:
        handler.write_decision(record2, sample_operation)

    assert decision_id in str(exc_info.value)


def test_unique_decision_id_allowed(handler, sample_operation):
    """唯一 decision_id 允許"""
    record1 = DecisionRecord(
        decision_id="dec_unique_001",
        operation_id="01JGTEST00000000000007",
        created_at="2025-12-29T10:30:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.8,
        input_hash="unique1",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["test"],
        risk_explanation="測試",
    )

    record2 = DecisionRecord(
        decision_id="dec_unique_002",  # 不同 ID
        operation_id="01JGTEST00000000000008",
        created_at="2025-12-29T10:35:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.MEDIUM,
        comparability_score=0.7,
        input_hash="unique2",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["test"],
        risk_explanation="測試",
    )

    # 兩次寫入都成功
    handler.write_decision(record1, sample_operation)
    handler.write_decision(record2, sample_operation)

    records = handler.read_all()
    assert len(records) == 2


# === 狀態轉換測試 ===


def test_pending_to_applied_allowed(handler):
    """PENDING → APPLIED 轉換允許"""
    handler._validate_transition(DecisionStatus.PENDING, DecisionStatus.APPLIED)
    # 不應拋出錯誤


def test_applied_to_reverted_allowed(handler):
    """APPLIED → REVERTED 轉換允許"""
    handler._validate_transition(DecisionStatus.APPLIED, DecisionStatus.REVERTED)
    # 不應拋出錯誤


def test_reverted_to_applied_blocked(handler):
    """REVERTED → APPLIED 轉換被阻擋"""
    with pytest.raises(InvalidTransitionError) as exc_info:
        handler._validate_transition(DecisionStatus.REVERTED, DecisionStatus.APPLIED)

    error_msg = str(exc_info.value)
    # 檢查包含狀態名稱（可能是小寫）
    assert "reverted" in error_msg.lower()
    assert "applied" in error_msg.lower()


def test_applied_to_pending_blocked(handler):
    """APPLIED → PENDING 轉換被阻擋"""
    with pytest.raises(InvalidTransitionError) as exc_info:
        handler._validate_transition(DecisionStatus.APPLIED, DecisionStatus.PENDING)

    error_msg = str(exc_info.value)
    # 檢查包含狀態名稱（可能是小寫）
    assert "applied" in error_msg.lower()
    assert "pending" in error_msg.lower()


# === mark_reverted() 整合測試 ===


def test_mark_reverted_creates_new_record_with_v11_fields(handler, sample_operation):
    """mark_reverted() 建立含 V1.1 欄位的新記錄"""
    # 建立原始記錄
    original_rationale = "原始決策的理由"
    original_record = DecisionRecord(
        decision_id="dec_original_for_revert",
        operation_id="01JGTEST00000000000009",
        created_at="2025-12-29T10:40:00Z",
        template_id="default",
        status=DecisionStatus.APPLIED,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.85,
        input_hash="revert123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["revert_test"],
        risk_explanation="回滾測試",
        decision_rationale=original_rationale,
    )

    handler.write_decision(original_record, sample_operation)

    # 執行回滾
    reverted_record = handler.mark_reverted(
        original_record.decision_id,
        sample_operation,
    )

    # 驗證 V1.1 欄位
    assert reverted_record.decision_rationale == original_rationale
    assert reverted_record.reverted_from_decision_id == original_record.decision_id
    assert reverted_record.status == DecisionStatus.REVERTED

    # 驗證建立了新記錄
    assert reverted_record.decision_id != original_record.decision_id

    # 驗證可從 handler 讀取
    loaded = handler.get_by_decision_id(reverted_record.decision_id)
    assert loaded is not None
    assert loaded.reverted_from_decision_id == original_record.decision_id
