# Phase 5 Stage 3 - V1-V4 審查歷程

<!-- 歷史文件：Codex #1 → Codex #2 → 專業審查 -->
<!-- 主規劃文件: ../plan.md -->

本文件記錄 Stage 3 規劃的審查迭代歷程，從 V1 初版至 V4 專業審查。

---

## 1. V1 初版任務（E1-E6）

| # | 任務 | 模組 | 複雜度 |
|---|------|------|--------|
| E1 | Memory 完整模型 | `models/decisions.py` + `io/decisions_handler.py` | MED |
| E2 | 決策 Wiki 編譯器 | `generation/decision_wiki.py` | MED |
| E3 | 風險評估模組 | `generation/risk_matrix.py` + `advisor/risk_assessor.py` | HIGH |
| E4 | 敏感度分析 | `generation/sensitivity_report.py` + `advisor/sensitivity_analyzer.py` | HIGH |
| E5 | 歷史查詢 CLI | `commands/advisor_cmd.py` extensions | MED |
| E6 | 文件與驗收 | `docs/advisor/` + `io_contract.md` | LOW |

---

## 2. Codex #1 Review 結果

### 2.1 識別的 3 個結構性問題

| # | 問題 | 影響 | 修正方案 |
|---|------|------|----------|
| **P1** | E2 生成位置違反 Phase 3 契約 | 違反「generation/ 只讀 derived」規則 | 改為 `life_capital/advisor/decision_wiki.py`，定義新 derived 子契約 |
| **P2** | DecisionRecord 欄位擴展未同步 | round-trip 資料遺失（read → write 丟欄位） | E1 必須同步更新 `decisions_handler.py` 的 parse/serialize |
| **P3** | rollback_count 與 append-only 不相容 | 無法正確計算回滾次數（缺乏 decision_id 關聯） | 新增 `reverted_from_decision_id` + 改為查詢時動態計算 |

### 2.2 識別的 5 個邊緣情境

| # | 情境 | 說明 |
|---|------|------|
| **EC1** | 空檔/缺失 decisions.yaml | history/wiki/explain 需容錯 |
| **EC2** | 時間排序一致性 | `created_at` 須明確排序策略（時間或 ULID） |
| **EC3** | 回滾鏈追蹤 | history 需顯示 reverted 關聯 |
| **EC4** | 非可比決策邊界 | E3/E4 演算法需明確「不可比是否可評估」 |
| **EC5** | 隱私與衍生文件 | Wiki 的 decision_rationale 需符合 redaction 規則 |

### 2.3 建議的改善方向

1. **版本管理升級**: 新增 `DECISIONS_SCHEMA_VERSION` / `ADVISOR_SCHEMA_VERSION` 版本常數
2. **欄位增補流程**: E1 修改 → schema 版本升級 → handler 同步 → 測試更新
3. **輸出契約明確化**: E3/E4 定義輸出格式、位置、provenance 與重建邊界
4. **CLI 狀態過濾**: history/explain 預設顯示 applied+pending，reverted 用「事件流」區塊
5. **族群化建議**: 一般用戶（摘要+風險標籤）、進階用戶（--format json/csv）、稽核者（完整 lineage）

---

## 3. V2 計劃（基於 Codex #1）

### 3.1 E1 Memory 完整模型（優先修正 P2）

**關鍵文件**:
- `life_capital/models/decisions.py` - 新增欄位 + round-trip 驗證
- `life_capital/io/decisions_handler.py` - 同步 parse/serialize 邏輯
- `life_capital/io/registry.py` - 新增 DECISIONS_SCHEMA_VERSION 升級

**修正清單**:
1. 定義新欄位（decision_rationale、reverted_from_decision_id）
2. 更新 handler 的 `_parse_record()` / `_record_to_dict()`
3. 實作 YAML round-trip 驗證測試
4. 版本升級流程（schema_version 遞增）

### 3.2 E2 Wiki 編譯器（修正 P1）

**關鍵修正**:
- 位置改為 `life_capital/advisor/decision_wiki.py`（不在 generation/）
- 定義新 derived 子類型與重建契約
- 新增 provenance_lite（calc_version + input_hash + sources）

### 3.3 E3/E4 風險評估與敏感度分析（修正 P3 + EC4）

**前置契約定義**:
- 輸出格式明確化（JSON schema）
- 輸出位置（derived/decision/ 或 derived/reports/）
- 不可比決策的評估規則（通過/拒絕/部分）
- Provenance 與重建邊界

### 3.4 E5 CLI 整合（EC1-EC3 容錯）

```bash
lc advisor history [--limit 10] [--status applied|pending|reverted]
lc advisor explain <decision_id> [--format json]
lc advisor risk-matrix [--format csv|json]
lc advisor sensitivity <decision_id> [--param rate|inflation]
```

---

## 4. Codex #2 Review 結果

### 4.1 識別的 8 個進階邊緣情境

| # | 情境 | 說明 | 受影響模組 |
|---|------|------|-----------|
| **EC6** | ID 重複處理 | operation_id/decision_id 衝突時的處理策略 | E1, decisions_handler |
| **EC7** | 狀態轉換規則 | pending → applied → reverted/expired 的合法路徑 | E1, E5 |
| **EC8** | 部分可比處理 | comparability_score 0.3-0.7 的決策如何評估 | E3, E4 |
| **EC9** | 舊資料欄位缺失 | 新欄位 fallback 策略（decision_rationale 等） | E1, decisions_handler |
| **EC10** | 時間來源一致性 | ULID vs UUID fallback、created_at 格式 | E1, E2 |
| **EC11** | 跨檔快照一致性 | decisions.yaml 與 canonical 資料的讀取時機 | E3, E4 |
| **EC12** | E2/E3 輸出的 Redaction | Wiki/risk-matrix 輸出需符合 redaction 規則 | E2, E3, privacy/ |
| **EC13** | 空檔/損壞處理 | decisions.yaml 格式錯誤時的容錯與恢復 | E1, E5 |

### 4.2 E2/E3 互操作性規則（5 條）

| # | 規則 | 說明 | 實作要求 |
|---|------|------|----------|
| **IR1** | DecisionRecord 欄位協調 | E2/E3 都讀 DecisionRecord，欄位擴展需同步 | E1 完成後凍結介面 |
| **IR2** | 輸出路徑 + 重建契約 | E2/E3 定義 derived 子路徑 + rebuild 規則 | io_contract.md 更新 |
| **IR3** | Redaction 一致性 | Wiki/risk-matrix 的去識別化須使用相同規則 | 共用 privacy/redaction/ |
| **IR4** | 共享比較/風險邏輯 | 可比性判定 + 風險標籤可抽出共用模組 | advisor/shared/ 模組 |
| **IR5** | Schema 版本 + IO 契約 | 新輸出格式需定義 schema_version | registry.py 統一管理 |

### 4.3 E4 敏感度分析澄清

| 項目 | 問題 | 建議解法 |
|------|------|----------|
| 基線優先級 | assumption_snapshot vs canonical 誰優先？ | assumption_snapshot 為主，canonical 為 fallback |
| 基線版本標記 | 如何追蹤敏感度分析的基線來源？ | 新增 `baseline_version` + `baseline_hash` 欄位 |
| 輸出 KPI 定義 | 敏感度輸出需包含哪些指標？ | 定義 `SensitivityResult` schema（delta、direction、significance） |
| 微擾範圍統一 | ±5%、±10% 是否需可配置？ | 預設值 + CLI 參數覆蓋（`--perturbation 5,10,15`） |

### 4.4 版本遷移策略

| 項目 | 說明 |
|------|------|
| Schema 演進策略 | 新增欄位使用 Optional + 預設值，刪除欄位需 migration script |
| Migration 工具 | `lc migrate --from 1.0 --to 1.1` 自動升級 decisions.yaml |
| 新欄位 Parser Fallback | `_parse_record()` 對缺失欄位使用預設值，不 raise |
| 向後相容保證 | V1.0 檔案可被 V1.1 handler 讀取（反向不保證） |

---

## 5. V3 計劃（基於 Codex #2）

### 5.1 E1 Memory 完整模型（強化）

**新增需求**（來自 Codex #2）:
- EC6: 實作 ID 衝突偵測（reject duplicate operation_id）
- EC7: 定義狀態轉換 FSM（pending → applied ✓, pending → reverted ✗）
- EC9: _parse_record() fallback 策略
- EC10: 時間來源統一（ULID 內建時間戳，created_at 為冗餘備份）

### 5.2 E2 Wiki 編譯器 + E3 風險評估（協調）

**前置條件**（IR1-IR5）:
1. E1 完成後凍結 DecisionRecord 介面
2. 建立 `advisor/shared/` 模組（可比性判定 + 風險標籤）
3. 定義共用 redaction 規則（IR3）
4. 更新 io_contract.md（IR2）

---

## 6. V4 專業審查結果

### 6.1 護欄強化清單（5 項）

| # | 護欄 | 實作位置 | 驗證方式 | 優先級 |
|---|------|----------|----------|--------|
| **G1** | `lc doctor --advisor` 健康檢查 | `commands/doctor.py` | CI 整合 | HIGH |
| **G2** | `validate_transition(from, to)` 狀態驗證 | `io/decisions_handler.py` | 單元測試 | HIGH |
| **G3** | Redaction golden set | `tests/advisor/golden/` | 回歸測試 | MEDIUM |
| **G4** | `lc migrate --dry-run` 預覽 | `commands/migrate_cmd.py` | 手動驗證 | MEDIUM |
| **G5** | File lock for concurrent writes | `io/decisions_handler.py` | 壓力測試 | LOW |

### 6.2 容錯與恢復設計

| 情境 | 處理方式 | 實作位置 |
|------|----------|----------|
| 空檔/缺失 | 顯示「無決策記錄」 | CLI 層 |
| 損壞 YAML | 錯誤訊息 + 恢復建議 | decisions_handler |
| 版本降級 | 拒絕 + 明確錯誤訊息 | decisions_handler |
| 遷移失敗 | dry-run + 備份機制 | migrate_cmd |

### 6.3 可測試性建議

| 模組 | 測試策略 | 工具 |
|------|----------|------|
| E1 Memory | round-trip + fallback + property-based | pytest + hypothesis |
| E2 Wiki | snapshot 比對 + redaction 驗證 | golden output |
| E3 Risk | 邊界值 + 隨機生成 | hypothesis |
| E4 Sensitivity | 數學公式驗證 + 整合測試 | pytest |

---

## 7. 關鍵檔案修改清單（V3）

### 必須修正的核心文件

1. **models/decisions.py**
   - 新增欄位：decision_rationale (str)
   - 新增欄位：reverted_from_decision_id (Optional[str])
   - 移除：rollback_count（改為動態計算）

2. **io/decisions_handler.py**
   - 更新 `_parse_record()` 支援新欄位
   - 更新 `_record_to_dict()` 序列化新欄位
   - 新增 `count_reverts(decision_id)` 動態計算

3. **io/registry.py**
   - 新增：`DECISIONS_SCHEMA_VERSION = "1.1"`
   - 新增：`ADVISOR_SCHEMA_VERSION = "1.0"`

---

## 8. 驗收標準摘要

### V2 驗收項目（Codex #1）

| # | 驗收項目 | 狀態 |
|---|----------|------|
| V2-1 | 3 個結構性問題修正 | ✅ |
| V2-2 | 5 個邊緣情境納入 | ✅ |
| V2-3 | 版本管理升級 | ✅ |
| V2-4 | E1-E5 相依性清晰 | ✅ |

### V3 驗收項目（Codex #2）

| # | 驗收項目 | 狀態 |
|---|----------|------|
| V3-1 | 8 個進階邊緣情境納入 | ✅ |
| V3-2 | 5 個互操作性規則 | ✅ |
| V3-3 | E4 基線策略明確 | ✅ |
| V3-4 | 版本遷移策略定義 | ✅ |

### V4 驗收項目（專業審查）

| # | 驗收項目 | 狀態 |
|---|----------|------|
| V4-1 | 5 個護欄強化設計 | ✅ |
| V4-2 | 容錯與恢復設計 | ✅ |
| V4-3 | 可測試性建議 | ✅ |
| V4-4 | 最終實作順序 | ✅ |
| V4-5 | 測試數量預估 | ✅ |

---

## 相關文件

| 文件 | 說明 |
|------|------|
| [../plan.md](../plan.md) | 主規劃文件（V7 收斂版） |
| [../contracts.md](../contracts.md) | 技術契約 |
| [v5-architecture.md](./v5-architecture.md) | V5 架構優化 |
| [v6-operations.md](./v6-operations.md) | V6 可運營性優化 |
