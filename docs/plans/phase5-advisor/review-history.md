# Phase 5 AI 顧問系統 - 審查歷程

> **核心計劃**: 詳見 [plan.md](./plan.md)
> **用途**: 本文件記錄深度規劃過程中的審查發現與決策演進，作為設計決策的參考依據

---

## 文件說明

本文件包含 Phase 5 深度規劃（/deep-plan）過程中的：
- Codex CLI 審查結果與發現
- 專業審查輪次的優化建議
- 系統鐵則對齊記錄
- 契約可執行化設計細節

這些內容對於理解「為什麼這樣設計」很有價值，但在日常實施中不需要頻繁參考。

---

## 🚨 Codex 審查第 2 輪關鍵發現

### 5 個核心假設缺口（必須顯式解決）

1. **偏好輸入能量化且可追蹤**
   - 多目標衝突 (買房 vs 退休 vs 教育) 需明確權重
   - M2 無法自動解決多目標，需 Stage 1 定義「偏好輸入最小集」

2. **所有方案可在共同時間範圍比較**
   - 短期赤字 vs 長期盈餘需分段評分或 Pareto 前緣
   - F3 單一分數可能失真，需「時間分段框架」

3. **資料缺失可單輪補齊**
   - 現實中補件多輪反覆
   - M3 fallback 需「降級輸出策略」與「可信度標籤」

4. **隱私 redaction 不移除決策關鍵特徵**
   - redacted_dto 必須有「決策必要特徵白名單」
   - 否則隱私層會阻斷決策訊號

5. **環境變數 (利率/通膨/匯率) 有可靠來源**
   - E4 敏感度分析需定性 + 定量邊界
   - 無可靠來源時只能定性，不宜定量排序

### 12 個邊緣情況 → 5 個凍結決策

**需 Stage 1 凍結**：
- [ ] F0a: 決策記憶資料模型 (含假設版本、偏好版本、時間區間、事件標記、可信度)
- [ ] F0b: 多目標權衡策略 (權重加總 vs Pareto vs 優先級)
- [ ] F0c: redacted_dto 決策必要特徵清單（超越隱私白名單）
- [ ] F0d: 時間分段評分框架 (分段+匯總 vs 多目標並列)
- [ ] F0e: 決策 Wiki vs Memory 職責邊界（寫入時機、可變性）

---

---

## 🎯 專業審查第 3 輪（V4.0）- 最佳化與實施就緒

### 核心改善項目（V3.0 → V4.0）

#### 1. **Stage 1 流程優化：串行→並行的精確定序**

**V3.0 問題**: F0a-e 與 F1-F7 依賴關係不清，時間評估過樂觀。

**V4.0 解決方案**:

| 週期 | 任務 | 性質 | 預估 | 交付物 |
|------|------|------|------|--------|
| **W1** | F0a-e 凍結決策 | **串行（必須先完成）** | 3-4 天 | FREEZING_DECISIONS.md + schemas 骨架 |
| **W2** | F1-F9 基礎建設 | 並行（5 個並行 + 同步點） | 5-6 天 | 隔離層 + 模板框架 + 基礎測試 |
| **Gate** | F0/F8/F9 驗收 | 同期檢查點 | 1 天 | Stage 1 簽核（進/不進 Stage 2） |

**關鍵**: 若 F0a-e 延期超過 3 天 → 啟動 B 計劃（簡化多目標為「權重」方案）。

#### 2. **凍結決策驗收標準明確化**

**F0a-e 應產出的文檔與驗收清單**：

```yaml
F0a: 決策記憶資料模型
  文檔: advisor/memory_schema.py（dataclass 定義）
  文件: FREEZING_DECISIONS.md §1（假設版本、可信度設計）
  驗收:
    ✅ 包含 assumption_version, assumption_snapshot, confidence_score
    ✅ 支援多場景（買房/投資/旅遊）
    ✅ test_freezing_decisions.py 中 F0a 子集通過（6+ tests）

F0b: 多目標權衡策略選定
  文檔: advisor/FREEZING_DECISIONS.md §2（選型評分表）
  決策: 推薦「權重加總」（最簡單），備選 Pareto 與優先級
  驗收:
    ✅ 選型評分表完成（複雜度/時間/準確度三維）
    ✅ M2 規則已根據選型調整
    ✅ test_scenario_rules.py 驗證權重機制

F0c: redacted_dto 決策必要特徵清單
  文檔: interfaces/redacted_dto.py + FREEZING_DECISIONS.md §3
  特徵清單:
    ✅ 支出彙總(月度總額/類別分佈)
    ✅ 流動性指標(赤字月數/資產耗盡日期)
    ✅ 風險信號(連續虧損/波動度)
    ✅ **禁止**: 具體金額/日期/地點/職業
  驗收:
    ✅ test_redaction_structural.py 中 composition tests 通過
    ✅ 0 次組合可識別性漏洞

F0d: 時間分段評分框架決定
  文檔: advisor/comparability.py + FREEZING_DECISIONS.md §4
  實例（買房場景）:
    - T1[0-6個月]: 首付資金充足性 (短期流動性)
    - T2[6-30年]: 貸款承受力 (長期現金流)
    - T3[30-60年]: 退休累積 (終身購買力)
    - 合成評分: T1(0.3) + T2(0.5) + T3(0.2) OR Pareto 前緣
  驗收:
    ✅ comparability.py 支援 time_segments 參數
    ✅ test_comparability.py 中時間分段 tests 通過
    ✅ 與 E4 敏感度分析銜接清晰

F0e: 決策 Wiki vs Memory 職責邊界明確
  文檔: FREEZING_DECISIONS.md §5 + CLAUDE.md Phase 5 護欄
  決策:
    - Memory: 記錄「決策建議 + 用戶反應」(append-only)
    - Wiki: 編譯「決策脈絡 + 學習教訓」(生成類)
    - Snapshot 時機: lc apply 時刻（operation 記錄）
    - 回滾: lc undo 同步 Memory（版本連結）
  驗收:
    ✅ decisions.yaml 結構定義完成
    ✅ test_decision_recorder.py 驗證序列化
    ✅ lc advisor history 與 decisions.yaml 同步
```

#### 3. **決策記憶衝突解決機制完整設計**

**Snapshot 時機與回滾協調**:

```python
# lc apply 時刻：記錄決策背景
@dataclass
class DecisionSnapshot:
    decision_id: str
    operation_id: str  # 與 lc apply 綁定
    timestamp: str     # ISO 8601
    assumptions: dict  # F0a 定義的假設快照
    context: RedactedDTO  # F0c 淨化後的決策上下文
    preference_weights: dict  # F0b 多目標權重
    comparable_score: float  # F0d 時間分段評分
    confidence: ConfidenceScore

# lc undo 時刻：撤銷決策
# → Financial Memory 中標記「reverted」
# → Wiki 不刪除（保留歷史脈絡）
# → 決策版本自動遞增
```

**驗收標準**:
- ✅ test_decision_recorder.py: snapshot 序列化 (5+ tests)
- ✅ test_financial_memory.py: 版本追蹤與回滾 (6+ tests)
- ✅ M4 通過前必須驗收

#### 4. **多目標權衡決策樹與選型框架**

**F0b 選型評分表**:

| 方案 | 複雜度 | 實施週期 | 準確度 | 推薦度 |
|------|--------|---------|--------|--------|
| **權重加總** | ⭐ (簡單) | 2-3 天 | 中等(0.7) | ✅ **推薦**（Stage 1 先采此） |
| Pareto 前緣 | ⭐⭐⭐ (複雜) | 5-6 天 | 高(0.9) | 🔶 備選（若時間充足） |
| 優先級規則 | ⭐⭐ (中等) | 3-4 天 | 高(0.85) | 🟡 考慮（業務規則複雜時） |

**預設決策**: F0b 凍結「權重加總」，M2 基於此實施。若需更複雜方案→通過 feature flag 實現漸進升級。

#### 5. **時間分段評分具體實例**

**買房場景詳細設計**:

```yaml
# 場景：年收120萬，欲購房200萬，可貸150萬，月還4000
comparability_framework:
  time_segments:
    - name: "首付階段"
      duration: "0-6個月"
      metrics:
        - 可用現金 vs 首付需求 (50萬)
        - 緊急備金充足性 (3個月開銷)
      threshold: 0.7  # 必須>70%才能比較

    - name: "貸款期"
      duration: "6個月-30年"
      metrics:
        - 月現金流 vs 月還款額 (4000元)
        - 利率風險承受度 (6%-8%)
      threshold: 0.6

    - name: "退休累積"
      duration: "30年-60年"
      metrics:
        - 資產淨值增長 (房產+儲蓄)
        - 終身購買力 (與退休規劃對標)
      threshold: 0.5

  final_score:
    # T1(首付):0.3 + T2(貸款):0.5 + T3(退休):0.2
    formula: "weighted_average"
    weights: {T1: 0.3, T2: 0.5, T3: 0.2}
    comparable_threshold: 0.6  # 總分>60%才輸出建議
```

**與 E4 敏感度分析銜接**:
- E4 輸入: F0d 定義的三個時段 + 權重
- E4 輸出: 「若利率+1% → T2 評分下降 15% → 總分 0.6→0.56」

#### 6. **里程碑監控點與應急計劃**

**實施過程中的關鍵檢查點**:

```yaml
Day 3 (W1 末):
  ✅ 檢查: F0a-e 凍結文檔是否 70% 完成
  ❌ 若延期>1天: 啟動 B 計劃（簡化 F0b 為「權重」）
  執行: 決策會議（30 分鐘）

Day 7 (W2 末):
  ✅ 檢查: F1-F9 基礎建設是否 80% 完成
  ❌ 若延期>2天: 重新估算 Stage 2 週期
  執行: Stage 1 簽核會議（1 小時）

Day 14 (Stage 2 末):
  ✅ 檢查: M1-M5 是否 80% 完成
  ❌ 若 M4 延期: 重新規劃 M6-M9 排期
  執行: MVP 驗收會議（1.5 小時）

每週進度報告範本:
  - 本週完成: [任務清單]
  - 延期項: [項目 + 原因]
  - 風險信號: [提前預警]
  - 下週優先級: [排序]
```

#### 7. **實施就緒檢查清單**

**V4.0 簽核條件** (進入實施前必須滿足):

```
[✅] 規劃完整性
  ✅ 3 階段任務清單明確（F1-F9 / M1-M9 / E1-E6）
  ✅ 5 項凍結決策文檔完整（F0a-e）
  ✅ 170+ 測試用例清單已列舉
  ✅ 檔案結構與修改清單對齊

[✅] 架構合理性
  ✅ Stage 1 依賴流程清晰（F0→F1-F9→F8/F9）
  ✅ 隱性依賴已列舉（advisor/ALLOWED_IMPORTS.md）
  ✅ 隔離層設計（privacy/redaction/ + interfaces/）合理
  ✅ Protocol vs Implementation 邊界明確

[✅] 風險管理
  ✅ 識別了 7 個高風險項 + 緩解策略
  ✅ 里程碑監控點已定義 + 應急計劃就緒
  ✅ 時間評估：11 週（高風險監控中）
  ✅ 決策凍結優先於實施（F0a-e 是關鍵路徑）

[✅] 可執行性
  ✅ 新增 35+ 檔案的路徑明確
  ✅ 修改 6 個現有檔案的內容清晰
  ✅ CLI 指令設計簡潔（lc advisor suggest/context/history/explain）
  ✅ 測試框架選型清晰（pytest + hypothesis）

[✅] 驗收標準
  ✅ 每個階段都有量化驗收標準（tests + git 簽核）
  ✅ 決策記憶機制可驗證（append-only + 版本追蹤）
  ✅ 隱私保護可測試（property-based + structural tests）
  ✅ 決策追蹤可審計（operation_id + snapshot 一致性）
```

---

---

## 🔒 V4.1 系統鐵則對齊 - 最終優化（6 項結構性收斂）

> 此章節確保 Phase 5 與系統四大鐵則完全一致：
> 1. 唯一入口寫入 canonical
> 2. 不可變 raw
> 3. derived 可重建
> 4. 全程可追溯

---

### 優化 1：Decision/Memory 寫入邊界對齊系統鐵則（最關鍵）

**V4.0 問題**：設計讓 `lc advisor suggest/history` 可能直接寫入 `decisions.yaml`，形成第二個 canonical 寫入口。

**V4.1 解決方案**：

```yaml
鐵則收斂:
  advisor 角色: 永遠只產生 proposals（不可寫 canonical）
  canonical 寫入: 只有 lc apply/undo 可寫入 canonical/decisions/

工作流程:
  1. lc advisor suggest "買房"
     → 產生 proposals/pending/advisor_<operation_id>.yaml
     → 內含: source="advisor", comparison_result, risk_tags, decision_snapshot_draft

  2. lc apply --confirm advisor_<operation_id>
     → 驗證 proposal 內容
     → 寫入 canonical/decisions/decisions.yaml（append-only）
     → 記錄 operation_id 於 .operation_log.jsonl

  3. lc undo --latest
     → 在 decisions.yaml 中 append「reverted 標記」
     → 決策版本自動遞增
     → 不刪除原記錄（保留審計軌跡）

禁止事項:
  ❌ advisor 直接寫 canonical/
  ❌ lc advisor history 修改 decisions.yaml
  ❌ 繞過 proposals 直接寫決策記憶
```

**影響的檔案修改**：

| 檔案 | 原設計 | V4.1 修正 |
|------|--------|----------|
| `advisor/proposal_generator.py` | 可能直接寫 | 只產生 proposals/pending/*.yaml |
| `io/decisions_handler.py` | 獨立寫入口 | 被 `lc apply/undo` 調用，不可獨立使用 |
| `commands/advisor_cmd.py` | suggest 可能寫入 | suggest 只產生 proposal，不寫 canonical |
| `commands/apply_cmd.py` | 不處理 decisions | 擴展支援 `source="advisor"` 的 proposals |

---

### 優化 2：路徑與 Registry 常數定版

**V4.0 問題**：多處散落路徑定義（models/decisions.py、io/registry.py、docs 中不同路徑）。

**V4.1 解決方案**：

```python
# io/registry.py - 唯一權威來源（Stage 1 F0 鎖定）

# Phase 5 路徑常數
CANONICAL_DECISIONS_DIR = "canonical/decisions"
DECISIONS_FILE = "decisions.yaml"
DECISIONS_PATH = f"{CANONICAL_DECISIONS_DIR}/{DECISIONS_FILE}"

# 審計日誌
ADVISOR_AUDIT_LOG = "derived/logs/advisor_audit.jsonl"

# 版本
ADVISOR_VERSION = "1.0"
DECISIONS_SCHEMA_VERSION = "1.0"
```

**強制規則**：
- ✅ 所有 handler、CLI、tests 必須引用 `registry` 常數
- ❌ 禁止硬編路徑（linter 檢查）
- ✅ F0 驗收標準：grep 搜尋無硬編 `"decisions"` 或 `"canonical/decisions"` 字串

---

### 優化 3：Redaction 分層（輸出面 vs 資料面）

**V4.0 問題**：`redacted_dto` 既要支援決策引擎，又要支援 CLI 顯示，需求耦合。

**V4.1 解決方案**：

```python
# 層級 1：決策引擎用（privacy/redaction/decision_context.py）
@dataclass(frozen=True)
class RedactedDecisionContext:
    """給決策比較器用的最小特徵集"""
    # 支出分佈（類別級，非金額）
    expense_distribution: dict[str, float]  # {"food": 0.3, "housing": 0.4, ...}

    # 流動性指標（泛化）
    deficit_month_count: int                # 赤字月份數
    runway_months: int | None               # 資產耗盡月數（若 >120 則為 None）

    # 風險信號
    consecutive_deficit_months: int         # 連續虧損月數
    income_volatility: str                  # "low" | "medium" | "high"

    # 來源追蹤（每個欄位的泛化等級）
    field_provenance: dict[str, str]        # {"deficit_month_count": "exact", "expense_distribution": "bucketed"}


# 層級 2：CLI 輸出用（privacy/redaction/presentation_view.py）
@dataclass
class RedactedPresentationView:
    """給 CLI/輸出用的友善化視圖"""
    context: RedactedDecisionContext        # 層級 1 資料

    # 輸出友善化
    summary_text: str                       # "您的財務狀況：中等風險，建議關注..."
    risk_explanation: str                   # "過去 6 個月有 2 個月赤字"
    comparison_narrative: str               # "方案 A vs 方案 B 的主要差異..."
```

**測試分層**：
- `test_redaction_structural.py`：專注層級 1 的結構與組合規則（property-based）
- `test_redaction_output.py`：專注層級 2 的字串輸出掃描（grep-based）

---

### 優化 4：Comparability 不可比時的輸出契約

**V4.0 問題**：fallback「需補資料」時，是否仍符合「2 個方案」的產品約束不明確。

**V4.1 解決方案**：

```python
@dataclass
class ComparisonResult:
    """決策比較結果（永遠輸出 2 個選項）"""

    # 可比較性評分
    comparability_score: float              # 0.0-1.0
    is_comparable: bool                     # comparability_score >= 0.6

    # 兩個選項（即使不可比也必須輸出）
    option_a: DecisionOption                # 保守方向
    option_b: DecisionOption                # 進取方向

    # 不可比時的補件指引
    blocking_reasons: list[str]             # ["time_range_mismatch", "missing_income_data"]
    required_inputs: list[RequiredInput]    # [{field: "monthly_income", reason: "計算貸款承受力"}]

    # 風險說明（無論是否可比都輸出）
    risk_tags: list[str]                    # ["high_leverage", "short_runway"]
    risk_explanation: str


@dataclass
class DecisionOption:
    """單一決策選項"""
    direction: str                          # "conservative" | "aggressive"
    label: str                              # "方案 A：延後購房" | "方案 B：現在購房"

    # 若可比：包含完整建議
    recommendation: str | None              # "建議延後 6 個月，累積首付至..."
    score: float | None                     # 0.0-1.0（只有可比時才有）

    # 若不可比：指引如何變成可比
    to_comparable_guidance: str | None      # "補充以下資料後可進行比較..."

    # 標記
    status: str                             # "comparable" | "not_comparable" | "partial"
```

**驗收標準**：
- ✅ 任何 `lc advisor suggest` 輸出都包含 `option_a` 和 `option_b`
- ✅ 不可比時 `status="not_comparable"` 且 `required_inputs` 非空
- ✅ 測試覆蓋：3 個可比 + 3 個不可比 + 3 個部分可比（每模板）

---

### 優化 5：測試 KPI 改成覆蓋面 KPI

**V4.0 問題**：承諾「150+ 單元 + 40+ 整合」容易變成數字膨脹負擔。

**V4.1 解決方案**：

```yaml
Stage 1 覆蓋面要求:
  黃金測資集（30 個固定 fixtures）:
    - DTO freeze: 5 fixtures（schema validation）
    - allowed imports: linter pass（無數字 KPI）
    - redaction contract: 10 fixtures（FORBIDDEN/SENSITIVE/COMPOSITION）
    - comparability scoring: 10 fixtures（時間分段、多目標）
    - isolation contract: 5 fixtures（依賴邊界）

  必過條件:
    ✅ isolation linter pass
    ✅ contract tests pass
    ✅ 黃金測資集 100% pass

Stage 2 覆蓋面要求:
  每個模板（5 個）至少:
    - 3 個可比成功案例
    - 3 個不可比案例（補件）
    - 3 個極端風險案例

  合計: 5 模板 × 9 案例 = 45 個場景測試

  必過條件:
    ✅ 所有模板場景 pass
    ✅ redaction structural tests pass
    ✅ E2E 流程驗證 pass

Stage 3 覆蓋面要求:
  敏感度分析:
    - 參數擾動集合（利率 ±2%、通膨 ±1%、收入 ±10%、支出 ±10%）
    - 每個擾動驗證 comparability_score 變化合理

  必過條件:
    ✅ 擾動集合覆蓋完整
    ✅ decision wiki 可重建
    ✅ audit log 完整
```

---

### 優化 6：審計事件結構（advisor_audit_event）

**新增**：定義決策建議的審計事件 schema，支撐生產驗證。

```python
# derived/logs/advisor_audit.jsonl 結構

@dataclass
class AdvisorAuditEvent:
    """決策建議審計事件"""

    # 追蹤標識
    event_id: str                           # UUID
    timestamp: str                          # ISO 8601
    operation_id: str | None                # 若已 apply
    decision_id: str | None                 # 若已 apply

    # 請求資訊
    request_type: str                       # "suggest" | "context" | "history"
    template_id: str | None                 # "buying_house" | "investment" | ...
    input_hash: str                         # scenario/projection 的 provenance hash

    # 比較結果
    comparability_score: float
    blocking_reasons: list[str]
    risk_tags: list[str]

    # 輸出追蹤
    redaction_profile_version: str          # "1.0"
    output_option_count: int                # 應該永遠是 2

    # 狀態
    status: str                             # "generated" | "applied" | "reverted" | "expired"
```

**審計日誌用途**：
- 生產驗證：「10+ 建議生成無 bug」→ 掃描 `status="generated"` 且無 error
- 追蹤完整率：`operation_id` 非空的比例
- 品質監控：`comparability_score` 分佈、`blocking_reasons` 熱點分析

---

### V4.1 對齊檢查清單

```yaml
系統鐵則對齊:
  ✅ 唯一入口: advisor 只出 proposals，decisions 只由 lc apply/undo 寫入
  ✅ 不可變性: decisions.yaml 為 append-only，回滾以 reverted 標記實現
  ✅ 可重建: derived/logs/advisor_audit.jsonl 可從 canonical 重建
  ✅ 可追溯: 每個決策都有 operation_id + input_hash + decision_id

架構收斂:
  ✅ 路徑常數: io/registry.py 為唯一來源
  ✅ Redaction 分層: DecisionContext（引擎）vs PresentationView（輸出）
  ✅ 輸出契約: 永遠輸出 2 個選項（可比或不可比都有）
  ✅ 測試 KPI: 改為覆蓋面 KPI，非數字承諾

影響的任務調整:
  F0: 新增 registry 常數定版（CANONICAL_DECISIONS_DIR 等）
  F2: Redaction 分成 DecisionContext + PresentationView
  F5: 比較器輸出 ComparisonResult（永遠 2 選項）
  M3: proposal_generator 只寫 proposals/，不寫 canonical
  M4: decisions_handler 只被 apply/undo 調用
  M8: 測試分層（structural vs output）
  M9: 場景覆蓋（每模板 9 案例）
```

---

---

## 🛡️ V4.2 契約可執行化 - 工程不可破壞（P0 + P1 + P2）

> 此章節將 V4.1 的「設計上對齊」升級為「工程上不可破壞」：
> - **P0 (Must-do)**: Schema 契約化 + ID 規則可測 + Derived 重建證明
> - **P1 (Recommended)**: 輸出結構擴展 + Redaction 版本化 + CLI 護欄
> - **P2 (Optional)**: Scenario Fixture Catalog

---

### P0.1: AdvisorProposalSchema 契約化（可執行、可 baseline）

**問題**: V4.1 的 ComparisonResult、DecisionOption 是文字規格，無法自動偵測 breaking change。

**V4.2 解決方案**:

```python
# advisor/schemas.py - 凍結版契約 schema

from dataclasses import dataclass, asdict
from typing import Literal
import json

@dataclass(frozen=True)
class AdvisorProposalPayload:
    """advisor proposal 的完整輸出 schema（契約化）"""

    # === 必填欄位 ===
    schema_version: str                     # "1.0" - 契約版本
    source: Literal["advisor"]              # 固定為 "advisor"
    operation_id: str                       # ULID 格式

    # 比較結果
    comparability_score: float              # 0.0-1.0
    is_comparable: bool

    # 永遠 2 個選項
    option_a: dict                          # DecisionOptionSchema
    option_b: dict                          # DecisionOptionSchema

    # 風險
    risk_tags: list[str]
    risk_explanation: str

    # === 不可比時必填 ===
    blocking_reasons: list[str]             # 若 is_comparable=False 則非空
    required_inputs: list[dict]             # RequiredInputSchema

    # === 追蹤欄位 ===
    input_hash: str                         # SHA-256 前 16 字元
    template_id: str
    comparator_version: str                 # "1.0"
    created_at: str                         # ISO 8601


@dataclass(frozen=True)
class DecisionOptionSchema:
    """單一決策選項的 schema"""
    direction: Literal["conservative", "aggressive"]
    label: str
    status: Literal["comparable", "not_comparable", "partial"]

    # 可比時
    recommendation: str | None
    score: float | None

    # 不可比時
    to_comparable_guidance: str | None


@dataclass(frozen=True)
class RequiredInputSchema:
    """補件需求的 schema"""
    field: str
    reason: str
    priority: Literal["required", "optional"]
```

**Baseline 機制**:

```yaml
# tests/contracts/baselines/advisor_proposal_v1.0.json
# 此檔案由 Stage 1 F0 凍結時生成，任何欄位變動都會被 CI 攔截

{
  "schema_version": "1.0",
  "required_fields": [
    "source", "operation_id", "comparability_score", "is_comparable",
    "option_a", "option_b", "risk_tags", "risk_explanation",
    "input_hash", "template_id", "comparator_version", "created_at"
  ],
  "option_required_fields": [
    "direction", "label", "status"
  ],
  "enum_constraints": {
    "source": ["advisor"],
    "direction": ["conservative", "aggressive"],
    "status": ["comparable", "not_comparable", "partial"]
  }
}
```

**契約測試**:

```python
# tests/contracts/test_advisor_schema_contract.py

import json
from pathlib import Path

BASELINE_PATH = Path("tests/contracts/baselines/advisor_proposal_v1.0.json")

def test_schema_baseline_exists():
    """契約 baseline 必須存在"""
    assert BASELINE_PATH.exists(), "Missing schema baseline file"

def test_schema_no_breaking_change():
    """比對當前 schema vs baseline，偵測 breaking change"""
    baseline = json.loads(BASELINE_PATH.read_text())
    current = extract_schema_from_dataclass(AdvisorProposalPayload)

    # 必填欄位不可減少
    missing = set(baseline["required_fields"]) - set(current["required_fields"])
    assert not missing, f"Breaking change: removed fields {missing}"

    # enum 值不可減少
    for enum_field, allowed in baseline["enum_constraints"].items():
        current_allowed = current["enum_constraints"].get(enum_field, [])
        removed = set(allowed) - set(current_allowed)
        assert not removed, f"Breaking change: {enum_field} removed values {removed}"

def test_schema_additive_change_allowed():
    """允許新增欄位（非 breaking）"""
    # 新增欄位只需更新 baseline，不會導致測試失敗
    pass
```

**驗收標準**:
- ✅ `tests/contracts/baselines/advisor_proposal_v1.0.json` 存在且凍結
- ✅ `test_advisor_schema_contract.py` 在 CI 中執行
- ✅ 任何移除欄位或 enum 值的變動都會失敗

---

### P0.2: operation_id / decision_id / input_hash 唯一性與對帳規則

**問題**: V4.1 定義了這些 ID，但沒有明確唯一性保證與對帳測試。

**V4.2 解決方案**:

```yaml
ID 規則定義:
  operation_id:
    格式: ULID（可排序、時間戳內嵌）
    唯一性: 全系統唯一（proposals + canonical 共用序列）
    生成時機: lc advisor suggest 執行時
    用途: 追蹤 proposal → apply → undo 全鏈路

  decision_id:
    格式: "dec_" + ULID
    唯一性: canonical/decisions/ 內唯一
    生成時機: lc apply 成功時（不是 suggest 時）
    用途: 識別已確認的決策記錄
    關聯: 1:1 對應 operation_id（applied 狀態）

  input_hash:
    格式: SHA-256 前 16 字元
    計算公式: hash(redacted_decision_context + template_id + comparator_version)
    唯一性: 不保證（相同輸入產生相同 hash = 設計意圖）
    用途: 偵測輸入變化、防止重複計算
```

**對帳測試（3 種類型）**:

```python
# tests/contracts/test_id_traceability.py

class TestOperationIdUniqueness:
    """operation_id 唯一性測試"""

    def test_no_duplicate_operation_id_in_proposals(self, tmp_path):
        """proposals/ 中不應有重複 operation_id"""
        # 生成 10 個 proposals
        ids = [generate_advisor_proposal(tmp_path) for _ in range(10)]
        assert len(ids) == len(set(ids)), "Duplicate operation_id detected"

    def test_operation_id_is_ulid_format(self):
        """operation_id 必須是 ULID 格式"""
        op_id = generate_operation_id()
        assert re.match(r'^[0-9A-Z]{26}$', op_id), f"Invalid ULID: {op_id}"


class TestDecisionIdGeneration:
    """decision_id 生成時機測試"""

    def test_suggest_does_not_create_decision_id(self, tmp_path):
        """lc advisor suggest 不應產生 decision_id"""
        proposal = run_advisor_suggest(tmp_path, "買房")
        assert proposal.get("decision_id") is None

    def test_apply_creates_decision_id(self, tmp_path):
        """lc apply 應產生 decision_id"""
        proposal = run_advisor_suggest(tmp_path, "買房")
        result = run_apply(tmp_path, proposal["operation_id"])
        assert result["decision_id"].startswith("dec_")

    def test_decision_id_linked_to_operation_id(self, tmp_path):
        """decision_id 必須能回溯到 operation_id"""
        proposal = run_advisor_suggest(tmp_path, "買房")
        result = run_apply(tmp_path, proposal["operation_id"])

        # 從 decisions.yaml 讀取
        decision = load_decision(tmp_path, result["decision_id"])
        assert decision["operation_id"] == proposal["operation_id"]


class TestInputHashDeterminism:
    """input_hash 確定性測試"""

    def test_same_input_same_hash(self, tmp_path):
        """相同輸入應產生相同 hash"""
        ctx1 = build_redacted_context(income=100000, expenses=80000)
        ctx2 = build_redacted_context(income=100000, expenses=80000)

        hash1 = compute_input_hash(ctx1, "buying_house", "1.0")
        hash2 = compute_input_hash(ctx2, "buying_house", "1.0")

        assert hash1 == hash2

    def test_different_input_different_hash(self, tmp_path):
        """不同輸入應產生不同 hash"""
        ctx1 = build_redacted_context(income=100000, expenses=80000)
        ctx2 = build_redacted_context(income=120000, expenses=80000)

        hash1 = compute_input_hash(ctx1, "buying_house", "1.0")
        hash2 = compute_input_hash(ctx2, "buying_house", "1.0")

        assert hash1 != hash2
```

**驗收標準**:
- ✅ `test_id_traceability.py` 包含 6+ 測試用例
- ✅ operation_id 使用 ULID（`import ulid`）
- ✅ decision_id 只在 `lc apply` 時生成
- ✅ input_hash 公式明確且可重現

---

### P0.3: Derived 可重建落地（rebuild 命令 + 重建測試）

**問題**: V4.1 聲稱 `derived/logs/advisor_audit.jsonl` 可重建，但沒有實際命令與測試。

**V4.2 解決方案**:

```bash
# 新增 rebuild target
lc rebuild --target=advisor_audit

# 行為定義:
# 1. 掃描 canonical/decisions/decisions.yaml 所有決策
# 2. 掃描 canonical/.operation_log.jsonl 找出 source="advisor" 的操作
# 3. 重新計算 audit events
# 4. 輸出至 derived/logs/advisor_audit.jsonl
# 5. 比對原檔（若存在）並報告差異
```

**rebuild 實作骨架**:

```python
# commands/rebuild_cmd.py 擴展

@app.command()
def rebuild(
    path: Path = typer.Option(...),
    target: str = typer.Option("all", help="all | reports | advisor_audit"),
    verify: bool = typer.Option(False, help="比對重建結果與現有檔案"),
):
    """從 canonical 重建 derived 資料"""

    if target in ("all", "advisor_audit"):
        rebuild_advisor_audit(path, verify=verify)


def rebuild_advisor_audit(data_path: Path, verify: bool = False):
    """重建 advisor_audit.jsonl"""

    # 1. 讀取 canonical 來源
    decisions = load_decisions(data_path / CANONICAL_DECISIONS_DIR)
    operations = load_operation_log(data_path / ".operation_log.jsonl")
    advisor_ops = [op for op in operations if op.get("source") == "advisor"]

    # 2. 重建 audit events
    events = []
    for op in advisor_ops:
        decision = find_decision_by_operation_id(decisions, op["operation_id"])
        event = AdvisorAuditEvent(
            event_id=generate_uuid(),
            timestamp=op["created_at"],
            operation_id=op["operation_id"],
            decision_id=decision["decision_id"] if decision else None,
            # ... 其他欄位
        )
        events.append(event)

    # 3. 寫入 derived
    audit_path = data_path / ADVISOR_AUDIT_LOG
    write_jsonl(audit_path, events)

    # 4. 驗證（若啟用）
    if verify:
        original = read_jsonl(audit_path.with_suffix(".jsonl.bak"))
        diff = compare_audit_logs(original, events)
        if diff:
            typer.echo(f"⚠️ 重建結果與原檔有差異: {diff}")
        else:
            typer.echo("✅ 重建結果與原檔一致")
```

**重建測試**:

```python
# tests/contracts/test_derived_rebuild.py

class TestAdvisorAuditRebuild:
    """advisor_audit.jsonl 重建測試"""

    def test_rebuild_from_scratch(self, tmp_path):
        """從空白狀態重建"""
        # 準備: 建立 canonical 資料
        setup_canonical_with_decisions(tmp_path, count=5)

        # 執行: 重建
        result = run_rebuild(tmp_path, target="advisor_audit")

        # 驗證: 檔案存在且行數正確
        audit_path = tmp_path / "derived/logs/advisor_audit.jsonl"
        assert audit_path.exists()
        assert count_lines(audit_path) == 5

    def test_rebuild_idempotent(self, tmp_path):
        """重建是冪等的（多次執行結果相同）"""
        setup_canonical_with_decisions(tmp_path, count=3)

        run_rebuild(tmp_path, target="advisor_audit")
        hash1 = file_hash(tmp_path / "derived/logs/advisor_audit.jsonl")

        run_rebuild(tmp_path, target="advisor_audit")
        hash2 = file_hash(tmp_path / "derived/logs/advisor_audit.jsonl")

        assert hash1 == hash2, "Rebuild should be idempotent"

    def test_rebuild_verify_detects_tampering(self, tmp_path):
        """--verify 能偵測手動竄改"""
        setup_canonical_with_decisions(tmp_path, count=3)
        run_rebuild(tmp_path, target="advisor_audit")

        # 竄改 derived
        tamper_audit_log(tmp_path)

        # 驗證: --verify 應報告差異
        result = run_rebuild(tmp_path, target="advisor_audit", verify=True)
        assert "差異" in result.output or "diff" in result.output.lower()
```

**驗收標準**:
- ✅ `lc rebuild --target=advisor_audit` 可執行
- ✅ `lc rebuild --target=advisor_audit --verify` 可比對原檔
- ✅ `test_derived_rebuild.py` 包含冪等性測試
- ✅ 重建結果與原檔 hash 一致（正常情況下）

---

### P1.1: Comparability 固定輸出說明欄位

**問題**: V4.1 的 ComparisonResult 缺少結構化的「為什麼不可比」說明。

**V4.2 解決方案**:

```python
@dataclass
class BlockingReasonDetail:
    """阻擋原因詳情（結構化）"""
    code: str                               # "TIME_RANGE_MISMATCH" | "MISSING_DATA" | ...
    message: str                            # 人類可讀說明
    severity: Literal["blocking", "warning"]
    affected_segments: list[str]            # ["T1_首付", "T2_貸款期"]


@dataclass
class ComparisonResult:
    # ... 原有欄位 ...

    # P1.1 新增: 結構化阻擋說明
    blocking_details: list[BlockingReasonDetail]  # 取代簡單的 blocking_reasons: list[str]

    # 保留向後相容
    @property
    def blocking_reasons(self) -> list[str]:
        """向後相容：回傳 code 清單"""
        return [d.code for d in self.blocking_details]
```

---

### P1.2: Redaction 版本化 Profile + Diff 測試

**問題**: Redaction 規則可能隨版本演進，需要追蹤變化。

**V4.2 解決方案**:

```python
# privacy/redaction/profile.py

@dataclass(frozen=True)
class RedactionProfile:
    """Redaction 規則版本"""
    version: str                            # "1.0"
    forbidden_fields: frozenset[str]
    sensitive_fields: frozenset[str]
    composition_rules: tuple[tuple[str, ...], ...]  # 禁止組合

    def diff(self, other: "RedactionProfile") -> dict:
        """比對兩個版本的差異"""
        return {
            "added_forbidden": self.forbidden_fields - other.forbidden_fields,
            "removed_forbidden": other.forbidden_fields - self.forbidden_fields,
            "added_sensitive": self.sensitive_fields - other.sensitive_fields,
            "removed_sensitive": other.sensitive_fields - self.sensitive_fields,
        }


# 版本定義
REDACTION_PROFILE_V1_0 = RedactionProfile(
    version="1.0",
    forbidden_fields=frozenset({"name", "id_number", "email", "phone", ...}),
    sensitive_fields=frozenset({"amount", "date", "location", "occupation", ...}),
    composition_rules=(
        ("occupation", "salary_range"),
        ("city", "job_title", "salary_range"),
        # ...
    ),
)

CURRENT_REDACTION_PROFILE = REDACTION_PROFILE_V1_0
```

**Diff 測試**:

```python
# tests/contracts/test_redaction_profile.py

def test_profile_version_tracked():
    """Redaction profile 版本必須記錄在 audit event"""
    event = generate_audit_event()
    assert event.redaction_profile_version == CURRENT_REDACTION_PROFILE.version

def test_profile_diff_detects_changes():
    """Profile diff 能偵測變化"""
    v1 = REDACTION_PROFILE_V1_0
    v2 = RedactionProfile(
        version="1.1",
        forbidden_fields=v1.forbidden_fields | {"new_field"},
        # ...
    )
    diff = v2.diff(v1)
    assert "new_field" in diff["added_forbidden"]
```

---

### P1.3: CLI --force 護欄

**問題**: `lc advisor suggest --force` 可能被誤用跳過重要檢查。

**V4.2 解決方案**:

```python
# commands/advisor_cmd.py

@app.command()
def suggest(
    query: str,
    force: bool = typer.Option(False, help="跳過確認提示（危險操作需額外確認）"),
):
    """生成決策建議"""

    # --force 護欄
    if force:
        # 檢查是否有 blocking_reasons
        result = run_comparison(query)
        if result.blocking_reasons:
            typer.echo("⚠️ 偵測到阻擋因素，--force 無法跳過:")
            for reason in result.blocking_details:
                typer.echo(f"  - [{reason.severity}] {reason.code}: {reason.message}")

            # 強制要求額外確認
            if not typer.confirm("確定要忽略這些警告繼續？", default=False):
                raise typer.Abort()

    # ... 正常流程 ...
```

**護欄規則**:

```yaml
--force 行為:
  無阻擋因素: 跳過預覽確認，直接生成 proposal
  有 warning 級阻擋: 顯示警告，要求二次確認
  有 blocking 級阻擋: 拒絕執行，必須先補齊資料

禁止 --force 的情況:
  - comparability_score < 0.3（資料嚴重不足）
  - blocking_details 含 severity="blocking"
  - redaction 偵測到敏感資訊洩漏風險
```

---

### P2.1: Scenario Fixture Catalog（選填）

**問題**: 測試時需要手動建立 fixtures，缺乏標準化。

**V4.2 解決方案**:

```yaml
# tests/fixtures/advisor/catalog.yaml

scenarios:
  # 買房場景
  buying_house_comparable:
    description: "標準可比場景：年收120萬，欲購房200萬"
    input:
      income: 1200000
      expenses: 800000
      savings: 500000
      target_property_value: 2000000
    expected:
      is_comparable: true
      comparability_score: ">0.7"
      option_a_direction: "conservative"
      option_b_direction: "aggressive"

  buying_house_not_comparable:
    description: "不可比場景：收入資料缺失"
    input:
      income: null
      expenses: 800000
    expected:
      is_comparable: false
      blocking_reasons: ["MISSING_INCOME_DATA"]
      required_inputs: ["monthly_income"]

  # 投資場景
  investment_comparable:
    description: "標準投資場景"
    # ...

fixture_loader:
  path: "tests/fixtures/advisor/"
  format: "yaml"
  auto_generate_tests: true  # 從 catalog 自動產生 pytest 用例
```

**自動測試生成**:

```python
# tests/advisor/test_scenarios_from_catalog.py

import pytest
from tests.fixtures.advisor import load_catalog

catalog = load_catalog()

@pytest.mark.parametrize("scenario_id,scenario", catalog.items())
def test_scenario(scenario_id, scenario, tmp_path):
    """從 catalog 自動生成的場景測試"""
    # Setup
    ctx = build_context_from_input(scenario["input"])

    # Execute
    result = run_advisor_suggest(tmp_path, ctx)

    # Assert
    expected = scenario["expected"]
    assert result["is_comparable"] == expected["is_comparable"]

    if "comparability_score" in expected:
        if expected["comparability_score"].startswith(">"):
            threshold = float(expected["comparability_score"][1:])
            assert result["comparability_score"] > threshold
```

---

### V4.2 對齊檢查清單

```yaml
P0 契約可執行化:
  ✅ P0.1: AdvisorProposalSchema + baseline 檔案
  ✅ P0.2: ID 規則（ULID operation_id + decision_id 生成時機 + input_hash 公式）
  ✅ P0.3: lc rebuild --target=advisor_audit + 冪等性測試

P1 推薦優化:
  ✅ P1.1: BlockingReasonDetail 結構化阻擋說明
  ✅ P1.2: RedactionProfile 版本化 + diff 機制
  ✅ P1.3: --force 護欄（blocking 級別拒絕執行）

P2 選填優化:
  🟡 P2.1: Scenario Fixture Catalog（視時間決定）

工程不可破壞性驗證:
  ✅ Schema baseline 存在且 CI 檢查
  ✅ ID 唯一性測試通過
  ✅ Derived 重建測試通過
  ✅ 任何 breaking change 都會被 CI 攔截
```

---

### V4.2 影響的任務調整

| 原任務 | V4.2 調整 |
|--------|----------|
| F0 | 新增 `tests/contracts/baselines/` 目錄 + baseline 檔案 |
| F8 | 新增 `test_advisor_schema_contract.py` |
| F8 | 新增 `test_id_traceability.py` |
| M3 | proposal_generator 使用 `AdvisorProposalPayload` dataclass |
| M4 | decision_id 只在 apply 時生成（不在 suggest） |
| M5 | decisions_handler 支援 `lc rebuild --target=advisor_audit` |
| E6 | 文件更新契約測試說明 |

---

*審查歷程版本: V4.2 - Codex ×2 + 專業審查 + 系統鐵則對齊 + 契約可執行化（最終版）*
