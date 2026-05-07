"""Decision Wiki 編譯器

將決策記憶編譯成 Markdown Wiki。

使用方式:
    from life_capital.generation.decision_wiki import generate_wiki

    wiki_content = generate_wiki(
        decisions=records,
        data_path=Path("~/.life-capital")
    )
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import List

from life_capital.io.advisor_derived_handler import AdvisorDerivedHandler
from life_capital.io.registry import (
    CANONICALIZATION_VERSION,
)
from life_capital.models.decisions import DecisionRecord, DecisionStatus
from life_capital.models.provenance import AdvisorDerivedProvenance, RebuildCommand


def generate_wiki(
    decisions: List[DecisionRecord],
    data_path: Path,
) -> str:
    """生成 Decision Wiki Markdown

    Args:
        decisions: 決策記錄列表
        data_path: 資料根目錄

    Returns:
        Markdown 格式的 Wiki 內容
    """
    # 過濾有效決策（非 reverted、非 expired）
    active_decisions = [
        d for d in decisions
        if d.status in (DecisionStatus.PENDING, DecisionStatus.APPLIED)
    ]

    # 按時間排序（最新在前）
    sorted_decisions = sorted(
        active_decisions,
        key=lambda d: d.created_at,
        reverse=True
    )

    # 生成 Wiki 內容
    lines = [
        "# Decision History",
        "",
        f"**Last Updated**: {datetime.now().isoformat()}",
        f"**Total Decisions**: {len(sorted_decisions)}",
        "",
    ]

    for decision in sorted_decisions:
        lines.extend(_format_decision(decision))
        lines.append("")  # 空行分隔

    return "\n".join(lines)


def _format_decision(decision: DecisionRecord) -> List[str]:
    """格式化單一決策為 Markdown

    Args:
        decision: 決策記錄

    Returns:
        Markdown 行列表
    """
    lines = [
        f"## {decision.decision_id}",
        "",
        f"**Status**: {decision.status.value}",
        f"**Confidence**: {decision.confidence.value}",
        f"**Comparability**: {decision.comparability_score:.2f}",
        f"**Template**: {decision.template_id}",
        f"**Created**: {decision.created_at}",
        "",
    ]

    # Decision Rationale（V1.1 新增）
    if decision.decision_rationale:
        lines.extend([
            "### Rationale",
            "",
            decision.decision_rationale,
            "",
        ])

    # Option A（保守方案）
    lines.extend([
        "### Option A (Conservative)",
        "",
        f"**Label**: {decision.option_a.label}",
    ])
    if decision.option_a.recommendation:
        lines.append(f"**Recommendation**: {decision.option_a.recommendation}")
    if decision.option_a.score is not None:
        lines.append(f"**Score**: {decision.option_a.score:.2f}")
    lines.append("")

    # Option B（進取方案）
    lines.extend([
        "### Option B (Aggressive)",
        "",
        f"**Label**: {decision.option_b.label}",
    ])
    if decision.option_b.recommendation:
        lines.append(f"**Recommendation**: {decision.option_b.recommendation}")
    if decision.option_b.score is not None:
        lines.append(f"**Score**: {decision.option_b.score:.2f}")
    lines.append("")

    # Risk Information
    if decision.risk_tags:
        lines.extend([
            "### Risk Tags",
            "",
            ", ".join(f"`{tag}`" for tag in decision.risk_tags),
            "",
        ])

    lines.extend([
        "### Risk Explanation",
        "",
        decision.risk_explanation,
        "",
    ])

    # Revert Information（V1.1 新增）
    if decision.reverted_from_decision_id:
        lines.extend([
            "### Reverted From",
            "",
            f"**Original Decision**: {decision.reverted_from_decision_id}",
            "",
        ])

    lines.append("---")

    return lines


def save_wiki(
    decisions: List[DecisionRecord],
    data_path: Path,
) -> Path:
    """生成並儲存 Decision Wiki

    Args:
        decisions: 決策記錄列表
        data_path: 資料根目錄

    Returns:
        Wiki 檔案路徑
    """
    # 生成內容
    content = generate_wiki(decisions, data_path)

    # 計算 input_hash
    canonical_data = [d.decision_id for d in decisions]
    input_str = json.dumps(canonical_data, sort_keys=True)
    input_hash = hashlib.sha256(input_str.encode()).hexdigest()

    # 計算 content_hash
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # 建立 Provenance
    provenance = AdvisorDerivedProvenance(
        artifact_type="decision_wiki",
        schema_version="1.0",
        calc_version="wiki_v1.0",
        canonicalization_version=CANONICALIZATION_VERSION,
        input_hash=input_hash,
        canonical_sources=["canonical/decisions/decisions.yaml"],
        generated_at=datetime.now().isoformat(),
        rebuild_command=RebuildCommand(
            cmd=["lc", "advisor", "wiki", "--rebuild"],
            cwd=".",
            env={},
            schema_version="1.0",
        ),
        content_hash=content_hash,
        redaction_profile_version="none",
    )

    # 使用 handler 原子寫入
    handler = AdvisorDerivedHandler(data_path)
    result = handler.write_with_provenance(
        artifact_type="decision_wiki",
        content=content,
        provenance=provenance,
        format="md",
    )

    return result[0]  # 返回內容檔案路徑
