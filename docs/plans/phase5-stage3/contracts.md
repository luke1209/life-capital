# Phase 5 Stage 3 - 技術契約

<!-- 版本: V7 收斂版 | 最後更新: 2024-12 -->
<!-- 主規劃文件: ./plan.md -->

本文件定義 Stage 3 實作的技術契約，包含 IO 規範、Schema 定義、可評估性模組。

---

## 1. 衍生物 IO 契約

### 1.1 命名規則（Normative）

```
{artifact_type}_{input_hash[:12]}_{schema_version}.{format}

範例:
- decision_wiki_a1b2c3d4e5f6_1.0.md
- risk_matrix_a1b2c3d4e5f6_1.0.json
- sensitivity_a1b2c3d4e5f6_1.0.json
```

### 1.2 檔案結構

```
derived/advisor/
├── decision_wiki_<hash>_1.0.md
├── decision_wiki_<hash>_1.0.meta.json   # Provenance sidecar
├── risk_matrix_<hash>_1.0.json
├── risk_matrix_<hash>_1.0.meta.json
├── sensitivity_<hash>_1.0.json
└── sensitivity_<hash>_1.0.meta.json
```

### 1.3 Provenance Schema（V7 版）

```python
@dataclass(frozen=True)
class AdvisorDerivedProvenance:
    """Stage 3 衍生物的 Provenance"""
    artifact_type: str                 # "decision_wiki" | "risk_matrix" | "sensitivity"
    schema_version: str                # "1.0"
    calc_version: str                  # 計算邏輯版本（如 "wiki_v1.0"）
    canonicalization_version: str      # V7: 輸入正規化版本
    input_hash: str                    # 輸入內容 SHA-256 hash（完整 64 hex）
    canonical_sources: list[str]       # 使用的 canonical 檔案列表
    generated_at: str                  # ISO 8601 時間戳
    rebuild_command: RebuildCommand    # V7: 結構化重建命令
    content_hash: str                  # V6: 輸出內容 hash
    redaction_profile_version: str     # V6: 去識別規則版本
```

### 1.4 原子寫入處理器

```python
class AdvisorDerivedHandler:
    """Stage 3 衍生物的統一寫入處理器"""
    ALLOWED_BASE = "derived/advisor"
    ALLOWED_EXTENSIONS = {".md", ".json", ".meta.json"}

    def write_with_provenance(
        self,
        artifact_type: str,
        content: str | dict,
        provenance: AdvisorDerivedProvenance,
        format: Literal["md", "json"],
        write_mode: WriteMode = WriteMode.ERROR_IF_EXISTS,
    ) -> WriteResult:
        """
        原子寫入 + sidecar provenance

        流程：
        1. 取得 file lock
        2. 路徑安全驗證
        3. 寫入 .tmp 檔案
        4. 寫入 .meta.json.tmp
        5. 原子 rename 兩個檔案
        6. 釋放 lock
        """
        ...
```

### 1.5 契約測試

```python
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

def test_rebuild_idempotent():
    """驗證重建產生相同 hash（確定性）"""
    ...
```

---

## 2. Canonicalization 契約（V7 Normative）

### 2.1 版本

```python
CANONICALIZATION_VERSION = "1.0"
# 變更版本 = 預期所有 input_hash 變更
```

### 2.2 欄位白名單（按此順序）

1. `decision_id` (string)
2. `template_id` (string)
3. `status` (enum value as string)
4. `confidence` (enum value as string)
5. `comparability_score` (Decimal, quantize "0.0001")
6. `option_a` (nested object, 遞迴 canonicalize)
7. `option_b` (nested object, 遞迴 canonicalize)
8. `risk_tags` (list[string], sorted alphabetically)

### 2.3 排除欄位

- `created_at`, `generated_at`（時間戳）
- `_seq`, `operation_id`（內部追蹤）
- file paths（環境相依）

### 2.4 數值規則

| 型別 | 規則 | 範例 |
|------|------|------|
| Decimal | quantize("0.0001") | 0.7 → "0.7000" |
| float | 禁止（必須先轉 Decimal） | - |
| string | strip() | " abc " → "abc" |
| list | sorted() | ["b","a"] → ["a","b"] |
| dict | keys sorted | {b:1,a:2} → {"a":2,"b":1} |

### 2.5 序列化格式

- JSON with `sort_keys=True`, `ensure_ascii=False`
- UTF-8 encoding
- 無尾隨換行

### 2.6 Golden Fixtures（3 份）

```python
GOLDEN_FIXTURES = [
    "minimal_single_decision.yaml",      # 最小單筆（基本覆蓋）
    "multiple_decisions_unsorted.yaml",  # 多筆亂序（排序驗證）
    "decimal_unicode_edge.yaml",         # Decimal 精度 + Unicode
]

# 每份包含：
# - input.yaml（原始決策記錄）
# - canonical.json（正規化後的 JSON）
# - canonical.sha256（hash 值）
```

---

## 3. generation/ 模組契約 V1.1

### 3.1 允許的輸入來源

1. `canonical/` - 正規化資料（如 decisions.yaml）
2. `derived/` - 已生成的衍生物（如報表）

### 3.2 禁止的輸入來源

- `raw/` - 原始輸入（必須經過 canonical 層）

### 3.3 輸出目標

- `derived/advisor/` - Stage 3 衍生物
- `derived/reports/` - Phase 3 報表

### 3.4 CI 檢查

```bash
# 預期結果：無輸出
grep -r "from life_capital.io.raw" life_capital/generation/
grep -r "raw_handler" life_capital/generation/
```

### 3.5 模組結構

```
life_capital/generation/
├── __init__.py
├── report_builder.py      # Phase 3 報表（既有）
├── decision_wiki.py       # E2: Wiki 編譯器
├── risk_matrix.py         # E3: 風險矩陣輸出
└── sensitivity_report.py  # E4: 敏感度報告
```

---

## 4. 可評估性模組

### 4.1 Evaluability 定義

```python
# advisor/shared/evaluability.py

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
```

### 4.2 閾值對照表

| comparability_score | 可推薦性 | 可評估性 | 警告訊息 |
|---------------------|----------|----------|----------|
| ≥0.7 | FULL | FULL | None |
| 0.5-0.7 | PARTIAL | FULL | "部分可比：推薦結果僅供參考" |
| 0.3-0.5 | NONE | WARNING | "低可比性：風險評估可能不準確" |
| <0.3 | NONE | SKIP | "不可比：跳過風險與敏感度評估" |

### 4.3 使用方式

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

## 5. 安全邊界（V7）

### 5.1 結構化 Rebuild Command

```python
@dataclass(frozen=True)
class RebuildCommand:
    """結構化重建命令（非字串拼接）"""
    cmd: list[str]         # ["lc", "advisor", "wiki", "--force"]
    cwd: str               # 工作目錄（相對於 data_path）
    env: dict[str, str]    # 環境變數（可選）
    schema_version: str    # 命令格式版本

    def to_safe_string(self) -> str:
        """安全轉換為顯示用字串"""
        return " ".join(shlex.quote(arg) for arg in self.cmd)
```

### 5.2 路徑驗證

```python
def _validate_path(self, path: Path) -> Path:
    """
    嚴格路徑驗證，防止 path traversal

    檢查項目：
    1. 是否在允許目錄下
    2. 副檔名是否在白名單內
    3. 路徑成分是否安全（禁止 ..）
    """
    resolved = path.resolve()
    allowed_base = (self.data_path / self.ALLOWED_BASE).resolve()

    if not str(resolved).startswith(str(allowed_base)):
        raise PathSecurityError(f"路徑超出允許範圍")

    if resolved.suffix not in self.ALLOWED_EXTENSIONS:
        raise PathSecurityError(f"不允許的副檔名")

    for part in resolved.parts:
        if part == ".." or part.startswith(" "):
            raise PathSecurityError(f"不安全的路徑成分")

    return resolved
```

---

## 6. Doctor 檢查項（V7）

### 6.1 Exit Code 規範

```python
class DoctorExitCode(IntEnum):
    SUCCESS = 0          # 無 error/warning
    HAS_WARNINGS = 1     # 有 warning，無 error
    HAS_ERRORS = 2       # 有 error
    EXECUTION_FAILED = 3 # 執行失敗（exception）
```

### 6.2 JSON 輸出格式

```json
{
  "timestamp": "2024-12-29T10:00:00Z",
  "checks_run": ["D01", "D02", "SEC01"],
  "issues": [
    {
      "id": "D02",
      "severity": "warning",
      "file": "derived/advisor/decision_wiki_abc123_1.0.md",
      "message": "content_hash 不符",
      "remediation": "lc advisor wiki --rebuild"
    }
  ],
  "summary": {
    "errors": 0,
    "warnings": 1,
    "info": 0
  }
}
```

### 6.3 檢查項清單

| ID | 名稱 | 嚴重度 | 修復方式 |
|----|------|--------|----------|
| D01 | derived 完整性 | error | 重建 |
| D02 | content_hash 驗證 | warning | `--rebuild` |
| D03 | orphan meta 偵測 | error | 刪除孤兒 |
| D04 | stale derived 偵測 | info | `--rebuild` |
| SEC01 | 路徑安全 | error | 移除非預期檔案 |
| SEC02 | 無子目錄污染 | warning | 檢查並移除 |
| SEC03 | rebuild_command 格式 | error | 重建 |

---

## 7. 測試策略

### 7.1 Wiki 測試（非全檔比對）

```python
def test_wiki_structure():
    """驗證 Wiki 結構正確"""
    content = generate_wiki(decisions)
    assert "# Decision History" in content
    assert "## dec_" in content
    assert "Status:" in content

def test_wiki_contains_required_tokens():
    """驗證必含 token 存在"""
    for dec in decisions:
        assert dec.decision_id in content
        assert dec.status.value in content
```

### 7.2 Sensitivity 不變量測試

```python
def test_sensitivity_invariant_zero_perturbation():
    """perturbation=0 時 delta=0"""
    result = analyze_sensitivity(decision, perturbation=0)
    assert result.delta == 0

def test_sensitivity_monotonicity():
    """利率上升 → 負擔不應下降"""
    result_low = analyze_sensitivity(decision, rate_perturbation=0.01)
    result_high = analyze_sensitivity(decision, rate_perturbation=0.02)
    assert result_high.burden >= result_low.burden
```

### 7.3 Migration Fixtures

```python
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
        assert records is not None
```

---

## 相關文件

| 文件 | 說明 |
|------|------|
| [plan.md](./plan.md) | 主規劃文件 |
| [../../contracts/io_contract.md](../../contracts/io_contract.md) | 全域 IO 契約 |
| [../../../CLAUDE.md](../../../CLAUDE.md) | 專案護欄規則 |
