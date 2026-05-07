# 開發流程規範

<!-- 職責聲明：此文件定義開發流程護欄，資料操作護欄請見 CLAUDE.md -->
<!-- Last Reviewed: 2025-12-29 -->

## 1. 文件職責分工

| 文件 | 職責 | 機器可驗證 |
|------|------|-----------|
| **CLAUDE.md** | 資料操作護欄（raw/canonical/derived） | `lc doctor` |
| **DEVELOPMENT.md** | 開發流程護欄（規劃/Git/文件） | 手動 |
| **README.md** | 用戶使用指南 | N/A |

### 規則優先級

- **MUST**: 違反將阻止合併
- **SHOULD**: 建議遵循，需說明例外理由
- **MAY**: 最佳實踐，不強制

---

## 2. 規劃文件結構 (MUST)

```
docs/
├── DEVELOPMENT.md         # 本文件
├── roadmap/
│   └── V2.5.md            # 開發藍圖（Phase 定義來源）
├── plans/
│   ├── phase1-data/       # Phase 1 目錄
│   │   ├── plan.md        # 當前有效規劃 + 驗收報告
│   │   └── archive/       # 歷史版本
│   ├── phase2-scenario/
│   │   └── ...
│   ├── phase3-generation/
│   │   └── ...
│   └── phase5-advisor/
│       ├── plan.md            # Stage 1+2 規劃與驗收
│       └── stage3-design.md   # Stage 3 設計文件
├── advisor/                   # Phase 5 API 文件
│   ├── stage3-design.md
│   └── stage3-api.md
└── examples/              # 靜態範例資料
```

### 命名規範

- **規劃 + 驗收**: `docs/plans/{phase}/plan.md`（驗收報告**內嵌**於末尾）
- **歸檔版本**: `docs/plans/{phase}/archive/v{n}-{描述}.md`

---

## 3. Phase 生命週期 (MUST)

### 3.1 開始新 Phase

1. [ ] 建立 `docs/plans/{phase}/` 目錄
2. [ ] 建立 `plan.md` 初版
3. [ ] 更新 `docs/roadmap/V2.5.md` 狀態為 `🔄`
4. [ ] 確認前置 Phase 已驗收

### 3.2 完成 Phase

在 `plan.md` 末尾新增驗收報告：

```markdown
---

## 驗收報告

> **狀態**: ✅ 通過
> **日期**: YYYY-MM-DD
> **Commit**: xxxxxxx

### 驗收標準

| # | 標準 | 結果 | 驗證 |
|---|------|------|------|
| 1 | 所有測試通過 | ✅ | `pytest tests/` |
| 2 | lc doctor 無 hard fail | ✅ | `lc doctor` |

### 依賴項目

| 依賴 | 來源 | 狀態 |
|------|------|------|
| 三層結構 | Phase 0 | ✅ |

### 後續 Backlog

- [列出發現但未實作的項目]
```

### 3.3 歸檔

Phase 完成後：
1. 最終 `plan.md` 保留（含驗收報告）
2. 舊版本移至 `archive/`
3. 更新 `V2.5.md` 狀態為 `✅`

---

## 4. Git 規範 (SHOULD)

### Commit 訊息

```
<type>(<scope>): <subject>

type: feat | fix | docs | refactor | test | chore
scope: cli | models | io | calculators | docs
```

### Branch 策略

- `main`: 穩定版本
- `phase/{n}-{name}`: 開發中 Phase
- `hotfix/{issue}`: 緊急修復

---

## 5. 變更檢查 (MUST)

執行任何變更前（詳見 CLAUDE.md 護欄規則）：

```bash
uv run pytest tests/ -x         # 測試通過
lc doctor --path ./data         # 無 hard fail
```

---

## 6. 契約測試流程 (MUST)

### 6.1 測試分類

| 測試類型 | 檔案位置 | 說明 |
|----------|----------|------|
| 單元測試 | `tests/` | 核心邏輯測試 |
| 契約測試 | `tests/contracts/` | Schema 穩定性 + 行為回歸 |
| CI 護欄 | `.github/workflows/` | 自動化檢查 |

### 6.2 契約測試執行

```bash
# 執行所有契約測試
uv run pytest tests/contracts/ -v

# 只執行 Schema 穩定性測試
uv run pytest tests/contracts/test_schema_stability.py -v

# 只執行行為回歸測試
uv run pytest tests/contracts/test_phase_contracts.py -v
```

### 6.3 Schema Baseline 更新流程

**觸發時機**: 當 `models/*.py` 中有**預期的**欄位變更

**流程**:
1. 確認變更類型（參考 `docs/contracts/schema_contract.md`）
   - **Breaking**: 欄位刪除/改名、型別變更、Optional→Required → **需修改程式碼**
   - **Compatible**: 新增 Optional 欄位、Enum 新增、驗證放寬 → **需 sign-off**
2. 更新 Baseline:
   ```bash
   # 更新單一模型
   python scripts/update_schema_baseline.py --model ExpenseRecord

   # 更新所有模型
   python scripts/update_schema_baseline.py --all
   ```
3. 檢視 diff 報告:
   ```bash
   python scripts/check_schema_diff.py
   ```
4. 提交時加上 `schema-approved` label（若為 Compatible 變更）

### 6.4 Golden Data 更新流程

**觸發時機**: 行為邏輯變更導致回歸測試失敗

**流程**:
1. 確認失敗原因是預期的行為變更（非 bug）
2. 更新 `tests/contracts/golden/` 中的對應檔案
3. 重新執行測試確認通過
4. 提交需 CODEOWNERS 審核

### 6.5 新增模型時

1. 在 `scripts/update_schema_baseline.py` 的 `TRACKED_MODELS` 新增模型
2. 執行 `python scripts/update_schema_baseline.py --model <ModelName>`
3. 確認 baseline 已產生於 `tests/contracts/baselines/`
4. 執行測試確認通過

#### 6.5.1 Dataclass 模型 (capture/)

`capture/` 模組使用 dataclass 而非 Pydantic（符合隔離規則）：

```python
# capture/models.py 使用 dataclass
from dataclasses import dataclass

@dataclass
class StagingEntry:
    entry_id: str
    raw_text: str
    # ...
```

**Baseline 更新流程**:
1. 在 `TRACKED_MODELS` 加入 `"StagingEntry": "life_capital.capture.models"`
2. 手動建立 JSON Schema baseline（dataclass 無 `model_json_schema()`）
3. 或使用 `dataclasses-json-schema` 工具轉換

**隔離規則驗證**:
```bash
# capture/ 不可依賴 models/
grep -r "from life_capital.models" life_capital/capture/
# 預期：無結果
```

#### 6.5.2 Advisor 模組 (advisor/ + privacy/)

Phase 5 AI 顧問系統新增以下模組：

**advisor/** - 決策比較器：
- `schemas.py`: 13 DTOs 凍結（DecisionCard, DecisionOption 等）
- `context_builder.py`: 上下文建構器
- `decision_comparator.py`: 可比較性判定（4 維特徵）
- `decisions_handler.py`: 決策記憶（append-only YAML）
- `templates/`: 5 個決策模板骨架

**privacy/redaction/** - 隱私保護：
- `engine.py`: Redaction 引擎
- `rules.py`: 三層規則（FORBIDDEN/SENSITIVE/COMPOSITION）
- `decision_context.py`: 去識別化上下文

**隔離規則驗證**:
```bash
# advisor/ 透過 interfaces/ 讀取 canonical
grep -r "from life_capital.interfaces" life_capital/advisor/
# 預期：使用 CanonicalReader Protocol
```

**測試統計**: 233 advisor-specific tests（含 53 redaction + 22 decisions_handler）

### 6.6 CI 護欄檢查項

| 檢查項 | 說明 | 失敗處理 |
|--------|------|----------|
| Schema 穩定性 | 比對 13 models baseline | 更新 baseline 或修復變更 |
| 行為回歸 | Golden Data 比對 | 確認變更或修復邏輯 |
| Flaky 偵測 | 一次 rerun 機制 | 調查並穩定測試 |
| Label 檢查 | Schema 變更需 `schema-approved` | 審核後加上 label |

---

## 6.5 新增 Advisor 模組時 (SHOULD)

### 新增生成器

1. [ ] 建立 `generation/{name}.py`
2. [ ] 實作 `generate()` 函數，回傳 Markdown 字串
3. [ ] 新增對應測試 `tests/generation/test_{name}.py`
4. [ ] 更新 `io/registry.py` 版本常數（如需）

### 新增分析器

1. [ ] 建立 `advisor/{name}.py`
2. [ ] 使用 `advisor/shared/evaluability.py` 判定可評估性
3. [ ] 新增對應測試 `tests/advisor/test_{name}.py`
4. [ ] 整合至 CLI（`commands/advisor.py`）

---

## 7. 現有文件處理（一次性）

```bash
# 遷移現有 Phase 1 規劃
mkdir -p docs/plans/phase1-data/archive
git mv docs/plans/phase1-data-v1.md docs/plans/phase1-data/archive/v1-initial.md
git mv docs/plans/phase1-data-v2.md docs/plans/phase1-data/archive/v2-round1.md
git mv docs/plans/phase1-data-v3.md docs/plans/phase1-data/archive/v3-round2.md
git mv docs/plans/phase1-data-v4.md docs/plans/phase1-data/plan.md
```

---

## 參考資料

- AI 護欄: [CLAUDE.md](../CLAUDE.md)
- 用戶指南: [README.md](../README.md)
- 開發藍圖: [docs/roadmap/V2.5.md](roadmap/V2.5.md)
