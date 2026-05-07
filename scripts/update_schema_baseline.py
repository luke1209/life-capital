#!/usr/bin/env python3
"""Schema Baseline 更新腳本

更新 tests/contracts/baselines/ 中的 JSON Schema 基準檔案。

使用方式：
    python scripts/update_schema_baseline.py --model ExpensePolicy
    python scripts/update_schema_baseline.py --all
    python scripts/update_schema_baseline.py --list

注意：
    - 這是 baseline 更新的唯一入口
    - 更新後需 CODEOWNERS 審核
    - 測試程式碼不可直接寫入 baseline
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

# 專案路徑
PROJECT_ROOT = Path(__file__).parent.parent

# 將專案根目錄加入 Python 路徑
sys.path.insert(0, str(PROJECT_ROOT))
BASELINE_DIR = PROJECT_ROOT / "tests" / "contracts" / "baselines"
MODELS_MODULE = "life_capital.models"

# 需要追蹤的模型清單
TRACKED_MODELS: dict[str, str] = {
    # model_name: module_path
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
    # Phase 4: Capture 自動化
    "StagingEntry": "life_capital.capture.models",
}


def get_model_class(model_name: str) -> type:
    """動態載入模型類別"""
    if model_name not in TRACKED_MODELS:
        raise ValueError(f"未知模型: {model_name}\n可用模型: {list(TRACKED_MODELS.keys())}")

    module_path = TRACKED_MODELS[model_name]
    module = importlib.import_module(module_path)
    return getattr(module, model_name)


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """正規化 schema（使用 schema_normalize 模組）"""
    # 動態導入以避免路徑問題
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from schema_normalize import normalize_schema as _normalize

    return _normalize(schema)


def update_baseline(model_name: str, dry_run: bool = False) -> dict[str, Any]:
    """更新單一模型的 baseline

    Parameters
    ----------
    model_name : str
        模型名稱
    dry_run : bool
        是否只檢查不寫入

    Returns
    -------
    dict
        變更資訊
    """
    model_cls = get_model_class(model_name)
    current_schema = normalize_schema(model_cls.model_json_schema())

    baseline_path = BASELINE_DIR / f"{model_name}.json"

    result = {
        "model": model_name,
        "baseline_path": str(baseline_path),
        "action": "unchanged",
        "diff": None,
    }

    if baseline_path.exists():
        existing = json.loads(baseline_path.read_text())
        if existing == current_schema:
            result["action"] = "unchanged"
            return result
        else:
            result["action"] = "updated"
            result["diff"] = {
                "old_keys": set(existing.get("properties", {}).keys()),
                "new_keys": set(current_schema.get("properties", {}).keys()),
            }
    else:
        result["action"] = "created"

    if not dry_run:
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(current_schema, indent=2, ensure_ascii=False) + "\n"
        )

    return result


def generate_diff_report(results: list[dict]) -> str:
    """生成 diff 報告"""
    lines = ["# Schema Baseline 變更報告", ""]

    created = [r for r in results if r["action"] == "created"]
    updated = [r for r in results if r["action"] == "updated"]
    unchanged = [r for r in results if r["action"] == "unchanged"]

    if created:
        lines.append("## 新建立")
        for r in created:
            lines.append(f"- `{r['model']}`")
        lines.append("")

    if updated:
        lines.append("## 已更新")
        for r in updated:
            lines.append(f"- `{r['model']}`")
            if r["diff"]:
                added = r["diff"]["new_keys"] - r["diff"]["old_keys"]
                removed = r["diff"]["old_keys"] - r["diff"]["new_keys"]
                if added:
                    lines.append(f"  - 新增欄位: {', '.join(sorted(added))}")
                if removed:
                    lines.append(f"  - 移除欄位: {', '.join(sorted(removed))}")
        lines.append("")

    if unchanged:
        lines.append("## 未變更")
        for r in unchanged:
            lines.append(f"- `{r['model']}`")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="更新 Schema Baseline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--model",
        type=str,
        help="要更新的模型名稱",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="更新所有追蹤的模型",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有追蹤的模型",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只檢查不寫入",
    )
    parser.add_argument(
        "--report",
        type=str,
        help="輸出 diff 報告到指定檔案",
    )

    args = parser.parse_args()

    if args.list:
        print("追蹤的模型清單：")
        for name, module in TRACKED_MODELS.items():
            print(f"  {name} ({module})")
        return

    if not args.model and not args.all:
        parser.print_help()
        print("\n錯誤：請指定 --model 或 --all")
        sys.exit(1)

    results = []

    if args.all:
        for model_name in TRACKED_MODELS:
            print(f"處理 {model_name}...")
            result = update_baseline(model_name, dry_run=args.dry_run)
            results.append(result)
            print(f"  {result['action']}")
    else:
        result = update_baseline(args.model, dry_run=args.dry_run)
        results.append(result)
        print(f"{args.model}: {result['action']}")

    # 生成報告
    report = generate_diff_report(results)
    print("\n" + report)

    if args.report:
        Path(args.report).write_text(report)
        print(f"報告已寫入: {args.report}")


if __name__ == "__main__":
    main()
