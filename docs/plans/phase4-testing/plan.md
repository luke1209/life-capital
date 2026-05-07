# Phase 4 提前開發計劃 - 用測試取代兩週等待

> **目標**: 建立自動化測試套件，證明 schema 穩定性，取代 2 週觀察期
> **策略**: Schema 契約測試 + 行為回歸測試 + 隔離開發 + 制度化流程 + 可運作 CI
> **預計效果**: 從 14 天縮短至 1.5-2 天，護欄確實生效且可長期維護

---

## LLM 閱讀順序建議（不分拆文件）

1. **V4.2 最終計劃**（核心藍圖）
2. **執行步驟（優先順序）+ 驗收標準**（落地與驗證）
3. **CI 護欄 + Gate 規則**（保證縮短等待期）
4. **Contract 規格（Schema + IO + Interface Policy）**（定義何謂變更）
5. **測試細節（Schema Diff / Golden Data / Mock-Real）**（技術實作）
6. **維護流程 + 失敗分級 + 回滾策略**（長期可運作）
7. **風險、時間比較、版本歷程**（背景與決策理由）

---

## V4.2 最終計劃

### Step 0: 定義 Contract 規格（V4.1 拆分，1.5 小時）

**目的**：明確定義什麼是「不可接受的變動」

#### 0A: Schema Contract（模型結構契約）

**輸出檔案**: `docs/contracts/schema_contract.md`

**Breaking Changes（測試失敗，無例外）**：
- 欄位刪除或改名
- 型別變更（str→int, Optional→Required）
- Enum 值刪除
- 驗證規則收緊（min_length 增加）
- **V4.1 新增**：預設值變更若影響序列化輸出、hash、排序

**Compatible Changes（需 Sign-off）**：
- 新增 Optional 欄位
- Enum 值新增
- 驗證規則放寬
- **僅**不影響輸出的預設值變更

#### 0B: IO Contract（輸出檔案格式契約）

**輸出檔案**: `docs/contracts/io_contract.md`

**V4.2 關鍵改進：Normative vs Illustrative 分層**

| 分類 | 定義 | 範例 | 變更處理 |
|------|------|------|----------|
| **Normative（規範）** | 必遵守，變更視為 Breaking | 檔名 pattern、必要欄位、meta schema、hash 長度/算法、路徑契約 | 需 sign-off |
| **Illustrative（示例）** | 可變，不觸發 Breaking | 報表文案、表格排序、欄位顯示順序、markdown 格式 | 無需審核 |

**Normative 項目（V4.2 明確列舉）**：
- `canonical/*.yaml` 必要欄位與型別
- `derived/scenarios/*.json` 結構 schema
- Provenance sidecar 必要欄位（`calc_version`, `input_hash`, `generated_at`）
- Hash 長度（SHA-256 前 8 字元）與算法
- 檔名 pattern（如 `expenses_YYYY-MM.yaml`）
- 路徑契約（三層結構：raw/canonical/derived）

**Illustrative 項目（V4.2 明確排除）**：
- `derived/reports/*.md` 的文案內容與排版
- 表格欄位的顯示順序（非語意）
- Markdown 格式細節（空行、縮排）
- JSON/YAML 的 key 輸出順序（由 canonicalization 處理）

**Breaking Changes（僅適用 Normative）**：
- 檔名 pattern 變更
- 必要欄位刪除或改名
- Hash 長度/演算法變更
- Provenance 結構變更

### Step 1: Schema Diff 測試（V4.1 強化，2-3 小時）

**建立檔案**: `tests/contracts/test_schema_stability.py`

#### V4.1 關鍵改進：Baseline 不可由測試寫入

```python
import json
from pathlib import Path
import pytest

BASELINE_DIR = Path("tests/contracts/baselines/")

def test_schema_json_schema_unchanged():
    """完整 JSON Schema 比對，不只欄位名稱"""
    for model_cls in [ExpenseRecord, MonthlyExpenses, ...]:
        baseline_path = BASELINE_DIR / f"{model_cls.__name__}.json"

        # V4.1: Baseline 必須存在，不可由測試自動建立
        if not baseline_path.exists():
            pytest.fail(
                f"Baseline not found: {baseline_path}\n"
                f"Run: python scripts/update_schema_baseline.py --model {model_cls.__name__}"
            )

        baseline = json.loads(baseline_path.read_text())
        current_schema = normalize_schema(model_cls.model_json_schema())
        diff = schema_diff(baseline, current_schema)
        assert not diff.has_breaking_changes, f"Breaking change: {diff}"
```

#### V4.2 強化：語意正規化（取代單純 key 排序）

**建立檔案**: `scripts/schema_normalize.py`

**問題**：V4.1 的 `normalize_schema()` 只排序 keys，仍有大量噪音來源：
- `$defs` 展開/引用形態差異
- `title`/`description`/`examples` 等 metadata
- `anyOf`/`oneOf` 子項順序
- `default` 的 Decimal 序列化格式差異

**V4.2 解法：兩階段正規化**

```python
# scripts/schema_normalize.py

# 語意白名單：只保留這些欄位，其他全部剔除
SEMANTIC_WHITELIST = {
    "type", "properties", "required", "items",
    "enum", "const", "default",
    "pattern", "format",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "minItems", "maxItems",
    "anyOf", "oneOf", "allOf", "$ref",
    "additionalProperties", "nullable"
}

def normalize_schema(schema: dict) -> dict:
    """語意正規化：兩階段處理"""
    # Phase 1: 語意過濾（剔除非契約欄位）
    filtered = semantic_filter(schema)
    # Phase 2: 結構正規化（穩定排序）
    return structural_normalize(filtered)

def semantic_filter(schema: dict) -> dict:
    """Phase 1: 只保留語意白名單欄位"""
    if not isinstance(schema, dict):
        return schema

    result = {}
    for key, value in schema.items():
        if key in SEMANTIC_WHITELIST:
            if isinstance(value, dict):
                result[key] = semantic_filter(value)
            elif isinstance(value, list):
                result[key] = [semantic_filter(v) if isinstance(v, dict) else v for v in value]
            else:
                result[key] = value
    return result

def structural_normalize(schema: dict) -> dict:
    """Phase 2: 結構正規化（穩定排序）"""
    if isinstance(schema, dict):
        return {k: structural_normalize(v) for k, v in sorted(schema.items())}
    if isinstance(schema, list):
        # 對 anyOf/oneOf 內的 schema 片段用 stable hash 排序
        if all(isinstance(item, dict) for item in schema):
            return sorted(
                [structural_normalize(v) for v in schema],
                key=lambda x: json.dumps(x, sort_keys=True)
            )
        return [structural_normalize(v) for v in schema]
    return schema
```

**測試只呼叫此模組**：
```python
from scripts.schema_normalize import normalize_schema

def test_schema_json_schema_unchanged():
    current_schema = normalize_schema(model_cls.model_json_schema())
    # ...
```

#### V4.1 新增：環境鎖定

```toml
# pyproject.toml
[tool.uv]
python = "3.12"  # Pin Python 版本

[project.dependencies]
pydantic = "==2.10.3"  # Pin Pydantic 版本
```

**測試範圍**（V2 擴充）：
- ✅ 欄位名稱與數量
- ✅ 欄位型別（type, anyOf）
- ✅ Required vs Optional（nullable）
- ✅ Enum 值列表
- ✅ 驗證規則（minLength, pattern, ge, le）
- ✅ 預設值（V4.1：影響輸出者視同 Breaking）

### Step 2: 行為不變量測試（拆分，3-4 小時）

**建立檔案**: `tests/contracts/test_phase_contracts.py`

**Part A: 結構性契約**

| Phase | 契約 | 測試 |
|-------|------|------|
| Phase 0 | raw→canonical→derived 閉環 | `test_three_layer_roundtrip` |
| Phase 0 | lc undo 可回滾 | `test_undo_rollback` |
| Phase 1 | 去重結果一致 | `test_dedupe_deterministic` |
| Phase 1 | raw 可重建 canonical | `test_rebuild_canonical` |

**Part B: Golden Data 回歸測試（V2 新增，V3 精細化）**

```python
# 使用固定 seed data 驗證行為不變
GOLDEN_DATA_DIR = Path("tests/contracts/golden/")

def test_dedupe_golden_data():
    """去重結果必須與 baseline 完全一致"""
    input_csv = GOLDEN_DATA_DIR / "dedupe_input.csv"
    expected_output = GOLDEN_DATA_DIR / "dedupe_expected.yaml"

    actual = run_dedupe(input_csv)
    assert actual == load_yaml(expected_output)

def test_rebuild_golden_data():
    """重建結果必須與 baseline 一致"""
    # ...
```

**V4.1 改進：可容忍差異定義**

| 欄位類型 | 可容忍差異 | 不可容忍差異 | V4.1 處理方式 |
|----------|------------|--------------|---------------|
| 時間戳 | 產生時間（generated_at） | 業務日期（date） | 分別比對 |
| 排序 | 同一層級順序 | 父子關係變動 | normalize 後比對 |
| 金額 | **無** | **任何差異** | **quantize 後 exact** |
| 字串 | 無 | 任何差異 | exact compare |

#### V4.2 強化：完整 Canonicalization Pipeline

**建立檔案**: `scripts/golden_data_diff.py`

**問題**：即使金額 quantize 後 exact compare，仍有序列化細節干擾：
- dict key order（YAML dump 順序）
- list 的無關排序
- newline、trailing spaces
- Decimal 字串化格式（"100" vs "100.00"）

**V4.2 解法：Canonicalization Pipeline**

```python
# scripts/golden_data_diff.py

from decimal import Decimal
from life_capital.calculators.rounding import quantize
import json
import yaml

# 允許排序的 list 欄位白名單（依 stable key 排序）
LIST_SORT_WHITELIST = {
    "transactions": "stable_id",      # 依 stable_id 排序
    "expenses": "date",               # 依 date 排序
    "categories": None,               # 字串 list，直接排序
}

# 禁止排序的 list（順序有語意）
LIST_PRESERVE_ORDER = {
    "children",      # 家庭成員順序可能有意義
    "targets",       # 目標優先順序有意義
}

def canonicalize(data: dict) -> dict:
    """完整 canonicalization pipeline"""
    # Step 1: 深拷貝避免修改原資料
    data = deep_copy(data)
    # Step 2: 正規化金額（quantize）
    data = normalize_amounts(data)
    # Step 3: 正規化 list（穩定排序）
    data = normalize_lists(data)
    # Step 4: 正規化 dict keys（排序）
    data = normalize_dict_keys(data)
    # Step 5: 移除可忽略欄位
    data = remove_ignorable_fields(data)
    return data

def normalize_amounts(data, path=""):
    """Step 2: 所有金額 quantize 後轉為標準字串格式"""
    if isinstance(data, dict):
        return {k: normalize_amounts(v, f"{path}.{k}") for k, v in data.items()}
    if isinstance(data, list):
        return [normalize_amounts(v, f"{path}[]") for v in data]
    if isinstance(data, (int, float, Decimal)):
        return str(quantize(Decimal(str(data))))
    return data

def normalize_lists(data, path=""):
    """Step 3: 依白名單規則排序 list"""
    if isinstance(data, dict):
        return {k: normalize_lists(v, k) for k, v in data.items()}
    if isinstance(data, list):
        normalized = [normalize_lists(v, path) for v in data]
        # 檢查是否在白名單
        if path in LIST_SORT_WHITELIST:
            sort_key = LIST_SORT_WHITELIST[path]
            if sort_key is None:
                return sorted(normalized)
            return sorted(normalized, key=lambda x: x.get(sort_key, ""))
        # 檢查是否需保留順序
        if path in LIST_PRESERVE_ORDER:
            return normalized
        # 預設：如果是 dict list，用 stable hash 排序
        if all(isinstance(item, dict) for item in normalized):
            return sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True))
        return normalized
    return data

def normalize_dict_keys(data):
    """Step 4: 遞迴排序 dict keys"""
    if isinstance(data, dict):
        return {k: normalize_dict_keys(v) for k, v in sorted(data.items())}
    if isinstance(data, list):
        return [normalize_dict_keys(v) for v in data]
    return data

def remove_ignorable_fields(data):
    """Step 5: 移除 generated_at 等時間戳"""
    IGNORABLE = {"generated_at", "created_at", "updated_at"}
    if isinstance(data, dict):
        return {k: remove_ignorable_fields(v) for k, v in data.items() if k not in IGNORABLE}
    if isinstance(data, list):
        return [remove_ignorable_fields(v) for v in data]
    return data

def golden_compare(expected_path: str, actual: dict) -> tuple[bool, str]:
    """Golden Data 比對入口"""
    expected = yaml.safe_load(open(expected_path))
    expected_c = canonicalize(expected)
    actual_c = canonicalize(actual)

    if expected_c == actual_c:
        return True, ""

    # 產出 diff 報告
    diff = generate_diff(expected_c, actual_c)
    return False, diff
```

**原因**：Life Capital 專案強調 Decimal 精度與 determinism，完整 pipeline 確保比對不受序列化細節干擾。

**V3 新增：邊緣情境測試**

```python
def test_empty_input():
    """空輸入不應崩潰"""
    assert run_dedupe(empty_csv) == []

def test_extreme_large_input():
    """極大輸入（10K 筆）應正常處理"""
    assert len(run_dedupe(large_csv)) <= 10000

def test_invalid_enum_handling():
    """非法 enum 值應拋出明確錯誤"""
    with pytest.raises(ValidationError, match="category"):
        run_import(invalid_category_csv)
```

### Step 3: CI 護欄 + Sign-off Gate（V4.1 強化，1.5-2 小時）

**修改**: `.github/workflows/` + `CODEOWNERS` + Branch Protection

#### V4.1 新增：可執行權限模型

**CODEOWNERS 設定**：
```
# .github/CODEOWNERS
docs/contracts/*           @core-maintainers
tests/contracts/*          @core-maintainers
life_capital/models/*      @core-maintainers
tests/contracts/baselines/ @core-maintainers
tests/contracts/golden/    @core-maintainers
```

**Protected Branch Rules**：
```yaml
# Required status checks:
- contract-tests      # Schema + Golden + Mock 測試
- regression-tests    # Phase 0-3 回歸

# Branch protection:
- Require pull request reviews: 1
- Require CODEOWNERS review for: docs/contracts/*, tests/contracts/*
- Require schema-approved label if schema_diff_report.md exists
```

#### 必擋 vs 可覆核規則（機器可判定）

| 規則類型 | 情境 | 動作 | 證據要求 | 判定方式 |
|----------|------|------|----------|----------|
| **必擋** | Schema breaking change | 自動阻止 | - | `diff.has_breaking_changes` |
| **必擋** | Golden Data 回歸失敗 | 自動阻止 | - | pytest exit code |
| **必擋** | Mock/Real 一致性失敗 | 自動阻止 | - | pytest exit code |
| **可覆核** | Compatible schema change | 需 label | diff 報告 | `schema_diff_report.md` 非空 |
| **可覆核** | Baseline 更新 | 需 CODEOWNERS | PR 描述 | 偵測 baselines/ 變更 |

**自動產出證據**：
- `schema_diff_report.md` - 欄位/型別變更清單
- `golden_data_diff.md` - 回歸測試差異詳情
- `mock_consistency_report.md` - Mock/Real 差異

```yaml
# .github/workflows/contract-check.yml
name: Contract Tests
on: [pull_request]

jobs:
  contract-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # V4.2 修正：使用 paths-filter 偵測變更路徑
      - name: Detect changed paths
        id: changes
        uses: dorny/paths-filter@v3
        with:
          filters: |
            baselines:
              - 'tests/contracts/baselines/**'
            golden:
              - 'tests/contracts/golden/**'
            schema:
              - 'life_capital/models/**'
            contracts:
              - 'docs/contracts/**'

      - name: Run contract tests
        run: |
          uv run pytest tests/contracts/ -v

      - name: Check schema changes
        run: |
          python scripts/check_schema_diff.py

      # V4.2 修正：使用 github-script 讀取 labels（避免 gh 權限問題）
      - name: Verify schema-approved label
        if: steps.changes.outputs.schema == 'true'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            if (!fs.existsSync('schema_diff_report.md')) {
              console.log('No schema changes detected');
              return;
            }

            const { data: pr } = await github.rest.pulls.get({
              owner: context.repo.owner,
              repo: context.repo.repo,
              pull_number: context.payload.pull_request.number
            });

            const hasLabel = pr.labels.some(l => l.name === 'schema-approved');
            if (!hasLabel) {
              core.setFailed("Schema changes detected but 'schema-approved' label is missing");
            }

      # V4.2 修正：使用 paths-filter 結果而非 changed_files
      - name: Verify baseline changes require CODEOWNERS
        if: steps.changes.outputs.baselines == 'true'
        run: |
          echo "::notice::Baseline changes detected - CODEOWNERS approval required"
```

### Step 4: Phase 4 隔離開發環境（V4.1 調整，2-3 小時）

**建立**:
- `feature/phase4-capture` branch
- `life_capital/interfaces/` - 穩定介面層（V4.1 新增）
- `tests/fixtures/mock_canonical.py` - Mock 層
- `life_capital/capture/__init__.py` - 新模組骨架

#### V4.1 改進：透過 Interface 層隔離（替代完全禁止 import）

```python
# life_capital/interfaces/canonical_reader.py
from typing import Protocol
from decimal import Decimal

class CanonicalReader(Protocol):
    """Phase 4 唯一可依賴的介面，不依賴 concrete models"""

    def get_categories(self) -> list[str]:
        """取得所有支出類別"""
        ...

    def get_expense_policy(self) -> dict[str, Decimal]:
        """取得支出政策比例"""
        ...

    def save_proposal(self, proposal: dict) -> str:
        """儲存提案，回傳 proposal_id"""
        ...
```

**隔離規則調整**：
- ❌ 舊規則：`capture/` 完全禁止 import `models/`
- ✅ V4.1：`capture/` 只能依賴 `interfaces/`，不可直接依賴 `models/`

```bash
# 驗證隔離（V4.1 調整）
grep -r "from life_capital.models" life_capital/capture/  # 應該為空
grep -r "from life_capital.interfaces" life_capital/capture/  # 應該有
```

#### V4.2 新增：Interface Version Policy

**輸出檔案**: `docs/contracts/interface_policy.md`

**問題**：Interface 層也會演進，若無版本策略，會成為新的漂移源。

**規則**：

| 變更類型 | 定義 | 處理方式 |
|----------|------|----------|
| **Breaking** | 刪除方法、改變方法簽名、改變返回型別 | 禁止（需版本遷移） |
| **Compatible** | 新增方法（提供 default 或 NotImplementedError） | 需 sign-off |
| **Internal** | 實作細節變更（不影響 Protocol） | 無需審核 |

**Protocol 變更規範**：

```python
# life_capital/interfaces/canonical_reader.py

from typing import Protocol, runtime_checkable

@runtime_checkable
class CanonicalReader(Protocol):
    """Phase 4 唯一可依賴的介面

    Version: 1.0
    Breaking changes require major version bump.
    """

    def get_categories(self) -> list[str]:
        """取得所有支出類別"""
        ...

    def get_expense_policy(self) -> dict[str, Decimal]:
        """取得支出政策比例"""
        ...

    def save_proposal(self, proposal: dict) -> str:
        """儲存提案，回傳 proposal_id"""
        ...

    # V4.2: 新增方法時提供 default（Compatible change）
    def get_version(self) -> str:
        """取得介面版本（V1.1 新增）"""
        return "1.0"  # default implementation
```

**CI 驗證**：

```python
# tests/contracts/test_interface_stability.py

def test_interface_methods_unchanged():
    """驗證 Protocol 方法簽名未變"""
    from life_capital.interfaces.canonical_reader import CanonicalReader
    import inspect

    baseline_path = Path("tests/contracts/baselines/CanonicalReader.json")
    if not baseline_path.exists():
        pytest.fail("Run: python scripts/update_interface_baseline.py")

    baseline = json.loads(baseline_path.read_text())
    current = extract_protocol_signature(CanonicalReader)

    # 只檢查 breaking changes（方法刪除或簽名變更）
    for method_name, sig in baseline.items():
        assert method_name in current, f"Method {method_name} was removed (breaking)"
        assert current[method_name] == sig, f"Method {method_name} signature changed (breaking)"
```

**V2 新增：Mock/Real 一致性測試**

```python
# tests/contracts/test_mock_consistency.py

class TestMockCanonicalConsistency:
    """確保 Mock 與 Real 行為一致"""

    @pytest.fixture(params=["mock", "real"])
    def canonical_reader(self, request, tmp_path):
        if request.param == "mock":
            return MockCanonicalReader()
        else:
            return RealCanonicalReader(tmp_path)

    def test_get_categories_consistency(self, canonical_reader):
        """Mock 和 Real 返回相同格式"""
        result = canonical_reader.get_categories()
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

    def test_error_handling_consistency(self, canonical_reader):
        """Mock 和 Real 錯誤處理一致"""
        with pytest.raises(FileNotFoundError):
            canonical_reader.load_nonexistent()
```

**V2 新增：錯誤情境矩陣（V3 擴充）**

| 情境 | Mock 行為 | Real 行為 | 測試 |
|------|-----------|-----------|------|
| 檔案不存在 | FileNotFoundError | FileNotFoundError | ✅ |
| 格式錯誤 | ValidationError | ValidationError | ✅ |
| 權限不足 | PermissionError | PermissionError | ✅ |
| 空資料 | 返回空 list | 返回空 list | ✅ V3 |
| 極大資料 | 正常處理 | 正常處理 | ✅ V3 |
| 非法 enum | ValidationError | ValidationError | ✅ V3 |

**V3 新增：錯誤通道一致性**

```python
def test_error_payload_consistency(canonical_reader):
    """錯誤訊息結構一致"""
    try:
        canonical_reader.load_nonexistent()
    except FileNotFoundError as e:
        assert hasattr(e, 'filename')  # 錯誤結構一致

def test_validation_error_format(canonical_reader):
    """驗證錯誤格式一致"""
    try:
        canonical_reader.parse_invalid_data()
    except ValidationError as e:
        # 確保錯誤格式可程式化處理
        assert hasattr(e, 'errors') or hasattr(e, 'json')
```

---

## 執行步驟（V4.2 優先順序）

| 優先級 | Step | 內容 | 時間 | V4.2 調整 |
|--------|------|------|------|-----------|
| **P0** | 4 | Phase 4 隔離環境 + Interface 層 + Version Policy | 2h | +Interface Version Policy |
| **P1** | 0 | Contract 規格（Schema + IO + Normative/Illustrative） | 2h | +分層定義 |
| **P1** | 1 | Schema Diff 測試 + 語意正規化 + Baseline 腳本 | 3h | +semantic whitelist |
| **P2** | 2 | Golden Data 測試 + Canonicalization Pipeline | 3.5h | +完整 pipeline |
| **P2** | 3 | CI 護欄 + paths-filter + github-script + Flaky | 2.5h | +可運作實作 |
| **P3** | - | Mock/Real 細緻化 | 延後 | 非關鍵路徑 |

**總時間**: 13-14 小時（約 1.5-2 天 MVP）

**V4.2 調整說明**：
- Step 0 增加 Normative/Illustrative 分層（+0.5h）
- Step 1 改用語意白名單正規化（+0.5h）
- Step 2 增加完整 canonicalization pipeline（+0.5h）
- Step 3 修正 CI 實作（paths-filter, github-script, flaky rerun）（+0.5h）
- Step 4 增加 Interface Version Policy（+0.5h）
- 總時間略增至 13-14h（但護欄真的會動）

---

## 驗收標準（V4.2 調整）

| 項目 | 標準 | 驗證方式 | V4.2 新增 |
|------|------|----------|-----------|
| Schema Contract | 規格文件完成 | `docs/contracts/schema_contract.md` 存在 | - |
| IO Contract | Normative/Illustrative 分層 | `docs/contracts/io_contract.md` 包含分類表 | ✅ |
| Schema 凍結 | 語意正規化 + JSON Schema 比對 | `pytest tests/contracts/test_schema_stability.py` | ✅ |
| Schema 正規化 | semantic whitelist + stable sort | `scripts/schema_normalize.py` 使用 | ✅ |
| Baseline 流程 | 測試不可寫 baseline | CI 驗證 + 腳本唯一入口 | - |
| 行為回歸 | Golden Data + Canonicalization | `pytest tests/contracts/test_phase_contracts.py` | ✅ |
| 金額比對 | canonicalize pipeline | `scripts/golden_data_diff.py` 使用 | ✅ |
| CI 護欄 | paths-filter + github-script | workflow 正確執行 | ✅ |
| 權限模型 | CODEOWNERS 生效 | Protected branch 驗證 | - |
| Sign-off Gate | Compatible change 需確認 | `schema-approved` label 檢查生效 | ✅ |
| Flaky 處理 | 一次 rerun + 報告 | flaky_report.md 產出 | ✅ |
| Mock 一致性 | Mock/Real 行為一致 | `pytest tests/contracts/test_mock_consistency.py` | - |
| Interface 隔離 | capture 只依賴 interfaces | `grep` 驗證 | - |
| Interface 版本 | Version Policy 文件 | `docs/contracts/interface_policy.md` 存在 | ✅ |

---

## V4.1 維護流程（強化）

### Golden Data 更新流程

**P0 Golden 集（關鍵路徑）**：
- `golden/dedupe_basic.yaml` - 基本去重
- `golden/rebuild_basic.yaml` - 基本重建
- `golden/report_basic.yaml` - 基本報表

**更新規則**：
| 層級 | 變更範圍 | 審核要求 |
|------|----------|----------|
| P0 | 關鍵路徑 | 雙人 CODEOWNERS sign-off |
| P1 | 邊緣情境 | 單人 review + 理由說明 |
| P2 | 擴充案例 | 單人 review |

**流程**：
1. 提出變更 PR
2. 說明變更理由（新增場景 / 行為修正 / 誤報修復）
3. 依層級審核
4. 更新 `docs/contracts/CHANGELOG.md`

### Schema Baseline 更新流程

**關鍵規則**：測試不可寫入 baseline

**流程**：
1. 執行 `python scripts/update_schema_baseline.py --model <ModelName>`
2. 自動產生 `schema_diff_report.md`
3. 檢視 diff 報告
4. 若為 Compatible 變更 → 加 `schema-approved` label + CODEOWNERS review
5. 若為 Breaking 變更 → **不允許合併**（需修改程式碼）

```bash
# 更新 baseline 的唯一入口
python scripts/update_schema_baseline.py --model ExpenseRecord
python scripts/update_schema_baseline.py --all  # 更新全部
```

---

## V4 新增：回滾策略（三層防護）

| 層級 | 觸發條件 | 動作 | 責任人 |
|------|----------|------|--------|
| **L1: CI 阻擋** | Breaking change / Golden 失敗 | 自動阻止 PR 合併 | 自動化 |
| **L2: 部署回滾** | 合併後測試失敗 | `git revert` + 重新部署 | 開發者 |
| **L3: 線上回滾** | 生產異常 | feature flag 關閉 | 值班人員 |

**本計劃範圍**: 專注於 L1（CI 阻擋），L2/L3 屬於未來 Phase 5 運維範疇。

---

## V4 新增：失敗分級

| 分級 | 定義 | 處理方式 |
|------|------|----------|
| **Breaking** | Schema 破壞性變更 | 必擋，無例外 |
| **Compatible** | Schema 相容性變更 | 需 sign-off |
| **Flaky** | 測試不穩定 | 標記 + 追蹤修復 |
| **Not-Actionable** | 環境問題 | 跳過 + 記錄 |

### V4.2 新增：Flaky 自動處置機制

**問題**：Flaky 測試會抵消「縮短等待期」的價值，導致無謂阻塞。

**解法：一次 Rerun 機制**

```yaml
# .github/workflows/contract-check.yml (補充)

      - name: Run contract tests with rerun
        id: tests
        run: |
          # 第一次執行
          if uv run pytest tests/contracts/ -v --tb=short 2>&1 | tee first_run.log; then
            echo "result=pass" >> $GITHUB_OUTPUT
          else
            echo "::warning::First run failed, attempting rerun..."
            # 只 rerun 失敗的測試
            if uv run pytest tests/contracts/ -v --tb=short --lf 2>&1 | tee rerun.log; then
              echo "result=flaky" >> $GITHUB_OUTPUT
              echo "::warning::Tests passed on rerun - marking as flaky"
            else
              echo "result=fail" >> $GITHUB_OUTPUT
            fi
          fi

      - name: Generate flaky report
        if: steps.tests.outputs.result == 'flaky'
        run: |
          echo "## Flaky Tests Detected" > flaky_report.md
          echo "The following tests failed on first run but passed on rerun:" >> flaky_report.md
          grep -E "^FAILED" first_run.log >> flaky_report.md || true
          echo "" >> flaky_report.md
          echo "**Action**: These tests should be investigated and stabilized." >> flaky_report.md

      - name: Upload flaky report
        if: steps.tests.outputs.result == 'flaky'
        uses: actions/upload-artifact@v4
        with:
          name: flaky-report
          path: flaky_report.md

      - name: Fail on real failures
        if: steps.tests.outputs.result == 'fail'
        run: exit 1
```

**Not-Actionable 處理**：

```yaml
      - name: Run contract tests
        id: tests
        continue-on-error: true
        run: |
          uv run pytest tests/contracts/ -v 2>&1 | tee test_output.log
          echo "exit_code=$?" >> $GITHUB_OUTPUT

      - name: Check for environment issues
        if: steps.tests.outputs.exit_code != '0'
        run: |
          # 檢查是否為環境問題（非測試邏輯錯誤）
          if grep -E "(ConnectionError|TimeoutError|OSError)" test_output.log; then
            echo "::warning::Environment issue detected - skipping"
            echo "not_actionable=true" >> $GITHUB_OUTPUT
          fi
```

**Flaky 追蹤機制**：
- Flaky 測試產出 `flaky_report.md` 作為 artifact
- 不阻擋 PR 合併
- 每週自動建立 issue 追蹤累積的 flaky tests

---

## 風險與緩解（V2 更新）

| 風險 | 機率 | 緩解 | V2 改善 |
|------|------|------|---------|
| 測試不完整，漏掉 schema 變動 | 低→ | 使用 `model_json_schema()` 完整快照 | ✅ 擴充至完整 JSON Schema |
| Phase 4 意外依賴 schema 細節 | 低 | Protocol 介面隔離 | ✅ 加入 Mock/Real 一致性測試 |
| Mock/Real 行為漂移 | 中 | - | ✅ 新增錯誤情境矩陣測試 |
| Compatible change 未被發現 | 中 | - | ✅ 新增 Sign-off Gate |
| 發現需要 schema 變動 | 低 | 回到正式流程 | ✅ 定義 Breaking vs Compatible |

---

## 時間比較（V4.2 最終）

| 方案 | 時間 | 信心度 | 說明 |
|------|------|--------|------|
| 原方案：等待 2 週 | 14 天 | 90% | 基於時間流逝 |
| V1：測試驅動 | 2-3 天 | 85% | 測試範圍有限 |
| V2：完整契約測試 | 3-4 天 | 92% | 涵蓋結構+行為 |
| V3：完整+邊緣情境 | 3-4 天 | 96% | 涵蓋邊緣+錯誤通道 |
| V4：MVP + 回滾策略 | 1-1.5 天 | 97% | 聚焦關鍵路徑 |
| V4.1：制度化 + 精確比對 | 1.5 天 | 97% | 可持續維護 |
| **V4.2：可運作實作** | **1.5-2 天** | **98%** | **護欄真的會動** |

**節省時間**: ~12 天
**信心度提升**: V4.2 透過修正 CI 實作問題達到 98% 信心度（護欄確實生效）

---

## 關鍵檔案（V4.2 更新）

| 用途 | 路徑 |
|------|------|
| Schema Contract 規格 | `docs/contracts/schema_contract.md` |
| IO Contract 規格 | `docs/contracts/io_contract.md` |
| Interface Policy | `docs/contracts/interface_policy.md` |
| Schema 契約測試 | `tests/contracts/test_schema_stability.py` |
| Interface 契約測試 | `tests/contracts/test_interface_stability.py` |
| Schema Baselines | `tests/contracts/baselines/*.json` |
| Phase 契約測試 | `tests/contracts/test_phase_contracts.py` |
| Golden Data | `tests/contracts/golden/*.yaml` |
| Mock 一致性測試 | `tests/contracts/test_mock_consistency.py` |
| Mock Canonical | `tests/fixtures/mock_canonical.py` |
| Interface 層 | `life_capital/interfaces/canonical_reader.py` |
| Phase 4 入口 | `life_capital/capture/__init__.py` |
| CI 護欄 | `.github/workflows/contract-check.yml` |
| CODEOWNERS | `.github/CODEOWNERS` |
| 版本常數 | `life_capital/io/registry.py` |
| Schema 正規化 | `scripts/schema_normalize.py` |
| Golden Canonicalization | `scripts/golden_data_diff.py` |

---

## V3 新增檔案清單

| 用途 | 路徑 |
|------|------|
| 邊緣情境測試 | `tests/contracts/test_edge_cases.py` |
| 差異報告腳本 | `scripts/check_schema_diff.py` |
| Golden Data 比對器 | `scripts/golden_data_diff.py` |

---

## V4 新增檔案清單

| 用途 | 路徑 |
|------|------|
| Schema Baseline 更新腳本 | `scripts/update_schema_baseline.py` |
| 維護流程文件 | `docs/contracts/MAINTENANCE.md` |

---

## V4.1 新增檔案清單

| 用途 | 路徑 |
|------|------|
| IO Contract 規格 | `docs/contracts/io_contract.md` |
| Interface 層定義 | `life_capital/interfaces/canonical_reader.py` |
| CODEOWNERS 設定 | `.github/CODEOWNERS` |
| Contract 變更日誌 | `docs/contracts/CHANGELOG.md` |

---

## V4.2 新增檔案清單

| 用途 | 路徑 |
|------|------|
| Schema 語意正規化 | `scripts/schema_normalize.py` |
| Golden Canonicalization | `scripts/golden_data_diff.py`（強化） |
| Interface Policy | `docs/contracts/interface_policy.md` |
| Interface 契約測試 | `tests/contracts/test_interface_stability.py` |
| Interface Baseline 更新 | `scripts/update_interface_baseline.py` |

---

## 版本歷程

| 版本 | 改善重點 | 來源 |
|------|----------|------|
| V1 | 初版架構 | 原始規劃 |
| V2 | 擴充 schema 範圍 + 時間修正 + 風險分層 | Codex 審查 #1 |
| V3 | 邊緣情境 + Golden Data 精細化 + Gate 規則明確化 | Codex 審查 #2 |
| V4 | 回滾策略 + 優先順序 + 維護流程 | 專家審查 #3 |
| V4.1 | Contract 拆分 + Baseline 流程 + Gate 權限 + Golden 精確比對 | 用戶審查 #4 |
| V4.2 | 可運作性修正：CI 實作修正 + 正規化強化 + Flaky 處理 | 用戶審查 #5 |

---

## 核心洞察

**兩週等待期的真正目的**：
1. 確保 canonical schema 不再變動
2. 確保 Phase 0-3 沒有 regression bugs
3. 建立信心：新開發不會破壞現有功能

**替代方案**：用自動化測試證明這三點，而非被動等待。

**V2 新增洞察（Codex 回饋）**：
- 測試必須涵蓋「完整 schema contract」，不只欄位名稱
- 需要定義「Breaking vs Compatible」變更規則
- 需要 Golden Data 行為回歸測試
- Mock/Real 一致性是隔離開發的關鍵風險

**V3 新增洞察（Codex 邊緣情境審查）**：
- Schema diff 只比對結構，無法捕捉**語意退化**
- Golden Data 需定義「可容忍差異」避免誤報
- Mock/Real 測試需涵蓋**錯誤通道**（error payload, timeout）
- Sign-off Gate 需明確定義「必擋」vs「可覆核」規則
- 需處理**並發/重試/部分失敗**情境

**V4 新增洞察（專家審查）**：
- 現有計劃偏「測試策略」，需補齊「**回滾策略**」
- 需定義失敗分級：Breaking / Compatible / **Flaky**
- Golden Data 維護成本最高，需建立**可更新流程**
- 實作優先順序應聚焦**最關鍵路徑**

**V4.1 新增洞察（用戶審查）**：
- Contract 需拆分為「**Schema Contract**」+「**IO Contract**」（輸出檔案格式）
- Baseline 更新**必須從測試中移除**，只能透過 explicit script
- Schema diff 需**正規化**避免環境漂移假陽性（pin Pydantic/Python 版本）
- 預設值變更需**細分**：影響輸出者視同 Breaking
- Gate 需落地為**可執行權限模型**（CODEOWNERS + required checks）
- Golden 比對應使用 **quantize 後 exact compare**（替代 ε 容忍）

**V4.2 新增洞察（用戶審查 - 可運作性）**：
- IO Contract 需區分「**Normative**（必遵守）」vs「**Illustrative**（示例）」，否則改報表文案也算 breaking
- Schema 正規化僅排序 key 不夠，需「**語意白名單**」剔除 title/description/$defs 形態差異
- GitHub Actions 的 `gh pr view` 有權限問題，需改用 **actions/github-script**
- `changed_files` 是數字不是路徑清單，需用 **paths-filter** 或 **changed-files** action
- Golden Data 的 YAML/JSON 序列化細節會干擾比對，需定義完整 **canonicalization pipeline**
- Flaky 測試會抵消「縮短等待期」的價值，需要 **一次 rerun 機制**
- Interface 層也會演進，需補 **interface version policy** 避免成為新的漂移源

---

## 深度規劃審查歷程

| 輪次 | 審查者 | 重點 | 改善 |
|------|--------|------|------|
| 1 | Codex | 結構完整性 | 擴充 schema 範圍、調整時間 |
| 2 | Codex | 邊緣情境 | Golden Data 精細化、Gate 規則 |
| 3 | 專家 | 護欄與容錯 | 回滾策略、優先順序、維護流程 |
| 4 | 用戶 | 制度化與精確性 | Contract 拆分、權限模型、quantize 比對 |
| 5 | 用戶 | 可運作性 | CI 實作修正、語意正規化、Flaky 處理、Interface Policy |

---

*V4.2 最終版：基於 Codex 兩輪 + 專家審查 + 用戶兩輪審查，達成 98% 信心度（護欄確實生效），1.5-2 天完成 MVP。*
