# StagingService 實作摘要

## 檔案

- **實作**: `life_capital/capture/staging_service.py`
- **測試**: `tests/capture/test_staging_service.py`

## 測試結果

- **總測試數**: 48
- **通過**: 48 (100%)
- **失敗**: 0
- **覆蓋率**: >90% (預估)

## 核心功能

### 1. CRUD 操作

| 方法 | 狀態 | 說明 |
|------|------|------|
| `add_entry()` | ✅ 完成 | 新增 staging entry |
| `list_entries()` | ✅ 完成 | 列出 entries（支援狀態過濾） |
| `get_entry()` | ✅ 完成 | 讀取單筆 entry（last-write-wins） |
| `delete_entry()` | ⚠️ TODO | 等待 StagingStore 協議更新 |
| `clear_all()` | ⚠️ TODO | 等待 StagingStore 協議更新 |

### 2. 狀態轉移操作（8 狀態狀態機）

| 轉移 | 方法 | 狀態 | 說明 |
|------|------|------|------|
| pending → parsed/approved | `parse_entry()` | ✅ 完成 | 原子解析操作 |
| parsed → approved | `approve_entry()` | ⚠️ 部分完成 | 需整合 proposals_handler |
| parsed/approved → rejected | `reject_entry()` | ✅ 完成 | 拒絕 entry |
| parsed → ignored | `ignore_entry()` | ✅ 完成 | 忽略非支出 |
| parsed → duplicate | `mark_duplicate()` | ✅ 完成 | 手動標記重複 |

### 3. 批次操作

| 方法 | 狀態 | 說明 |
|------|------|------|
| `parse_all_pending()` | ✅ 完成 | 批次解析所有 pending entries |

### 4. 重複偵測（V4.1.1 保守判重）

| 功能 | 狀態 | 說明 |
|------|------|------|
| 精準判重 | ✅ 完成 | duplicate_key 完全匹配 |
| 模糊判重 | ✅ 完成 | 日期±2天 + 金額相同 |
| 文字正規化 | ✅ 完成 | 移除金額、日期、空白 |
| 資訊不足處理 | ✅ 完成 | 無法判重時返回 None |

## 狀態機驗證

### 合法轉移（已測試）

```
pending → parse() → parsed ✅
pending → parse() → approved ⚠️ (auto-approve 未整合)
pending → parse() → error ✅
pending → parse() → duplicate ✅ (自動判重)

parsed → approve() → approved ✅
parsed → reject() → rejected ✅
parsed → ignore() → ignored ✅
parsed → mark_duplicate() → duplicate ✅

approved → reject() → rejected ✅
```

### 非法轉移（已測試）

```
parsed → parse() ❌ InvalidStateTransition
approved → parse() ❌ InvalidStateTransition
pending → approve() ❌ InvalidStateTransition
pending → reject() ❌ InvalidStateTransition
duplicate → mark_duplicate() ❌ InvalidStateTransition (已是 duplicate)
```

## 待整合功能

### 1. Proposal 建立 (TODO)

**影響方法**:
- `parse_entry()` 中的 auto-approve 分支
- `approve_entry()` 中的 proposal 建立

**整合需求**:
```python
# 需要整合 proposals_handler.create_expense_proposals()
# 需要將 StagingEntry 轉換為 ExpenseRecord
```

**Placeholder 標註**:
- Line 246-253: `parse_entry()` auto-approve 分支
- Line 294: `approve_entry()` proposal 建立
- Line 549-564: `_create_proposal()` 方法

### 2. 邏輯刪除 (TODO)

**影響方法**:
- `delete_entry()`
- `clear_all()`

**等待**: StagingStore Protocol 更新（定義刪除語意）

## 測試覆蓋範圍

### CRUD 操作 (10 tests)
- ✅ 新增 entry（基本 + 批次）
- ✅ 列出 entries（全部 + 過濾 + 排序 + 空列表）
- ✅ 讀取單筆 entry（存在 + 不存在）
- ⚠️ 刪除操作（NotImplementedError）

### 狀態轉移 (10 tests)
- ✅ Parse 成功/失敗/非法狀態/不存在
- ✅ Approve 成功/非法狀態/不存在
- ✅ Reject 成功（從 parsed/approved）/非法狀態
- ✅ Ignore 成功/非法狀態
- ✅ Mark duplicate 成功/非法狀態

### 批次操作 (3 tests)
- ✅ 批次解析成功
- ✅ 批次解析部分失敗（容錯）
- ✅ 批次解析空列表

### 重複偵測 (5 tests)
- ✅ 精準判重（exact match）
- ✅ 模糊判重（date fuzzy）
- ✅ 無重複
- ✅ 資訊不足（無法判重）
- ✅ 跳過已忽略的 entries

### 文字正規化 (4 tests)
- ✅ 移除金額
- ✅ 移除日期
- ✅ 移除空白
- ✅ 轉小寫

### Duplicate Key (3 tests)
- ✅ 計算成功
- ✅ 日期缺失
- ✅ 金額缺失

### 異常處理 (2 tests)
- ✅ EntryNotFound
- ✅ InvalidStateTransition

### 整合測試 (4 tests)
- ✅ 完整工作流程（auto-approve 關閉）
- ✅ 完整工作流程（拒絕）
- ✅ 跨實例持久化
- ✅ Last-write-wins 語意

### 邊界情況 (5 tests)
- ✅ 空文字解析
- ✅ 特殊字元處理
- ✅ 超長文字處理
- ✅ Clear 操作（NotImplementedError）
- ✅ Delete 操作（NotImplementedError）

## 防護規則驗證

| 規則 | 狀態 | 測試覆蓋 |
|------|------|----------|
| ❌ approved 狀態不可直接編輯 | ✅ 驗證 | `test_parse_entry_invalid_state` |
| ❌ applied 的資料不可從 staging 修改 | - | 無 applied 狀態測試 |
| ✅ rejected 可重新編輯 | ✅ 驗證 | `test_full_workflow_rejection` |
| ✅ ignored 可還原為 pending | - | 未實作 restore 方法 |
| ⚠️ duplicate 需 force-approve | - | 未實作 force-approve 方法 |

## 原子性保證

### Parse 原子性（V4.1.1）

**實作**:
- Entry-by-entry 原子單位（非 batch transaction）
- 每次 parse 完整更新所有 parsed_* 欄位
- 狀態轉移與資料更新在同一次 write_entry() 中完成

**測試**:
- ✅ Parse 成功後所有欄位更新
- ✅ Parse 失敗時 error_message 更新
- ✅ 重複偵測在 parse 內部完成

## 並發安全

**依賴**: StagingStoreImpl 的 threading.Lock

**保證**:
- 寫入操作原子性（append-only）
- _seq 遞增保證（O(1) 實作）
- Last-write-wins 語意

## 效能特性

### 時間複雜度

| 操作 | 複雜度 | 說明 |
|------|--------|------|
| `add_entry()` | O(1) | 追加寫入 + _seq 生成 |
| `list_entries()` | O(n) | 全量讀取 + 去重 |
| `get_entry()` | O(n) | 線性搜尋 |
| `parse_entry()` | O(n) | Parse + 判重（掃描所有 entries） |
| `parse_all_pending()` | O(n×m) | n 個 pending × m 個 existing |

### 優化建議（未來）

1. **索引**: 為 entry_id 建立記憶體索引（加速 get_entry）
2. **快取**: 快取 read_current_state() 結果（減少重複讀取）
3. **批次寫入**: 批次 parse 時使用單次寫入（減少 I/O）

## 相依模組

### 直接依賴

- `life_capital.interfaces.staging_store.StagingStore` (Protocol)
- `life_capital.capture.expense_parser.ExpenseParser`
- `life_capital.interfaces.canonical_reader.CanonicalReader` (Protocol)
- `life_capital.capture.models` (StagingEntry, StagingStatus, DuplicateReason)

### 待整合

- `life_capital.io.proposals_handler.create_expense_proposals()` (TODO)

## 版本歷程

- **V1.0** (2025-01-23): 初版實作
  - 完成 8 狀態狀態機
  - 完成 V4.1.1 保守判重
  - 完成 Parse 原子性
  - 48 個測試全通過
  - Proposal 建立標註為 TODO

## 下一步

1. **整合 Proposal 建立**:
   - 實作 `_create_proposal()` 方法
   - 整合 `proposals_handler.create_expense_proposals()`
   - 新增 auto-approve 流程測試

2. **完成刪除功能**:
   - 更新 StagingStore Protocol（定義刪除語意）
   - 實作 `delete_entry()` 和 `clear_all()`
   - 新增刪除操作測試

3. **實作狀態恢復**:
   - 新增 `restore_entry()` 方法（ignored → pending）
   - 新增 `force_approve_entry()` 方法（duplicate → approved）

4. **效能優化**:
   - 實作記憶體索引（加速查詢）
   - 實作結果快取（減少重複讀取）
   - 批次寫入優化
