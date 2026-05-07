# Phase 5 Stage 3 - V6 可運營性優化

<!-- 歷史文件：可運營性反饋 -->
<!-- 主規劃文件: ../plan.md -->

本文件記錄 V6 可運營性優化內容，基於可運營性反饋將 V5 優化為更具決定論、可重建、可偵測異常的版本。

---

## 1. 優化 #1: input_hash 規範化與決定論測試

**問題**: V5 的 `input_hash` 可能因序列化順序、時間戳、精度差異導致相同輸入產生不同 hash。

**解法**: 定義 canonicalization 規則與最小 hash 來源集合。

### 1.1 Canonicalization 規則

```python
# io/advisor_derived_handler.py

def canonicalize_input(decisions: list[DecisionRecord]) -> bytes:
    """
    將輸入正規化為確定性格式

    規則：
    1. key 排序：固定順序（alphabetical 或 schema 定義順序）
    2. 欄位白名單：只含語意欄位，排除 generated_at、_seq 等
    3. Decimal 量化：統一 quantize("0.0001")
    4. 日期格式：ISO 8601（YYYY-MM-DDTHH:MM:SS）
    5. 字串正規化：strip + 小寫（若適用）
    """
    canonical_records = []
    for dec in sorted(decisions, key=lambda d: d.decision_id):
        canonical_records.append({
            "decision_id": dec.decision_id,
            "template_id": dec.template_id,
            "status": dec.status.value,
            "confidence": dec.confidence.value,
            "comparability_score": str(Decimal(dec.comparability_score).quantize(Decimal("0.0001"))),
            "option_a": _canonicalize_option(dec.option_a),
            "option_b": _canonicalize_option(dec.option_b),
            "risk_tags": sorted(dec.risk_tags),
            # 不含: created_at, generated_at, _seq（非語意欄位）
        })
    return json.dumps(canonical_records, sort_keys=True, ensure_ascii=False).encode("utf-8")
```

### 1.2 Hash 來源最小集合

```yaml
input_hash_sources:
  必須包含:
    - decisions.yaml（經 canonicalize 處理）
    - calc_version（計算邏輯版本）
    - schema_version（輸出格式版本）
    - redaction_profile_version（去識別規則版本，V6 新增）

  排除（不影響語意）:
    - generated_at（產生時間戳）
    - _seq（內部序號）
    - operation_id（操作追蹤 ID）
    - file paths（絕對路徑）
```

### 1.3 決定論測試

```python
# tests/contracts/test_input_hash_determinism.py

from hypothesis import given, strategies as st

@given(st.lists(st.builds(DecisionRecord, ...)))
def test_hash_determinism(decisions):
    """相同輸入應產生相同 hash（property-based）"""
    hash1 = compute_input_hash(decisions)
    hash2 = compute_input_hash(decisions)
    assert hash1 == hash2

def test_hash_excludes_generated_at():
    """generated_at 變更不應影響 hash"""
    dec1 = make_decision(generated_at="2024-01-01T00:00:00")
    dec2 = make_decision(generated_at="2024-12-31T23:59:59")
    assert compute_input_hash([dec1]) == compute_input_hash([dec2])

def test_hash_includes_semantic_fields():
    """語意欄位變更應影響 hash"""
    dec1 = make_decision(comparability_score=0.7)
    dec2 = make_decision(comparability_score=0.8)
    assert compute_input_hash([dec1]) != compute_input_hash([dec2])

def test_rebuild_produces_same_hash():
    """重建應產生相同 input_hash"""
    # 第一次生成
    result1 = generate_wiki(decisions)
    hash1 = result1.provenance.input_hash

    # 清除 derived/，重建
    clear_derived()
    result2 = generate_wiki(decisions)
    hash2 = result2.provenance.input_hash

    assert hash1 == hash2
```

---

## 2. 優化 #2: AdvisorDerivedHandler 寫入策略與篡改偵測

**問題**: V5 只定義「原子寫入」，未明確幂等行為、覆寫策略、篡改偵測。

**解法**: 引入 `write_mode` 參數與 `content_hash` 驗證。

### 2.1 Write Mode 參數

```python
# io/advisor_derived_handler.py

from enum import Enum
from typing import Literal

class WriteMode(Enum):
    ERROR_IF_EXISTS = "error_if_exists"    # 檔案存在則 raise（預設，最安全）
    OVERWRITE = "overwrite"                 # 強制覆寫（需明確指定）
    SKIP_IF_EXISTS = "skip_if_exists"      # 若 hash 相同則跳過

class AdvisorDerivedHandler:
    def write_with_provenance(
        self,
        artifact_type: str,
        content: str | dict,
        provenance: AdvisorDerivedProvenance,
        format: Literal["md", "json"],
        write_mode: WriteMode = WriteMode.ERROR_IF_EXISTS,  # 預設最安全
    ) -> WriteResult:
        """
        統一寫入邏輯

        Returns:
            WriteResult:
                - status: "created" | "overwritten" | "skipped" | "error"
                - path: Path
                - content_hash: str（用於篡改偵測）
        """
        target_path = self._compute_path(artifact_type, provenance.input_hash, provenance.schema_version, format)

        if target_path.exists():
            if write_mode == WriteMode.ERROR_IF_EXISTS:
                raise FileExistsError(f"{target_path} 已存在，使用 --force 覆寫")
            elif write_mode == WriteMode.SKIP_IF_EXISTS:
                existing_hash = self._compute_content_hash(target_path)
                new_hash = self._compute_content_hash_from_content(content)
                if existing_hash == new_hash:
                    return WriteResult(status="skipped", path=target_path, content_hash=existing_hash)
                # hash 不同但選擇 skip → 警告
                logger.warning(f"{target_path} 內容已變更，但模式為 skip")
                return WriteResult(status="skipped", path=target_path, content_hash=existing_hash)
            # OVERWRITE: 繼續寫入

        # 原子寫入邏輯（V5 已定義）
        ...
```

### 2.2 Content Hash 篡改偵測

```python
# Provenance 擴充
@dataclass(frozen=True)
class AdvisorDerivedProvenance:
    artifact_type: str
    schema_version: str
    calc_version: str
    input_hash: str
    canonical_sources: list[str]
    generated_at: str
    rebuild_command: str
    content_hash: str  # V6 新增：輸出內容的 SHA-256 hash
```

```python
# lc doctor --advisor 檢查
def check_derived_integrity(derived_dir: Path) -> list[IntegrityIssue]:
    """檢查 derived 檔案是否被篡改"""
    issues = []
    for meta_file in derived_dir.glob("*.meta.json"):
        content_file = meta_file.with_suffix("")  # 移除 .meta.json
        if not content_file.exists():
            issues.append(IntegrityIssue(
                type="orphan_meta",
                file=meta_file,
                message="meta.json 存在但內容檔案遺失"
            ))
            continue

        meta = json.loads(meta_file.read_text())
        expected_hash = meta.get("content_hash")
        actual_hash = compute_file_hash(content_file)

        if expected_hash != actual_hash:
            issues.append(IntegrityIssue(
                type="content_tampered",
                file=content_file,
                message=f"內容 hash 不符：expected {expected_hash[:8]}..., actual {actual_hash[:8]}...",
                remediation="執行 lc advisor wiki --rebuild 重建"
            ))
    return issues
```

### 2.3 lc doctor --advisor 檢查項

```yaml
doctor_advisor_checks:
  - id: "D01"
    name: "derived 完整性"
    check: "所有 derived 檔案都有對應 .meta.json"
    severity: "error"

  - id: "D02"
    name: "content_hash 驗證"
    check: "derived 內容與 meta.json 記錄的 hash 一致"
    severity: "warning"
    remediation: "lc advisor wiki --rebuild"

  - id: "D03"
    name: "orphan meta 偵測"
    check: "meta.json 必須有對應的內容檔案"
    severity: "error"
    remediation: "刪除孤立 meta.json 或重建內容"

  - id: "D04"
    name: "stale derived 偵測"
    check: "input_hash 與當前 canonical 不符"
    severity: "info"
    remediation: "lc advisor wiki --rebuild"
```

---

## 3. 優化 #3: Derived 生命週期與 CLI 快取行為

**問題**: V5 未定義 derived 何時「過期」、CLI 是否應重建、--force 行為。

**解法**: 定義生命週期狀態與 CLI 快取策略。

### 3.1 生命週期狀態

```python
# io/advisor_derived_handler.py

class DerivedStatus(Enum):
    GENERATED = "generated"    # 剛產生，與 canonical 同步
    BOUND = "bound"            # 被其他 artifact 引用（不可刪除）
    STALE = "stale"            # input_hash 與當前 canonical 不符
    SUPERSEDED = "superseded"  # 已被新版本取代（可清理）
```

```python
def get_derived_status(artifact_path: Path, current_canonical_hash: str) -> DerivedStatus:
    """判斷 derived 檔案的生命週期狀態"""
    meta_path = Path(str(artifact_path) + ".meta.json")
    if not meta_path.exists():
        return DerivedStatus.STALE  # 無 meta → 視為過期

    meta = json.loads(meta_path.read_text())
    stored_hash = meta.get("input_hash")

    if stored_hash != current_canonical_hash:
        return DerivedStatus.STALE

    return DerivedStatus.GENERATED
```

### 3.2 CLI 快取行為

```bash
# 預設：使用快取（若非 stale）
lc advisor wiki
# 若 derived 存在且 hash 相符 → 直接讀取
# 若 derived 不存在或 stale → 重建

# 強制重建
lc advisor wiki --force
# 無論 derived 狀態，強制重建

# 只顯示 stale 狀態
lc advisor wiki --check-stale
# 不產生輸出，只報告是否需要重建

# 顯示最新（即使 stale 也顯示現有）
lc advisor wiki --latest
# 即使 stale 也顯示現有 derived（加警告）
```

### 3.3 清理策略

```bash
# 清理過期 derived
lc advisor cleanup --stale
# 刪除所有 status=STALE 的 derived

# 清理被取代的 derived
lc advisor cleanup --superseded
# 刪除所有 status=SUPERSEDED 的 derived

# 完整重建（先清理後重建）
lc advisor rebuild --all
# 等同於 cleanup --stale && wiki --force && risk-matrix --force && ...
```

---

## 4. 優化 #4: Redaction Profile 版本化與契約測試

**問題**: V5 未定義 redaction 規則變更如何追蹤，輸出 schema 未與 evaluability 對齊。

**解法**: 版本化 redaction profile，標準化輸出欄位。

### 4.1 Redaction Profile 版本化

```python
# privacy/redaction/rules.py

REDACTION_PROFILE_VERSION = "1.0"  # 新增版本常數

@dataclass(frozen=True)
class RedactionProfile:
    """去識別化規則集"""
    version: str                    # "1.0"
    forbidden_patterns: list[str]   # 完全禁止的 pattern
    sensitive_fields: list[str]     # 需遮蔽的欄位
    composition_rules: list[str]    # 組合推論風險規則
```

```python
# Provenance 擴充（V6）
@dataclass(frozen=True)
class AdvisorDerivedProvenance:
    artifact_type: str
    schema_version: str
    calc_version: str
    input_hash: str
    canonical_sources: list[str]
    generated_at: str
    rebuild_command: str
    content_hash: str               # V6 新增
    redaction_profile_version: str  # V6 新增：使用的去識別規則版本
```

### 4.2 輸出 Schema 標準化（與 Evaluability 對齊）

```python
# 所有 E2/E3/E4 輸出應包含的 evaluability 欄位

@dataclass
class EvaluabilityOutput:
    """統一的可評估性輸出欄位"""
    comparability_score: float
    recommendability: RecommendabilityLevel
    evaluability: EvaluabilityLevel
    warnings: list[str]           # V6 新增：警告訊息
    limitations: list[str]        # V6 新增：已知限制
    confidence: ConfidenceLevel   # 與 DecisionRecord 對齊
```

```python
# E3 Risk Matrix 輸出範例
@dataclass
class RiskMatrixOutput:
    decision_id: str
    risk_tags: list[str]
    risk_explanation: str

    # Evaluability 欄位
    evaluability: EvaluabilityOutput

    # Provenance
    provenance: AdvisorDerivedProvenance

# E4 Sensitivity 輸出範例
@dataclass
class SensitivityOutput:
    decision_id: str
    parameter: str
    perturbation: float
    delta: float
    direction: str  # "increase" | "decrease" | "neutral"
    significance: str  # "high" | "medium" | "low"

    # Evaluability 欄位
    evaluability: EvaluabilityOutput

    # Provenance
    provenance: AdvisorDerivedProvenance
```

### 4.3 結構化組合測試

```python
# tests/contracts/test_redaction_contract.py

def test_redaction_profile_versioned():
    """確認 redaction profile 有版本號"""
    profile = get_current_redaction_profile()
    assert profile.version == REDACTION_PROFILE_VERSION

def test_derived_provenance_includes_redaction_version():
    """確認 derived 輸出包含 redaction profile version"""
    result = generate_wiki(decisions)
    assert result.provenance.redaction_profile_version == REDACTION_PROFILE_VERSION

@pytest.mark.parametrize("artifact_type", ["decision_wiki", "risk_matrix", "sensitivity"])
def test_output_includes_evaluability_fields(artifact_type):
    """確認所有衍生物輸出包含標準化 evaluability 欄位"""
    result = generate_artifact(artifact_type, decisions)
    for item in result.items:
        assert hasattr(item, "evaluability")
        assert hasattr(item.evaluability, "warnings")
        assert hasattr(item.evaluability, "limitations")
        assert hasattr(item.evaluability, "confidence")

def test_redaction_combination_rules():
    """組合推論風險：單一欄位安全，但組合可能危險"""
    profile = get_current_redaction_profile()

    # 單一欄位測試
    assert is_safe({"category": "health"}, profile) == True
    assert is_safe({"date": "2024-01-15"}, profile) == True

    # 組合測試
    combined = {"category": "health", "date": "2024-01-15", "amount": 5000}
    assert is_safe(combined, profile) == False  # 可推論特定醫療事件
```

---

## 5. V6 驗收標準

| # | 驗收項目 | 驗證方式 | 狀態 |
|---|----------|----------|------|
| V6-1 | input_hash 決定論 | test_input_hash_determinism.py 通過 | ✅ |
| V6-2 | canonicalization 規則 | 規則文件化 + 單元測試 | ✅ |
| V6-3 | write_mode 三種模式 | 單元測試覆蓋 | ✅ |
| V6-4 | content_hash 篡改偵測 | lc doctor --advisor 檢查 | ✅ |
| V6-5 | 生命週期狀態機 | DerivedStatus 狀態轉換測試 | ✅ |
| V6-6 | CLI 快取行為 | --force/--latest/--check-stale 整合測試 | ✅ |
| V6-7 | redaction profile 版本化 | provenance 包含版本號 | ✅ |
| V6-8 | evaluability 輸出標準化 | 所有 E2/E3/E4 輸出含 warnings/limitations | ✅ |

---

## 6. 測試預估（V6）

| 模組 | V5 預估 | V6 調整 | 說明 |
|------|---------|---------|------|
| 基礎設施 | 15-20 | 22-28 | +canonicalization + write_mode + lifecycle |
| E1 Memory | 20-25 | 20-25 | 不變 |
| E2 Wiki | 18-22 | 20-24 | +evaluability output |
| E3 Risk | 22-26 | 24-28 | +evaluability output |
| E4 Sensitivity | 28-32 | 30-34 | +evaluability output |
| E5 CLI | 15-18 | 20-24 | +cache behavior tests |
| E6 Docs | 8-10 | 10-12 | +doctor checks |
| 契約測試 | - | 12-16 | V6 新增：redaction + determinism |
| **合計** | **126-153** | **158-191** | **+25%（契約測試強化）** |

**最終基線**: 841 tests → **999-1032 tests**

---

## 相關文件

| 文件 | 說明 |
|------|------|
| [../plan.md](../plan.md) | 主規劃文件（V7 收斂版） |
| [../contracts.md](../contracts.md) | 技術契約 |
| [v1-v4-reviews.md](./v1-v4-reviews.md) | Codex 審查歷程 |
| [v5-architecture.md](./v5-architecture.md) | V5 架構優化 |
