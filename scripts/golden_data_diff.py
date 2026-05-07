"""Golden Data 比對模組

提供完整的 canonicalization pipeline，用於 Golden Data 回歸測試。

Pipeline 步驟：
1. deep_copy - 避免修改原資料
2. normalize_amounts - 金額 quantize
3. normalize_lists - list 穩定排序
4. normalize_dict_keys - dict keys 排序
5. remove_ignorable_fields - 移除時間戳等

用途：
- Golden Data 比對時消除序列化細節干擾
- 確保測試結果可重現
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

# === 排序規則定義 ===

# 允許排序的 list 欄位白名單（key: 排序欄位名稱）
LIST_SORT_WHITELIST: dict[str, str | None] = {
    "transactions": "stable_id",  # 依 stable_id 排序
    "expenses": "date",  # 依 date 排序
    "records": "date",  # ExpenseRecord list 依 date 排序
    "categories": None,  # 字串 list，直接排序
    "sources": "name",  # 收入來源依 name 排序
    "targets": "name",  # 目標依 name 排序
}

# 禁止排序的 list（順序有語意）
LIST_PRESERVE_ORDER: set[str] = {
    "children",  # 家庭成員順序可能有意義
    "projections",  # 投影順序是時間序列
}

# 可忽略的欄位（比對時移除）
IGNORABLE_FIELDS: set[str] = {
    "generated_at",
    "created_at",
    "updated_at",
    "timestamp",
}


def deep_copy(data: Any) -> Any:
    """Step 1: 深拷貝避免修改原資料"""
    return copy.deepcopy(data)


def quantize_decimal(value: Decimal, scale: int = 0) -> Decimal:
    """Quantize Decimal 到指定精度

    Parameters
    ----------
    value : Decimal
        要 quantize 的值
    scale : int
        小數位數（0 = 元，2 = 角分）

    Returns
    -------
    Decimal
        quantize 後的值
    """
    from decimal import ROUND_HALF_UP

    if scale == 0:
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    else:
        quantizer = Decimal("0." + "0" * scale)
        return value.quantize(quantizer, rounding=ROUND_HALF_UP)


def normalize_amounts(data: Any, path: str = "") -> Any:
    """Step 2: 所有金額 quantize 後轉為標準字串格式

    Parameters
    ----------
    data : Any
        資料結構
    path : str
        當前路徑（用於除錯）

    Returns
    -------
    Any
        正規化後的結構
    """
    if isinstance(data, dict):
        return {k: normalize_amounts(v, f"{path}.{k}") for k, v in data.items()}
    if isinstance(data, list):
        return [normalize_amounts(v, f"{path}[]") for v in data]
    if isinstance(data, (int, float)):
        # 轉為 Decimal 後 quantize
        return str(quantize_decimal(Decimal(str(data))))
    if isinstance(data, Decimal):
        return str(quantize_decimal(data))
    return data


def normalize_lists(data: Any, path: str = "") -> Any:
    """Step 3: 依白名單規則排序 list

    Parameters
    ----------
    data : Any
        資料結構
    path : str
        當前欄位名稱（用於查詢排序規則）

    Returns
    -------
    Any
        排序後的結構
    """
    if isinstance(data, dict):
        return {k: normalize_lists(v, k) for k, v in data.items()}

    if isinstance(data, list):
        # 先遞迴處理子元素
        normalized = [normalize_lists(v, path) for v in data]

        # 檢查是否在白名單
        if path in LIST_SORT_WHITELIST:
            sort_key = LIST_SORT_WHITELIST[path]
            if sort_key is None:
                # 字串 list，直接排序
                return sorted(normalized, key=lambda x: str(x) if x is not None else "")
            # 依指定欄位排序
            return sorted(
                normalized,
                key=lambda x: x.get(sort_key, "") if isinstance(x, dict) else str(x),
            )

        # 檢查是否需保留順序
        if path in LIST_PRESERVE_ORDER:
            return normalized

        # 預設：如果是 dict list，用 stable hash 排序
        if all(isinstance(item, dict) for item in normalized):
            return sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True))

        return normalized

    return data


def normalize_dict_keys(data: Any) -> Any:
    """Step 4: 遞迴排序 dict keys

    Parameters
    ----------
    data : Any
        資料結構

    Returns
    -------
    Any
        keys 排序後的結構
    """
    if isinstance(data, dict):
        return {k: normalize_dict_keys(v) for k, v in sorted(data.items())}
    if isinstance(data, list):
        return [normalize_dict_keys(v) for v in data]
    return data


def remove_ignorable_fields(data: Any) -> Any:
    """Step 5: 移除可忽略欄位（時間戳等）

    Parameters
    ----------
    data : Any
        資料結構

    Returns
    -------
    Any
        移除後的結構
    """
    if isinstance(data, dict):
        return {
            k: remove_ignorable_fields(v)
            for k, v in data.items()
            if k not in IGNORABLE_FIELDS
        }
    if isinstance(data, list):
        return [remove_ignorable_fields(v) for v in data]
    return data


def canonicalize(data: Any) -> Any:
    """完整 canonicalization pipeline

    將資料正規化為可穩定比對的格式。

    Parameters
    ----------
    data : Any
        原始資料

    Returns
    -------
    Any
        正規化後的資料

    Examples
    --------
    >>> data = {"amount": 123.45, "generated_at": "2025-01-01"}
    >>> result = canonicalize(data)
    >>> result
    {'amount': '123'}
    """
    # Step 1: 深拷貝避免修改原資料
    data = deep_copy(data)
    # Step 2: 正規化金額（quantize）
    data = normalize_amounts(data)
    # Step 3: 正規化 list（穩定排序）
    data = normalize_lists(data)
    # Step 4: 正規化 dict keys（排序）
    data = normalize_dict_keys(data)
    # Step 5: 移除可忽略欄位
    data = remove_ignorable_fields(data)
    return data


def generate_diff(expected: Any, actual: Any, path: str = "") -> list[str]:
    """生成差異報告

    Parameters
    ----------
    expected : Any
        期望值
    actual : Any
        實際值
    path : str
        當前路徑

    Returns
    -------
    list[str]
        差異描述列表
    """
    diffs: list[str] = []

    if type(expected) is not type(actual):
        diffs.append(
            f"{path}: 型別不同 - 期望 {type(expected).__name__}, 實際 {type(actual).__name__}"
        )
        return diffs

    if isinstance(expected, dict):
        all_keys = set(expected.keys()) | set(actual.keys())
        for key in sorted(all_keys):
            new_path = f"{path}.{key}" if path else key
            if key not in expected:
                diffs.append(f"{new_path}: 新增欄位 = {actual[key]!r}")
            elif key not in actual:
                diffs.append(f"{new_path}: 移除欄位 (原值 = {expected[key]!r})")
            else:
                diffs.extend(generate_diff(expected[key], actual[key], new_path))

    elif isinstance(expected, list):
        if len(expected) != len(actual):
            diffs.append(f"{path}: 長度不同 - 期望 {len(expected)}, 實際 {len(actual)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            diffs.extend(generate_diff(e, a, f"{path}[{i}]"))
        # 處理多餘元素
        for i in range(len(expected), len(actual)):
            diffs.append(f"{path}[{i}]: 新增元素 = {actual[i]!r}")
        for i in range(len(actual), len(expected)):
            diffs.append(f"{path}[{i}]: 移除元素 (原值 = {expected[i]!r})")

    else:
        if expected != actual:
            diffs.append(f"{path}: 值不同 - 期望 {expected!r}, 實際 {actual!r}")

    return diffs


def golden_compare(expected_path: str | Path, actual: dict) -> tuple[bool, str]:
    """Golden Data 比對入口

    Parameters
    ----------
    expected_path : str | Path
        期望值檔案路徑（YAML 或 JSON）
    actual : dict
        實際結果

    Returns
    -------
    tuple[bool, str]
        (是否相等, 差異報告)

    Examples
    --------
    >>> is_equal, diff = golden_compare("tests/golden/expected.yaml", actual_result)
    >>> if not is_equal:
    ...     print(diff)
    """
    path = Path(expected_path)

    # 讀取期望值
    if path.suffix in (".yaml", ".yml"):
        with open(path, "r", encoding="utf-8") as f:
            expected = yaml.safe_load(f)
    elif path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            expected = json.load(f)
    else:
        raise ValueError(f"不支援的檔案格式: {path.suffix}")

    # Canonicalize 雙方
    expected_c = canonicalize(expected)
    actual_c = canonicalize(actual)

    if expected_c == actual_c:
        return True, ""

    # 產出 diff 報告
    diffs = generate_diff(expected_c, actual_c)
    report = "\n".join([f"- {d}" for d in diffs])
    return False, f"Golden Data 比對失敗:\n{report}"


if __name__ == "__main__":
    # 測試範例
    sample_data = {
        "amount": 123.456,
        "generated_at": "2025-01-01T12:00:00",
        "records": [
            {"date": "2025-01-02", "value": 200},
            {"date": "2025-01-01", "value": 100},
        ],
    }

    print("原始資料:")
    print(json.dumps(sample_data, indent=2, default=str))
    print("\nCanonicalize 後:")
    result = canonicalize(sample_data)
    print(json.dumps(result, indent=2, default=str))
