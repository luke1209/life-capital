"""測試 DecisionRecord V1.1 新欄位

測試新增的 decision_rationale 與 reverted_from_decision_id 欄位。
"""

from life_capital.models.decisions import (
    ConfidenceLevel,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
)


def test_new_fields_optional():
    """V1.1 新欄位為 optional"""
    record = DecisionRecord(
        decision_id="dec_test001",
        operation_id="op_test001",
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

    # 新欄位應為 None（預設值）
    assert record.decision_rationale is None
    assert record.reverted_from_decision_id is None


def test_decision_rationale_preserved():
    """decision_rationale 正確保留"""
    rationale = "基於當前市場條件，建議採取保守策略"

    record = DecisionRecord(
        decision_id="dec_test002",
        operation_id="op_test002",
        created_at="2025-12-29T10:00:00Z",
        template_id="default",
        status=DecisionStatus.APPLIED,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.85,
        input_hash="def456",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=["market_risk"],
        risk_explanation="市場風險說明",
        decision_rationale=rationale,
    )

    assert record.decision_rationale == rationale


def test_reverted_from_decision_id_link():
    """reverted_from_decision_id 回滾鏈正確連結"""
    original_id = "dec_original001"

    reverted_record = DecisionRecord(
        decision_id="dec_reverted001",
        operation_id="op_reverted001",
        created_at="2025-12-29T10:05:00Z",
        template_id="default",
        status=DecisionStatus.REVERTED,
        confidence=ConfidenceLevel.MEDIUM,
        comparability_score=0.7,
        input_hash="ghi789",
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
        reverted_by="op_reverted001",
        reverted_from_decision_id=original_id,
    )

    assert reverted_record.reverted_from_decision_id == original_id
    assert reverted_record.is_reverted()


def test_v10_compatibility():
    """V1.0 欄位仍可用（向後相容）"""
    record = DecisionRecord(
        decision_id="dec_v10_001",
        operation_id="op_v10_001",
        created_at="2025-12-29T10:00:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.8,
        input_hash="v10hash",
        option_a=DecisionOption(
            direction="conservative",
            label="V1.0 方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="V1.0 方案 B",
        ),
        risk_tags=["v10_risk"],
        risk_explanation="V1.0 風險",
        # V1.0 不含 decision_rationale 與 reverted_from_decision_id
    )

    # 所有 V1.0 欄位正常運作
    assert record.decision_id == "dec_v10_001"
    assert record.status == DecisionStatus.PENDING
    assert record.confidence == ConfidenceLevel.HIGH
    assert record.decision_rationale is None
    assert record.reverted_from_decision_id is None


def test_frozen_immutable():
    """frozen dataclass 不可變"""
    record = DecisionRecord(
        decision_id="dec_frozen001",
        operation_id="op_frozen001",
        created_at="2025-12-29T10:00:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.8,
        input_hash="frozen123",
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

    try:
        record.decision_rationale = "嘗試修改"
        assert False, "應該拋出錯誤"
    except AttributeError:
        pass  # 預期行為


def test_default_values_none():
    """新欄位預設值為 None"""
    record = DecisionRecord(
        decision_id="dec_default001",
        operation_id="op_default001",
        created_at="2025-12-29T10:00:00Z",
        template_id="default",
        status=DecisionStatus.PENDING,
        confidence=ConfidenceLevel.MEDIUM,
        comparability_score=0.6,
        input_hash="default123",
        option_a=DecisionOption(
            direction="conservative",
            label="方案 A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="方案 B",
        ),
        risk_tags=[],
        risk_explanation="",
    )

    assert record.decision_rationale is None
    assert record.reverted_from_decision_id is None


def test_max_length_rationale():
    """decision_rationale 支援長文本"""
    long_rationale = "基於" + "詳細分析" * 200 + "的結論"

    record = DecisionRecord(
        decision_id="dec_long001",
        operation_id="op_long001",
        created_at="2025-12-29T10:00:00Z",
        template_id="default",
        status=DecisionStatus.APPLIED,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.9,
        input_hash="long123",
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
        decision_rationale=long_rationale,
    )

    # 中文字元：「詳細分析」= 4 字 × 200 = 800 字 + 「基於」+ 「的結論」
    assert len(record.decision_rationale) > 500
    assert record.decision_rationale == long_rationale


def test_decision_id_format_validation():
    """decision_id 格式驗證（邏輯測試）"""
    # 此處主要測試 dataclass 是否接受正確格式
    valid_formats = [
        "dec_01JGTEST00000000000001",
        "dec_ABC123DEF456GHI789JKL",
        "dec_lowercase_ulid_example",
    ]

    for dec_id in valid_formats:
        record = DecisionRecord(
            decision_id=dec_id,
            operation_id="op_test",
            created_at="2025-12-29T10:00:00Z",
            template_id="default",
            status=DecisionStatus.PENDING,
            confidence=ConfidenceLevel.MEDIUM,
            comparability_score=0.5,
            input_hash="format123",
            option_a=DecisionOption(
                direction="conservative",
                label="方案 A",
            ),
            option_b=DecisionOption(
                direction="aggressive",
                label="方案 B",
            ),
            risk_tags=[],
            risk_explanation="",
        )

        assert record.decision_id == dec_id
