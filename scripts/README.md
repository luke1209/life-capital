# Life Capital Scripts

此目錄包含 Life Capital 專案的輔助腳本。

## init_seed_data.py

初始化 `~/.life-capital/` 的 seed 資料，用於快速建立開發/測試環境。

### 用途

- 快速建立完整的測試資料集（7 個月）
- 驗證資料管道與計算邏輯
- 支援不同月份的自訂資料生成
- 遵守 CLAUDE.md 護欄規則

### 使用方式

#### 基本用法（建立完整資料集）

```bash
# 使用預設路徑 ~/.life-capital/，建立 7 個月完整資料
python3 scripts/init_seed_data.py

# 或使用 uv（推薦）
uv run scripts/init_seed_data.py
```

#### 自訂月份

```bash
# 建立 3 個月的資料
uv run scripts/init_seed_data.py --months 3

# 建立 12 個月的資料
uv run scripts/init_seed_data.py --months 12 --path ./custom_data_dir
```

#### 建立最小資料集

```bash
# 僅建立 1 個月（2024-12），用於快速測試
uv run scripts/init_seed_data.py --minimal
```

#### 自訂資料目錄

```bash
# 使用自訂路徑而不是 ~/.life-capital/
uv run scripts/init_seed_data.py --path /tmp/my_data --months 5

# 使用相對路徑
uv run scripts/init_seed_data.py --path ./test_data --months 3
```

#### 強制覆寫

```bash
# 若資料目錄已存在，使用 --force 強制覆寫
uv run scripts/init_seed_data.py --path ./data --force
```

### 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--path PATH` | 資料目錄路徑 | `~/.life-capital/` |
| `--months MONTHS` | 月份數量（1-12） | 7 |
| `--minimal` | 建立最小資料集（1 個月） | 否 |
| `--force` | 強制覆寫既有資料 | 否 |

### 輸出

腳本成功執行後會：

1. **建立目錄結構**:
   - `canonical/`: 正規化資料（4 個設定檔）
   - `canonical/expenses/`: 月度支出 CSV 檔案
   - `raw/imports/`: 原始匯入資料（帶 Provenance）
   - `derived/`: 計算結果（由 `lc rebuild` 生成）

2. **顯示統計資訊**:
   ```
   📊 資料統計:
      設定檔: 4
         • expense_policy.yaml
         • life_assumptions.yaml
         • lifetime_targets.yaml
         • monthly_income.yaml
      月度支出: 7
         • expenses_2024_06.csv
         • expenses_2024_07.csv
         ...
   ```

3. **提示後續步驟**:
   ```
   💡 後續步驟:
      1. 驗證資料: lc doctor --path ...
      2. 執行測試: uv run pytest tests/
      3. 查看說明: lc --help
   ```

### 生成的資料範例

#### 配置檔案

- **life_assumptions.yaml**: 生活假設（通膨率、投資報酬率等）
- **monthly_income.yaml**: 月收入（Person A 85K + Person B 55K）
- **expense_policy.yaml**: 支出政策（10 個分類）
- **lifetime_targets.yaml**: 人生目標（4 個目標）

#### 月度支出數據

每月包含約 10-13 筆交易：

- **必要支出**: 住房、食品、運輸、公用事業
- **選擇性支出**: 娛樂、外出用餐、購物
- **儲蓄投資**: 儲蓄、投資、保險

**特殊月份**:
- **7 月**: 新增 8K 暑假旅遊
- **12 月**: 新增 39K 保險費 + 5K 聖誕禮物 - 500 退款

#### 支付者區分

交易記錄支付者：
- `person_a`: Person A 個人支出
- `person_b`: Person B 個人支出
- `shared`: 夫妻共同支出

### 資料驗證

建立資料後，執行：

```bash
# 驗證資料完整性與一致性
lc doctor --path ~/.life-capital

# 執行單元測試
uv run pytest tests/

# 執行特定測試
uv run pytest tests/test_seed_data.py -v
```

### 常見問題

#### Q: 為什麼資料目錄已存在時失敗？

A: 腳本預設不覆寫既有資料以避免意外損失。使用 `--force` 強制覆寫：

```bash
uv run scripts/init_seed_data.py --force
```

#### Q: 如何建立不同時間範圍的資料？

A: 目前腳本從 2024-06 開始生成，可通過 `--months` 控制長度：

```bash
# 建立 2024-06 ~ 2024-08（3 個月）
uv run scripts/init_seed_data.py --months 3

# 建立 2024-12 ~ 2024-12（1 個月）
uv run scripts/init_seed_data.py --minimal
```

#### Q: 為什麼某些檔案是 read-only？

A: 按照 CLAUDE.md 護欄規則，`raw/` 目錄中的檔案設為 `chmod 444` 以防止意外修改。

### 實作細節

腳本基於 `SeedDataBuilder` 類（`tests/fixtures/seed_data.py`），遵守：

1. **CLAUDE.md 護欄**:
   - 所有寫入操作通過受控入口
   - 追蹤 operation log
   - Decimal 強制用於財務計算

2. **資料完整性**:
   - 所有 YAML 檔案包含 `schema_version`
   - CSV 檔案包含標準欄位（date, amount, category, payer）
   - raw 檔案包含 Provenance 註解

3. **可重建性**:
   - `derived/` 資料可從 `raw/ + canonical/` 完全重建
   - 支援 `lc rebuild` 驗證一致性

### 相關檔案

- 資料模型: `life_capital/models/`
- 資料 I/O: `life_capital/io/`
- 測試資料: `tests/fixtures/seed_data.py`
- 專案護欄: `CLAUDE.md`

---

## verify_seed_data.py

驗證 seed 資料的結構、hash、counts、事件鏈與 redaction 規則。

### 用途

- 驗證 seed 資料結構完整性
- 檢查檔案 hash 一致性（防止 seed 漂移）
- 驗證 staging 狀態分佈與 advisor 事件鏈
- 檢測文字檔 BOM/CRLF 問題
- 驗證 redaction 規則正確性

### 使用方式

#### 基本驗證

```bash
# 驗證預設路徑 ./data/seed
python scripts/verify_seed_data.py

# 或使用 uv（推薦）
uv run scripts/verify_seed_data.py
```

#### JSON 報告輸出

```bash
# 輸出 JSON 格式報告
uv run scripts/verify_seed_data.py --report json
# 輸出: {"ok": true, "errors": []}
```

#### 更新 Lock 檔案

```bash
# 更新 seed_lock.json（檔案 hash 快照）
uv run scripts/verify_seed_data.py --update-lock
```

#### 顯示 Hash 差異

```bash
# 顯示 hash 不一致的檔案與內容預覽
uv run scripts/verify_seed_data.py --diff
```

#### 自訂資料路徑

```bash
# 驗證指定路徑
uv run scripts/verify_seed_data.py --path /custom/seed/path
```

### 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--path PATH` | Seed 資料路徑 | `./data/seed` |
| `--update-lock` | 更新 seed_lock.json | 否 |
| `--report FORMAT` | 輸出格式（json） | 文字 |
| `--diff` | 顯示 hash 不一致的詳情 | 否 |

### 驗證項目

1. **結構驗證**:
   - `seed_manifest.json` 存在
   - 必要目錄結構完整

2. **Hash 驗證**:
   - `expected_hashes`（manifest 內定義）
   - `seed_lock.json`（所有檔案 hash）

3. **Counts 驗證**:
   - staging 狀態分佈（pending/parsed/approved/error/duplicate）
   - advisor proposals、decisions、audit_actions 數量

4. **不變量驗證**:
   - approved entry 必須有 proposal_id
   - duplicate entry 必須有 duplicate_of 參照
   - proposal 檔案必須存在

5. **事件鏈驗證**:
   - Phase 5 advisor chain（suggest → apply → undo）
   - 負向測試案例（duplicate_operation_id）

6. **Redaction 驗證**:
   - 禁止欄位遮蔽（email、phone_number）
   - 組合推論違規偵測

7. **文字格式驗證**:
   - 無 BOM
   - 無 CRLF

### 輸出範例

#### 成功

```
seed verify ok
```

#### 失敗

```
seed verify failed:
- hash mismatch: staging/entries.jsonl
- staging count mismatch: approved
```

#### JSON 報告

```json
{
  "ok": true,
  "errors": []
}
```

### 典型工作流程

```bash
# 1. 生成 seed 資料
uv run scripts/init_seed_data.py --path ./data/seed --phase all

# 2. 驗證 seed 資料
uv run scripts/verify_seed_data.py --path ./data/seed

# 3. 更新 lock 檔案（若 hash 變更是預期的）
uv run scripts/verify_seed_data.py --path ./data/seed --update-lock

# 4. 輸出 JSON 報告（CI 整合）
uv run scripts/verify_seed_data.py --path ./data/seed --report json
```

### 相關檔案

- Seed 初始化: `scripts/init_seed_data.py`
- Seed Manifest: `data/seed/seed_manifest.json`
- Seed Lock: `data/seed/seed_lock.json`
- Seed 計劃: `docs/plans/seed-data/plan.md`
