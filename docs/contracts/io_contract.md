# IO Contract

> 定義輸出檔案格式的變更規則，區分 Normative（必遵守）與 Illustrative（示例）

## 目的

明確定義哪些輸出格式屬於「契約」、哪些屬於「可變內容」，避免改報表文案也被視為 breaking change。

## Normative vs Illustrative 分層

### Normative（規範 - 必遵守）

變更視為 Breaking Change，需 sign-off：

| 項目 | 範例 | 說明 |
|------|------|------|
| 檔名 pattern | `expenses_YYYY_MM.csv` | 必須符合既定格式 |
| 必要欄位 | `canonical/expenses/*.yaml` 的 `date`, `amount` | 刪除會破壞下游 |
| Meta schema | Provenance sidecar 結構 | 自動化工具依賴 |
| Hash 長度/算法 | SHA-256 前 8 字元 | 影響去重邏輯 |
| 路徑契約 | 三層結構 raw/canonical/derived | 影響所有 I/O |

### Illustrative（示例 - 可變）

變更無需審核，不觸發 Breaking：

| 項目 | 範例 | 說明 |
|------|------|------|
| 報表文案 | `derived/reports/*.md` 的標題文字 | 人類閱讀用 |
| 表格欄位顯示順序 | Markdown 表格欄位排序 | 非語意順序 |
| Markdown 格式細節 | 空行、縮排 | 排版用途 |
| JSON/YAML key 輸出順序 | 由 canonicalization 處理 | 序列化細節 |

## Normative 項目詳列

### 1. 檔名 Pattern

```yaml
# canonical/expenses/
expenses_YYYY_MM.yaml  # YYYY: 4位數年, MM: 2位數月

# derived/reports/
monthly_summary_YYYY_MM_<hash12>.md
projection_<hash12>.json

# raw/imports/
YYYYMMDD_HHMMSS_<hash8>.csv
```

**變更規則**：修改 pattern 需版本遷移 + migration script

### 2. 必要欄位

#### canonical/*.yaml

```yaml
# 所有 canonical 檔案必須包含
schema_version: "1.1"  # 必要

# expenses 必要欄位
date: "YYYY-MM-DD"     # 必要
amount: Decimal        # 必要，可負
category: str          # 必要
payer: str            # 必要（V1.1+）
```

#### derived/scenarios/*.json

```json
{
  "scenario_id": "required",
  "base_params": "required object",
  "projections": "required array",
  "provenance": "required object"
}
```

### 3. Provenance Sidecar

```python
@dataclass(frozen=True)
class DerivedProvenance:
    calc_version: str       # 必要：計算邏輯版本
    input_hash: str         # 必要：輸入 SHA-256 hash
    canonical_sources: list # 必要：來源檔案列表
    generated_at: str       # 必要：ISO 8601 時間戳
```

**任何欄位刪除或改名都是 Breaking Change**

### 4. Hash 規格

| 用途 | 算法 | 長度 | 範例 |
|------|------|------|------|
| 去重 key | SHA-256 | 8 hex | `a1b2c3d4` |
| 檔名 hash | SHA-256 | 12 hex | `a1b2c3d4e5f6` |
| 輸入 hash | SHA-256 | 完整 64 hex | `a1b2...` |

**變更算法或長度是 Breaking Change**

### 5. 路徑契約

```
~/.life-capital/
├── raw/                    # 不可變原始輸入
│   ├── imports/            # 匯入檔案
│   └── manual/             # 手動記錄
├── canonical/              # 正規化資料（唯一入口）
│   ├── expenses/           # 按月切檔
│   ├── decisions/          # 決策記憶（Phase 5）
│   │   └── decisions.yaml  # append-only 決策記錄
│   └── .operation_log.jsonl
├── derived/                # 計算結果（可重建）
│   ├── reports/            # 報表
│   ├── scenarios/          # 情境分析
│   └── logs/               # 審計日誌
│       └── advisor_audit.jsonl
├── staging/                # 待處理輸入（Phase 4）
│   └── entries.jsonl
└── proposals/              # 待確認變更
    └── pending/
```

**新增目錄 = Compatible Change（需 sign-off）**
**刪除/改名目錄 = Breaking Change**

### 6. decisions_handler 契約（Phase 5）

```yaml
# canonical/decisions/decisions.yaml
schema_version: "1.0"    # 必要：decisions schema version
version: "1.0"           # 必要：memory version
last_updated: "ISO8601"  # 必要：最後更新時間

records:
  - decision_id: "dec_<ULID>"      # 必要：ULID 格式
    operation_id: "<ULID>"          # 必要：操作追蹤
    created_at: "ISO8601"           # 必要：建立時間
    template_id: "string"           # 必要：決策模板 ID
    status: "pending|applied|reverted|expired"  # 必要
    confidence: "high|medium|low"   # 必要
    comparability_score: float      # 必要：0.0-1.0
    input_hash: "string"            # 必要：輸入 hash
    option_a: object                # 必要：保守方案
    option_b: object                # 必要：進取方案
    risk_tags: array                # 必要：風險標籤
    risk_explanation: string        # 必要：風險說明
```

**寫入規則**:
- 只有 `lc apply` / `lc undo` 可調用 `decisions_handler`
- 回滾使用 append-only 語意（新增 reverted 記錄，不修改既有）
- 每次寫入必須提供 `operation_id`

## Illustrative 項目詳列

### 1. 報表文案

```markdown
<!-- 可變：標題文字 -->
# 2024年12月支出摘要

<!-- 可變：說明段落 -->
本月總支出較上月增加 5%...

<!-- 可變：表格標題 -->
| 類別 | 金額 | 占比 |
```

### 2. 表格欄位順序

非語意順序可自由調整：

```markdown
<!-- 以下兩種等價，順序可變 -->
| 類別 | 金額 | 占比 |
| 金額 | 類別 | 占比 |
```

### 3. Markdown 格式

```markdown
<!-- 以下細節可變 -->
- 標題層級（# vs ##）
- 空行數量
- 縮排字元（空格 vs tab）
- list marker（- vs *）
```

### 4. JSON/YAML 序列化順序

由 canonicalization pipeline 處理，比對時忽略：

```yaml
# 以下兩種 canonicalize 後等價
{a: 1, b: 2}
{b: 2, a: 1}
```

## Breaking Changes 處理流程

### 偵測

1. CI 執行 `tests/contracts/test_io_contract.py`
2. 比對 Normative 項目的 baseline

### 處理

1. **檔名 pattern 變更**：
   - 建立 migration script
   - 提供 rollback 方案
   - 雙人 CODEOWNERS review

2. **必要欄位變更**：
   - 更新 Schema Contract
   - 確保向後相容或 migration

3. **Hash 規格變更**：
   - 禁止（除非重大版本升級）

## 測試機制

### Normative 測試

```python
def test_filename_pattern():
    """驗證檔名符合 Normative pattern"""
    for file in canonical_expenses_dir.glob("*.yaml"):
        assert re.match(r"expenses_\d{4}_\d{2}\.yaml", file.name)

def test_provenance_required_fields():
    """驗證 Provenance 必要欄位存在"""
    for file in derived_dir.glob("**/*.meta.json"):
        prov = json.load(file)
        assert "calc_version" in prov
        assert "input_hash" in prov
        assert "generated_at" in prov
```

### Illustrative 不測試

報表內容、格式細節**不應**有對應測試，以避免：
- 修改文案觸發 CI 失敗
- 增加維護負擔
- 阻礙 UX 改善

## 7. Canonicalization Normative（V7 規範）

### 7.1 目的

定義決策記憶輸入的正規化規則，確保 hash 穩定性與可重現性。

### 7.2 Canonicalization Version

```python
CANONICALIZATION_VERSION = "1.0"
# 變更此版本號 = 預期所有 input_hash 變更
```

**版本變更規則**：任何影響正規化結果的規則修改都必須升版。

### 7.3 欄位白名單（按此順序）

| # | 欄位名稱 | 型別 | 處理規則 |
|---|----------|------|----------|
| 1 | decision_id | string | 保持原值 |
| 2 | template_id | string | strip() |
| 3 | status | enum | enum value as string |
| 4 | confidence | enum | enum value as string |
| 5 | comparability_score | Decimal | quantize("0.0001") |
| 6 | option_a | object | 遞迴 canonicalize |
| 7 | option_b | object | 遞迴 canonicalize |
| 8 | risk_tags | list[string] | sorted alphabetically |

### 7.4 排除欄位

以下欄位在正規化時會被移除（不參與 hash 計算）：

- `created_at`, `generated_at` - 時間戳（環境相依）
- `_seq`, `operation_id` - 內部追蹤 ID
- `file`, `path` - 檔案路徑（環境相依）
- `reverted_at`, `reverted_by` - 回滾追蹤（不影響決策本質）

### 7.5 數值處理規則

| 型別 | 規則 | 範例 |
|------|------|------|
| Decimal | quantize("0.0001") | 0.7 → "0.7000" |
| float | **禁止**（必須先轉 Decimal） | - |
| string | strip() | " abc " → "abc" |
| list | sorted() | ["b","a"] → ["a","b"] |
| dict | keys sorted recursively | {b:1,a:2} → {"a":2,"b":1} |
| enum | .value as string | Status.PENDING → "pending" |

### 7.6 序列化格式

```python
json.dumps(
    canonical_data,
    sort_keys=True,
    ensure_ascii=False,
    separators=(',', ':'),  # 緊湊格式，無空格
    indent=None,             # 無縮排
)
```

**重要細節**：
- UTF-8 encoding
- 無尾隨換行
- sort_keys=True（保證順序）
- ensure_ascii=False（支援 Unicode）

### 7.7 Golden Fixtures（3 份測試 Baseline）

```
tests/fixtures/canonicalization/
├── minimal_single_decision/
│   ├── input.yaml          # 原始決策記錄
│   ├── canonical.json      # 正規化後的 JSON
│   └── canonical.sha256    # hash 值（純文字）
├── multiple_decisions_unsorted/
│   ├── input.yaml
│   ├── canonical.json
│   └── canonical.sha256
└── decimal_unicode_edge/
    ├── input.yaml
    ├── canonical.json
    └── canonical.sha256
```

**測試目的**：
- `minimal_single_decision` - 基本正規化正確性
- `multiple_decisions_unsorted` - 排序邏輯驗證
- `decimal_unicode_edge` - Decimal 精度與 Unicode 處理

### 7.8 Hash 穩定性驗證

```python
def test_canonicalization_stable():
    """驗證 canonicalization hash 穩定"""
    for golden in GOLDEN_FIXTURES:
        expected_hash = golden.read_hash()
        actual_hash = canonicalize_and_hash(golden.input)
        assert actual_hash == expected_hash, f"Hash 漂移: {golden.name}"
```

### 7.9 Breaking Change 定義

以下變更視為 Breaking Change：

| 變更類型 | 範例 | 處理方式 |
|----------|------|----------|
| 欄位順序調整 | 將 status 移到第 1 位 | 升版 + 全部 rehash |
| 數值精度變更 | quantize("0.01") → quantize("0.001") | 升版 + migration |
| 排序規則變更 | 改用 locale-aware sort | 升版 + 更新 goldens |
| 序列化格式變更 | 改用 YAML 或加入縮排 | 升版 + 重建 |

## 8. AdvisorDerivedProvenance Schema（V7 版）

### 8.1 目的

定義 Stage 3 衍生物（決策 Wiki、風險矩陣、敏感度報告）的 Provenance metadata。

### 8.2 Schema 定義

```python
@dataclass(frozen=True)
class RebuildCommand:
    """結構化重建命令（非字串拼接）"""
    cmd: list[str]         # ["lc", "advisor", "wiki", "--force"]
    cwd: str               # 工作目錄（相對於 data_path）
    env: dict[str, str]    # 環境變數（可選，預設 {}）
    schema_version: str    # 命令格式版本（固定 "1.0"）

    def to_safe_string(self) -> str:
        """安全轉換為顯示用字串"""
        import shlex
        return " ".join(shlex.quote(arg) for arg in self.cmd)

@dataclass(frozen=True)
class AdvisorDerivedProvenance:
    """Stage 3 衍生物的 Provenance（V7 版）"""
    artifact_type: str                 # "decision_wiki" | "risk_matrix" | "sensitivity"
    schema_version: str                # "1.0"
    calc_version: str                  # 計算邏輯版本（如 "wiki_v1.0"）
    canonicalization_version: str      # V7: 輸入正規化版本
    input_hash: str                    # 輸入內容 SHA-256 hash（完整 64 hex）
    canonical_sources: list[str]       # 使用的 canonical 檔案列表
    generated_at: str                  # ISO 8601 時間戳
    rebuild_command: RebuildCommand    # V7: 結構化重建命令
    content_hash: str                  # V6: 輸出內容 hash（SHA-256 完整 64 hex）
    redaction_profile_version: str     # V6: 去識別規則版本（如 "1.0"）
```

### 8.3 必要欄位（Normative）

所有欄位都是必要的，缺少任何一個都視為格式錯誤。

### 8.4 Breaking Change 處理

| 欄位變更 | 處理方式 |
|----------|----------|
| 新增欄位 | 更新 schema_version |
| 刪除欄位 | Breaking change，需 migration |
| 改名欄位 | Breaking change，需 migration |

## 9. 路徑安全驗證（V7 規範）

### 9.1 目的

防止 path traversal 攻擊與檔案系統污染。

### 9.2 AdvisorDerivedHandler 路徑規則

```python
ALLOWED_BASE = "derived/advisor"
ALLOWED_EXTENSIONS = {".md", ".json", ".meta.json"}

def _validate_path(self, path: Path) -> Path:
    """
    嚴格路徑驗證，防止 path traversal

    檢查項目：
    1. 是否在允許目錄下（ALLOWED_BASE）
    2. 副檔名是否在白名單內
    3. 路徑成分是否安全（禁止 ..、空格開頭）

    Raises:
        PathSecurityError: 不安全的路徑
    """
    resolved = path.resolve()
    allowed_base = (self.data_path / self.ALLOWED_BASE).resolve()

    # 檢查 1: 是否在允許範圍內
    if not str(resolved).startswith(str(allowed_base)):
        raise PathSecurityError(f"路徑超出允許範圍: {resolved}")

    # 檢查 2: 副檔名白名單
    if resolved.suffix not in self.ALLOWED_EXTENSIONS:
        raise PathSecurityError(f"不允許的副檔名: {resolved.suffix}")

    # 檢查 3: 路徑成分安全性
    for part in resolved.parts:
        if part == ".." or part.startswith(" "):
            raise PathSecurityError(f"不安全的路徑成分: {part}")

    return resolved
```

### 9.3 禁止的路徑模式

| 模式 | 範例 | 原因 |
|------|------|------|
| 包含 `..` | `../../../etc/passwd` | path traversal |
| 絕對路徑超出範圍 | `/tmp/malicious.md` | 跨目錄攻擊 |
| 空格開頭的成分 | `derived/advisor/ evil.md` | 隱藏檔案 |
| 不在白名單的副檔名 | `script.sh`, `.exe` | 程式碼注入 |

### 9.4 測試要求

```python
def test_path_traversal_blocked():
    """測試 ../ 攻擊被阻擋"""
    with pytest.raises(PathSecurityError):
        handler._validate_path(Path("derived/advisor/../../secrets.txt"))

def test_absolute_path_outside_base_blocked():
    """測試絕對路徑超出範圍被阻擋"""
    with pytest.raises(PathSecurityError):
        handler._validate_path(Path("/tmp/evil.md"))

def test_allowed_extensions_only():
    """測試只允許白名單副檔名"""
    with pytest.raises(PathSecurityError):
        handler._validate_path(Path("derived/advisor/script.sh"))
```

## 10. Stage 3 Advisor Enhancements（V1.1 規範）

### 10.1 DecisionRecord V1.1 Schema

#### 新增欄位

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `decision_rationale` | Optional[str] | ❌ | 決策理由說明（V1.1+）|
| `reverted_from_decision_id` | Optional[str] | ❌ | 回滾來源決策 ID（V1.1+）|

#### V1.0 → V1.1 相容性

```python
# V1.0 檔案讀取時，新欄位預設為 None
def _parse_record(data: dict) -> DecisionRecord:
    return DecisionRecord(
        # ... V1.0 欄位 ...
        decision_rationale=data.get("decision_rationale"),  # V1.1 fallback
        reverted_from_decision_id=data.get("reverted_from_decision_id")  # V1.1 fallback
    )

# V1.1 寫入時，只寫非 None 欄位（避免污染 V1.0 格式）
def _record_to_dict(record: DecisionRecord) -> dict:
    data = {
        # ... V1.0 欄位 ...
    }
    if record.decision_rationale is not None:
        data["decision_rationale"] = record.decision_rationale
    if record.reverted_from_decision_id is not None:
        data["reverted_from_decision_id"] = record.reverted_from_decision_id
    return data
```

### 10.2 狀態轉換規則（State Machine）

```python
ALLOWED_TRANSITIONS = {
    (None, DecisionStatus.PENDING),        # 新建決策
    (DecisionStatus.PENDING, DecisionStatus.APPLIED),      # 套用決策
    (DecisionStatus.APPLIED, DecisionStatus.REVERTED),     # 回滾決策
    (DecisionStatus.PENDING, DecisionStatus.REVERTED),     # 取消決策
}

def _validate_transition(from_status, to_status):
    if (from_status, to_status) not in ALLOWED_TRANSITIONS:
        raise InvalidTransitionError(f"非法狀態轉換: {from_status} → {to_status}")
```

**禁止的轉換**:
- `REVERTED → APPLIED` - 不可復原回滾
- `APPLIED → PENDING` - 不可撤銷已套用的決策
- 任何跳躍式轉換（必須循序）

### 10.3 ID 重複檢查機制

```python
def _check_duplicate_decision_id(self, decision_id: str):
    """檢查 decision_id 是否重複"""
    existing_ids = {r.decision_id for r in self.read_all()}
    if decision_id in existing_ids:
        raise DuplicateDecisionIDError(f"Decision ID 已存在: {decision_id}")
```

**規則**:
- 在 `write_decision()` 前必須檢查
- append-only 語意（不允許覆寫）
- 使用 ULID 格式確保唯一性

### 10.4 測試要求

```python
def test_v10_v11_backward_compatibility():
    """V1.0 檔案可被 V1.1 handler 讀取"""
    handler_v11 = DecisionsHandler(path)
    record_v10 = handler_v11.read_from_v10_file("tests/fixtures/decisions/v1.0_minimal.yaml")

    assert record_v10.decision_rationale is None  # V1.0 無此欄位
    assert record_v10.reverted_from_decision_id is None

def test_v11_fields_only_written_when_not_none():
    """V1.1 欄位只在非 None 時寫入"""
    record = DecisionRecord(..., decision_rationale=None)
    data = handler._record_to_dict(record)

    assert "decision_rationale" not in data  # 不應出現
```

## 11. Evaluability Module（共享模組規範）

### 11.1 目的

定義決策的「可推薦性」與「可評估性」雙維度評分系統。

### 11.2 Recommendability 閾值

```python
class RecommendabilityLevel(Enum):
    FULL = "full"       # comparability >= 0.7 - 可直接推薦
    PARTIAL = "partial" # 0.5 <= comparability < 0.7 - 謹慎推薦
    NONE = "none"       # comparability < 0.5 - 不推薦
```

| 級別 | 閾值 | 說明 |
|------|------|------|
| FULL | >= 0.7 | 高度可比較，可信度高 |
| PARTIAL | 0.5-0.7 | 中度可比較，需額外驗證 |
| NONE | < 0.5 | 低可比較性，不建議採用 |

### 11.3 Evaluability 閾值

```python
class EvaluabilityLevel(Enum):
    FULL = "full"       # comparability >= 0.5 - 可分析
    WARNING = "warning" # 0.3 <= comparability < 0.5 - 警告
    SKIP = "skip"       # comparability < 0.3 - 跳過
```

| 級別 | 閾值 | 說明 |
|------|------|------|
| FULL | >= 0.5 | 可進行完整分析 |
| WARNING | 0.3-0.5 | 可分析但品質有疑慮 |
| SKIP | < 0.3 | 資料品質不足，跳過分析 |

### 11.4 雙維度決策矩陣

| Comparability | Recommendability | Evaluability | 行動 |
|---------------|------------------|--------------|------|
| >= 0.7 | FULL | FULL | 直接推薦 + 完整分析 |
| 0.5-0.7 | PARTIAL | FULL | 謹慎推薦 + 完整分析 |
| 0.3-0.5 | NONE | WARNING | 不推薦 + 警告分析 |
| < 0.3 | NONE | SKIP | 不推薦 + 跳過分析 |

### 11.5 使用範例

```python
from life_capital.advisor.shared.evaluability import evaluate_decision

def analyze_sensitivity(decision: DecisionRecord) -> Optional[SensitivityAnalysis]:
    """敏感度分析（只分析 comparability >= 0.3 的決策）"""
    eval_result = evaluate_decision(decision)

    if eval_result.is_evaluable == EvaluabilityLevel.SKIP:
        return None  # 跳過低品質決策

    # 繼續分析...
    return SensitivityAnalysis(...)

def assess_risk(decision: DecisionRecord) -> Optional[RiskAssessment]:
    """風險評估（只評估 comparability >= 0.3 的決策）"""
    eval_result = evaluate_decision(decision)

    if eval_result.comparability < Decimal("0.3"):
        return None  # 跳過

    if eval_result.is_evaluable == EvaluabilityLevel.WARNING:
        warnings.append(eval_result.warning_message)

    return RiskAssessment(...)
```

### 11.6 Breaking Change 規則

| 變更類型 | 處理方式 |
|----------|----------|
| 閾值調整（如 0.7 → 0.75） | 升版 + 更新所有使用處 |
| 新增級別 | 相容變更（需文件說明） |
| 刪除級別 | Breaking change |
| 改名級別（如 FULL → HIGH） | Breaking change |

## 相關檔案

| 用途 | 路徑 |
|------|------|
| IO 契約測試 | `tests/contracts/test_io_contract.py` |
| Canonicalization 測試 | `tests/contracts/test_canonicalization_goldens.py` |
| 路徑常數 | `life_capital/io/registry.py` |
| 檔名 pattern | `life_capital/io/registry.py` |
| AdvisorDerivedHandler | `life_capital/io/advisor_derived_handler.py` |
| Provenance models | `life_capital/models/provenance.py` |
| DecisionsHandler | `life_capital/io/decisions_handler.py` |
| Evaluability module | `life_capital/advisor/shared/evaluability.py` |
