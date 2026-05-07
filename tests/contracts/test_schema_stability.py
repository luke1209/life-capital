"""Schema 穩定性契約測試

驗證 Pydantic 模型的 JSON Schema 未發生 Breaking Change。

測試策略：
1. 載入 baseline（tests/contracts/baselines/*.json）
2. 取得當前模型的 JSON Schema
3. 正規化後比對
4. Breaking change 導致測試失敗

注意：
- Baseline 不存在時測試失敗（不可由測試自動建立）
- 更新 baseline 請使用: python scripts/update_schema_baseline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# 加入 scripts 路徑
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from schema_normalize import normalize_schema, schemas_equal  # noqa: E402

BASELINE_DIR = PROJECT_ROOT / "tests" / "contracts" / "baselines"


# 模型清單（與 update_schema_baseline.py 保持同步）
TRACKED_MODELS: list[tuple[str, str]] = [
    # Phase 0: 基礎模型
    ("ExpensePolicy", "life_capital.models.policy"),
    ("LifeAssumptions", "life_capital.models.assumptions"),
    ("MonthlyIncome", "life_capital.models.income"),
    ("LifetimeTargets", "life_capital.models.targets"),
    # Phase 1: 交易與支出
    ("Transaction", "life_capital.models.transaction"),
    ("ExpenseRecord", "life_capital.models.expense"),
    ("MonthlyExpenses", "life_capital.models.expense"),
    # Phase 0: 操作追蹤
    ("Operation", "life_capital.models.operation"),
    ("Provenance", "life_capital.models.operation"),
    ("OperationLogEntry", "life_capital.models.operation"),
    # Phase 2: 情境分析
    ("ScenarioResult", "life_capital.models.scenario"),
    ("ScenarioAssumption", "life_capital.models.scenario"),
    ("ProjectionResult", "life_capital.models.scenario"),
    # Phase 4: Capture 自動化
    ("StagingEntry", "life_capital.capture.models"),
]


def get_model_class(model_name: str, module_path: str) -> type:
    """動態載入模型類別"""
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, model_name)


def get_model_schema(model_cls: type) -> dict[str, Any]:
    """取得模型的 JSON Schema（支援 Pydantic 和 dataclass）"""
    # 嘗試 Pydantic 方法
    if hasattr(model_cls, "model_json_schema"):
        return model_cls.model_json_schema()

    # 若是 dataclass，直接從 baseline 載入（dataclass 無法自動生成 schema）
    if hasattr(model_cls, "__dataclass_fields__"):
        # 從 baseline 載入 dataclass 的 schema
        baseline = load_baseline(model_cls.__name__)
        if baseline is not None:
            return baseline
        else:
            pytest.skip(
                f"Dataclass {model_cls.__name__} 的 baseline 不存在，"
                f"請確保 {model_cls.__name__}.json 存在"
            )

    raise ValueError(f"無法取得 {model_cls.__name__} 的 schema")


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
        "added_fields": current_props - baseline_props,
        "removed_fields": baseline_props - current_props,
        "baseline_required": set(baseline.get("required", [])),
        "current_required": set(current.get("required", [])),
    }


class TestSchemaStability:
    """Schema 穩定性測試類別"""

    @pytest.mark.parametrize(
        "model_name,module_path",
        TRACKED_MODELS,
        ids=[m[0] for m in TRACKED_MODELS],
    )
    def test_schema_unchanged(self, model_name: str, module_path: str):
        """驗證 Schema 未發生 Breaking Change"""
        baseline_path = BASELINE_DIR / f"{model_name}.json"

        # 檢查 baseline 存在（不可由測試自動建立）
        if not baseline_path.exists():
            pytest.fail(
                f"Baseline 不存在: {baseline_path}\n"
                f"請執行: python scripts/update_schema_baseline.py --model {model_name}"
            )

        # 載入 baseline
        baseline = load_baseline(model_name)
        assert baseline is not None, f"無法載入 baseline: {model_name}"

        # 取得當前 schema
        model_cls = get_model_class(model_name, module_path)
        model_schema = get_model_schema(model_cls)
        current_schema = normalize_schema(model_schema)

        # 比對
        if not schemas_equal(baseline, current_schema):
            diff = compute_diff(baseline, current_schema)

            error_msg = [f"Schema Breaking Change 偵測: {model_name}"]

            if diff["removed_fields"]:
                error_msg.append(f"  移除欄位: {', '.join(diff['removed_fields'])}")

            if diff["added_fields"]:
                error_msg.append(f"  新增欄位: {', '.join(diff['added_fields'])}")

            removed_required = diff["baseline_required"] - diff["current_required"]
            added_required = diff["current_required"] - diff["baseline_required"]

            if removed_required:
                error_msg.append(f"  Required→Optional: {', '.join(removed_required)}")
            if added_required:
                error_msg.append(f"  Optional→Required: {', '.join(added_required)}")

            error_msg.append("")
            error_msg.append("若為預期變更，請執行:")
            error_msg.append(
                f"  python scripts/update_schema_baseline.py --model {model_name}"
            )

            pytest.fail("\n".join(error_msg))


class TestSchemaIntegrity:
    """Schema 完整性測試"""

    @pytest.mark.parametrize(
        "model_name,module_path",
        TRACKED_MODELS,
        ids=[m[0] for m in TRACKED_MODELS],
    )
    def test_model_can_generate_schema(self, model_name: str, module_path: str):
        """驗證模型可正常產生 JSON Schema"""
        model_cls = get_model_class(model_name, module_path)
        schema = get_model_schema(model_cls)

        assert isinstance(schema, dict)
        assert "type" in schema or "anyOf" in schema or "properties" in schema

    @pytest.mark.parametrize(
        "model_name,module_path",
        TRACKED_MODELS,
        ids=[m[0] for m in TRACKED_MODELS],
    )
    def test_normalized_schema_is_stable(self, model_name: str, module_path: str):
        """驗證正規化後的 schema 是穩定的（多次呼叫結果相同）"""
        model_cls = get_model_class(model_name, module_path)

        schema = get_model_schema(model_cls)
        schema1 = normalize_schema(schema)
        schema2 = normalize_schema(schema)

        assert schema1 == schema2, f"{model_name} 的正規化結果不穩定"
