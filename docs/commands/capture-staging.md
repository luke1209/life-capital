# Phase 4 CAPTURE - CLI 指令使用指南

> **Phase 4 實作狀態**: ✅ 完成（21/21 tasks, 608 tests）
> **最後更新**: 2025-12-29

---

## 概述

Phase 4 CAPTURE 提供自然語言支出記錄功能，透過兩個 CLI 指令實現：

| 指令 | 用途 | 狀態 |
|------|------|------|
| `lc capture` | 捕捉零散輸入至 staging | ✅ 已實作 |
| `lc staging` | 管理 staging entries | ✅ 已實作（8 個子指令） |

---

## 基本工作流程

```bash
# 1. 捕捉支出記錄
lc capture "昨天吃了 320 元拉麵"

# 2. 列出待處理項目
lc staging list --status pending

# 3. 解析並轉換為 proposals（V4.1: 唯一解析路徑）
lc staging parse --confirm

# 4. 最後進入正式流程
lc apply --confirm
```

---

## lc capture 指令

### 基本用法

```bash
# 單筆記錄
lc capture "昨天吃了 320 元拉麵"
lc capture "12/25 聖誕禮物 1500"
lc capture "捷運加值 500 交通"

# 批次匯入
lc capture --batch expenses.txt
```

### 參數說明

| 參數 | 說明 | 預設值 | 範例 |
|------|------|--------|------|
| `TEXT` | 支出描述文字（可選） | - | `"昨天吃了 320 元拉麵"` |
| `--batch` | 批次匯入檔案路徑 | - | `--batch file.txt` |
| `--source` | 來源標記 | `cli` | `--source api` |
| `--path` | 資料目錄路徑 | `~/.life-capital/` | `--path ./data` |

### 輸出範例

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              ✅ 已加入 staging                 ┃
┃     Entry ID: abc12345-...                    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  raw_text: 昨天吃了 320 元拉麵
  status: pending
  created_at: 2024-12-27T10:30:00

下一步: lc staging parse --confirm
```

---

## lc staging 指令

### 子指令清單

| 子指令 | 用途 | 狀態 |
|--------|------|------|
| `list` | 列出 staging entries | ✅ |
| `show` | 顯示 entry 詳細資訊 | ✅ |
| `parse` | 解析 pending entries | ✅ |
| `approve` | 手動批准 entry | ✅ |
| `reject` | 拒絕 entry | ✅ |
| `ignore` | 忽略 entry（非支出） | ✅ |
| `delete` | 刪除 staging entry | ✅ |
| `clear` | 清除所有 entries | ✅ |
| `repair` | 修復不一致狀態 | ✅ |

---

### 1. lc staging list

列出 staging entries，支援狀態過濾。

```bash
# 列出所有 entries
lc staging list

# 列出 pending entries
lc staging list --status pending

# 列出已解析的 entries
lc staging list --status parsed
```

**狀態值**:
- `pending` ⏳ - 待解析
- `parsed` 🔍 - 已解析，待確認
- `error` ❌ - 解析失敗
- `approved` ✅ - 已批准，proposal 已建立
- `rejected` 🚫 - 已拒絕
- `ignored` ⚠️ - 非支出
- `duplicate` 🔄 - 重複輸入
- `applied` 📦 - 終態：已進入 canonical

**輸出範例**:

```
                 Staging Entries (3)

┏━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Status  ┃ ID       ┃ Raw Text     ┃ Conf   ┃ Created     ┃
┡━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━┩
│ ⏳ pend │ abc12345 │ 昨天吃了...  │ -      │ 2024-12-27  │
│ 🔍 pars │ def67890 │ 12/25 聖誕... │ 90.0%  │ 2024-12-26  │
│ ✅ appr │ ghi11111 │ 捷運加值...  │ 100.0% │ 2024-12-25  │
└─────────┴──────────┴──────────────┴────────┴─────────────┘
```

---

### 2. lc staging show

顯示單筆 entry 的詳細資訊。

```bash
lc staging show abc12345
```

**輸出範例**:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              🔍 parsed                        ┃
┃     Entry ID: abc12345-...                    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

基本資訊
  raw_text: 昨天吃了 320 元拉麵
  created_at: 2024-12-27T10:30:00
  source: cli

解析結果
  📅 date: 2024-12-26 [✓] (source: builtin_exact)
  💰 amount: 320 [✓] (source: exact)
  📂 category: food [✓] (source: exact)

信心度: 90.0%
  amount: 0.40
  date: 0.30
  category: 0.20
```

---

### 3. lc staging parse

解析 pending entries（V4.1: 唯一解析路徑）。

```bash
# Dry-run（預設）
lc staging parse

# 執行解析
lc staging parse --confirm
```

**功能**:
- 批次解析所有 pending entries
- 自動抽取日期、金額、類別
- 計算信心度
- 檢查 auto-approve 護欄
- 偵測重複

**輸出範例**:

```
🔄 解析中...

✅ approved abc12345: Proposal 已建立
🔍 parsed   def67890
❌ error    ghi11111: 無法抽取金額

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              ✅ 解析完成                       ┃
┃   成功: 2/3 | 失敗: 1/3                       ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

### 4. lc staging approve

手動批准 entry（建立 proposal）。

```bash
lc staging approve abc12345
```

**狀態轉移**: `parsed` → `approved`

**輸出範例**:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              ✅ 已批准                         ┃
┃     Entry ID: abc12345-...                    ┃
┃     Proposal ID: proposal_abc123.yaml         ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

### 5. lc staging reject

拒絕 entry。

```bash
lc staging reject abc12345 --reason "金額錯誤"
```

**狀態轉移**: `parsed`/`approved` → `rejected`

**輸出範例**:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              🚫 已拒絕                         ┃
┃     Entry ID: abc12345-...                    ┃
┃     Reason: 金額錯誤                           ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

### 6. lc staging ignore

忽略 entry（非支出）。

```bash
lc staging ignore abc12345 --reason "非支出記錄"
```

**狀態轉移**: `parsed` → `ignored`

---

### 7. lc staging delete

刪除 staging entry（邏輯刪除）。

```bash
# 需確認
lc staging delete abc12345

# 跳過確認
lc staging delete abc12345 --yes
```

**輸出範例**:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              🗑️ 已刪除                         ┃
┃     Entry ID: abc12345-...                    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

### 8. lc staging clear

清除所有 entries（邏輯刪除）。

```bash
# 清除所有
lc staging clear

# 只清除 pending
lc staging clear --status pending

# 跳過確認
lc staging clear --yes
```

**輸出範例**:

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              🗑️ 已清除                         ┃
┃     已清除 3 筆 entries                       ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

### 9. lc staging repair

偵測並修復 staging 資料不一致狀態。

```bash
# 檢查不一致（dry-run）
lc staging repair --dry-run

# 執行修復
lc staging repair
```

**偵測的不一致類型**:
- `approved_without_proposal`: 已批准但無 proposal_id
- `proposal_without_approved`: 有 proposal_id 但狀態非 approved
- `applied_without_canonical`: 已 applied 但無 canonical_record_id

**輸出範例**:

```
🔍 偵測不一致...

發現 2 筆不一致:
  abc12345: approved_without_proposal
  def67890: proposal_without_approved

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              ✅ 修復完成                       ┃
┃     修復: 2 筆                                ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

## 錯誤處理

### 常見錯誤

| 錯誤訊息 | 原因 | 解法 |
|----------|------|------|
| `Entry not found` | entry_id 不存在 | 使用 `lc staging list` 檢查 |
| `Invalid state transition` | 狀態轉移不合法 | 檢查當前狀態與目標狀態 |
| `Cannot parse: ...` | 解析失敗（金額/日期/類別） | 手動修正原始文字或使用 `--reason` 拒絕 |
| `Duplicate detected` | 重複輸入 | 使用 `lc staging show` 查看比對結果 |

---

## 參考資料

- **規劃文件**: `docs/plans/phase4-capture/plan.md`
- **實作狀態**: `docs/roadmap/V2.5.md` (Phase 4 CAPTURE)
- **測試**: `tests/capture/test_staging_service.py`
- **原始碼**:
  - `life_capital/commands/capture_cmd.py`
  - `life_capital/commands/staging_cmd.py`
  - `life_capital/capture/staging_service.py`

---

*Phase 4 CAPTURE - 完成（21/21 tasks, 608 tests）✅*
