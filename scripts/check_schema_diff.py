#!/usr/bin/env python3
"""Schema Diff 檢查腳本

檢查當前模型 Schema 與 baseline 的差異，產出 diff 報告。

用於 CI 中偵測 schema 變更並要求審核。

使用方式：
    python scripts/check_schema_diff.py

輸出：
    - 若有變更：產出 schema_diff_report.md 並回傳 exit code 1
    - 若無變更：回傳 exit code 0
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

# 專案路徑
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from schema_normalize import normalize_schema  # noqa: E402

BASELINE_DIR = PROJECT_ROOT / "tests" / "contracts" / "baselines"

# 需要追蹤的模型清單（與 update_schema_baseline.py 同步）
TRACKED_MODELS: dict[str, str] = {
    # Phase 0: 基礎模型
    "ExpensePolicy": "life_capital.models.policy",
    "LifeAssumptions": "life_capital.models.assumptions",
    "MonthlyIncome": "life_capital.models.income",
    "LifetimeTargets": "life_capital.models.targets",
    # Phase 1: 交易與支出
    "Transaction": "life_capital.models.transaction",
    "ExpenseRecord": "life_capital.models.expense",
    "MonthlyExpenses": "life_capital.models.expense",
    # Phase 0: 操作追蹤
    "Operation": "life_capital.models.operation",
    "Provenance": "life_capital.models.operation",
    "OperationLogEntry": "life_capital.models.operation",
    # Phase 2: 情境分析
    "ScenarioResult": "life_capital.models.scenario",
    "ScenarioAssumption": "life_capital.models.scenario",
    "ProjectionResult": "life_capital.models.scenario",
}


def get_model_class(model_name: str) -> type:
    """動態載入模型類別"""
    if model_name not in TRACKED_MODELS:
        raise ValueError(f"未知模型: {model_name}")

    module_path = TRACKED_MODELS[model_name]
    module = importlib.import_module(module_path)
    return getattr(module, model_name)


def load_baseline(model_name: str) -> dict[str, Any] | None:
    """載入 baseline 檔案"""
    baseline_path = BASELINE_DIR / f"{model_name}.json"
    if not baseline_path.exists():
        return None
    return json.loads(baseline_path.read_text())


def compute_diff(
    baseline: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    """計算 schema 差異"""
    baseline_props = set(baseline.get("properties", {}).keys())
    current_props = set(current.get("properties", {}).keys())

    return {
        "added_fields": sorted(current_props - baseline_props),
        "removed_fields": sorted(baseline_props - current_props),
        "baseline_required": set(baseline.get("required", [])),
        "current_required": set(current.get("required", [])),
    }


def classify_change(diff: dict[str, Any]) -> str:
    """分類變更類型"""
    # Breaking changes
    if diff["removed_fields"]:
        return "breaking"

    removed_required = diff["baseline_required"] - diff["current_required"]
    added_required = diff["current_required"] - diff["baseline_required"]

    if added_required:
        return "breaking"  # Optional→Required 是 breaking

    # Compatible changes
    if diff["added_fields"] or removed_required:
        return "compatible"

    return "unchanged"


def main() -> int:
    """主程式"""
    changes: list[dict[str, Any]] = []
    missing_baselines: list[str] = []

    for model_name in TRACKED_MODELS:
        baseline = load_baseline(model_name)

        if baseline is None:
            missing_baselines.append(model_name)
            continue

        try:
            model_cls = get_model_class(model_name)
            current_schema = normalize_schema(model_cls.model_json_schema())
        except Exception as e:
            print(f"無法載入模型 {model_name}: {e}")
            continue

        if baseline != current_schema:
            diff = compute_diff(baseline, current_schema)
            change_type = classify_change(diff)

            changes.append({
                "model": model_name,
                "type": change_type,
                "diff": diff,
            })

    # 產出報告
    if not changes and not missing_baselines:
        print("✅ 無 Schema 變更")
        return 0

    report_lines = ["# Schema Diff Report", ""]

    if missing_baselines:
        report_lines.append("## ⚠️ Missing Baselines")
        report_lines.append("")
        for model in missing_baselines:
            report_lines.append(f"- `{model}`")
        report_lines.append("")
        report_lines.append("執行以下命令建立 baseline:")
        report_lines.append("")
        report_lines.append("```bash")
        report_lines.append("python scripts/update_schema_baseline.py --all")
        report_lines.append("```")
        report_lines.append("")

    breaking_changes = [c for c in changes if c["type"] == "breaking"]
    compatible_changes = [c for c in changes if c["type"] == "compatible"]

    if breaking_changes:
        report_lines.append("## 🚨 Breaking Changes")
        report_lines.append("")
        report_lines.append("**這些變更需要修改或 migration 才能合併：**")
        report_lines.append("")

        for change in breaking_changes:
            report_lines.append(f"### `{change['model']}`")
            report_lines.append("")
            diff = change["diff"]

            if diff["removed_fields"]:
                report_lines.append(f"- 移除欄位: {', '.join(diff['removed_fields'])}")

            added_required = diff["current_required"] - diff["baseline_required"]
            if added_required:
                report_lines.append(f"- Optional→Required: {', '.join(sorted(added_required))}")

            report_lines.append("")

    if compatible_changes:
        report_lines.append("## ✅ Compatible Changes")
        report_lines.append("")
        report_lines.append("**這些變更需要 `schema-approved` label：**")
        report_lines.append("")

        for change in compatible_changes:
            report_lines.append(f"### `{change['model']}`")
            report_lines.append("")
            diff = change["diff"]

            if diff["added_fields"]:
                report_lines.append(f"- 新增欄位: {', '.join(diff['added_fields'])}")

            removed_required = diff["baseline_required"] - diff["current_required"]
            if removed_required:
                report_lines.append(f"- Required→Optional: {', '.join(sorted(removed_required))}")

            report_lines.append("")

    report_lines.append("---")
    report_lines.append("")
    report_lines.append("若為預期變更，請執行:")
    report_lines.append("")
    report_lines.append("```bash")
    report_lines.append("python scripts/update_schema_baseline.py --all")
    report_lines.append("```")

    report = "\n".join(report_lines)

    # 寫入報告
    report_path = PROJECT_ROOT / "schema_diff_report.md"
    report_path.write_text(report)
    print(f"📄 Schema diff 報告已產出: {report_path}")
    print(report)

    # 有 breaking changes 回傳 1
    if breaking_changes:
        return 1

    # 只有 compatible changes 回傳 0（但仍需 label）
    return 0


if __name__ == "__main__":
    sys.exit(main())
