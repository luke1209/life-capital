"""Decision Wiki 編譯器測試

測試 Decision Wiki 的生成邏輯，包含結構、內容、過濾與排序。
"""

import json
import tempfile
from pathlib import Path

import pytest

from life_capital.generation.decision_wiki import (
    _format_decision,
    generate_wiki,
    save_wiki,
)
from life_capital.models.decisions import (
    ConfidenceLevel,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
)


@pytest.fixture
def sample_decisions():
    """範例決策記錄列表"""
    return [
        DecisionRecord(
            decision_id="dec_001",
            operation_id="op_001",
            created_at="2024-12-28T10:00:00Z",
            template_id="template_a",
            status=DecisionStatus.APPLIED,
            confidence=ConfidenceLevel.HIGH,
            comparability_score=0.85,
            input_hash="abc123" * 8,
            option_a=DecisionOption(
                direction="conservative",
                label="Option A: Conservative approach",
                recommendation="Stay safe",
                score=0.7,
            ),
            option_b=DecisionOption(
                direction="aggressive",
                label="Option B: Aggressive approach",
                recommendation="Take risk",
                score=0.8,
            ),
            risk_tags=["market_volatility", "liquidity"],
            risk_explanation="Market conditions uncertain",
            decision_rationale="Based on recent market analysis",
        ),
        DecisionRecord(
            decision_id="dec_002",
            operation_id="op_002",
            created_at="2024-12-29T11:00:00Z",
            template_id="template_b",
            status=DecisionStatus.PENDING,
            confidence=ConfidenceLevel.MEDIUM,
            comparability_score=0.65,
            input_hash="def456" * 8,
            option_a=DecisionOption(
                direction="conservative",
                label="Option A: Wait",
            ),
            option_b=DecisionOption(
                direction="aggressive",
                label="Option B: Act now",
            ),
            risk_tags=["timing"],
            risk_explanation="Timing is critical",
        ),
        # Reverted decision (should be excluded)
        DecisionRecord(
            decision_id="dec_003",
            operation_id="op_003",
            created_at="2024-12-27T09:00:00Z",
            template_id="template_a",
            status=DecisionStatus.REVERTED,
            confidence=ConfidenceLevel.LOW,
            comparability_score=0.5,
            input_hash="ghi789" * 8,
            option_a=DecisionOption(
                direction="conservative",
                label="Reverted option A",
            ),
            option_b=DecisionOption(
                direction="aggressive",
                label="Reverted option B",
            ),
            risk_tags=[],
            risk_explanation="Reverted due to error",
            reverted_from_decision_id="dec_001",
        ),
        # Expired decision (should be excluded)
        DecisionRecord(
            decision_id="dec_004",
            operation_id="op_004",
            created_at="2024-12-26T08:00:00Z",
            template_id="template_c",
            status=DecisionStatus.EXPIRED,
            confidence=ConfidenceLevel.HIGH,
            comparability_score=0.9,
            input_hash="jkl012" * 8,
            option_a=DecisionOption(
                direction="conservative",
                label="Expired option A",
            ),
            option_b=DecisionOption(
                direction="aggressive",
                label="Expired option B",
            ),
            risk_tags=[],
            risk_explanation="Expired naturally",
        ),
    ]


# === 結構測試 (6 tests) ===


def test_wiki_has_title(sample_decisions):
    """Wiki 包含標題"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "# Decision History" in wiki


def test_wiki_has_timestamp(sample_decisions):
    """Wiki 包含時間戳"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "**Last Updated**:" in wiki


def test_wiki_has_decision_count(sample_decisions):
    """Wiki 包含決策數量"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "**Total Decisions**:" in wiki
    # 只計算有效決策（排除 reverted 與 expired）
    assert "**Total Decisions**: 2" in wiki


def test_decision_section_has_id(sample_decisions):
    """每個決策有 ID 標題"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "## dec_001" in wiki
    assert "## dec_002" in wiki
    # Reverted 與 expired 不應出現
    assert "## dec_003" not in wiki
    assert "## dec_004" not in wiki


def test_decision_has_status(sample_decisions):
    """決策包含狀態資訊"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "**Status**: applied" in wiki
    assert "**Status**: pending" in wiki


def test_decision_has_options(sample_decisions):
    """決策包含兩個選項"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "### Option A (Conservative)" in wiki
    assert "### Option B (Aggressive)" in wiki


# === 必含 Token 測試 (5 tests) ===


def test_decision_id_in_wiki(sample_decisions):
    """decision_id 在 Wiki 中"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "dec_001" in wiki
    assert "dec_002" in wiki


def test_status_value_in_wiki(sample_decisions):
    """status.value 在 Wiki 中"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "applied" in wiki
    assert "pending" in wiki


def test_template_id_in_wiki(sample_decisions):
    """template_id 在 Wiki 中"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "template_a" in wiki
    assert "template_b" in wiki


def test_risk_tags_in_wiki(sample_decisions):
    """risk_tags 在 Wiki 中"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "`market_volatility`" in wiki
    assert "`liquidity`" in wiki
    assert "`timing`" in wiki


def test_option_labels_in_wiki(sample_decisions):
    """option labels 在 Wiki 中"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "Option A: Conservative approach" in wiki
    assert "Option B: Aggressive approach" in wiki
    assert "Option A: Wait" in wiki
    assert "Option B: Act now" in wiki


# === V1.1 欄位測試 (3 tests) ===


def test_rationale_in_wiki_if_present(sample_decisions):
    """rationale 出現時包含"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "### Rationale" in wiki
    assert "Based on recent market analysis" in wiki


def test_rationale_absent_if_none():
    """rationale 為 None 時不包含"""
    decision = DecisionRecord(
        decision_id="dec_no_rationale",
        operation_id="op_999",
        created_at="2024-12-30T12:00:00Z",
        template_id="template_x",
        status=DecisionStatus.APPLIED,
        confidence=ConfidenceLevel.HIGH,
        comparability_score=0.9,
        input_hash="xyz999" * 8,
        option_a=DecisionOption(
            direction="conservative",
            label="A",
        ),
        option_b=DecisionOption(
            direction="aggressive",
            label="B",
        ),
        risk_tags=[],
        risk_explanation="No risk",
        decision_rationale=None,  # 明確為 None
    )

    lines = _format_decision(decision)
    content = "\n".join(lines)
    assert "### Rationale" not in content


def test_reverted_from_in_wiki(sample_decisions):
    """reverted_from_decision_id 出現時包含"""
    # dec_003 is reverted, so not in main wiki
    # Let's check if it would appear in formatting
    reverted = [d for d in sample_decisions if d.decision_id == "dec_003"][0]
    lines = _format_decision(reverted)
    content = "\n".join(lines)
    assert "### Reverted From" in content
    assert "dec_001" in content


# === 順序與過濾 (3 tests) ===


def test_decisions_sorted_by_time(sample_decisions):
    """按時間排序（最新在前）"""
    wiki = generate_wiki(sample_decisions, Path("."))
    # dec_002 (2024-12-29) 應在 dec_001 (2024-12-28) 之前
    pos_002 = wiki.find("## dec_002")
    pos_001 = wiki.find("## dec_001")
    assert pos_002 < pos_001, "最新決策應該排在前面"


def test_reverted_excluded(sample_decisions):
    """reverted 決策被排除"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "dec_003" not in wiki


def test_expired_excluded(sample_decisions):
    """expired 決策被排除"""
    wiki = generate_wiki(sample_decisions, Path("."))
    assert "dec_004" not in wiki


# === 整合測試 (3 tests) ===


def test_save_wiki_creates_file(sample_decisions):
    """save_wiki() 建立檔案"""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_path = Path(tmpdir)
        # 建立必要目錄
        (data_path / "derived" / "advisor").mkdir(parents=True)

        result_path = save_wiki(sample_decisions, data_path)

        assert result_path.exists()
        assert result_path.suffix == ".md"


def test_save_wiki_creates_meta(sample_decisions):
    """建立 .meta.json"""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_path = Path(tmpdir)
        (data_path / "derived" / "advisor").mkdir(parents=True)

        result_path = save_wiki(sample_decisions, data_path)
        meta_path = result_path.with_suffix(".md.meta.json")

        assert meta_path.exists()


def test_save_wiki_provenance_correct(sample_decisions):
    """Provenance 正確"""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_path = Path(tmpdir)
        (data_path / "derived" / "advisor").mkdir(parents=True)

        result_path = save_wiki(sample_decisions, data_path)
        meta_path = result_path.with_suffix(".md.meta.json")

        with open(meta_path, "r") as f:
            meta = json.load(f)

        assert meta["artifact_type"] == "decision_wiki"
        assert meta["schema_version"] == "1.0"
        assert meta["calc_version"] == "wiki_v1.0"
        assert meta["canonicalization_version"] == "1.0"
        assert len(meta["input_hash"]) == 64  # SHA-256
        assert len(meta["content_hash"]) == 64  # SHA-256
        assert meta["canonical_sources"] == ["canonical/decisions/decisions.yaml"]
        assert meta["rebuild_command"]["cmd"] == ["lc", "advisor", "wiki", "--rebuild"]
        assert meta["redaction_profile_version"] == "none"
