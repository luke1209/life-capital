"""Risk Matrix 輸出生成器

生成 JSON 格式的風險矩陣報告。

使用方式:
    from life_capital.generation.risk_matrix import generate_risk_matrix

    matrix = generate_risk_matrix(decisions, data_path)
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from life_capital.advisor.risk_assessor import assess_risk
from life_capital.io.advisor_derived_handler import AdvisorDerivedHandler
from life_capital.io.registry import (
    ADVISOR_PROVENANCE_VERSION,
    CANONICALIZATION_VERSION,
)
from life_capital.models.decisions import DecisionRecord, DecisionStatus
from life_capital.models.provenance import (
    AdvisorDerivedProvenance,
    RebuildCommand,
)


def generate_risk_matrix(
    decisions: list[DecisionRecord],
    data_path: Path,
) -> dict[str, Any]:
    """生成風險矩陣 JSON

    Args:
        decisions: 決策記錄列表
        data_path: 資料根目錄

    Returns:
        風險矩陣字典
    """
    # 過濾有效決策
    active_decisions = [
        d
        for d in decisions
        if d.status in (DecisionStatus.PENDING, DecisionStatus.APPLIED)
    ]

    # 評估風險
    assessments = []
    skipped_count = 0

    for decision in active_decisions:
        assessment = assess_risk(decision)
        if assessment:
            assessments.append(
                {
                    "decision_id": assessment.decision_id,
                    "risk_level": assessment.risk_level,
                    "risk_tags": assessment.risk_tags,
                    "risk_explanation": assessment.risk_explanation,
                    "warnings": assessment.warnings,
                }
            )
        else:
            skipped_count += 1

    # 統計
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    for a in assessments:
        risk_counts[a["risk_level"]] += 1

    return {
        "generated_at": datetime.now().isoformat(),
        "total_decisions": len(active_decisions),
        "assessed_count": len(assessments),
        "skipped_count": skipped_count,
        "risk_distribution": risk_counts,
        "assessments": assessments,
    }


def save_risk_matrix(
    decisions: list[DecisionRecord],
    data_path: Path,
) -> Path:
    """生成並儲存風險矩陣

    Args:
        decisions: 決策記錄列表
        data_path: 資料根目錄

    Returns:
        矩陣檔案路徑
    """
    # 生成內容
    matrix = generate_risk_matrix(decisions, data_path)

    # 計算 input_hash
    canonical_data = [d.decision_id for d in decisions]
    input_str = json.dumps(canonical_data, sort_keys=True)
    input_hash = hashlib.sha256(input_str.encode()).hexdigest()

    # 計算 content_hash
    content_str = json.dumps(matrix, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(content_str.encode()).hexdigest()

    # 建立 Provenance
    provenance = AdvisorDerivedProvenance(
        artifact_type="risk_matrix",
        schema_version=ADVISOR_PROVENANCE_VERSION,
        calc_version="risk_v1.0",
        canonicalization_version=CANONICALIZATION_VERSION,
        input_hash=input_hash,
        canonical_sources=["canonical/decisions/decisions.yaml"],
        generated_at=datetime.now().isoformat(),
        rebuild_command=RebuildCommand(
            cmd=["lc", "advisor", "risk-matrix", "--rebuild"],
            cwd=".",
            env={},
            schema_version="1.0",
        ),
        content_hash=content_hash,
        redaction_profile_version="none",
    )

    # 使用 handler 原子寫入
    handler = AdvisorDerivedHandler(data_path)
    content_path, meta_path = handler.write_with_provenance(
        artifact_type="risk_matrix",
        content=matrix,
        provenance=provenance,
        format="json",
    )

    return content_path
