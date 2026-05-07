"""Schema 語意正規化模組

提供兩階段正規化處理：
1. 語意過濾（保留契約相關欄位）
2. 結構正規化（穩定排序）

用途：
- 消除環境差異造成的假陽性
- 確保跨版本 Pydantic 的比對一致性
"""

from __future__ import annotations

import json
from typing import Any

# 語意白名單：只保留這些欄位，其他全部剔除
# 這些欄位定義了 Schema 的「契約語意」
SEMANTIC_WHITELIST: set[str] = {
    # 型別定義
    "type",
    "properties",
    "required",
    "items",
    # 值約束
    "enum",
    "const",
    "default",
    # 格式約束
    "pattern",
    "format",
    # 數值約束
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    # 長度約束
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    # 組合型別
    "anyOf",
    "oneOf",
    "allOf",
    "$ref",
    # 額外屬性
    "additionalProperties",
    "nullable",
}

# 剔除欄位（用於說明，實際邏輯是白名單）
EXCLUDED_FIELDS: set[str] = {
    "title",  # 顯示用名稱
    "description",  # 說明文字
    "examples",  # 範例值
    "$defs",  # 定義展開形態（內部引用）
    "$schema",  # JSON Schema 版本宣告
    "$id",  # Schema ID
}


def semantic_filter(schema: Any) -> Any:
    """Phase 1: 只保留語意白名單欄位

    遞迴過濾 schema，只保留影響契約語意的欄位。

    Parameters
    ----------
    schema : Any
        JSON Schema 結構

    Returns
    -------
    Any
        過濾後的結構
    """
    if not isinstance(schema, dict):
        return schema

    result: dict[str, Any] = {}
    for key, value in schema.items():
        if key in SEMANTIC_WHITELIST:
            if isinstance(value, dict):
                result[key] = semantic_filter(value)
            elif isinstance(value, list):
                result[key] = [
                    semantic_filter(v) if isinstance(v, dict) else v for v in value
                ]
            else:
                result[key] = value

    return result


def structural_normalize(schema: Any) -> Any:
    """Phase 2: 結構正規化（穩定排序）

    遞迴排序 dict keys 與 list 內容，確保輸出穩定。

    Parameters
    ----------
    schema : Any
        JSON Schema 結構

    Returns
    -------
    Any
        正規化後的結構
    """
    if isinstance(schema, dict):
        return {k: structural_normalize(v) for k, v in sorted(schema.items())}

    if isinstance(schema, list):
        normalized = [structural_normalize(v) for v in schema]
        # 對 anyOf/oneOf 內的 schema 片段用 stable hash 排序
        if all(isinstance(item, dict) for item in normalized):
            return sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True))
        return normalized

    return schema


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """語意正規化：兩階段處理

    完整的 schema 正規化流程，適用於契約測試比對。

    Parameters
    ----------
    schema : dict
        原始 JSON Schema（通常來自 model.model_json_schema()）

    Returns
    -------
    dict
        正規化後的 schema，可用於穩定比對

    Examples
    --------
    >>> from life_capital.models.policy import ExpensePolicy
    >>> schema = ExpensePolicy.model_json_schema()
    >>> normalized = normalize_schema(schema)
    """
    # Phase 1: 語意過濾（剔除非契約欄位）
    filtered = semantic_filter(schema)
    # Phase 2: 結構正規化（穩定排序）
    return structural_normalize(filtered)


def schema_to_json(schema: dict[str, Any]) -> str:
    """將 schema 轉為穩定的 JSON 字串

    Parameters
    ----------
    schema : dict
        JSON Schema

    Returns
    -------
    str
        JSON 字串（已排序、縮排）
    """
    normalized = normalize_schema(schema)
    return json.dumps(normalized, indent=2, ensure_ascii=False)


def schemas_equal(schema1: dict[str, Any], schema2: dict[str, Any]) -> bool:
    """比較兩個 schema 是否語意等價

    Parameters
    ----------
    schema1 : dict
        第一個 schema
    schema2 : dict
        第二個 schema

    Returns
    -------
    bool
        是否等價
    """
    return normalize_schema(schema1) == normalize_schema(schema2)


if __name__ == "__main__":
    # 測試範例
    sample_schema = {
        "title": "ExpensePolicy",  # 會被過濾
        "description": "支出政策",  # 會被過濾
        "type": "object",  # 保留
        "properties": {
            "amount": {
                "title": "Amount",  # 會被過濾
                "type": "integer",  # 保留
                "minimum": 0,  # 保留
            }
        },
        "required": ["amount"],  # 保留
    }

    print("原始 schema:")
    print(json.dumps(sample_schema, indent=2))
    print("\n正規化後:")
    print(schema_to_json(sample_schema))
