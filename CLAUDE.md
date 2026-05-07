# Life Capital - Claude Code 執行規範

<!-- 供 Claude Code CLI 讀取；用戶指南見 README.md -->

## 專案入口

| 項目 | 值 |
|------|-----|
| Entrypoint | `lc` (Typer CLI) |
| 資料目錄 | `~/.life-capital/` 或 `--path` 指定 |
| 測試 | `uv run pytest tests/` |
| 驗證 | `lc validate --path ./data` |
| 健檢 | `lc doctor --path ./data` |
| 版本常數 | `io/registry.py` |

## 護欄規則（必須遵守）

> 標記 `[doctor]` 為機器可驗證項目，由 `lc doctor` 自動檢查

### 1. 寫入邊界 `[doctor]`

| 層級 | 允許寫入者 | 追蹤 |
|------|-----------|------|
| `raw/` | 無（chmod 444，只能新增） | Provenance 完整版 |
| `canonical/` | 只有 `lc apply` | `operation_id` |
| `canonical/decisions/` | 只有 `lc apply/undo`，append-only | `operation_id` |
| `derived/` | `calculators/` 與 `commands/` | `provenance_lite` |
| `derived/advisor/` | 只有 `AdvisorDerivedHandler.write_with_provenance()` | AdvisorDerivedProvenance |
| `proposals/` | AI/用戶可寫 | 無（待 `--confirm` 審核） |

### 2. 不可逆操作護欄

修改 `canonical/` 前必須：
1. 先執行 `lc validate`
2. 使用 `--confirm` 或 `--yes` 確認
3. 操作前自動記錄可回滾資訊

批次遷移/重算必須先 dry-run。

### 3. Decimal 強制 `[doctor]`

```
外部輸入 → to_decimal() → calculators 內部計算 → quantize() → 輸出
```

- `calculators/` 內部只能用 `Decimal`，禁止 `float`
- 四捨五入策略：`ROUND_HALF_UP`（固定）
- 貨幣精度：`scale=0`（元）或 `scale=2`（角分）

### 4. Schema 版本一致 `[doctor]`

所有 YAML 的 `schema_version` 必須等於 `CURRENT_SCHEMA_VERSION`（見 `io/registry.py`）。
不一致時拒絕操作，提示執行 migration。

### 5. Derived 可重建 `[doctor]`

`lc rebuild` 必須能從 `raw/` + `canonical/` 100% 重建 `derived/`。
重建後 hash 不一致 → derived 有手動修改，需人工確認。

### 6. Advisor 衍生物護欄

- 輸出位置：只能在 `derived/advisor/`
- 副檔名白名單：`.md`, `.json`, `.meta.json`
- 每個輸出必須有 sidecar `.meta.json`（含 `artifact_type`, `canonicalization_version`, `input_hash`, `rebuild_command`）

### 7. 可評估性判定

`comparability_score < 0.6` 時，跳過風險/敏感度評估，返回 `None`。

## 禁止事項

| # | 禁止 | 正確做法 |
|---|------|----------|
| 1 | 繞過 `lc apply` 直接修改 `canonical/` | `proposals/` → `lc apply` |
| 2 | 手動修改 `derived/` 後當真相 | `lc rebuild` 重建 |
| 3 | `float` 進入 `calculators/` | `to_decimal()` 轉換 |
| 4 | Hardcode 檔名或路徑 | 使用 `io/registry.py` 常數 |
| 5 | 直接 `open()` 寫入 YAML | `yaml_handler.save_yaml()` |
| 6 | 跳過 validate 直接 apply | 先 `lc validate` |
| 7 | 覆寫 `raw/` 已存在的檔案 | raw 不可變，只能新增 |
| 8 | 無備份/dry-run 的批次遷移 | 先備份，後執行 |
| 9 | 直接修改 `canonical/decisions/` 記錄 | `lc undo` 建立 `reverted` 記錄 |
| 10 | 繞過 `AdvisorDerivedHandler` 寫入 `derived/advisor/` | `write_with_provenance()` |

## 失敗處理

| 情境 | 處理方式 |
|------|----------|
| validate 失敗 | 停止操作，不修改任何檔案 |
| apply 失敗 | `lc undo --latest` 回滾 |
| 遷移失敗 | 還原最近備份，執行 `lc rebuild` |

## 執行任何變更前

```bash
lc validate --path ./data
uv run pytest tests/ -x
```

## 參考資料

- 用戶指南：`README.md`
- 開發流程：`docs/DEVELOPMENT.md`
- V2.5 規劃：`docs/roadmap/V2.5.md`
