# Stage 3 設計文件

> Phase 5 Stage 3: 決策追蹤與 Wiki 功能實作

## 概述

Stage 3 為 Life Capital Advisor 模組新增決策記憶、Wiki 編譯、風險評估、敏感度分析與 CLI 整合功能。

### 關鍵目標
- **E1**: 擴展決策記憶（DecisionRecord V1.1）
- **E2**: 自動生成 Decision Wiki
- **E3**: 風險評估與分層
- **E4**: 敏感度分析
- **E5**: CLI 命令整合

## 架構設計

### 模組依賴圖

```
┌─────────────────┐
│ CLI Commands    │ lc advisor history/explain/cleanup
│ (commands/)     │ lc doctor --advisor
└────────┬────────┘
         │
         ├──────────────────────────────┬─────────────────────┐
         │                              │                     │
┌────────▼────────┐         ┌───────────▼──────────┐  ┌──────▼──────────┐
│ DecisionsHandler│         │ Generation Modules   │  │ Analyzer Modules│
│ (io/)           │         │ (generation/)        │  │ (advisor/)      │
│ - V1.1 schema   │         │ - decision_wiki.py   │  │ - risk_assessor.py
│ - State machine │         │ - risk_matrix.py     │  │ - sensitivity_analyzer.py
│ - ID validation │         │ - sensitivity_report.py
└────────┬────────┘         └───────────┬──────────┘  └──────┬──────────┘
         │                              │                     │
         │                    ┌─────────▼─────────┐          │
         │                    │ Shared Modules    │          │
         └────────────────────│ (advisor/shared/) │──────────┘
                              │ - evaluability.py │
                              └───────────────────┘
                                       │
                              ┌────────▼─────────┐
                              │ AdvisorDerivedHandler
                              │ (io/)            │
                              │ - Path security  │
                              │ - Provenance     │
                              └──────────────────┘
```

## E1: Memory 擴展設計

### DecisionRecord V1.1 Schema

#### 新增欄位

| 欄位 | 型別 | 用途 |
|------|------|------|
| `decision_rationale` | Optional[str] | 記錄決策理由，提供上下文給未來審查 |
| `reverted_from_decision_id` | Optional[str] | 追蹤回滾來源，建立決策歷史鏈 |

#### 向後相容策略

**讀取（V1.0 → V1.1）**：
```python
# 舊檔案缺少新欄位時，使用 None 作為預設值
decision_rationale = data.get("decision_rationale")  # 回傳 None for V1.0
reverted_from_decision_id = data.get("reverted_from_decision_id")  # 回傳 None for V1.0
```

**寫入（V1.1 → V1.0 相容格式）**：
```python
# 只寫入非 None 的欄位，避免污染 V1.0 格式
if record.decision_rationale is not None:
    data["decision_rationale"] = record.decision_rationale
# V1.0 讀取器會忽略未知欄位
```

### 狀態機設計

```
         ┌────────┐
         │  None  │ (新建)
         └───┬────┘
             │
             ▼
      ┌──────────┐
      │ PENDING  │────┐
      └────┬─────┘    │ (取消)
           │          │
           │(套用)    │
           ▼          ▼
      ┌──────────┐   ┌──────────┐
      │ APPLIED  │───│ REVERTED │
      └──────────┘   └──────────┘
           (回滾)
```

**允許的狀態轉換**：
- `None → PENDING` - 新建決策
- `PENDING → APPLIED` - 套用決策
- `PENDING → REVERTED` - 取消決策
- `APPLIED → REVERTED` - 回滾決策

**禁止的狀態轉換**：
- `REVERTED → APPLIED` - 已回滾不可復原
- `APPLIED → PENDING` - 已套用不可撤銷
- 任何跳躍式轉換（必須循序）

### ID 重複檢查

```python
def _check_duplicate_decision_id(self, decision_id: str):
    """在寫入前檢查 ID 唯一性"""
    existing_ids = {r.decision_id for r in self.read_all()}
    if decision_id in existing_ids:
        raise DuplicateDecisionIDError(f"Decision ID 已存在: {decision_id}")
```

**ULID 格式**：
- 格式：`dec_<26位 ULID>`
- 範例：`dec_01ARZ3NDEKTSV4RRFFQ69G5FAV`
- 優點：時間排序 + 唯一性 + 可讀性

## E2: Wiki 編譯器設計

### Markdown 生成邏輯

```python
def generate_wiki(decisions: List[DecisionRecord], data_path: Path) -> str:
    """
    生成策略：
    1. 過濾：只包含 active 決策（PENDING/APPLIED）
    2. 排序：按 created_at 降序（最新在前）
    3. 格式化：每個決策一個 section
    4. 連結：內部交叉引用
    """
    active_decisions = [
        d for d in decisions
        if d.status in (DecisionStatus.PENDING, DecisionStatus.APPLIED)
    ]

    sorted_decisions = sorted(
        active_decisions,
        key=lambda d: d.created_at,
        reverse=True
    )

    sections = []
    for decision in sorted_decisions:
        sections.append(_format_decision(decision))

    return "\n\n".join(["# Decision History", ""] + sections)
```

### Provenance 追蹤

```python
provenance = AdvisorDerivedProvenance(
    artifact_type="decision_wiki",
    schema_version="1.0",
    calc_version="wiki_v1.0",
    canonicalization_version="1.0",
    input_hash=compute_hash(decisions),  # SHA-256
    canonical_sources=["canonical/advisor/decisions/decisions.yaml"],
    generated_at=datetime.now().isoformat(),
    rebuild_command=RebuildCommand(
        cmd=["lc", "advisor", "wiki", "--force"],
        cwd=".",
        env={},
        schema_version="1.0"
    ),
    content_hash=compute_hash(markdown_content),
    redaction_profile_version="1.0"
)
```

### RebuildCommand 結構

使用 `list[str]` 而非字串拼接，防止注入攻擊：

```python
@dataclass(frozen=True)
class RebuildCommand:
    cmd: list[str]         # ["lc", "advisor", "wiki", "--force"]
    cwd: str               # "."
    env: dict[str, str]    # {}
    schema_version: str    # "1.0"

    def to_safe_string(self) -> str:
        import shlex
        return " ".join(shlex.quote(arg) for arg in self.cmd)
```

## E3: 風險評估設計

### Evaluability 共享模組

```python
# 雙維度評分系統
class RecommendabilityLevel(Enum):
    FULL = "full"       # >= 0.7 - 可直接推薦
    PARTIAL = "partial" # 0.5-0.7 - 謹慎推薦
    NONE = "none"       # < 0.5 - 不推薦

class EvaluabilityLevel(Enum):
    FULL = "full"       # >= 0.5 - 可分析
    WARNING = "warning" # 0.3-0.5 - 警告
    SKIP = "skip"       # < 0.3 - 跳過
```

**設計原則**：
- Recommendability 用於推薦決策
- Evaluability 用於決定是否執行分析
- 閾值基於經驗與統計分析

### 風險分層（low/medium/high）

```python
def assess_risk(decision: DecisionRecord) -> Optional[RiskAssessment]:
    """
    風險分層邏輯：
    - high: risk_tags >= 3
    - medium: risk_tags >= 1
    - low: risk_tags == 0
    """
    eval_result = evaluate_decision(decision)

    if eval_result.is_evaluable == EvaluabilityLevel.SKIP:
        return None  # comparability < 0.3，跳過

    risk_tag_count = len(decision.risk_tags)
    risk_level = (
        "high" if risk_tag_count >= 3 else
        "medium" if risk_tag_count >= 1 else
        "low"
    )

    return RiskAssessment(
        decision_id=decision.decision_id,
        risk_level=risk_level,
        risk_tags=decision.risk_tags,
        risk_explanation=decision.risk_explanation,
        warnings=[...]
    )
```

### 風險標籤系統

常見標籤：
- `market_volatility` - 市場波動風險
- `regulatory_uncertainty` - 法規不確定性
- `liquidity_risk` - 流動性風險
- `operational_complexity` - 操作複雜度
- `counterparty_risk` - 交易對手風險

## E4: 敏感度分析設計

### 微擾測試策略

```python
# ±5%, ±10% 雙層微擾
for delta_pct in [Decimal("0.05"), Decimal("0.10")]:
    for direction in [-1, 1]:
        perturbed_value = baseline_value * (1 + delta_pct * direction)
        delta_burden = compute_delta(perturbed_value)
        perturbations.append({...})
```

**測試參數**：
- `discount_rate` - 折現率
- `horizon_years` - 時間範圍

**預期行為**：
- 折現率上升 → burden 上升（現值效應）
- 時間範圍延長 → burden 變化取決於模型

### 單調性檢查

```python
# 折現率上升應導致 burden 上升（允許 ±0.01 浮點誤差）
if param_name == 'discount_rate' and direction > 0:
    if delta_burden < Decimal("-0.01"):
        is_monotonic = False
        warnings.append(f"Non-monotonic: {param_name} increase led to burden decrease")
```

### Decimal 運算規範

**規則**：
1. 輸入轉換：`to_decimal()` 強制轉換
2. 內部計算：只使用 `Decimal` 型別
3. 輸出量化：`quantize()` 格式化
4. 序列化：轉為 `str` 或 `float`（JSON 相容）

```python
# 輸入
baseline_value = Decimal(str(params.discount_rate))

# 計算
delta_burden = baseline_burden * delta_pct * direction

# 輸出
perturbations.append({
    'baseline_value': str(baseline_value.quantize(Decimal("0.0001"))),
    'delta_burden': str(delta_burden.quantize(Decimal("0.01")))
})
```

## E5: CLI 整合設計

### history 命令

```bash
lc advisor history [PATH] --limit 10 --status pending
```

**功能**：
- 顯示決策歷史記錄
- 支援狀態過濾（pending/applied/reverted）
- 可限制顯示筆數
- Rich table 輸出（ID/標題/時間/狀態/風險等級）

### explain 命令

```bash
lc advisor explain <decision_id> [PATH]
```

**功能**：
- 詳細解釋單一決策
- 顯示 Decision Rationale（V1.1）
- 策略列表、比較結果、風險評估
- Rich panel 美化輸出
- 決策不存在回傳 exit(1)

### cleanup 命令

```bash
lc advisor cleanup [PATH] --keep-latest 3 --dry-run
```

**功能**：
- 清理舊的 derived advisor 檔案
- 保留最新 N 個版本
- dry-run 預覽模式（不實際刪除）
- 互動式確認（可取消）

### doctor --advisor 命令

```bash
lc doctor [PATH] --advisor --format json
```

**功能**：
- 健康檢查 advisor 模組
- 檢查項目：
  1. `derived/advisor/` 目錄存在
  2. 所有 YAML 檔案有 `_provenance`
  3. 所有 `content_hash` 可驗證
  4. 沒有孤立檔案（無對應 canonical 決策）
- Exit codes：
  - 0: ok
  - 1: warning
  - 2: error
- JSON/text 雙格式輸出

## 安全邊界設計

### 路徑驗證三層檢查

```python
def _validate_path(self, path: Path) -> Path:
    """
    Layer 1: 基底目錄檢查
    - 確保路徑在 derived/advisor/ 下
    """
    resolved = path.resolve()
    allowed_base = (self.data_path / "derived/advisor").resolve()

    if not str(resolved).startswith(str(allowed_base)):
        raise PathSecurityError("路徑超出允許範圍")

    """
    Layer 2: 副檔名白名單
    - 只允許 .md, .json, .meta.json
    """
    if resolved.suffix not in {".md", ".json", ".meta.json"}:
        raise PathSecurityError("不允許的副檔名")

    """
    Layer 3: 路徑成分檢查
    - 禁止 ..（path traversal）
    - 禁止空格開頭（隱藏檔案）
    """
    for part in resolved.parts:
        if part == ".." or part.startswith(" "):
            raise PathSecurityError("不安全的路徑成分")

    return resolved
```

### 允許基底目錄

```
derived/advisor/
├── reports/          # 報告輸出目錄
│   ├── decision_wiki.md
│   ├── risk_matrix.yaml
│   └── sensitivity_analysis.yaml
└── meta/             # Provenance metadata
    ├── decision_wiki.meta.json
    ├── risk_matrix.meta.json
    └── sensitivity_analysis.meta.json
```

### 副檔名白名單

| 副檔名 | 用途 |
|--------|------|
| `.md` | Wiki Markdown 輸出 |
| `.json` | 結構化報告（風險矩陣、敏感度） |
| `.meta.json` | Provenance metadata（未來擴展）|

### 路徑成分檢查

**禁止的模式**：
- `..` - path traversal 攻擊
- ` evil.md` - 空格開頭（可能被隱藏）
- `/tmp/evil.md` - 絕對路徑超出範圍

**允許的模式**：
- `derived/advisor/reports/wiki.md`
- `derived/advisor/reports/2025/risk.json`

## 測試策略

### 單元測試（85+ tests）

| 模組 | 測試數量 | 覆蓋項目 |
|------|----------|----------|
| Phase 1 (Infrastructure) | 20 | canonicalization, path security, RebuildCommand |
| Phase 2 (Memory) | 21 | V1.0↔V1.1 相容性, 狀態轉換, ID 檢查 |
| Phase 3a (Wiki) | 20 | 結構測試, token 測試, 過濾排序 |
| Phase 3b (Risk) | 24 | evaluability, 風險分層, 整合 |
| Phase 4 (Sensitivity) | 40 | 不變量, 單調性, 邊界值, Decimal |
| Phase 5 (CLI) | 24 | history, explain, cleanup, doctor |
| **總計** | **149** | - |

### 整合測試（CLI 命令）

```python
def test_full_workflow_e1_to_e5(tmp_path):
    """端到端工作流程測試"""
    # 1. 寫入決策（E1）
    handler = DecisionsHandler(tmp_path)
    handler.write_decision(decision)

    # 2. 生成 Wiki（E2）
    wiki_path = save_wiki(decisions, tmp_path)
    assert wiki_path.exists()

    # 3. 生成風險矩陣（E3）
    risk_report = generate_risk_matrix(decisions, tmp_path)
    assert risk_report['assessed_count'] > 0

    # 4. 生成敏感度報告（E4）
    sens_report = generate_sensitivity_report(decisions, tmp_path)
    assert sens_report['analyzed_count'] > 0

    # 5. CLI 命令（E5）
    result = runner.invoke(app, ["history", str(tmp_path)])
    assert result.exit_code == 0
```

### Golden Fixtures（Canonicalization）

```
tests/fixtures/canonicalization/
├── minimal_single_decision/
│   ├── input.yaml          # 原始決策
│   ├── canonical.json      # 正規化 JSON
│   └── canonical.sha256    # 預期 hash
├── multiple_decisions_unsorted/
│   ├── input.yaml
│   ├── canonical.json
│   └── canonical.sha256
└── decimal_unicode_edge/
    ├── input.yaml
    ├── canonical.json
    └── canonical.sha256
```

**用途**：
- 驗證 canonicalization 演算法穩定性
- 檢測 hash 漂移（Breaking Change）
- 確保跨版本一致性

### Cross-version Fixtures（V1.0 ↔ V1.1）

```
tests/fixtures/decisions/
├── v1.0_minimal.yaml          # 最小 V1.0 決策
├── v1.0_with_reverts.yaml     # 包含回滾的 V1.0
├── v1.1_new_fields.yaml       # V1.1 新欄位
└── v1.1_full_features.yaml    # V1.1 完整功能
```

**測試目標**：
- V1.0 檔案可被 V1.1 handler 讀取
- V1.1 欄位在 V1.0 中被忽略
- Round-trip 測試（讀取→修改→寫回→再讀取）

## 效能考量

### 決策數量與 Wiki 生成

| 決策數量 | Wiki 大小 | 生成時間 |
|----------|-----------|----------|
| 10 | ~5 KB | <100 ms |
| 100 | ~50 KB | <500 ms |
| 1000 | ~500 KB | <5 s |

**優化策略**：
- 使用 lazy loading（只載入需要的決策）
- 增量更新（只重建變更的部分）
- 快取機制（避免重複計算）

### Decimal 運算效能

```python
# 避免：每次都創建新 Decimal
for i in range(1000):
    result = Decimal(str(i)) * Decimal("0.05")  # 慢

# 優化：重用常數
FIVE_PERCENT = Decimal("0.05")
for i in range(1000):
    result = Decimal(str(i)) * FIVE_PERCENT  # 快
```

## 未來擴展

### E6: 決策樹視覺化（未實作）
- Graphviz/Mermaid 圖表生成
- 決策依賴關係圖
- 時間軸視圖

### E7: 決策導出（未實作）
- 匯出至 PDF/Excel
- API 整合（REST/GraphQL）
- 資料倉儲同步

### E8: 機器學習整合（未實作）
- 風險預測模型
- 決策推薦引擎
- 異常檢測

## 相關檔案

| 類型 | 路徑 |
|------|------|
| 契約文件 | `docs/contracts/io_contract.md` |
| API 參考 | `docs/advisor/stage3-api.md` |
| 規劃文件 | `docs/plans/phase5-stage3/plan.md` |
| 路由決策 | `~/.claude/cp-router/logs/rr_p5s3impl.json` |
