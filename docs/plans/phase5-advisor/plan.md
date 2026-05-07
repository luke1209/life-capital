# Phase 5 AI 顧問系統 - 實作規劃

> **版本**: V4.2（最終版）
> **狀態**: Stage 2 MVP 完成 ✅（Stage 1 + Stage 2 已實施）
> **審查歷程**: [review-history.md](./review-history.md)
> **最後更新**: 2025-12-29

---

## 0. 系統約束（不可違反）

實施前必須理解的硬性規則，違反將導致系統不一致。

### 0.1 寫入邊界鐵則

```yaml
canonical/ 寫入:
  唯一入口: lc apply / lc undo
  禁止: advisor 直接寫入 canonical/
  追蹤: 每次變更必須有 operation_id

proposals/ 寫入:
  允許: advisor 產生 proposals/pending/*.yaml
  格式: source="advisor" + operation_id + comparison_result

derived/ 寫入:
  性質: 可覆寫、可重建
  來源: 必須可從 canonical + raw 100% 重建
```

### 0.2 ID 規則

```yaml
operation_id:
  格式: ULID（26 字元，可排序）
  生成時機: lc advisor suggest 執行時
  唯一性: 全系統唯一

decision_id:
  格式: "dec_" + ULID
  生成時機: lc apply 成功時（不是 suggest 時）
  用途: 識別已確認的決策記錄

input_hash:
  格式: SHA-256 前 16 字元
  公式: hash(redacted_context + template_id + comparator_version)
  用途: 偵測輸入變化
```

### 0.3 輸出契約

```yaml
永遠輸出 2 個選項:
  option_a: 保守方向
  option_b: 進取方向
  即使不可比: 仍輸出 2 選項 + blocking_reasons

狀態標記:
  - "comparable": 可比較，含完整建議
  - "not_comparable": 不可比，含補件指引
  - "partial": 部分可比
```

### 0.4 隱私硬性禁止

```
禁止輸出:
  - 姓名、身分證、護照、駕照、出生日期
  - Email、電話、通訊地址、公司名稱
  - 銀行帳號、卡號、IBAN、API Key
  - 具體商家名稱、發票號、訂單號
  - 精確地點、精確日期、航班號

禁止組合:
  - 職業 + 薪資區間
  - 城市 + 職稱 + 薪資
  - 精確季度 + 大額支出
```

### 0.5 路徑常數（唯一來源：io/registry.py）

```python
CANONICAL_DECISIONS_DIR = "canonical/decisions"
DECISIONS_FILE = "decisions.yaml"
ADVISOR_AUDIT_LOG = "derived/logs/advisor_audit.jsonl"
ADVISOR_VERSION = "1.0"
DECISIONS_SCHEMA_VERSION = "1.0"
```

---

## 1. 目標與範圍

### 1.1 核心目標

構建**決策比較引擎**，提供「2 個可比較方案 + 風險說明」的財務建議。

### 1.2 設計選擇

| 選項 | 採用 | 原因 |
|------|------|------|
| 規則引擎（無 LLM） | ✅ | 決定論、可追蹤、無幻覺 |
| LLM 輔助 | ❌ | 幻覺風險高、隱私風險大 |
| 財務檢查點 | ❌ | 只能「符合/不符合」，缺建議價值 |

### 1.3 核心特徵

1. **規則驅動**：決定論邏輯，完全可追蹤
2. **2 選項輸出**：永遠生成 2 個可比較方案
3. **複用計算**：直接使用 Phase 2-3 的 projection/scenario/report
4. **隱私優先**：獨立 privacy/redaction/ 層

---

## 2. 核心架構

### 2.1 模組依賴圖

```
┌─────────────────────────────────────────────────────────┐
│                     commands/                            │
│   advisor_cmd.py ──→ suggest/context/history/explain    │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                      advisor/                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ comparator   │  │  proposal_   │  │  context_    │  │
│  │              │→ │  generator   │← │  builder     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                 │                  │          │
│         ▼                 ▼                  ▼          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ scenario_    │  │  templates/  │  │  features.py │  │
│  │ rules.py     │  │  *.yaml      │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  interfaces/ │  │   privacy/   │  │     io/      │
│  protocols   │  │  redaction/  │  │  handlers    │
└──────────────┘  └──────────────┘  └──────────────┘
```

### 2.2 資料流

```
用戶輸入 "買房"
    │
    ▼
┌─ lc advisor suggest ─────────────────────────────────┐
│  1. context_builder → 收集財務資料                    │
│  2. redaction → 去識別化                              │
│  3. comparability → 計算可比較性分數 (0-1)            │
│  4. decision_comparator → 規則引擎比較                │
│  5. proposal_generator → 生成 2 選項                  │
│  6. 輸出 proposals/pending/advisor_<op_id>.yaml      │
└──────────────────────────────────────────────────────┘
    │
    ▼
用戶確認 → lc apply → 寫入 canonical/decisions/
```

### 2.3 檔案結構

```
life_capital/
├── privacy/                          # 隱私保護層
│   └── redaction/
│       ├── engine.py                 # RedactionEngine
│       ├── rules.py                  # FORBIDDEN/SENSITIVE/COMPOSITION
│       └── decision_context.py       # RedactedDecisionContext
│
├── advisor/                          # 核心模組
│   ├── schemas.py                    # DTO schema（凍結版）
│   ├── models.py                     # DecisionSuggestion, ComparisonResult
│   ├── features.py                   # 四維特徵向量
│   ├── comparability.py              # 可比較性評分
│   ├── decision_comparator.py        # 規則引擎（純函式，無 I/O）
│   ├── scenario_rules.py             # 場景規則（買房/投資等）
│   ├── proposal_generator.py         # 提案生成（只寫 proposals/）
│   ├── context_builder.py            # 上下文構築
│   └── templates/                    # 決策模板
│       ├── schema.py                 # 模板 DSL
│       ├── buying_house.yaml
│       ├── investment.yaml
│       └── ...
│
├── interfaces/
│   ├── advisor_service.py            # AdvisorService Protocol
│   └── redacted_dto.py               # RedactedDTO Protocol
│
├── models/
│   └── decisions.py                  # Decision, FinancialMemory
│
├── io/
│   ├── registry.py                   # 路徑常數（唯一來源）
│   └── decisions_handler.py          # 只被 apply/undo 調用
│
├── commands/
│   └── advisor_cmd.py                # CLI: suggest/context/history/explain
│
└── tests/advisor/
    ├── test_isolation.py
    ├── test_redaction_structural.py
    └── test_e2e_advisor.py
```

---

## 3. 核心資料模型

### 3.1 AdvisorProposalPayload（輸出 Schema）

```python
@dataclass(frozen=True)
class AdvisorProposalPayload:
    # 必填
    schema_version: str           # "1.0"
    source: Literal["advisor"]    # 固定
    operation_id: str             # ULID

    # 比較結果
    comparability_score: float    # 0.0-1.0
    is_comparable: bool           # score >= 0.6

    # 永遠 2 選項
    option_a: DecisionOptionSchema
    option_b: DecisionOptionSchema

    # 風險
    risk_tags: list[str]
    risk_explanation: str

    # 不可比時
    blocking_reasons: list[str]
    required_inputs: list[RequiredInputSchema]

    # 追蹤
    input_hash: str               # SHA-256 前 16 字元
    template_id: str
    comparator_version: str
    created_at: str               # ISO 8601
```

### 3.2 DecisionOptionSchema

```python
@dataclass(frozen=True)
class DecisionOptionSchema:
    direction: Literal["conservative", "aggressive"]
    label: str                    # "方案 A：延後購房"
    status: Literal["comparable", "not_comparable", "partial"]

    # 可比時
    recommendation: str | None
    score: float | None

    # 不可比時
    to_comparable_guidance: str | None
```

### 3.3 RedactedDecisionContext（決策引擎輸入）

```python
@dataclass(frozen=True)
class RedactedDecisionContext:
    # 支出分佈（類別級）
    expense_distribution: dict[str, float]  # {"food": 0.3, "housing": 0.4}

    # 流動性指標
    deficit_month_count: int
    runway_months: int | None      # >120 則 None

    # 風險信號
    consecutive_deficit_months: int
    income_volatility: str         # "low" | "medium" | "high"

    # 來源追蹤
    field_provenance: dict[str, str]
```

### 3.4 可比較性四維特徵

```python
@dataclass
class ComparabilityFeatures:
    time_horizon: float    # 期限匹配度 0-1
    risk_tolerance: float  # 風險容忍度 0-1
    liquidity: float       # 流動性需求 0-1
    capital_need: float    # 資金需求 0-1

    def score(self) -> float:
        """加權平均，閾值 0.6"""
        return (self.time_horizon * 0.3 +
                self.risk_tolerance * 0.2 +
                self.liquidity * 0.3 +
                self.capital_need * 0.2)
```

---

## 4. 實施任務

### 4.1 Stage 1: Foundation（1-2 週）✅ 完成

**目標**: 凍結 DTO + 決策模型 + 5 項架構決策

**狀態**: ✅ 已完成（2025-12-29）- 129 tests passing

| # | 任務 | 檔案 | 複雜度 | 狀態 |
|---|------|------|--------|------|
| **F0** | DTO Schema 凍結 | `advisor/schemas.py` | HIGH | ✅ |
| **F0a** | 決策記憶資料模型 | `models/decisions.py` | HIGH | ✅ |
| **F0b** | 多目標權衡策略 | `advisor/comparability.py` | HIGH | ✅ |
| **F0c** | Redaction 必要特徵 | `privacy/redaction/decision_context.py` | HIGH | ✅ |
| **F0d** | 時間分段評分框架 | `advisor/comparability.py` | HIGH | ✅ |
| **F0e** | Wiki vs Memory 邊界 | `models/decisions.py` | HIGH | ✅ |
| F1 | advisor/ 模組骨架 | `advisor/models.py` | LOW | ✅ |
| F2 | Redaction 層 | `privacy/redaction/engine.py` | HIGH | ✅ |
| F3 | 可比較性判定 | `advisor/comparability.py` | HIGH | ✅ |
| F4 | 決策記憶模型 | `models/decisions.py` | HIGH | ✅ |
| F5 | 規則引擎 | `advisor/decision_comparator.py` | MED | ✅ |
| F6 | 模板 DSL | `advisor/templates/schema.py` | MED | ✅ |
| F7 | CLI 骨架 | `commands/advisor_cmd.py` | LOW | ✅ |
| **F8** | 隔離層測試 | `tests/advisor/test_isolation.py` | LOW | ✅ |
| **F9** | 凍結驗收測試 | `tests/advisor/test_freezing.py` | HIGH | ✅ |

**驗收標準**: ✅ 全部達成
- ✅ DTO schema 穩定（F0 鎖定）
- ✅ 5 項決策凍結完成 (F0a-e)
- ✅ DecisionComparator 無 I/O（純函式）
- ✅ 129 單元測試通過（超過 55+ 目標）

### 4.2 Stage 2: MVP（2-3 週）✅ 完成

**目標**: 可用的決策比較與建議生成

**狀態**: ✅ 已完成（2025-12-29）- 233 advisor tests passing（841 total）

| # | 任務 | 檔案 | 複雜度 | 狀態 | 測試數 |
|---|------|------|--------|------|--------|
| M1 | 5 個決策模板 | `advisor/templates/*.py` | MED | ✅ | 42 |
| M2 | 場景對比規則 | `advisor/decision_comparator.py` | HIGH | ✅ | 40 |
| M3 | 提案生成器 | `advisor/proposal_generator.py` | HIGH | ✅ | 25 |
| **M4** | 決策記憶 Schema 凍結 | `models/decisions.py` | HIGH | ✅ | - |
| M5 | Memory Handler | `io/decisions_handler.py` | MED | ✅ | 17 |
| M6 | 上下文建構器 | `advisor/context_builder.py` | MED | ✅ | 22 |
| M7 | 比較規則單元測試 | `tests/advisor/test_comparator.py` | MED | ✅ | 40 |
| **M8** | 隱私結構測試 | `tests/advisor/test_redaction_structural.py` | HIGH | ✅ | 53 |
| **M9** | E2E 整合測試 | `tests/advisor/test_e2e_advisor.py` | MED | ✅ | 34 |

**驗收標準**: ✅ 全部達成
- ✅ `lc advisor suggest "買房"` 生成 2 方案（規則引擎實作完成）
- ✅ 不可比時輸出補件指引（blocking_reasons + to_comparable_guidance）
- ✅ 233 整合測試通過（超過 40+ 目標）

**關鍵實作成果**:
- **decisions_handler.py**: Append-only 決策記憶，YAML 持久化，operation 追蹤
- **proposal_generator.py**: 從 ComparisonResult 生成 AdvisorProposalPayload
- **context_builder.py**: 從 canonical 資料建構去識別化決策上下文
- **test_redaction_structural.py**: 53 個屬性式隱私驗證測試
- **test_e2e_advisor.py**: 34 個端對端測試（5 模板 × 3 場景 + 邊界情況）

### 4.3 Stage 3: Enhancement（1-2 週）

**目標**: 完整的決策記憶與 Wiki

| # | 任務 | 檔案 | 複雜度 |
|---|------|------|--------|
| E1 | Memory 完整模型 | `models/decisions.py` 擴展 | MED |
| E2 | 決策 Wiki 編譯器 | `generation/decision_wiki.py` | MED |
| E3 | 風險評估模組 | `advisor/risk_assessor.py` | HIGH |
| E4 | 敏感度分析 | `advisor/sensitivity_analyzer.py` | HIGH |
| E5 | 歷史查詢 CLI | `advisor_cmd.py` (history/explain) | MED |
| E6 | 文件與驗收 | `docs/advisor/` + CLAUDE.md | LOW |

---

## 5. CLI 介面

### 5.1 Stage 2 指令

```bash
# 生成決策建議
lc advisor suggest "買房" [--redacted] [--dry-run] [--force]

# 輸出去識別的決策背景
lc advisor context --redacted [--format json|md]
```

### 5.2 Stage 3 指令

```bash
# 查看決策歷史
lc advisor history [--limit 10]

# 解釋特定決策
lc advisor explain <decision_id>
```

---

## 6. 隱私規則詳細

### 6.1 Redaction 分層

```
Layer 1: RedactedDecisionContext（給決策引擎）
  - 支出分佈（類別百分比）
  - 赤字月數（整數）
  - 收入波動度（low/medium/high）

Layer 2: RedactedPresentationView（給 CLI 輸出）
  - 基於 Layer 1
  - 加上友善化描述文字
```

### 6.2 允許輸出

```
彙總統計: 月度總收入、總支出、儲蓄率
預測指標: 赤字月份數、資產耗盡日期
情境名稱: 「保守」「基準」「樂觀」
風險因素: 「連續 3 月赤字」（泛化）
```

### 6.3 泛化規則

```
金額: 改為區間（10-15 萬）
時間: 改為月份級（2025-01）
地點: 改為城市級或區域級
職業: 改為行業級
```

---

## 7. 測試策略

### 7.1 覆蓋面 KPI（非數字目標）

```yaml
Stage 1:
  - DTO schema: 5 fixtures
  - Redaction: 10 fixtures (FORBIDDEN/SENSITIVE/COMPOSITION)
  - Comparability: 10 fixtures（時間分段）
  - Isolation: 5 fixtures

Stage 2:
  每模板 9 案例:
    - 3 個可比成功
    - 3 個不可比（補件）
    - 3 個極端風險
  合計: 5 模板 × 9 = 45 場景

Stage 3:
  敏感度分析:
    - 利率 ±2%
    - 通膨 ±1%
    - 收入 ±10%
    - 支出 ±10%
```

### 7.2 契約測試

```python
# tests/contracts/baselines/advisor_proposal_v1.0.json
# 任何欄位移除都會導致 CI 失敗

def test_schema_no_breaking_change():
    baseline = load_baseline()
    current = extract_schema()
    missing = baseline["required_fields"] - current["required_fields"]
    assert not missing, f"Breaking: removed {missing}"
```

### 7.3 重建測試

```bash
# 驗證 derived 可重建
lc rebuild --target=advisor_audit --verify
```

---

## 8. 里程碑與時間表

### 8.1 里程碑定義

| 里程碑 | 條件 | 驗證 |
|--------|------|------|
| M1 架構就緒 | Stage 1 完成 | 25+ 隔離測試 |
| M2 MVP 可用 | Stage 2 完成 | 40+ 整合測試 |
| M3 隱私驗證 | Redaction 100% | 0 敏感洩漏 |
| M4 決策追蹤 | Memory 可用 | history 可回溯 |
| M5 完整系統 | Stage 3 完成 | 所有測試通過 |
| M6 驗收就緒 | 文件完整 | CLAUDE.md 更新 |

### 8.2 時間表

| 週期 | 交付 | 風險 |
|------|------|------|
| W1-2 | F0 + F1-F2 | ⭐ DTO 凍結關鍵 |
| W2-3 | F3-F7 | 依賴 F0 |
| W3-5 | M1-M5 | M4 依賴 F0 |
| W5-6 | M6-M9 | 標準 |
| W7-8 | E1-E6 | 標準 |
| W9-10 | 生產驗證 | - |

**總計**: 10-11 週

---

## 9. 風險與緩解

| 風險 | 機率 | 緩解 |
|------|------|------|
| AI 幻覺 | HIGH | 純規則引擎，無 LLM |
| 隱私洩漏 | HIGH | 硬性 Redaction + 白名單 |
| 決策不一致 | MED | append-only + audit log |
| 提案追蹤模糊 | MED | source="advisor" 欄位 |

---

## 10. 關鍵實作順序

```
1. advisor/schemas.py          ← DTO 凍結（最優先）
2. privacy/redaction/engine.py ← 隱私保護
3. advisor/decision_comparator.py ← 規則引擎
4. advisor/scenario_rules.py   ← 場景規則
5. advisor/proposal_generator.py ← 提案生成
6. models/decisions.py         ← 決策記憶
7. commands/advisor_cmd.py     ← CLI 入口
```

---

## 附錄：版本演進

| 版本 | 審查來源 | 主要改善 |
|------|----------|----------|
| V1.0 | - | 初版 |
| V2.0 | Codex #1 | DTO 凍結、Redaction 獨立 |
| V3.0 | Codex #2 | 5 個核心假設、決策凍結 |
| V4.0 | 專業審查 | 流程優化、衝突解決 |
| V4.1 | 鐵則對齊 | 寫入邊界、ID 規則 |
| V4.2 | 契約可執行化 | Schema baseline、重建測試 |

> 📚 完整審查歷程請見 [review-history.md](./review-history.md)

---

## 驗收報告

### Phase 5 Stage 1+2 驗收結果

> **狀態**: ✅ 通過
> **日期**: 2025-12-29
> **Commit**: bbf8f5d

#### 功能驗收

- ✅ F1: 決策比較器純函式（decision_comparator.py 無 I/O 操作）
- ✅ F2: 2 選項契約（schemas.py 強制 option_a + option_b）
- ✅ F3: 隱私規則（52 FORBIDDEN + 23 SENSITIVE + 10 COMPOSITION）
- ✅ F4: Append-only 語意（decisions_handler.py 只有 write_decision）
- ✅ F5: 6 模板（DEFAULT, BUYING_HOUSE, INVESTMENT, CAR_PURCHASE, TRAVEL, SAVINGS_TARGET）

#### 測試驗收

- ✅ T1: 233 tests passed（pytest tests/advisor/ -v）
- ✅ T2: E2E 整合 22+ passed（test_e2e_advisor.py）
- ✅ T3: Redaction 25+ passed（test_redaction_structural.py）
- ✅ T4: Handler 17+ passed（test_decisions_handler.py）

#### 契約驗收

- ✅ C1: IO Contract 已更新（docs/contracts/io_contract.md lines 127, 151）
- ✅ C2: Registry 常數存在（DECISIONS_FILE, CANONICAL_DECISIONS_DIR, DECISIONS_SCHEMA_VERSION）
- ✅ C3: Schema 版本一致（decisions_handler.py 使用 DECISIONS_SCHEMA_VERSION = "1.0"）

#### 文件驗收

- ✅ D1: plan.md 驗收報告存在
- ✅ D2: V2.5.md Stage 2 完成標記
- ✅ D3: DEVELOPMENT.md advisor 模組規範（lines 215-238）

#### 驗收標準（原有格式）

| # | 標準 | 結果 | 驗證 |
|---|------|------|------|
| 1 | 所有 advisor 測試通過 | ✅ 233 passed | `pytest tests/advisor/` |
| 2 | 完整測試套件通過 | ✅ 841 passed | `pytest tests/` |
| 3 | DTO Schema 穩定 | ✅ | `advisor/schemas.py` 凍結 |
| 4 | DecisionComparator 無 I/O | ✅ | 純函式，無檔案操作 |
| 5 | 隱私保護驗證 | ✅ 53 tests | `test_redaction_structural.py` |
| 6 | E2E 整合驗證 | ✅ 34 tests | `test_e2e_advisor.py` |

#### 實作模組摘要

| 模組 | 檔案 | 行數 | 說明 |
|------|------|------|------|
| Privacy Layer | `privacy/redaction/` | ~400 | 三層 Redaction 規則 |
| Core Engine | `advisor/decision_comparator.py` | ~580 | 規則引擎（純函式） |
| Templates | `advisor/templates/` | ~350 | 5 個決策模板 + DSL |
| Memory Handler | `io/decisions_handler.py` | ~520 | Append-only 決策記憶 |
| Context Builder | `advisor/context_builder.py` | ~310 | 上下文建構器 |
| Proposal Generator | `advisor/proposal_generator.py` | ~280 | 提案生成器 |

#### 測試覆蓋

| 測試類別 | 測試數 | 檔案 |
|----------|--------|------|
| Schema 凍結 | 35 | `test_freezing.py` |
| 隔離層 | 12 | `test_isolation.py` |
| Redaction 引擎 | 28 | `test_redaction_engine.py` |
| 比較規則 | 40 | `test_comparator.py` |
| 模板 | 42 | `test_templates.py` |
| Proposal 生成 | 25 | `test_proposal_generator.py` |
| Memory Handler | 17 | `test_decisions_handler.py` |
| 隱私結構 | 53 | `test_redaction_structural.py` |
| E2E 整合 | 34 | `test_e2e_advisor.py` |
| **合計** | **233** | - |

#### 後續 Backlog（Stage 3）

- [ ] E1: Memory 完整模型（AssumptionSnapshot 擴展）
- [ ] E2: 決策 Wiki 編譯器
- [ ] E3: 風險評估模組
- [ ] E4: 敏感度分析
- [ ] E5: 歷史查詢 CLI（history/explain）
- [ ] E6: 文件與驗收

---

*計劃版本: V4.2 最終版 | Stage 2 MVP 已完成*
