# E3 風險評估模組 - 實作總結

**實作日期**: 2024-12-29
**階段**: Phase 5 Stage 3
**狀態**: ✅ 完成

## 實作內容

### 1. 共用可評估性模組

**檔案**: `life_capital/advisor/shared/evaluability.py`

- ✅ `RecommendabilityLevel` Enum（FULL, PARTIAL, NONE）
- ✅ `EvaluabilityLevel` Enum（FULL, WARNING, SKIP）
- ✅ `DecisionEvaluability` dataclass
- ✅ `evaluate_decision()` 函式

**閾值對照表**:

| comparability_score | 可推薦性 | 可評估性 | 警告訊息 |
|---------------------|----------|----------|----------|
| ≥0.7 | FULL | FULL | None |
| 0.5-0.7 | PARTIAL | FULL | "部分可比：推薦結果僅供參考" |
| 0.3-0.5 | NONE | WARNING | "低可比性：風險評估可能不準確" |
| <0.3 | NONE | SKIP | "不可比：跳過風險與敏感度評估" |

### 2. 風險評估器

**檔案**: `life_capital/advisor/risk_assessor.py`

- ✅ `RiskAssessment` dataclass
- ✅ `assess_risk()` 函式
- ✅ 風險等級計算邏輯（基於 risk_tags 數量）
  - 0 tags → low
  - 1-2 tags → medium
  - ≥3 tags → high
- ✅ 可評估性整合（< 0.3 返回 None）
- ✅ 警告訊息處理

### 3. 風險矩陣生成器

**檔案**: `life_capital/generation/risk_matrix.py`

- ✅ `generate_risk_matrix()` - 生成 JSON 矩陣
- ✅ `save_risk_matrix()` - 儲存檔案 + Provenance
- ✅ 過濾有效決策（PENDING/APPLIED）
- ✅ 統計分佈（low/medium/high）
- ✅ 跳過計數（comparability_score < 0.3）

**輸出格式**:
```json
{
  "generated_at": "ISO 8601",
  "total_decisions": 4,
  "assessed_count": 3,
  "skipped_count": 1,
  "risk_distribution": {"low": 1, "medium": 1, "high": 1},
  "assessments": [...]
}
```

## 測試覆蓋

### `tests/advisor/test_evaluability.py` (10 tests)

- ✅ `test_full_recommendable_ge_07` - ≥0.7 為 FULL
- ✅ `test_partial_recommendable_05_07` - 0.5-0.7 為 PARTIAL
- ✅ `test_none_recommendable_lt_05` - <0.5 為 NONE
- ✅ `test_full_evaluable_ge_05` - ≥0.5 為 FULL
- ✅ `test_warning_evaluable_03_05` - 0.3-0.5 為 WARNING
- ✅ `test_skip_evaluable_lt_03` - <0.3 為 SKIP
- ✅ `test_warning_message_correct` - 警告訊息正確
- ✅ `test_boundary_070_is_full` - 邊界 0.70 為 FULL
- ✅ `test_boundary_050_is_partial` - 邊界 0.50 為 PARTIAL
- ✅ `test_boundary_030_is_warning` - 邊界 0.30 為 WARNING

### `tests/advisor/test_risk_assessor.py` (8 tests)

- ✅ `test_assess_risk_high_level` - ≥3 tags 為 high
- ✅ `test_assess_risk_medium_level` - 1-2 tags 為 medium
- ✅ `test_assess_risk_low_level` - 0 tags 為 low
- ✅ `test_assess_risk_skip_lt_03` - <0.3 返回 None
- ✅ `test_assess_risk_warning_added` - WARNING 等級加警告
- ✅ `test_assess_risk_no_warning_full` - FULL 等級無警告
- ✅ `test_risk_tags_preserved` - risk_tags 保留
- ✅ `test_risk_explanation_preserved` - risk_explanation 保留

### `tests/generation/test_risk_matrix.py` (6 tests)

- ✅ `test_matrix_has_required_keys` - 包含必要鍵
- ✅ `test_risk_distribution_correct` - 統計正確
- ✅ `test_skipped_count_correct` - 跳過計數正確
- ✅ `test_assessments_list_valid` - assessments 列表合法
- ✅ `test_save_risk_matrix_creates_file` - save 建立檔案
- ✅ `test_save_risk_matrix_provenance` - Provenance 正確

**總計**: 24 個測試（超過最低 22 個要求）

## 驗收狀態

- ✅ `advisor/shared/evaluability.py` 已建立
- ✅ `advisor/risk_assessor.py` 已建立
- ✅ `generation/risk_matrix.py` 已建立
- ✅ `evaluate_decision()` 實作完成
- ✅ `assess_risk()` 實作完成
- ✅ `generate_risk_matrix()` 與 `save_risk_matrix()` 實作完成
- ✅ 至少 24 個測試通過（> 22 個最低要求）
- ✅ 邊界值測試涵蓋 0.30、0.50、0.70

## 技術細節

### 可評估性分層設計

採用雙維度判定：
1. **Recommendability**（可推薦性）：影響 Stage 2 的推薦輸出
2. **Evaluability**（可評估性）：影響 Stage 3 的風險/敏感度評估

兩者共用 `comparability_score`，但閾值不同：
- Recommendability: 0.5, 0.7
- Evaluability: 0.3, 0.5

### Provenance 整合

使用 `AdvisorDerivedHandler` 確保：
- 原子寫入（臨時檔案 + rename）
- Sidecar metadata（.meta.json）
- 路徑安全驗證（防止 path traversal）
- Content hash 驗證（SHA-256）

### Python 3.9 相容性

使用 `Optional[str]` 而非 `str | None`，確保 Python 3.9 相容性。

## 後續整合

E3 風險評估模組已準備好與以下模組整合：
- E4: 敏感度分析（共用 `evaluability.py`）
- CLI: `lc advisor risk-matrix` 指令
- Wiki: 風險矩陣嵌入決策 Wiki

## 參考文件

- [contracts.md](./contracts.md) - 技術契約
- [plan.md](./plan.md) - Stage 3 主規劃
