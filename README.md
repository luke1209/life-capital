# Life Capital

<!-- 不可變規則：此文件為用戶使用指南的唯一來源 -->
<!-- 技術規範請見 CLAUDE.md，兩文件職責不重疊 -->

終身財務規劃系統 - 幫助你與伴侶共同管理財務目標

> **Demo notice**: All sample data in `docs/examples/` and `tests/fixtures/`
> are synthetic. Member IDs (`person_a`, `person_b`) and amounts do not
> represent real individuals or financial situations.

## 工程作品集視角

本專案作為公開作品集，展示以下工程實踐：

- **護欄式架構**：raw / canonical / derived 三層寫入邊界，搭配 `lc apply`/`lc undo` 不可逆操作護欄
- **Decimal 強制**：金融計算全程使用 `Decimal` + `ROUND_HALF_UP`，禁止 `float` 進入 calculators
- **Schema 版本管控**：YAML schema 與 `CURRENT_SCHEMA_VERSION` 強一致，含 migration 工具
- **契約測試**：phase contracts、staging state machine 測試確保跨階段相容性
- **TDD 驅動**：190+ 測試覆蓋核心邏輯，包含 E2E、契約、單元三層
- **多階段交付**：phase1-data → phase5-advisor 完整迭代足跡（見 `docs/plans/`）

## 這是什麼？

Life Capital 是一個 CLI 財務規劃工具，專為**雙人共同財務規劃**設計：

- 計算達成人生目標所需的每月儲蓄
- 追蹤支出並檢查是否符合預算
- 匯入銀行帳單並自動分類
- 支援回滾操作，避免誤操作造成資料遺失
- **資料完全本地化，不上傳任何資訊**

## 快速開始

```bash
# 安裝
uv sync

# 初始化資料目錄
lc init --path ./data

# 驗證資料
lc validate --path ./data

# 你的第一個財務報表
lc summary --path ./data
```

## 核心概念

| 名詞 | 說明 | 範例 |
|------|------|------|
| 目標 (Target) | 一次性財務目標 | 買房頭期、旅遊基金 |
| 支出政策 (Policy) | 每月預算分配 | 餐飲 30%、交通 10% |
| 支付者 (Payer) | 支出記錄的付款人 | person_a / person_b / shared |
| 擁有者 (Owner) | 收入來源的歸屬人 | person_a / person_b / shared |
| 三層資料 | raw→canonical→derived | 匯入→正規化→報表 |
| Staging (待處理) | 自然語言輸入的暫存區 | 「昨天吃了 320 元拉麵」→ 解析 → proposals |

## 使用情境

### 情境 1: 雙人共同記帳與週對帳

「我和伴侶每週對帳一次，各自記錄支出後合併檢視」

```bash
# 各自匯入當週消費（CSV 含 payer 欄位區分付款人）
lc import ~/my_expenses.csv --path ~/Dropbox/life-capital

# 檢查支出占比
lc expense check --path ~/Dropbox/life-capital
```

**CSV 格式範例**：
```csv
date,amount,category,payer,note,merchant
2025-01-05,1200,transportation,person_a,加油,中油
2025-01-08,2800,food,person_b,超市採買,家樂福
```

### 情境 2: 共同目標追蹤

「我們想存旅遊基金，需要知道每人每月要存多少」

```bash
# 計算終身財務需求
lc lifetime --path ./data
```

### 情境 3: 自然語言快速記帳（Phase 4）

「我想用自然語言快速記帳，不想手動填 CSV」

```bash
# 單筆捕捉
lc capture "昨天吃了 320 元拉麵" --path ./data
lc capture "12/25 聖誕禮物 1500" --path ./data
lc capture "捷運加值 500 交通" --path ./data

# 列出待處理項目
lc staging list --path ./data

# 解析並建立 proposals（AI 自動抽取日期、金額、類別）
lc staging parse --confirm --path ./data

# 批准並進入正式流程
lc staging approve <entry_id> --path ./data
lc apply --confirm --path ./data
```

**批次匯入**：
```bash
# 從檔案批次讀取（每行一筆）
lc capture --batch ~/expenses.txt --path ./data
```

**修復不一致狀態**：
```bash
# 偵測 staging 資料不一致
lc staging repair --dry-run --path ./data

# 執行修復
lc staging repair --path ./data
```

### 情境 4: 匯入銀行帳單

「我下載了銀行 CSV，想匯入系統」

```bash
lc import ~/bank_statement.csv --path ./data
lc apply --confirm --path ./data
```

### 情境 5: 生成財務報表

「我想查看未來 12 個月的現金流預測，並比較不同情境」

```bash
# 先執行預測計算（如果尚未執行）
lc project --save --path ./data

# 生成月度摘要（顯示總收入、總支出、平均現金流）
lc report --type monthly --path ./data

# 生成完整預測表（12-24 個月明細）
lc report --type projection --path ./data

# 生成所有報表並存檔到 derived/reports/
lc report --save --path ./data

# 生成 JSON 格式報表
lc report --format json --path ./data
```

**報表類型說明**：
- `monthly_summary`: 月度現金流摘要（總覽）
- `projection_table`: 12-24 個月預測明細表
- `scenario_comparison`: 情境比較表（需先執行 `lc scenario`）

### 情境 6: 回滾錯誤操作

「我不小心匯入錯誤的資料，想撤銷」

```bash
# 回滾最近操作
lc undo --latest --path ./data

# 或指定操作 ID
lc undo --operation op_abc123 --path ./data
```

### 情境 7: AI 顧問決策分析（Phase 5）

「我想追蹤過去的財務決策並分析風險」

```bash
# 查看決策歷史
lc advisor history --path ./data

# 解釋特定決策
lc advisor explain --id decision_123 --path ./data

# 生成風險矩陣
lc advisor risk-matrix --path ./data

# 執行敏感度分析
lc advisor sensitivity --path ./data
```

## 指令參考

| 指令 | 用途 |
|------|------|
| `lc init` | 初始化資料目錄 |
| `lc validate` | 驗證資料完整性 |
| `lc lifetime` | 計算終身需求 |
| `lc project` | 現金流預測與分析 |
| `lc scenario` | 情境分析與比較 |
| `lc report` | 生成財務報表（月度摘要、預測表、情境比較）|
| `lc summary` | 財務總覽 |
| `lc expense check` | 支出占比檢查 |
| `lc doctor` | 環境與資料檢查 |
| `lc import <csv>` | 匯入 CSV |
| `lc capture <text>` | 自然語言捕捉支出（Phase 4）|
| `lc staging list` | 列出待處理項目（Phase 4）|
| `lc staging parse` | 解析並建立 proposals（Phase 4）|
| `lc staging approve <id>` | 批准 entry（Phase 4）|
| `lc staging repair` | 修復 staging 不一致（Phase 4）|
| `lc apply --confirm` | 確認變更 |
| `lc undo --operation <id>` | 回滾操作 |
| `lc rebuild` | 重建衍生資料 |

> 完整 staging 子指令請見 `lc staging --help`
> 未來規劃指令請見 `docs/roadmap/V2.5.md`

## 架構概念

Life Capital 採用「軟體與資料分離」設計：

```
軟體 (life-capital/)     ←  計算邏輯、CLI 指令
        ↓ 讀取 / 寫入 ↑
資料 (~/.life-capital/)  ←  你的財務數據
```

**好處**：
- 升級軟體不影響資料
- 資料可獨立備份、加密、雲端同步
- 同一份軟體可服務多個資料目錄（`--path`）

> 技術細節請見 `CLAUDE.md`

## 資料目錄

```
~/.life-capital/
├── raw/           # 原始匯入（不可變）
├── canonical/     # 正規化資料
├── derived/       # 計算結果（可重建）
├── staging/       # 待處理的自然語言輸入（Phase 4）
└── proposals/     # 待確認變更
```

## 安全與隱私

### 重要：這不是雲端服務

Life Capital 是本地工具，**沒有帳號、沒有權限控制**。
共享同一份資料目錄的人，可以看到並修改所有資料。

### 資料儲存

- 所有資料存在 `~/.life-capital/`（或 `--path` 指定的目錄）
- **不上傳任何資訊**到雲端

### 備份策略

- 直接複製整個資料目錄
- 建議：每次匯入前先備份

### 雙人共用方式

將 `--path` 指向共享目錄（如 Dropbox）。

**限制說明**：
- 這是「完全信任」模型，沒有權限隔離
- 若需要私人支出隱私，請使用獨立資料目錄

## 同步衝突 SOP

使用 Dropbox/iCloud 等同步服務時可能遇到檔案衝突。

### 預防措施

1. **避免同時編輯**: 約定誰在操作時另一人不動
2. **操作前同步**: 確保本地是最新版本
3. **小批次 apply**: 避免大量未 apply 的 proposals 堆積

### 衝突發生時的處理流程

```
1. 暫停所有 lc 操作
2. 在 Finder/Explorer 找到衝突檔案（通常有 "(衝突)" 字樣）
3. 比對兩版本差異：
   - YAML 檔: 手動合併或選擇較新版本
   - JSONL 檔: 合併兩者的 entries（注意 operation_id 不可重複）
4. 刪除衝突副本，保留合併後的檔案
5. 執行 `lc validate` 確認資料完整
6. 若 derived/ 不一致，執行 `lc rebuild`
7. 執行 `lc doctor` 確認無 hard fail
```

### 無法手動解決時

```bash
# 最後手段：從備份還原
cp -r ~/backup/life-capital ~/.life-capital
lc rebuild
```

## 常見問題

### Q: 如何備份資料？

直接複製 `~/.life-capital/` 目錄，或使用 `--path` 指向雲端同步資料夾。

### Q: 如何與伴侶共享？

將 `--path` 指向共享目錄（如 Dropbox）。注意：沒有權限隔離，請見「安全與隱私」。

### Q: 資料存在哪裡？

預設 `~/.life-capital/`，可用 `--path` 自訂。

### Q: 誤操作怎麼辦？

使用 `lc undo --latest` 回滾最近操作。

### Q: derived/ 被刪除了怎麼辦？

使用 `lc rebuild` 從 raw/ + canonical/ 重建。

### Q: lc validate 失敗怎麼辦？

診斷步驟：
1. 檢視錯誤訊息，確認是哪個檔案/哪一筆
2. 常見錯誤：
   - `category not found`：檢查 expense_policy.yaml 是否有該分類
   - `schema version mismatch`：執行 `lc doctor` 檢查版本
   - `duplicate entry`：檢查 CSV 是否有重複記錄
3. 修正資料後重新執行 `lc validate`

### Q: 同步衝突怎麼辦？

請見「同步衝突 SOP」章節。

## 版本資訊

| 版本 | 日期 | 說明 |
|------|------|------|
| V2.5 Phase 4 | 2025-12-29 | CAPTURE 模組：自然語言記帳與狀態機 (30 CLI 測試, 13 整合測試) |
| V2.0 Phase 3 | 2025-12-28 | 報表生成模組：驗收完成 (9/9 contracts, 190 測試) |
| V2.0 Phase 2 | 2025-12-28 | Scenario 模組：現金流預測與情境分析 (181 測試) |
| V2.0 Phase 0 | 2024-12-27 | 三層架構、import/apply/undo/rebuild |
| Schema 1.1 | 2024-12-27 | 新增 payer/owner 欄位支援雙人記帳 |
| MVP V5.1.3 | 2024-12-26 | 7 核心指令、66 測試 |
