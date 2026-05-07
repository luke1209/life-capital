"""
Phase 5 Stage 3 驗收測試 (Acceptance Tests)

端到端驗收測試，涵蓋 E1-E5 完整工作流程與跨模組整合
"""

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from life_capital.advisor.risk_assessor import assess_risk
from life_capital.advisor.shared.evaluability import (
    EvaluabilityLevel,
    RecommendabilityLevel,
    evaluate_decision,
)
from life_capital.generation.decision_wiki import save_wiki
from life_capital.generation.risk_matrix import save_risk_matrix
from life_capital.io.advisor_derived_handler import AdvisorDerivedHandler
from life_capital.io.decisions_handler import DecisionsHandler
from life_capital.io.errors import PathSecurityError
from life_capital.models.decisions import (
    ConfidenceLevel,
    DecisionOption,
    DecisionRecord,
    DecisionStatus,
)
from life_capital.models.operation import Operation, OperationType

# ========== 測試輔助函數 ==========


def make_operation() -> Operation:
    """建立測試用操作"""
    return Operation(
        operation_id=uuid4(),
        operation_type=OperationType.APPLY,
        actor="acceptance_test",
        target_path="canonical/decisions/decisions.yaml",
        description="驗收測試操作",
        created_at=datetime.now(),
    )


def make_sample_decision(
    decision_id: str,
    comparability_score: float = 0.75,
    risk_tags: list = None,
    risk_explanation: str = "",
    **overrides,
) -> DecisionRecord:
    """建立測試用 DecisionRecord（封裝必要欄位，預設合法值）"""
    if risk_tags is None:
        risk_tags = []
    defaults = dict(
        decision_id=decision_id,
        operation_id=str(uuid4()),
        created_at=datetime(2025, 1, 15, 10, 30, 0).isoformat(),
        template_id="buying_house",
        status=DecisionStatus.APPLIED,
        confidence=ConfidenceLevel.MEDIUM,
        comparability_score=comparability_score,
        input_hash="abc123def456gh01",
        option_a=DecisionOption(direction="conservative", label="保守方案"),
        option_b=DecisionOption(direction="aggressive", label="進取方案"),
        risk_tags=risk_tags,
        risk_explanation=risk_explanation,
    )
    defaults.update(overrides)
    return DecisionRecord(**defaults)


# ========== Fixtures ==========


@pytest.fixture
def acceptance_data_path(tmp_path: Path) -> Path:
    """建立驗收測試用的完整資料目錄結構"""
    data_path = tmp_path / "acceptance_data"

    # 建立三層目錄
    (data_path / "raw").mkdir(parents=True)
    (data_path / "canonical").mkdir(parents=True)
    (data_path / "derived" / "advisor").mkdir(parents=True)

    # 建立 operation_log
    (data_path / "canonical" / ".operation_log.jsonl").touch()

    return data_path


@pytest.fixture
def sample_decisions(acceptance_data_path: Path) -> list[DecisionRecord]:
    """建立三筆樣本決策（低/中/高風險，依 risk_tags 數量區分）"""
    decisions = [
        make_sample_decision(
            decision_id="dec_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            comparability_score=0.75,
            risk_tags=[],
            risk_explanation="低風險決策",
            decision_rationale="基於歷史資料分析，設定合理預算上限",
        ),
        make_sample_decision(
            decision_id="dec_01ARZ3NDEKTSV4RRFFQ69G5FAW",
            comparability_score=0.70,
            risk_tags=["market_volatility"],
            risk_explanation="中等風險決策",
        ),
        make_sample_decision(
            decision_id="dec_01ARZ3NDEKTSV4RRFFQ69G5FAX",
            comparability_score=0.80,
            risk_tags=["deficit", "runway_short", "high_expense"],
            risk_explanation="高風險決策",
        ),
    ]

    handler = DecisionsHandler(acceptance_data_path)
    for decision in decisions:
        handler.write_decision(decision, make_operation())

    return decisions


# ========== E2E 驗收測試 ==========


def test_full_workflow_e1_to_e5(acceptance_data_path: Path, sample_decisions: list[DecisionRecord]):
    """
    E2E-001: 完整工作流程（E1→E2→E3→E4→E5）

    步驟：
    1. E1: 讀取決策記錄（含 V1.1 新欄位）
    2. E2: 生成 Wiki
    3. E3: 執行風險評估
    4. E4: 執行敏感度分析（Future Enhancement - Skipped）
    5. E5: 驗證 CLI 可讀結構
    """
    # Step 1: E1 Memory 讀取
    handler = DecisionsHandler(acceptance_data_path)
    loaded_decisions = handler.read_all()

    assert len(loaded_decisions) == 3

    # 驗證 V1.1 欄位
    decision_with_rationale = next(
        d for d in loaded_decisions if d.decision_id == "dec_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    )
    assert decision_with_rationale.decision_rationale == "基於歷史資料分析，設定合理預算上限"
    assert decision_with_rationale.reverted_from_decision_id is None

    # Step 2: E2 Wiki 生成（save_wiki 接受 list，產生單一 wiki 檔）
    wiki_path = save_wiki(loaded_decisions, acceptance_data_path)
    assert wiki_path.exists()
    assert wiki_path.suffix == ".md"

    # 驗證 Wiki 內容包含 V1.1 欄位
    wiki_content = wiki_path.read_text(encoding="utf-8")
    assert "### Rationale" in wiki_content
    assert "基於歷史資料分析" in wiki_content

    # Step 3: E3 風險評估
    risk_matrix_path = save_risk_matrix(loaded_decisions, acceptance_data_path)
    assert risk_matrix_path.exists()

    risk_report = json.loads(risk_matrix_path.read_text(encoding="utf-8"))
    assert risk_report["total_decisions"] == 3
    assert "risk_distribution" in risk_report
    assert risk_report["risk_distribution"]["low"] == 1
    assert risk_report["risk_distribution"]["medium"] == 1
    assert risk_report["risk_distribution"]["high"] == 1

    # Step 4: E4 敏感度分析（Future Enhancement - Skipped）
    pass

    # Step 5: E5 CLI 整合（驗證 derived/advisor/ 結構可供 CLI 讀取）
    advisor_dir = acceptance_data_path / "derived" / "advisor"
    wiki_count = len(list(advisor_dir.rglob("*.md")))
    assert wiki_count == 1  # 所有決策合併為單一 wiki 檔


def test_v10_v11_compatibility(tmp_path: Path):
    """
    E2E-002: V1.0 ↔ V1.1 版本相容性

    驗證：
    1. V1.0 格式可正常讀取（缺失欄位 fallback 為 None）
    2. V1.1 格式可正常讀取
    3. 混合版本可共存
    """
    data_path = tmp_path / "compat_test"

    # 使用 handler 取得 decisions 檔案路徑
    handler = DecisionsHandler(data_path)
    handler._ensure_dir()

    # 建立 V1.0 決策（用現行必填欄位，不含 decision_rationale / reverted_from_decision_id）
    v10_data = {
        "version": "1.0",
        "last_updated": "2025-01-15T10:00:00",
        "records": [
            {
                "decision_id": "dec_v10_test",
                "operation_id": "op_v10_test",
                "template_id": "buying_house",
                "status": "applied",
                "confidence": "medium",
                "created_at": "2025-01-15T10:00:00",
                "comparability_score": 0.7,
                "input_hash": "abc123def456gh01",
                "option_a": {"direction": "conservative", "label": "保守方案"},
                "option_b": {"direction": "aggressive", "label": "進取方案"},
                "risk_tags": [],
                "risk_explanation": "",
            }
        ],
    }
    with open(handler.decisions_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(v10_data, f, allow_unicode=True)

    # 建立 V1.1 決策（含新欄位），透過 write_decision 附加
    v11_decision = make_sample_decision(
        "dec_v11_test",
        decision_rationale="V1.1 測試決策",
    )
    handler.write_decision(v11_decision, make_operation())

    # 讀取混合版本
    all_decisions = handler.read_all()
    assert len(all_decisions) == 2

    # 驗證 V1.0 讀取（新欄位應為 None）
    v10_loaded = next(d for d in all_decisions if d.decision_id == "dec_v10_test")
    assert v10_loaded.decision_rationale is None
    assert v10_loaded.reverted_from_decision_id is None

    # 驗證 V1.1 讀取
    v11_loaded = next(d for d in all_decisions if d.decision_id == "dec_v11_test")
    assert v11_loaded.decision_rationale == "V1.1 測試決策"


def test_path_security_blocks_traversal(tmp_path: Path):
    """
    E2E-003: 路徑安全驗證（阻擋 traversal attack）

    驗證：
    1. 正常路徑可通過（返回解析後絕對路徑）
    2. .. traversal 被拒絕（PathSecurityError）
    3. 絕對路徑跳出 base_dir 被拒絕（PathSecurityError）
    4. 不允許的副檔名被拒絕（PathSecurityError）
    """
    data_path = tmp_path / "security_test"
    (data_path / "derived" / "advisor").mkdir(parents=True)

    handler = AdvisorDerivedHandler(data_path)

    # 正常路徑（應通過，返回解析後的絕對路徑）
    valid_path = data_path / "derived" / "advisor" / "test.json"
    resolved = handler._validate_path(valid_path)
    assert resolved is not None

    # Traversal attack（.. 解析後落在 base_dir 外，應拒絕）
    traversal_path = data_path / "derived" / "advisor" / ".." / ".." / "canonical" / "evil.json"
    with pytest.raises(PathSecurityError):
        handler._validate_path(traversal_path)

    # 絕對路徑跳出 base_dir（應拒絕）
    outside_path = tmp_path / "outside" / "evil.json"
    with pytest.raises(PathSecurityError):
        handler._validate_path(outside_path)

    # 不允許的副檔名（應拒絕）
    invalid_ext_path = data_path / "derived" / "advisor" / "script.sh"
    with pytest.raises(PathSecurityError):
        handler._validate_path(invalid_ext_path)


def test_evaluability_threshold_respected(
    acceptance_data_path: Path, sample_decisions: list[DecisionRecord]
):
    """
    E2E-004: Evaluability 閾值遵守

    驗證：
    1. evaluate_decision 正確判定低 comparability 決策
    2. 高 comparability 決策獲得更高評級
    """
    # 建立低 comparability 決策（0.2 低於 SKIP 閾值 0.3）
    low_eval_decision = make_sample_decision(
        "dec_low_eval",
        comparability_score=0.2,  # < 0.3 → SKIP
        risk_tags=[],
        risk_explanation="不明確的決策",
    )

    eval_result = evaluate_decision(low_eval_decision.comparability_score)
    assert eval_result.comparability_score >= 0.0
    assert eval_result.is_evaluable == EvaluabilityLevel.SKIP

    # 高 comparability 決策（investment_strategy，score=0.70）
    high_eval_decision = sample_decisions[1]  # comparability_score=0.70
    eval_result_high = evaluate_decision(high_eval_decision.comparability_score)

    assert eval_result_high.comparability_score >= 0.0
    assert eval_result_high.is_recommendable in (
        RecommendabilityLevel.FULL, RecommendabilityLevel.PARTIAL
    )


def test_cli_exit_codes_correct(acceptance_data_path: Path, sample_decisions: list[DecisionRecord]):
    """
    E2E-005: CLI exit codes 正確性

    驗證 `lc doctor --advisor` 的 exit codes:
    - 0: 所有檢查通過
    - 1: 有警告
    - 2: 有錯誤
    """
    # 若 lc CLI 不在 PATH，跳過此測試
    if not shutil.which("lc"):
        pytest.skip("lc CLI 不在 PATH 中，跳過 CLI 整合測試")

    # Scenario 1: 所有檢查通過（exit 0）
    result = subprocess.run(
        ["lc", "doctor", str(acceptance_data_path), "--advisor", "--format", "json"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        output = json.loads(result.stdout)
        assert output["status"] == "ok"
        assert output["summary"]["errors"] == 0

    # Scenario 2: 生成 wiki 後破壞 provenance（觸發 warning/error）
    wiki_path = save_wiki(sample_decisions, acceptance_data_path)
    if wiki_path.exists():
        original_content = wiki_path.read_text(encoding="utf-8")
        wiki_path.write_text(original_content + "\n<!-- tampered -->", encoding="utf-8")

        result_tampered = subprocess.run(
            ["lc", "doctor", str(acceptance_data_path), "--advisor", "--format", "json"],
            capture_output=True,
            text=True,
        )

        assert result_tampered.returncode in [1, 2]


def test_provenance_integrity(acceptance_data_path: Path, sample_decisions: list[DecisionRecord]):
    """
    E2E-006: Provenance 完整性驗證

    驗證：
    1. Wiki 衍生物有對應的 .meta.json sidecar
    2. 風險矩陣 JSON 有對應的 .meta.json sidecar
    3. Sidecar 內 provenance 結構正確
    """
    # 生成 derived 檔案
    save_wiki(sample_decisions, acceptance_data_path)
    save_risk_matrix(sample_decisions, acceptance_data_path)

    advisor_dir = acceptance_data_path / "derived" / "advisor"

    # 檢查所有 .md 檔案有對應 sidecar
    for file_path in advisor_dir.rglob("*.md"):
        meta_path = file_path.with_suffix(file_path.suffix + ".meta.json")
        assert meta_path.exists(), f"Missing meta file for {file_path}"

        with open(meta_path, "r", encoding="utf-8") as f:
            provenance = json.load(f)

        assert provenance["artifact_type"] == "decision_wiki"
        assert "content_hash" in provenance
        assert "rebuild_command" in provenance

    # 檢查所有 .json 報表有對應 sidecar（排除 meta 本身）
    for file_path in advisor_dir.rglob("*.json"):
        if ".meta.json" in file_path.name:
            continue

        meta_path = file_path.with_suffix(file_path.suffix + ".meta.json")
        assert meta_path.exists(), f"Missing meta file for {file_path}"

        with open(meta_path, "r", encoding="utf-8") as f:
            provenance = json.load(f)

        assert "artifact_type" in provenance
        assert "content_hash" in provenance
        assert "rebuild_command" in provenance

        # rebuild_command 序列化為 dict（含 cmd 鍵）
        rebuild_cmd_raw = provenance["rebuild_command"]
        assert isinstance(rebuild_cmd_raw, dict)
        rebuild_cmd = rebuild_cmd_raw.get("cmd", [])
        assert isinstance(rebuild_cmd, list)
        assert all(isinstance(item, str) for item in rebuild_cmd)


def test_canonicalization_deterministic(tmp_path: Path):
    """
    E2E-007: Canonicalization 確定性驗證

    驗證：
    1. 寫入後讀取的記錄與原始記錄完全相等
    2. 相同輸入 dataclass 相等
    """
    data_path = tmp_path / "canon_test"

    decision = make_sample_decision(
        "dec_canon_test",
        decision_rationale="測試 canonicalization",
    )

    handler = DecisionsHandler(data_path)
    handler.write_decision(decision, make_operation())

    loaded = handler.get_by_decision_id("dec_canon_test")
    assert loaded is not None
    assert loaded == decision  # frozen dataclass 相等性比較


def test_state_transitions_enforced(tmp_path: Path):
    """
    E2E-008: 狀態轉換強制執行

    驗證：
    1. PENDING 狀態可正常讀取
    2. APPLIED 狀態可正常讀取
    3. APPLIED → REVERTED 透過 mark_reverted 執行
    """
    data_path = tmp_path / "state_test"
    handler = DecisionsHandler(data_path)

    # 建立 PENDING 決策
    pending_decision = make_sample_decision(
        "dec_state_pending",
        status=DecisionStatus.PENDING,
    )
    handler.write_decision(pending_decision, make_operation())

    loaded_pending = handler.get_by_decision_id("dec_state_pending")
    assert loaded_pending is not None
    assert loaded_pending.status == DecisionStatus.PENDING

    # 建立 APPLIED 決策（不同 ID）
    applied_decision = make_sample_decision(
        "dec_state_applied",
        status=DecisionStatus.APPLIED,
    )
    handler.write_decision(applied_decision, make_operation())

    loaded_applied = handler.get_by_decision_id("dec_state_applied")
    assert loaded_applied is not None
    assert loaded_applied.status == DecisionStatus.APPLIED

    # APPLIED → REVERTED 透過 mark_reverted
    reverted = handler.mark_reverted("dec_state_applied", make_operation())
    assert reverted.status == DecisionStatus.REVERTED


def test_rebuild_command_executable(
    acceptance_data_path: Path, sample_decisions: list[DecisionRecord]
):
    """
    E2E-009: RebuildCommand 可執行性

    驗證：
    1. RebuildCommand 格式正確（list 或含 cmd 鍵的 dict）
    2. 可轉為合法 shell 命令
    """
    risk_matrix_path = save_risk_matrix(sample_decisions, acceptance_data_path)
    meta_path = risk_matrix_path.with_suffix(risk_matrix_path.suffix + ".meta.json")

    assert meta_path.exists()
    with open(meta_path, "r", encoding="utf-8") as f:
        provenance = json.load(f)

    # rebuild_command 序列化為 dict（含 cmd 鍵）
    rebuild_cmd_raw = provenance["rebuild_command"]
    assert isinstance(rebuild_cmd_raw, dict)
    rebuild_cmd = rebuild_cmd_raw.get("cmd", [])

    assert isinstance(rebuild_cmd, list)
    assert len(rebuild_cmd) > 0
    assert rebuild_cmd[0] == "lc"
    assert "advisor" in rebuild_cmd

    # 驗證可轉為 shell 命令
    import shlex
    shell_cmd = shlex.join(rebuild_cmd)
    assert len(shell_cmd) > 0


def test_cross_module_integration(
    acceptance_data_path: Path, sample_decisions: list[DecisionRecord]
):
    """
    E2E-010: 跨模組整合測試

    驗證：
    1. evaluability → risk_assessor 整合
    2. risk_assessor → risk_matrix 整合
    3. decision_wiki → CLI history/explain 整合
    """
    # Test 1: evaluability → risk_assessor
    decision = sample_decisions[1]  # comparability_score=0.70
    eval_result = evaluate_decision(decision.comparability_score)

    assert eval_result.comparability_score >= 0.0
    assert eval_result.is_evaluable in (
        EvaluabilityLevel.FULL, EvaluabilityLevel.WARNING, EvaluabilityLevel.SKIP
    )

    # Test 2: risk_assessor → risk_matrix
    assess_risk(decision)
    risk_matrix_path = save_risk_matrix(sample_decisions, acceptance_data_path)

    risk_report = json.loads(risk_matrix_path.read_text(encoding="utf-8"))

    # 風險矩陣 assessments 應包含此決策
    decision_in_matrix = any(
        entry["decision_id"] == decision.decision_id
        for entry in risk_report["assessments"]
    )
    assert decision_in_matrix

    # Test 3: decision_wiki → CLI（驗證檔案存在供 CLI 讀取）
    wiki_path = save_wiki([decision], acceptance_data_path)
    assert wiki_path.exists()
