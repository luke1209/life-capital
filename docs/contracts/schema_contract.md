# Schema Contract

> 定義 Pydantic 模型的變更規則與測試驗證機制

## 目的

明確定義什麼是「不可接受的 Schema 變動」，確保 Phase 4+ 開發時的模型穩定性。

## 變更分類

### Breaking Changes（測試失敗，無例外）

以下變更會導致契約測試失敗，必須解決後才能合併：

| 變更類型 | 範例 | 影響 |
|----------|------|------|
| 欄位刪除 | 移除 `category` 欄位 | 既有資料無法解析 |
| 欄位改名 | `category` → `type` | 既有資料無法解析 |
| 型別變更 | `str` → `int` | 驗證失敗 |
| Optional → Required | `note: Optional[str]` → `note: str` | 既有資料驗證失敗 |
| Enum 值刪除 | 移除 `EXPENSE` 選項 | 既有資料驗證失敗 |
| 驗證規則收緊 | `min_length: 1` → `min_length: 3` | 部分資料驗證失敗 |
| 預設值變更（影響輸出） | `payer: str = "shared"` → `payer: str = "person_a"` | 輸出結果變動 |

### Compatible Changes（需 Sign-off）

以下變更需要人工審核，但不會導致測試失敗：

| 變更類型 | 範例 | 審核重點 |
|----------|------|----------|
| 新增 Optional 欄位 | 新增 `note: Optional[str]` | 確認不影響既有邏輯 |
| Enum 值新增 | 新增 `REFUND` 選項 | 確認處理邏輯已就緒 |
| 驗證規則放寬 | `min_length: 3` → `min_length: 1` | 確認業務邏輯接受 |
| 預設值變更（不影響輸出） | 內部快取預設值 | 確認行為一致 |

## 涵蓋範圍

### 測試涵蓋的模型

```
life_capital/models/
├── base.py              → VersionedModel
├── policy.py            → ExpensePolicy, CategoryGroup
├── assumptions.py       → LifeAssumptions
├── targets.py           → LifetimeTargets
├── income.py            → MonthlyIncome
├── transaction.py       → Transaction
├── expense.py           → Expense, MonthlyExpenses
├── operation.py         → Operation, Provenance
└── scenario.py          → Scenario, ScenarioResult
```

### 測試項目

每個模型的 JSON Schema 需驗證：

| 項目 | 說明 |
|------|------|
| 欄位名稱與數量 | `properties` 清單 |
| 欄位型別 | `type`, `anyOf` |
| Required vs Optional | `required` 清單, `nullable` |
| Enum 值列表 | `enum` 陣列 |
| 驗證規則 | `minLength`, `pattern`, `ge`, `le` 等 |
| 預設值 | `default`（影響輸出者） |

## 測試機制

### Baseline 檔案

每個模型對應一個 baseline：

```
tests/contracts/baselines/
├── ExpensePolicy.json
├── LifeAssumptions.json
├── MonthlyIncome.json
├── Transaction.json
└── ...
```

### 測試流程

```python
def test_schema_unchanged():
    baseline = load_baseline("ExpensePolicy.json")
    current = normalize_schema(ExpensePolicy.model_json_schema())
    diff = schema_diff(baseline, current)
    assert not diff.has_breaking_changes, f"Breaking: {diff}"
```

### Baseline 更新規則

1. **測試不可自動建立 baseline** - 若 baseline 不存在，測試失敗
2. **只能透過 explicit script 更新**：
   ```bash
   python scripts/update_schema_baseline.py --model ExpensePolicy
   ```
3. **更新後需 CODEOWNERS 審核**

## 語意正規化

為避免環境差異造成假陽性，Schema 比對前需正規化：

### 保留欄位（Semantic Whitelist）

```python
SEMANTIC_WHITELIST = {
    "type", "properties", "required", "items",
    "enum", "const", "default",
    "pattern", "format",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "minItems", "maxItems",
    "anyOf", "oneOf", "allOf", "$ref",
    "additionalProperties", "nullable"
}
```

### 剔除欄位

以下欄位不影響契約語意，剔除以減少噪音：

- `title` - 顯示用名稱
- `description` - 說明文字
- `examples` - 範例值
- `$defs` - 定義展開形態

## 環境鎖定

為確保跨環境一致性：

```toml
# pyproject.toml
[tool.uv]
python = "3.12"

[project.dependencies]
pydantic = "==2.10.3"
```

## 審核流程

### Breaking Change

1. CI 自動阻止合併
2. 需修改程式碼解決

### Compatible Change

1. 執行 `python scripts/update_schema_baseline.py`
2. 檢視 `schema_diff_report.md`
3. 加上 `schema-approved` label
4. CODEOWNERS 審核後合併

## 相關檔案

| 用途 | 路徑 |
|------|------|
| Schema 契約測試 | `tests/contracts/test_schema_stability.py` |
| Baseline 目錄 | `tests/contracts/baselines/*.json` |
| 正規化模組 | `scripts/schema_normalize.py` |
| Baseline 更新腳本 | `scripts/update_schema_baseline.py` |
