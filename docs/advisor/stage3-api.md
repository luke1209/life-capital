# Stage 3 API 參考

> Phase 5 Stage 3 Advisor 模組 API 完整參考文件

## CLI 命令

### lc advisor history

**用法**：顯示決策歷史記錄

```bash
lc advisor history [OPTIONS] [PATH]
```

**參數**：
- `PATH` (可選): 資料目錄路徑，預設 `~/.life-capital`
- `--limit INTEGER`: 顯示最近 N 筆決策（預設 10）
- `--status TEXT`: 過濾狀態（pending/applied/reverted）

**輸出**：Rich table 格式，包含：
- Decision ID (ULID 格式)
- 標題
- 創建時間
- 狀態 (pending/applied/reverted)
- 風險等級

**範例**：
```bash
# 顯示最近 10 筆決策
lc advisor history

# 顯示最近 20 筆決策
lc advisor history --limit 20

# 只顯示已應用的決策
lc advisor history --status applied

# 指定資料目錄
lc advisor history --path ./my-data --limit 5
```

**Exit Codes**：
- `0`: 成功
- `1`: 找不到決策記錄（warning）

---

### lc advisor explain

**用法**：詳細解釋單一決策

```bash
lc advisor explain <DECISION_ID> [OPTIONS] [PATH]
```

**參數**：
- `DECISION_ID` (必填): 決策 ID (ULID 格式，如 `dec_01ARZ3NDEKTSV4RRFFQ69G5FAV`)
- `PATH` (可選): 資料目錄路徑，預設 `~/.life-capital`

**輸出**：Rich panel 格式，包含：
- 基本資訊 (ID, 標題, 類型, 狀態)
- 決策理由 (V1.1 新增欄位)
- 風險評估
- 敏感度分析結果
- 回復歷史（若已回復）
- Evaluability 評分

**範例**：
```bash
# 解釋決策
lc advisor explain dec_01ARZ3NDEKTSV4RRFFQ69G5FAV

# 指定資料目錄
lc advisor explain dec_01ARZ3NDEKTSV4RRFFQ69G5FAV --path ./my-data
```

**Exit Codes**：
- `0`: 成功
- `1`: 決策不存在

---

### lc advisor cleanup

**用法**：清理舊的 derived advisor 檔案

```bash
lc advisor cleanup [OPTIONS] [PATH]
```

**參數**：
- `PATH` (必填): 資料目錄路徑
- `--keep-latest INTEGER`: 保留最近 N 個版本（預設 3）
- `--dry-run`: 預覽模式，不實際刪除

**行為**：
- 掃描 `derived/advisor/reports/` 目錄
- 按照檔案修改時間排序
- 保留最新的 N 個檔案
- 互動式確認（除非 --dry-run）

**範例**：
```bash
# 預覽將刪除的檔案
lc advisor cleanup ./data --dry-run

# 保留最近 5 個版本
lc advisor cleanup ./data --keep-latest 5

# 執行清理（會顯示確認提示）
lc advisor cleanup ./data
```

**Exit Codes**：
- `0`: 成功或取消操作
- `1`: 找不到報表目錄

---

### lc doctor --advisor

**用法**：檢查 advisor 模組健康狀態

```bash
lc doctor [OPTIONS] [PATH]
```

**參數**：
- `PATH` (必填): 資料目錄路徑
- `--advisor`: 啟用 advisor 模組檢查
- `--format TEXT`: 輸出格式（text/json，預設 text）

**檢查項目**：
1. **Directory Exists**: `derived/advisor/` 是否存在
2. **Provenance Valid**: 所有 YAML 檔案是否包含有效的 `_provenance`
3. **Hash Verified**: 所有 `content_hash` 是否與實際內容一致
4. **No Orphaned Files**: 是否有未追蹤的檔案

**輸出格式** (text):
```
Advisor Module Health Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Directory exists
✓ Provenance valid
✓ Content hash verified
✓ No orphaned files

Summary: All checks passed (4/4)
Status: OK
```

**輸出格式** (json):
```json
{
  "status": "ok",
  "checks": [
    {"name": "Directory exists", "status": "pass", "message": "..."},
    {"name": "Provenance valid", "status": "pass", "message": "..."},
    {"name": "Hash verified", "status": "pass", "message": "..."},
    {"name": "No orphaned files", "status": "pass", "message": "..."}
  ],
  "summary": {
    "total": 4,
    "passed": 4,
    "warnings": 0,
    "errors": 0
  }
}
```

**Exit Codes**：
- `0`: 所有檢查通過（ok）
- `1`: 有警告（warning）
- `2`: 有錯誤（error）

**範例**：
```bash
# 文字格式輸出
lc doctor ./data --advisor

# JSON 格式輸出
lc doctor ./data --advisor --format json

# 用於 CI/CD 檢查
lc doctor ./data --advisor && echo "Health check passed"
```

---

## Python API

### evaluability 模組

#### evaluate_decision()

**函式簽名**：
```python
def evaluate_decision(decision: DecisionRecord) -> EvaluabilityResult:
    """評估決策的可推薦性與可評估性"""
```

**參數**：
- `decision` (DecisionRecord): 決策記錄物件

**回傳**：
- `EvaluabilityResult`: 包含 `recommendability` 和 `comparability` 分數

**範例**：
```python
from life_capital.advisor.evaluability import evaluate_decision
from life_capital.models.decisions import DecisionRecord

decision = DecisionRecord(
    decision_id="dec_01ARZ3NDEKTSV4RRFFQ69G5FAV",
    decision_type="expense_policy",
    status="pending",
    created_at="2025-01-15T10:30:00",
    decision_payload={
        "category": "食物",
        "monthly_budget": "5000",
        "rationale": "根據過去 3 個月平均支出設定"
    },
    risk_level="low"
)

result = evaluate_decision(decision)
print(f"Recommendability: {result.recommendability}")  # 0.8
print(f"Comparability: {result.comparability}")        # 0.6
```

**Recommendability 閾值**：
- `≥ 0.7`: FULL（完整推薦）
- `0.5-0.7`: PARTIAL（部分推薦，需加註說明）
- `< 0.5`: NONE（不推薦）

**Comparability 閾值**：
- `≥ 0.5`: FULL（完整可評估）
- `0.3-0.5`: WARNING（可評估但需標註不確定性）
- `< 0.3`: SKIP（跳過評估）

---

### sensitivity_analyzer 模組

#### analyze_sensitivity()

**函式簽名**：
```python
def analyze_sensitivity(
    decision: DecisionRecord,
    baseline_strategy: str = "baseline_v1"
) -> Optional[SensitivityAnalysis]:
    """分析決策參數敏感度，若 comparability < 0.3 回傳 None"""
```

**參數**：
- `decision` (DecisionRecord): 決策記錄
- `baseline_strategy` (str): 基準策略名稱，預設 `"baseline_v1"`

**回傳**：
- `SensitivityAnalysis` 或 `None`（若 evaluability 不足）

**邏輯**：
1. 呼叫 `evaluate_decision()` 檢查 `comparability`
2. 若 `comparability < 0.3`，回傳 `None`（不執行敏感度分析）
3. 執行 ±5%, ±10% 微擾測試（discount_rate, horizon_years）
4. 檢查單調性（discount_rate ↑ → burden ↓）

**範例**：
```python
from life_capital.advisor.sensitivity_analyzer import analyze_sensitivity

result = analyze_sensitivity(decision)

if result is None:
    print("Evaluability 不足，跳過敏感度分析")
else:
    print(f"Baseline: {result.baseline_strategy}")
    print(f"Monotonic: {result.is_monotonic}")
    for p in result.perturbations:
        print(f"  {p['parameter']}: {p['delta_pct']} → burden={p['burden']}")
```

**SensitivityAnalysis 結構**：
```python
@dataclass(frozen=True)
class SensitivityAnalysis:
    decision_id: str
    baseline_strategy: str
    perturbations: List[Dict[str, Any]]  # [{ parameter, delta_pct, burden, change_pct }]
    is_monotonic: bool
    warnings: List[str]
```

---

### decision_wiki 模組

#### generate_decision_wiki()

**函式簽名**：
```python
def generate_decision_wiki(
    decision: DecisionRecord,
    data_path: Path
) -> str:
    """生成單一決策的 Markdown Wiki 頁面"""
```

**參數**：
- `decision` (DecisionRecord): 決策記錄
- `data_path` (Path): 資料根目錄路徑

**回傳**：
- `str`: Markdown 格式的 Wiki 內容

**輸出格式**：
```markdown
# Decision: [標題]

## 基本資訊
- **ID**: dec_xxx
- **類型**: expense_policy
- **狀態**: applied
- **風險等級**: low
- **創建時間**: 2025-01-15 10:30:00

## 決策內容
...

## 決策理由
(V1.1 新增欄位，若存在則顯示)

## 風險評估
...

## 敏感度分析
(若 evaluability 足夠則顯示微擾結果)
```

**範例**：
```python
from life_capital.generation.decision_wiki import generate_decision_wiki

wiki_content = generate_decision_wiki(decision, Path("./data"))
print(wiki_content)
```

---

#### save_decision_wiki()

**函式簽名**：
```python
def save_decision_wiki(
    decision: DecisionRecord,
    data_path: Path
) -> Path:
    """生成並儲存 Wiki，回傳儲存路徑"""
```

**行為**：
1. 呼叫 `generate_decision_wiki()` 生成內容
2. 計算 `content_hash` (SHA-256)
3. 建立 `AdvisorDerivedProvenance`（含 RebuildCommand）
4. 原子寫入 `derived/advisor/wikis/dec_xxx.md`

**範例**：
```python
from life_capital.generation.decision_wiki import save_decision_wiki

output_path = save_decision_wiki(decision, Path("./data"))
print(f"Wiki saved to: {output_path}")
```

---

### risk_matrix 模組

#### generate_risk_matrix()

**函式簽名**：
```python
def generate_risk_matrix(
    decisions: List[DecisionRecord],
    data_path: Path
) -> Dict[str, Any]:
    """生成風險矩陣報告"""
```

**參數**：
- `decisions` (List[DecisionRecord]): 決策列表
- `data_path` (Path): 資料根目錄

**回傳**：
- `Dict[str, Any]`: JSON 格式報告

**報告結構**：
```json
{
  "total_decisions": 10,
  "risk_distribution": {
    "low": 5,
    "medium": 3,
    "high": 2
  },
  "stratification": {
    "high": [
      {
        "decision_id": "dec_xxx",
        "title": "...",
        "risk_level": "high",
        "created_at": "...",
        "evaluability": {
          "recommendability": 0.5,
          "comparability": 0.7,
          "recommendation": "PARTIAL"
        }
      }
    ],
    "medium": [],
    "low": []
  }
}
```

**範例**：
```python
from life_capital.generation.risk_matrix import generate_risk_matrix

report = generate_risk_matrix(all_decisions, Path("./data"))
print(f"Total: {report['total_decisions']}")
print(f"High risk: {report['risk_distribution']['high']}")
```

---

#### save_risk_matrix()

**函式簽名**：
```python
def save_risk_matrix(
    decisions: List[DecisionRecord],
    data_path: Path
) -> Path:
    """生成並儲存風險矩陣報告"""
```

**行為**：
1. 呼叫 `generate_risk_matrix()` 生成報告
2. 計算 `content_hash`
3. 建立 `AdvisorDerivedProvenance`
4. 原子寫入 `derived/advisor/reports/risk_matrix_YYYYMMDD_HHMMSS.json`

---

### sensitivity_report 模組

#### generate_sensitivity_report()

**函式簽名**：
```python
def generate_sensitivity_report(
    decisions: List[DecisionRecord],
    data_path: Path
) -> Dict[str, Any]:
    """生成敏感度分析報告"""
```

**報告結構**：
```json
{
  "analyzed_count": 5,
  "skipped_count": 3,
  "analyses": [
    {
      "decision_id": "dec_xxx",
      "baseline_strategy": "baseline_v1",
      "is_monotonic": true,
      "perturbations": [
        {
          "parameter": "discount_rate",
          "delta_pct": "0.05",
          "burden": "123456.78",
          "change_pct": "-2.5"
        }
      ],
      "warnings": []
    }
  ]
}
```

---

## 資料模型

### DecisionRecord (V1.1)

**Schema 版本**：1.1

**欄位定義**：
```python
@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str                         # ULID 格式 dec_xxx
    decision_type: str                       # 決策類型
    status: str                              # pending/applied/reverted
    created_at: str                          # ISO 8601
    decision_payload: Dict[str, Any]         # 決策內容（JSON）
    risk_level: str                          # low/medium/high
    tags: Optional[List[str]] = None         # 標籤列表
    decision_rationale: Optional[str] = None # V1.1 新增：決策理由
    reverted_from_decision_id: Optional[str] = None  # V1.1 新增：回復來源
```

**狀態轉換規則**：
- `None` → `PENDING`
- `PENDING` → `APPLIED`
- `PENDING` → `REVERTED`
- `APPLIED` → `REVERTED`

**禁止轉換**：
- `REVERTED` → `APPLIED`
- `APPLIED` → `PENDING`
- 任何跳躍式轉換

---

### EvaluabilityResult

```python
@dataclass(frozen=True)
class EvaluabilityResult:
    recommendability: Decimal  # 0.0-1.0
    comparability: Decimal     # 0.0-1.0
```

**計算邏輯**：
- `recommendability`: 根據 decision_payload 結構化程度、rationale 完整性、risk_level 判斷
- `comparability`: 根據可量化參數數量、歷史資料可用性判斷

---

### AdvisorDerivedProvenance (V1.0)

```python
@dataclass(frozen=True)
class AdvisorDerivedProvenance:
    schema_version: str                    # "1.0"
    provenance_type: str                   # "advisor_derived"
    content_hash: str                      # SHA-256 hash（不含 _provenance）
    generated_at: str                      # ISO 8601
    input_decisions: List[str]             # 輸入決策 ID 列表
    canonical_version: str                 # Canonical 版本（預留）
    rebuild_command: List[str]             # 重建指令（structured list）
```

**RebuildCommand 格式**：
```python
rebuild_command = [
    "lc", "advisor", "rebuild",
    "--decision-ids", "dec_xxx,dec_yyy",
    "--output", "derived/advisor/reports/risk_matrix.json"
]
```

**注意事項**：
- 不使用字串拼接，使用 `list[str]`
- 路徑/參數需用 `shlex.quote()` 處理
- 執行時使用 `subprocess.run(rebuild_command, check=True)`

---

## 安全邊界

### 路徑驗證（AdvisorDerivedHandler）

**三層驗證**：

1. **Base Directory Check**:
   - 檔案必須位於 `derived/advisor/` 下
   - 使用 `Path.resolve()` 解析絕對路徑
   - 檢查是否為 base_dir 的子路徑

2. **Extension Whitelist**:
   - 允許副檔名：`.md`, `.json`, `.meta.json`
   - 拒絕其他所有副檔名

3. **Component Check**:
   - 禁止路徑包含 `..`（traversal attack）
   - 禁止空白開頭的元件名稱

**範例**（會被拒絕的路徑）：
```python
# Traversal attack
"derived/advisor/../../canonical/decisions.yaml"  # ❌

# 不在 base_dir 下
"derived/reports/risk_matrix.json"  # ❌

# 不允許的副檔名
"derived/advisor/script.sh"  # ❌

# 空白開頭
"derived/advisor/ malicious.json"  # ❌
```

---

## 測試策略

### 測試檔案結構

```
tests/
├── advisor/
│   ├── test_evaluability.py              # evaluability 模組（20 tests）
│   ├── test_risk_assessor.py             # risk_assessor 模組（24 tests）
│   ├── test_sensitivity_analyzer.py      # sensitivity_analyzer 模組（16 tests）
│   └── test_decision_wiki.py             # decision_wiki 模組（20 tests）
├── generation/
│   ├── test_risk_matrix.py               # risk_matrix 生成（24 tests）
│   └── test_sensitivity_report.py        # sensitivity_report 生成（24 tests）
├── commands/
│   ├── test_advisor_cmd.py               # CLI 命令（14 tests）
│   └── test_doctor_advisor.py            # doctor --advisor（10 tests）
├── io/
│   ├── test_canonical_handler.py         # Canonical handler（21 tests）
│   └── test_path_security.py             # 路徑安全（額外測試）
└── acceptance/
    └── test_stage3_acceptance.py         # E2E 驗收測試（待建立）
```

### 測試覆蓋率要求

- **單元測試**：≥80%
- **整合測試**：≥70%
- **E2E 驗收測試**：所有主要使用情境

---

## 版本相容性

### V1.0 → V1.1 Migration

**新增欄位**：
- `decision_rationale: Optional[str]`
- `reverted_from_decision_id: Optional[str]`

**讀取策略**：
- 使用 `.get()` 方法，缺失欄位回傳 `None`
- 允許 V1.0 格式正常讀取

**寫入策略**：
- 只寫入非 `None` 欄位
- 避免污染 V1.0 格式檔案

**測試要求**：
- 建立 V1.0/V1.1 cross-version fixtures
- 測試向前/向後相容性

---

## 效能考量

### 批次操作建議

- **決策歷史查詢**：使用 `--limit` 限制輸出量
- **大量決策分析**：使用 generator pattern 避免一次載入所有決策
- **敏感度分析**：跳過 comparability < 0.3 的決策（節省計算）

### 快取策略

- **Evaluability 結果**：可快取於記憶體（決策不變時重用）
- **Wiki 生成**：檢查 content_hash，避免重複生成
- **風險矩陣**：批次更新，避免逐筆計算

---

## 常見問題

### Q1: 如何重建所有 derived advisor 資料？

```bash
# 使用 lc rebuild 指令（假設未來實作）
lc rebuild --module advisor --path ./data

# 或手動刪除 derived/advisor/ 並重新生成
rm -rf ./data/derived/advisor/
lc advisor history --path ./data  # 觸發重新生成
```

### Q2: RebuildCommand 為何使用 list[str] 而非字串？

**原因**：
- 避免 shell injection 風險
- 參數自動轉義（使用 `shlex.quote()`）
- 可直接傳入 `subprocess.run()`

**錯誤示範**：
```python
# ❌ 字串拼接（有 injection 風險）
cmd = f"lc advisor rebuild --decision-ids {decision_ids}"
```

**正確示範**：
```python
# ✅ 結構化列表
cmd = ["lc", "advisor", "rebuild", "--decision-ids", decision_ids]
subprocess.run(cmd, check=True)
```

### Q3: 為何 sensitivity_analyzer 會回傳 None？

**原因**：
- 決策的 `comparability < 0.3`，無法進行有意義的敏感度分析
- 遵循 evaluability 模組的 SKIP 規則

**處理方式**：
```python
result = analyze_sensitivity(decision)
if result is None:
    print("跳過敏感度分析（evaluability 不足）")
else:
    # 使用 result
    print(f"Baseline: {result.baseline_strategy}")
    print(f"Monotonic: {result.is_monotonic}")
```

### Q4: 如何處理 V1.0 舊檔案？

**自動相容**：
- 讀取時使用 `.get()` fallback
- 不需手動遷移

**主動升級**（若需要新欄位）：
1. 讀取 V1.0 決策
2. 補充 `decision_rationale` 欄位
3. 使用 `lc apply` 重新儲存（自動升級為 V1.1）

---

## 參考資料

- **設計文件**: `docs/advisor/stage3-design.md`
- **契約規範**: `docs/contracts/io_contract.md` (Section 10 & 11)
- **測試範例**: `tests/advisor/`, `tests/generation/`, `tests/commands/`
- **主專案 README**: `README.md`
