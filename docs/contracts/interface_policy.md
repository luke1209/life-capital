# Interface Version Policy

> 定義 `life_capital/interfaces/` 層的演進規則

## 目的

Interface 層提供 Phase 4+ 模組與核心系統之間的穩定契約。
若無版本策略，Interface 也會成為漂移源，抵消隔離帶來的穩定性。

## 變更分類

| 類型 | 定義 | 處理方式 | 範例 |
|------|------|----------|------|
| **Breaking** | 刪除方法、改變簽名、改變返回型別 | **禁止**（需版本遷移） | 刪除 `get_categories()` |
| **Compatible** | 新增方法（提供 default 或 NotImplementedError） | 需 sign-off | 新增 `get_version()` |
| **Internal** | 實作細節變更（不影響 Protocol） | 無需審核 | 重構內部邏輯 |

## Breaking Change 規則

Breaking change **必須**執行版本遷移：

1. 在 `canonical_reader.py` 更新 `INTERFACE_VERSION`
2. 提供 migration 路徑（如 adapter pattern）
3. 更新所有依賴模組
4. 建立新的 Interface Baseline

## Compatible Change 規則

新增方法時**必須**提供 default：

```python
# 正確：提供 default implementation
def get_version(self) -> str:
    """取得介面版本（V1.1 新增）"""
    return "1.0"  # default implementation

# 錯誤：沒有 default
def new_method(self) -> str:
    ...  # 這會破壞既有實作
```

## CI 驗證

### 1. 隔離驗證

確保 `capture/` 只依賴 `interfaces/`：

```bash
# 應該為空（無直接依賴 models）
grep -r "from life_capital.models" life_capital/capture/

# 應該有結果（正確依賴 interfaces）
grep -r "from life_capital.interfaces" life_capital/capture/
```

### 2. Protocol 穩定性

`tests/contracts/test_interface_stability.py` 驗證 Protocol 簽名未變：

```python
def test_interface_methods_unchanged():
    baseline = load_baseline("CanonicalReader.json")
    current = extract_protocol_signature(CanonicalReader)

    # 檢查 breaking changes
    for method_name, sig in baseline.items():
        assert method_name in current, f"Method {method_name} was removed"
        assert current[method_name] == sig, f"Signature changed"
```

### 3. Baseline 更新

只能透過 explicit script 更新：

```bash
python scripts/update_interface_baseline.py --protocol CanonicalReader
```

## 檔案結構

```
life_capital/interfaces/
├── __init__.py              # 匯出 Protocols
├── canonical_reader.py      # Phase 4 主要介面
└── (future protocols...)

docs/contracts/
├── interface_policy.md      # 此文件
└── ...

tests/contracts/
├── test_interface_stability.py  # Protocol 穩定性測試
└── baselines/
    └── CanonicalReader.json     # Protocol 簽名基準
```

## 版本歷程

| 版本 | 日期 | 變更 |
|------|------|------|
| 1.0 | 2025-12-28 | 初版：定義 `CanonicalReader` Protocol |

## 審核要求

| 變更類型 | CODEOWNERS 審核 | `interface-approved` Label |
|----------|-----------------|---------------------------|
| Breaking | 雙人 | 必須 |
| Compatible | 單人 | 必須 |
| Internal | 無 | 無 |
