# Phase 5 Stage 3 - V5 架構優化

<!-- 歷史文件：架構師反饋 -->
<!-- 主規劃文件: ../plan.md -->

本文件記錄 V5 架構優化內容，基於架構師反饋將 V4 優化為更可落地、可維護、可重建的版本。

---

## 1. 核心優化 #1: Stage 3 衍生輸出 IO 契約統一

**問題**: E2 Wiki、E3 risk-matrix、E4 sensitivity 目前各自定義契約，缺乏統一規格。

**解法**: 建立與 Phase 3 報表同級的統一契約。

### 1.1 命名規則（Normative）

```
{artifact_type}_{input_hash[:12]}_{schema_version}.{format}

範例:
- decision_wiki_a1b2c3d4e5f6_1.0.md
- risk_matrix_a1b2c3d4e5f6_1.0.json
- sensitivity_a1b2c3d4e5f6_1.0.json
```

### 1.2 Provenance Sidecar（不內嵌）

```python
# 所有 Stage 3 衍生物使用外部 .meta.json，沿用 Phase 3 模式
# 檔案結構：
# derived/advisor/
#   ├── decision_wiki_<hash>_1.0.md
#   ├── decision_wiki_<hash>_1.0.meta.json  # ← Provenance 在此
#   ├── risk_matrix_<hash>_1.0.json
#   └── risk_matrix_<hash>_1.0.meta.json

@dataclass(frozen=True)
class AdvisorDerivedProvenance:
    """Stage 3 衍生物的 Provenance（與 Phase 3 對齊）"""
    artifact_type: str             # "decision_wiki" | "risk_matrix" | "sensitivity"
    schema_version: str            # "1.0"
    calc_version: str              # 計算邏輯版本（如 "wiki_v1.0"）
    input_hash: str                # 輸入內容 SHA-256 hash（完整 64 hex）
    canonical_sources: list[str]   # 使用的 canonical 檔案列表
    generated_at: str              # ISO 8601 時間戳
    rebuild_command: str           # 重建命令（如 "lc advisor wiki --rebuild"）
```

### 1.3 原子寫入 + File Lock 統一

```python
# io/advisor_derived_handler.py（新建）

class AdvisorDerivedHandler:
    """Stage 3 衍生物的統一寫入處理器"""

    def write_with_provenance(
        self,
        artifact_type: str,
        content: str | dict,
        provenance: AdvisorDerivedProvenance,
        format: Literal["md", "json"]
    ) -> Path:
        """
        原子寫入 + sidecar provenance，與 G5 file lock 整合

        流程：
        1. 取得 file lock
        2. 寫入 .tmp 檔案
        3. 寫入 .meta.json.tmp
        4. 原子 rename 兩個檔案
        5. 釋放 lock
        """
        ...
```

### 1.4 契約測試條款

```python
# tests/contracts/test_advisor_derived_contract.py

def test_naming_convention():
    """驗證所有 Stage 3 衍生物符合命名規則"""
    pattern = r"^(decision_wiki|risk_matrix|sensitivity)_[a-f0-9]{12}_\d+\.\d+\.(md|json)$"
    for file in derived_advisor_dir.glob("*"):
        if not file.name.endswith(".meta.json"):
            assert re.match(pattern, file.name)

def test_provenance_sidecar_exists():
    """驗證每個衍生物都有對應的 .meta.json"""
    for file in derived_advisor_dir.glob("*.md"):
        assert file.with_suffix(".meta.json").exists()
    for file in derived_advisor_dir.glob("*.json"):
        if not file.name.endswith(".meta.json"):
            assert Path(str(file) + ".meta.json").exists()

def test_rebuild_idempotent():
    """驗證重建產生相同 hash（確定性）"""
    ...
```

---

## 2. 核心優化 #2: E2 模組歸屬明確化

**問題**: E2 從 `generation/` 搬到 `advisor/` 只是繞過限制，長期會讓 advisor/ 同時承擔 online 建議 + offline 編譯。

**解法選項**:

| 選項 | 說明 | 優點 | 缺點 |
|------|------|------|------|
| **A（採用）** | 擴充 `generation/` 契約 | 與 Phase 3 一致，沿用成功模式 | 需明確新契約 |
| B | 建立 `derived_builders/` 子域 | 職責清晰 | 新增目錄結構 |

### 2.1 選項 A：擴充 generation/ 契約（推薦）

**原契約**（Phase 3）:
> generation/ 只能讀 derived，輸出到 derived

**擴充契約**（Stage 3）:
> generation/ 可生成 derived，輸入必須來自 canonical/derived（不可碰 raw）

```python
GENERATION_CONTRACT = """
## generation/ 模組契約 V1.1（Stage 3 擴充）

### 允許的輸入來源
1. canonical/ - 正規化資料（如 decisions.yaml）
2. derived/ - 已生成的衍生物（如報表）

### 禁止的輸入來源
- raw/ - 原始輸入（必須經過 canonical 層）

### 輸出目標
- derived/advisor/ - Stage 3 衍生物
- derived/reports/ - Phase 3 報表

### CI 檢查
- grep -r "from life_capital.io.raw" life_capital/generation/
  預期：無結果
- grep -r "raw_handler" life_capital/generation/
  預期：無結果
"""
```

### 2.2 模組結構調整

```
life_capital/generation/
├── __init__.py
├── report_builder.py      # Phase 3 報表（既有）
├── decision_wiki.py       # E2: Wiki 編譯器（從 advisor/ 移回）
├── risk_matrix.py         # E3: 風險矩陣輸出
└── sensitivity_report.py  # E4: 敏感度報告
```

**注意**: `advisor/` 保留 online 功能（comparator, decisions_handler, context_builder）

---

## 3. 核心優化 #3: 可比性與可評估性分離

**問題**: `comparability_score` 0.3-0.7 區間在 E3/E4 各自解釋，維護差異會很痛。

**解法**: 引入兩個獨立旗標，集中在 `advisor/shared/`。

### 3.1 判定模組設計

```python
# advisor/shared/evaluability.py

from dataclasses import dataclass
from enum import Enum

class RecommendabilityLevel(Enum):
    """可推薦程度"""
    FULL = "full"           # ≥0.7: 完整 A/B 排序與推薦
    PARTIAL = "partial"     # 0.5-0.7: 可推薦但需標註
    NONE = "none"           # <0.5: 不可推薦

class EvaluabilityLevel(Enum):
    """可評估程度（風險/敏感度）"""
    FULL = "full"           # ≥0.5: 完整評估
    WARNING = "warning"     # 0.3-0.5: 可評估但強制加警告
    SKIP = "skip"           # <0.3: 跳過評估

@dataclass(frozen=True)
class DecisionEvaluability:
    """決策的可評估性判定結果"""
    comparability_score: float
    is_recommendable: RecommendabilityLevel
    is_evaluable: EvaluabilityLevel
    warning_message: str | None

def evaluate_decision(comparability_score: float) -> DecisionEvaluability:
    """
    集中判定邏輯，E3/E4/E5 共用

    閾值定義（來自 decision_comparator 的 4D 特徵）:
    - ≥0.7: 完整可比，可推薦 + 可評估
    - 0.5-0.7: 部分可比，可推薦（標註）+ 可評估
    - 0.3-0.5: 低可比，不可推薦 + 可評估（警告）
    - <0.3: 不可比，不可推薦 + 跳過評估
    """
    ...
```

### 3.2 E3/E4 使用方式

```python
# advisor/risk_assessor.py
from advisor.shared.evaluability import evaluate_decision, EvaluabilityLevel

def assess_risk(decision: DecisionRecord) -> RiskAssessment | None:
    eval_result = evaluate_decision(decision.comparability_score)

    if eval_result.is_evaluable == EvaluabilityLevel.SKIP:
        return None  # 不輸出

    assessment = _compute_risk(decision)

    if eval_result.is_evaluable == EvaluabilityLevel.WARNING:
        assessment.warnings.append(eval_result.warning_message)

    return assessment
```

---

## 4. 附加優化

### 4.1 E1 遷移策略硬化

```python
# tests/contracts/test_decisions_migration.py

# 跨版本 fixtures（V1.0、V1.1 各 3-5 份）
MIGRATION_FIXTURES = [
    "tests/fixtures/decisions/v1.0_minimal.yaml",
    "tests/fixtures/decisions/v1.0_with_reverts.yaml",
    "tests/fixtures/decisions/v1.0_edge_cases.yaml",
    "tests/fixtures/decisions/v1.1_new_fields.yaml",
    "tests/fixtures/decisions/v1.1_full_features.yaml",
]

def test_forward_compatible():
    """V1.1 handler 必須能讀 V1.0 檔案"""
    handler = DecisionsHandler(schema_version="1.1")
    for fixture in [f for f in MIGRATION_FIXTURES if "v1.0" in f]:
        records = handler.read(fixture)
        assert records is not None  # 不 raise

def test_migrate_dry_run_output():
    """migrate --dry-run 輸出差異摘要格式"""
    result = run_command(["lc", "migrate", "--dry-run", "--from", "1.0", "--to", "1.1"])
    assert "Added fields:" in result.stdout
    assert "decision_rationale" in result.stdout
```

### 4.2 測試策略壓縮

| 模組 | V4 測試 | V5 優化後 | 優化方式 |
|------|---------|-----------|----------|
| E2 Wiki | 25-30 | 18-22 | 結構段落 + 必含 token（非全檔比對） |
| E3 Risk | 30-35 | 22-26 | 集中在共用判定模組測試 |
| E4 Sensitivity | 35-40 | 28-32 | 不變量測試（perturbation=0, 單調性） |
| **合計** | 145-175 | **120-145** | -20% |

### 4.3 CLI 族群化簡化

```bash
# 預設：一般用戶（摘要）
lc advisor history

# 進階用戶（穩定 schema）
lc advisor history --format json

# 稽核視圖（完整 lineage）
lc advisor history --verbose
# 或
lc advisor history --audit
```

**不新增命令**，用 flag 區分。

---

## 5. 更新後的實作順序（V5）

```
Phase 1: 基礎設施
├── 建立 io/advisor_derived_handler.py（統一 IO 契約）
├── 更新 io_contract.md（generation/ 契約擴充）
├── 建立 advisor/shared/evaluability.py（可比性/可評估性）
└── 建立跨版本 migration fixtures

Phase 2: E1 Memory 完整模型
├── 新增欄位 + handler 同步
├── 實作 ID 重複檢查 + 狀態轉換驗證
├── 實作 fallback 策略
└── 測試：round-trip + 跨版本 fixtures

Phase 3: E2 + E3（generation/ 統一）
├── E2: generation/decision_wiki.py
├── E3: generation/risk_matrix.py（讀取 + 輸出 JSON）
├── advisor/risk_assessor.py（評估邏輯，使用 shared/evaluability）
├── 共用 AdvisorDerivedHandler
└── 測試：結構 + 必含 token（非全檔）

Phase 4: E4 敏感度分析
├── generation/sensitivity_report.py
├── advisor/sensitivity_analyzer.py（使用 shared/evaluability）
├── 基線策略 + 微擾範圍
└── 測試：不變量 + 單調性

Phase 5: E5 CLI 整合
├── history/explain/risk-matrix/sensitivity 命令
├── --format json / --verbose / --audit
├── 狀態過濾 + 容錯
└── 測試：integration

Phase 6: E6 文件與驗收
├── 更新 docs/contracts/io_contract.md
├── stage3-design.md / stage3-api.md
├── lc doctor --advisor
└── 最終驗收
```

---

## 6. V5 驗收標準

| # | 驗收項目 | 驗證方式 | 狀態 |
|---|----------|----------|------|
| V5-1 | IO 契約統一 | test_advisor_derived_contract.py | ✅ |
| V5-2 | generation/ 契約擴充 | CI import 掃描無 raw 依賴 | ✅ |
| V5-3 | 可比性/可評估性分離 | shared/evaluability.py 存在 | ✅ |
| V5-4 | 測試數量壓縮 | 120-145 tests（vs V4 145-175） | ✅ |
| V5-5 | 跨版本 migration fixtures | 5+ fixtures 存在 | ✅ |

---

## 相關文件

| 文件 | 說明 |
|------|------|
| [../plan.md](../plan.md) | 主規劃文件（V7 收斂版） |
| [../contracts.md](../contracts.md) | 技術契約 |
| [v1-v4-reviews.md](./v1-v4-reviews.md) | Codex 審查歷程 |
| [v6-operations.md](./v6-operations.md) | V6 可運營性優化 |
