# Phase 5 Stage 3 - 決策追蹤與 Wiki 實作規劃

<!-- 版本: V7 收斂版 | 最後更新: 2024-12 -->
<!-- 詳細技術契約: ./contracts.md -->
<!-- 歷史脈絡: ./archive/ -->

> **目標**: 實作 6 個 Stage 3 任務（決策追蹤擴展、Wiki 編譯器、風險評估、敏感度分析、CLI 整合、文件完成）
> **測試基線**: 841 tests → 985-1020 tests（+144-179）
> **定位**: V7 後不再做架構優化，只做 bugfix/安全修補/契約版本演進

---

## 1. 任務總覽

| # | 任務 | 模組 | 複雜度 | 測試數 |
|---|------|------|--------|--------|
| **基礎** | IO 契約 + 共用模組 | `io/advisor_derived_handler.py` + `advisor/shared/` | MED | 15-20 |
| E1 | Memory 完整模型 | `models/decisions.py` + `io/decisions_handler.py` | MED | 20-25 |
| E2 | 決策 Wiki 編譯器 | `generation/decision_wiki.py` | MED | 18-22 |
| E3 | 風險評估模組 | `generation/risk_matrix.py` + `advisor/risk_assessor.py` | HIGH | 22-26 |
| E4 | 敏感度分析 | `generation/sensitivity_report.py` + `advisor/sensitivity_analyzer.py` | HIGH | 28-32 |
| E5 | 歷史查詢 CLI | `commands/advisor_cmd.py` extensions | MED | 15-18 |
| E6 | 文件與驗收 | `docs/advisor/` + `io_contract.md` | LOW | 8-10 |

### 相依性

```
基礎設施（IO 契約 + shared/evaluability + migration fixtures）
  ↓
E1 (Memory 擴展 + handler 同步 + 狀態轉換)
  ↓
E2 + E3 [平行：共用 AdvisorDerivedHandler + evaluability]
  ↓
E4 (敏感度分析，使用 shared/evaluability)
  ↓
E5 (CLI 整合，--format/--verbose/--audit)
  ↓
E6 (文件與驗收，io_contract.md 更新)
```

---

## 2. V7 收斂範圍

### 2.1 優化項目分級

| 級別 | 項目 | 決策 |
|------|------|------|
| **必做** | Canonicalization 契約化 + 3 Goldens | ✅ hash 漂移防護 |
| **必做** | Doctor 結構化輸出 + exit codes | ✅ CI 護欄關鍵 |
| **必做** | 路徑安全 + 結構化 RebuildCommand | ✅ 安全邊界 |
| **應做** | Reconcile/Repair | ⏸️ 最小化：3 狀態 |
| **應做** | Retention Policy | ⏸️ 只做 `cleanup --keep-latest N` |
| **延後** | 共用序列化層 | ❌ Post-Stage3 |

### 2.2 最小範圍 (M1-M4)

| ID | 範圍 | 說明 | 狀態 |
|----|------|------|------|
| **V7-M1** | Canonicalization Normative + 3 goldens | 含 version 入 provenance | 必做 |
| **V7-M2** | `lc doctor --advisor --format json` + exit codes | 0/1/2/3 | 必做 |
| **V7-M3** | Path validation + RebuildCommand 結構化 | 安全邊界 | 必做 |
| **V7-M4** | `cleanup --keep-latest N` | 只做一個策略 | 可選 |

### 2.3 延後項目（Post-Stage3）

- 完整 Reconcile（CORRUPTED_META 自動修復）
- superseded_by 全鏈追蹤
- 共用序列化層 `outputs.py`

---

## 3. 實作順序（6 個 Phase）

### Phase 1: 基礎設施（V7-M1 + M3）
- [ ] 更新 `io_contract.md`（Canonicalization Normative 規格）
- [ ] 建立 canonicalization goldens（3 份 fixture）
- [ ] 更新 `AdvisorDerivedProvenance`（+canonicalization_version）
- [ ] 實作 `RebuildCommand` 結構化（安全邊界）
- [ ] 實作路徑安全驗證（traversal 防護）
- [ ] 測試：goldens + 安全邊界（8-12 tests）

### Phase 2: E1 Memory 完整模型
- [ ] 新增欄位（decision_rationale, reverted_from_decision_id）
- [ ] handler 同步（parse/serialize）
- [ ] 實作 ID 重複檢查 + 狀態轉換驗證
- [ ] 實作 fallback 策略
- [ ] 測試：round-trip + 跨版本 fixtures（20-25 tests）

### Phase 3: E2 + E3（平行開發）
- [ ] E2: `generation/decision_wiki.py`
- [ ] E3: `generation/risk_matrix.py` + `advisor/risk_assessor.py`
- [ ] 使用 `AdvisorDerivedHandler`（V6 寫入策略）
- [ ] 測試：結構 + 必含 token（18-22 + 22-26 tests）

### Phase 4: E4 敏感度分析
- [ ] `generation/sensitivity_report.py`
- [ ] `advisor/sensitivity_analyzer.py`
- [ ] 基線策略 + 微擾範圍
- [ ] 測試：不變量 + 單調性（28-32 tests）

### Phase 5: E5 CLI 整合（V7-M2 + M4）
- [ ] history/explain/risk-matrix/sensitivity 命令
- [ ] `doctor --advisor --format json`（M2）
- [ ] doctor exit codes 0/1/2/3（M2）
- [ ] `cleanup --keep-latest N`（M4，可選）
- [ ] 測試：JSON 輸出 + exit codes + cleanup（18-24 tests）

### Phase 6: E6 文件與驗收
- [ ] 更新 `docs/contracts/io_contract.md`
- [ ] 建立 `docs/advisor/stage3-design.md`
- [ ] 建立 `docs/advisor/stage3-api.md`
- [ ] 安全邊界文件化
- [ ] 最終驗收測試（8-10 tests）

---

## 4. 驗收標準

### 4.1 必做項目（M1-M3）

| # | 驗收項目 | 驗證方式 |
|---|----------|----------|
| V7-M1a | Canonicalization Normative 規格 | `io_contract.md` 更新 |
| V7-M1b | Canonicalization goldens | **3 份** fixture + 測試通過 |
| V7-M1c | `canonicalization_version` in provenance | 欄位存在 + 測試 |
| V7-M2a | `doctor --format json` | JSON 輸出測試 |
| V7-M2b | doctor exit codes | 0/1/2/3 行為測試 |
| V7-M3a | `RebuildCommand` 結構化 | 禁止字串拼接 |
| V7-M3b | 路徑安全驗證 | traversal 攻擊測試 |

### 4.2 可選項目（M4）

| # | 驗收項目 | 驗證方式 |
|---|----------|----------|
| V7-M4 | `cleanup --keep-latest N` | CLI 測試 + dry-run |

---

## 5. 測試預估

| 模組 | 測試數 | 說明 |
|------|--------|------|
| 基礎設施 | 20-26 | canonicalization goldens (3份) + security |
| E1 Memory | 20-25 | round-trip + 跨版本 |
| E2 Wiki | 18-22 | 結構 + 必含 token |
| E3 Risk | 22-26 | 邊界值 + evaluability |
| E4 Sensitivity | 28-32 | 不變量 + 單調性 |
| E5 CLI | 18-24 | doctor json + exit codes |
| E6 Docs | 8-10 | 驗收 |
| 契約測試 | 10-14 | 3 份 goldens |
| **合計** | **144-179** | |

**最終基線**: 841 tests → **985-1020 tests**

---

## 6. 關鍵決策摘要

### 已解決問題（V1-V4）
- **P1**: E2 位置 → 回歸 `generation/`，擴充契約
- **P2**: 欄位擴展未同步 → handler parse/serialize 同步
- **P3**: rollback_count 不相容 → 動態計算 + `reverted_from_decision_id`

### 邊緣情境（EC1-EC13）
- 空檔/缺失容錯
- 時間排序一致性（ULID）
- 部分可比處理（0.3-0.7）
- 跨檔快照一致性
- 隱私 redaction 規則

### 護欄設計（G1-G5）
- `lc doctor --advisor` 健康檢查
- `validate_transition()` 狀態驗證
- Redaction golden set
- `lc migrate --dry-run` 預覽
- File lock for concurrent writes

---

## 7. 相關文件

| 文件 | 說明 |
|------|------|
| [contracts.md](./contracts.md) | 技術契約（IO、Schema、Evaluability） |
| [archive/v1-v4-reviews.md](./archive/v1-v4-reviews.md) | Codex 審查歷程 |
| [archive/v5-architecture.md](./archive/v5-architecture.md) | V5 架構優化 |
| [archive/v6-operations.md](./archive/v6-operations.md) | V6 可運營性優化 |
| [../../../CLAUDE.md](../../../CLAUDE.md) | 專案護欄規則 |
| [../../contracts/io_contract.md](../../contracts/io_contract.md) | IO 契約定義 |
