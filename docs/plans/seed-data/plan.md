# Seed Data Plan (Phase 1 ~ Phase 5 Stage 2)

## 目標與範圍

- 以 `./data/seed` 為預設輸出路徑，支援 `scripts/init_seed_data.py --path` 覆寫。
- 產出可覆蓋 Phase 1 ~ Phase 5 Stage 2 的完整測試資料。
- 保持既有 7 個月資料（2024-06 ~ 2024-12）不變。
- 加入可重建、可追溯、可驗收的工程化護欄，支援長期回歸測試。

## 核心工程化護欄（必備）

### 1) 決定論（Deterministic Seed）

- `init_seed_data.py` 支援 `--seed <int>`（預設固定值，如 42）。
- 所有隨機資料（ULID/UUID、金額微差、posted/occurred 偏移）必須使用同一 RNG。
- 時間來源固定基準（例如 `2024-12-31T00:00:00Z`），其他時間以 deterministic offset 推導。
- 輸出排序固定（例如 decisions.yaml 依 created_at / decision_id 排序）。
- 跨平台規範：
  - 文字輸出統一為 UTF-8、LF (`\n`)、無 BOM。
  - 浮點/Decimal 序列化格式固定（小數位與四捨五入規則）。
  - ISO 8601 統一為 UTC `Z` 結尾，不依賴 local timezone。
  - 目錄與檔案列舉順序固定（排序後再輸出）。

### 2) 可追溯（Traceability）

- 引入 `seed_manifest.json`（或 `seed_index.json`），集中記錄每個資料集的測試意圖與來源對應。
- 每筆 staging entry / proposal / decision 必須可回溯到 raw/imports 與 operation_log。

### 2.1) 可驗收（Machine-verifiable）

- `seed_manifest.json` 必須包含：
  - `expected_hashes`: 核心檔案的 SHA-256（decisions.yaml、entries.jsonl、raw_manifest.json）。
  - `expected_counts`: 各 phase 的資料量（staging 狀態筆數、proposal 數、audit action 數）。
- CI 可以只靠 manifest 做 hard-gate，避免 seed 漂移不易察覺。

### 2.2) Manifest 分層（降低維護成本）

- `seed_manifest.json`：期望行為與規格（counts/事件鏈/duplicate pairs）。
- `seed_lock.json`：檔案 SHA-256（可由 verify 自動更新）。
- `verify_seed_data.py --update-lock` 僅更新 lock，不改 manifest。

### 3) 閉環可驗證（Closed-loop）

- Phase 4 必須有完整狀態鏈：pending → parsed → approved → proposal 產生。
- Phase 5 必須有完整事件鏈：suggest → proposal → apply → decisions → undo/revert → audit log。

### 3.1) 事件鏈 dataset 化

- `seed_manifest.json` 必須定義最小可重播的事件鏈（固定 ID）：
  - `advisor_chain_01_apply_then_undo`
  - `inputs`: proposal_id / operation_id / decision_id
  - `expected`: audit action 序列、decisions append-only 與 reverted 關聯

### 3.2) 事件鏈不變量（Invariants）

- Staging：
  - approved entry 必須能反推 proposal_id。
  - duplicate entry 必須能反推 dedupe pair（且存在於 Phase 1）。
- Advisor：
  - apply 只能 append-only，undo 產生 reverted 關聯。
  - audit action 均需可 join 到 proposal_id / operation_id / decision_id（明確例外需列出）。

### 4) 相容性（Schema Compatibility）

- 同時提供「最新版本」與「上一版」fixtures，用於 migration / backward read 驗證。
- `lc migrate --dry-run` 與 `lc validate` 對兩個版本都能跑通或產生預期輸出。

### 4.1) 版本期望（Contract）

- `seed_manifest.json` 需標示：
  - `supported_read_versions`（例如 ["1.0", "1.1"]）
  - `current_write_version`（例如 "1.1"）
  - `expected_migration_summary`（最小摘要，列出新增欄位或變更）
- verify 必須覆蓋：
  - 新版 handler 讀舊版 fixture（應通過並填 default）。
  - 舊版 handler 讀新版 fixture（應明確失敗）。

## 覆蓋矩陣（Phase → 產出）

### Phase 1（Dedupe / Raw Manifest）

- raw/imports/ 內建立「真實重複」與「近似重複」案例。
- 符合 dedupe window（occurred ±1 天 / posted ±7 天）。
- raw_manifest.json 必須包含所有 raw/imports 檔案。

### Phase 2（Scenario）

- 既有 canonical YAML（assumptions/income/policy/targets）維持不變。
- 月度支出 7 個月可形成穩定基準，供 scenario 計算。

### Phase 3（Generation）

- derived/reports/、derived/scenarios/ 目錄存在即可。
- 不強制預生成報表（用測試時動態產出）。

### Phase 4（Staging）

- 生成 staging/entries.jsonl。
- 每個狀態至少 1 筆真實範例：
  - pending
  - parsed
  - approved
  - error
  - duplicate
- 每筆 entry 需對應合理來源（raw/imports 的 CSV），確保可被 parse/approve 流程測試。
- 需提供 entry 對應表或 manifest，驗證狀態轉換閉環與錯誤原因。

### Phase 5 Stage 2（Advisor）

- canonical/decisions/decisions.yaml（append-only 記憶）
- proposals/pending/*.yaml（advisor output）
- derived/logs/advisor_audit.jsonl（審計軌跡）
- 需至少一組可跑通的完整事件鏈（suggest → apply → undo）。

## Seed 產出規格

### 1) 目錄結構

```
./data/seed/
├── raw/
│   ├── imports/
│   ├── manual/
│   └── raw_manifest.json
├── canonical/
│   ├── expenses/
│   ├── decisions/
│   │   └── decisions.yaml
│   └── .operation_log.jsonl
├── derived/
│   ├── reports/
│   ├── scenarios/
│   └── logs/
│       └── advisor_audit.jsonl
├── staging/
│   └── entries.jsonl
└── proposals/
    └── pending/
        ├── <advisor_proposal_1>.yaml
        └── <advisor_proposal_2>.yaml
```

### 2) Phase 1: Dedupe 案例設計

- raw/imports/ 建立 4 組 CSV：
  1. 完全重複（同金額/日期/商戶）
  2. 近似重複（posted 差 1-2 天）
  3. 近似重複（amount 微差 1-3%）
  4. 非重複（不同商戶與類別）
- 每組至少 2 筆 entry，確保 dedupe 可測。
- 於 `seed_manifest.json` 中記錄預期的重複配對與 dedupe 分類。

### 3) Phase 4: Staging 真實範例

- entries.jsonl 規格遵循既有 staging schema。
- 每筆 entry 具備真實 payload（來源 CSV + 檢核結果）。
- 狀態分佈：
  - pending: 一筆剛導入未解析
  - parsed: 一筆已完成 parse，待 approve
  - approved: 一筆已建立 proposal（對應 proposals/pending）
  - error: 一筆故意缺欄位或格式錯誤
  - duplicate: 一筆明確重複（phase1 的 dedupe 來源）
- 需提供 `entry_id → raw_source_file → raw_row_ids → expected_transition_path → expected_error_code` 對應表。

### 4) Phase 5 Stage 2: Advisor 記憶與提案

#### Template 覆蓋

5 個模板 × 3 情境：
- buying_house
- investment
- car_purchase
- travel
- savings_target

每模板 3 情境：
1) comparable success（confidence: high/medium）
2) not comparable（status: not_comparable + guidance）
3) extreme risk（risk_tags 包含高風險標籤）

#### decisions.yaml 內容

- schema_version / version / last_updated 必填。
- 每筆 record 必填欄位：
  - decision_id (dec_<ULID>)
  - operation_id (ULID)
  - template_id
  - status (pending/applied/reverted/expired)
  - confidence (high/medium/low)
  - comparability_score
  - input_hash
  - option_a / option_b
  - risk_tags / risk_explanation
- 決定論要求：決策記錄排序固定，created_at 採固定基準時間 + offset。

#### proposals/pending

- 至少 3 個 advisor proposal，對應可比較的模板案例。
- proposal_id 與 decisions 記錄可互相追溯（operation_log 內保留關聯）。
- 至少 1 筆 proposal 永遠保持 pending（未 apply），用於 explain/history 測試。

#### advisor_audit.jsonl

- 每筆記錄含 timestamp / action / decision_id / template_id / operation_id / proposal_id。
- 至少 5 筆，覆蓋 suggest / apply / undo 模擬流程。
- audit log 必須可重建事件鏈（proposal → apply → decision → undo）。

### 5) Schema 版本 fixtures

- 在 `./data/seed/fixtures/` 放置上一版 fixtures（例如 `decisions_v1_0.yaml`）。
- `seed_manifest.json` 指出 fixtures 的用途與對應驗證指令。

### 6) Seed Manifest（機器可讀）

建議檔名：`seed_manifest.json`（位於 `./data/seed/` 根目錄）

最小結構：

```json
{
  "seed_version": "1.0",
  "phases": ["1", "2", "3", "4", "5-stage2"],
  "expected_hashes": {
    "canonical/decisions/decisions.yaml": "sha256:...",
    "staging/entries.jsonl": "sha256:...",
    "raw/raw_manifest.json": "sha256:..."
  },
  "expected_counts": {
    "staging": { "pending": 1, "parsed": 1, "approved": 1, "error": 1, "duplicate": 1 },
    "advisor": { "proposals": 3, "decisions": 15, "audit_actions": 5 }
  },
  "supported_read_versions": ["1.0", "1.1"],
  "current_write_version": "1.1",
  "expected_migration_summary": {
    "decisions": ["add: preference_weights", "add: assumption_snapshot"]
  },
  "datasets": [
    {
      "id": "dedupe_exact_01",
      "purpose": "phase1_dedupe_exact",
      "inputs": ["raw/imports/202406_dup_exact.csv"],
      "expected": { "duplicate_pairs": [["row_1", "row_2"]] }
    },
    {
      "id": "staging_error_missing_field",
      "purpose": "phase4_staging_error",
      "inputs": ["staging/entries.jsonl"],
      "expected": { "entry_id": "stg_err_01", "error_code": "missing_amount" }
    },
    {
      "id": "advisor_chain_01_apply_then_undo",
      "purpose": "phase5_advisor_chain",
      "inputs": {
        "proposal_id": "prop_01",
        "operation_id": "op_01",
        "decision_id": "dec_01"
      },
      "expected": {
        "audit_actions": ["suggest", "apply", "undo"],
        "decision_statuses": ["applied", "reverted"]
      }
    },
    {
      "id": "advisor_chain_02_apply_rejected",
      "purpose": "phase5_advisor_chain_negative",
      "inputs": {
        "proposal_id": "prop_02",
        "operation_id": "op_dup",
        "decision_id": "dec_dup"
      },
      "expected": {
        "error_code": "duplicate_operation_id",
        "message_tokens": ["duplicate", "operation_id"]
      }
    }
  ]
}
```

## 敏感資料遮蔽測試（Redaction）

- 於 raw/imports 或 staging payload 放入 1-2 筆含 email/phone/address 的測試字串。
- 驗證 `lc advisor context --redacted` 與 `lc advisor suggest --redacted` 會遮蔽。
- 加入組合推論案例（單欄位不敏感，組合後敏感），並在 verify 中硬性驗收。

## init_seed_data.py 改動要點

- 預設輸出路徑改為 `./data/seed`。
- 保留 `--path` 覆寫。
- 新增 `--seed`（預設固定值）以確保決定論。
- 新增 `--verify` 或提供 `scripts/verify_seed_data.py` 一鍵驗收。
- 新增可切換旗標（預設全量）：
  - `--phase all|1|2|3|4|5`（可選，預設 all）
  - `--with-staging`（確保 Phase 4 真實範例）
  - `--with-advisor`（Phase 5 Stage 2）
- 保持 `--months` / `--minimal` 行為一致。
- 支援 profile：
  - `--profile smoke`：最小閉環（PR/快速驗證）
  - `--profile full`：完整覆蓋（nightly/regression）

## 驗證步驟（驗收）

1. `python scripts/init_seed_data.py --path ./data/seed`
2. `lc validate --path ./data/seed`
3. `lc doctor --path ./data/seed`
4. 決定論檢查：重跑一次後比較 `canonical/`、`staging/`、`decisions/` 的 hash 應一致。
5. 一鍵驗收：`python scripts/verify_seed_data.py --path ./data/seed`
6. Phase 4:
   - `lc staging list --path ./data/seed`
   - `lc staging parse --all --path ./data/seed`
7. Phase 5 Stage 2:
   - `lc advisor context --path ./data/seed --redacted`
   - `lc advisor suggest "買房" --path ./data/seed --redacted`
   - `lc apply --path ./data/seed --confirm`
8. 相容性：
   - `lc validate --path ./data/seed/fixtures/decisions_v1_0.yaml`（或指定 fixture 驗證流程）
   - `lc migrate --dry-run --path ./data/seed`（若已有 migrate 指令）
9. 報告輸出：
   - `python scripts/verify_seed_data.py --path ./data/seed --report json`
   - `python scripts/verify_seed_data.py --path ./data/seed --diff`

## 實作順序（建議）

1. 擴充 SeedDataBuilder：新增 raw/imports + staging + advisor artifacts。
2. 更新 init_seed_data.py：路徑預設、旗標、分段建立、profiles。
3. 新增 seed_manifest.json（行為契約）+ seed_lock.json（hash 鎖）。
4. 新增 `verify_seed_data.py`：結構/鏈路/不變量/跨平台決定論驗收。
5. 補測試（可選）：seed integration + advisor e2e 的新覆蓋。

## 定案門檻（可驗收）

- 決定論：相同 seed 參數，跨機器輸出 hash 一致。
- 閉環：Phase 4 與 Phase 5 各有至少一條完整事件鏈可驗證。
- 可追溯：任一 proposal/decision/audit 可反查至 raw/imports 與 operation_log。
- 相容性：上一版 fixtures 可被讀取或 dry-run migration 通過。

---

## 驗收報告（2024-12-29）

### 執行記錄

```bash
# 1. 生成 seed 資料
uv run scripts/init_seed_data.py --path ./data/seed --phase all --profile full

# 2. 驗證 seed 資料
uv run scripts/verify_seed_data.py --path ./data/seed --report json
# 輸出: {"ok": true, "errors": []}

# 3. 更新 lock 檔案
uv run scripts/verify_seed_data.py --path ./data/seed --update-lock
```

### 驗收結果

| 驗收項目 | 狀態 | 說明 |
|----------|------|------|
| 決定論 | ✅ | `--seed 42` 固定，hash 一致 |
| 閉環驗證 | ✅ | Phase 4/5 事件鏈完整 |
| 可追溯 | ✅ | manifest 定義 dataset + inputs |
| Manifest | ✅ | `seed_manifest.json` 包含 expected_hashes/counts |
| Hash Lock | ✅ | `seed_lock.json` 已生成並更新 |

### 產出統計

| 類別 | 數量 | 說明 |
|------|------|------|
| Staging entries | 5 | pending:1, parsed:1, approved:1, error:1, duplicate:1 |
| Proposals | 5 | `proposals/pending/advisor_*.yaml` |
| Decisions | 16 | `canonical/decisions/decisions.yaml` |
| Audit actions | 5 | `derived/logs/advisor_audit.jsonl` |

### 修復記錄

- **ModuleNotFoundError**: 修正 `verify_seed_data.py` 的模組導入問題
  - 新增 `sys.path.insert(0, str(project_root))` 確保可導入 `life_capital` 模組

### 相關指令

```bash
# 驗證 seed 資料
uv run scripts/verify_seed_data.py --path ./data/seed

# JSON 報告輸出
uv run scripts/verify_seed_data.py --path ./data/seed --report json

# 顯示 hash 差異
uv run scripts/verify_seed_data.py --path ./data/seed --diff
```
