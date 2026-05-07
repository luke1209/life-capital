# Phase 4 CAPTURE - Compact Reference (實作版)

> **Single Source of Truth** - 精簡版執行合約（反映實際實作狀態）
> **完整計劃**: `plan.md` (V4.1.1)
> **狀態**: Week 1-2 P0 完成 ✅ | Week 3-4 待開始 ⏳

**最後更新**: 2025-12-28
**版本**: V4.1.1 Compact (實作版)

---

## A. 變更摘要（必留）

### 問題
**現狀**: 零散支出輸入（對話、筆記、口述）無法直接進入結構化資料，需手動轉寫為 CSV

**痛點**:
- 手動轉寫耗時、易錯
- 日期/金額/類別解析規則散落各處
- 無法漸進式解析（一次失敗全失敗）

### 設計
**核心策略**: Interface 隔離 + 漸進式解析 + Proposal 工作流程

**三階段流程**:
```
用戶輸入 → staging/ → proposals/ → canonical/
  ↓           ↓          ↓           ↓
capture    parse      apply       資料層
```

**關鍵設計決策**:
1. **Interface 隔離**: `capture/` 只依賴 `interfaces/`，StagingEntry 定義於 `capture/models.py`（dataclass，非 Pydantic）
2. **8 狀態狀態機**: pending → parsed → approved → applied（終態）
3. **信心度機制**: 加權評分（R×0.35 + F×0.30 + A×0.20 + Cr×0.15）+ 三欄位確定性護欄
4. **JSONL append-only**: last-write-wins 語意 + _seq 並發控制（threading.Lock）
5. **終態追蹤**: proposal_id（approved 時寫入）+ canonical_record_id（applied 時寫入）
6. **保守判重**: 需 date + amount + normalized_text 完整匹配

### 影響邊界

**新增模組** (✅ 已實作):
- `life_capital/capture/` - 5 個 .py 檔案（完全隔離，只依賴 interfaces/）
  - `models.py` - StagingEntry dataclass + 5 個 Enum
  - `date_adapter.py` - 日期解析（內建規則優先 + dateparser fallback）
  - `entity_extractor.py` - 實體抽取（金額/日期/類別/商家）
  - `expense_parser.py` - 解析器核心 + 信心度計算 + auto-approve 護欄
  - `staging_service.py` - 8 狀態狀態機 + 保守判重
- `life_capital/interfaces/staging_store.py` - StagingStore Protocol
- `life_capital/io/staging_store.py` - JSONL 實作（append-only + _seq）

**新增 CLI** (✅ 已實作):
- `lc capture "..."` - 捕捉零散輸入（單筆/批次）
- `lc staging list/show/parse/approve/reject/ignore` - staging 管理（8 個子指令）

**新增測試** (⚠️ 部分完成):
- `tests/capture/test_date_adapter.py` - 37 tests ✅
- `tests/capture/test_staging_service.py` - 48 tests ✅
- `tests/capture/test_entity_extractor.py` - ⏳ 待補（26 邊緣情境）
- `tests/capture/test_expense_parser.py` - ⏳ 待補
- `tests/commands/test_capture_cmd.py` - ⏳ 待補
- `tests/commands/test_staging_cmd.py` - ⏳ 待補（38 tests）

**輸出變更** (⏳ 待建立):
- `~/.life-capital/staging/entries.jsonl` - 新增（使用時自動建立）
- `~/.life-capital/proposals/pending/` - 透過 proposals_handler 建立

**不影響**:
- `canonical/` 寫入邏輯（維持 `lc apply` 唯一入口）
- `raw/` / `derived/` 結構
- 現有 Phase 0-3 功能

---

## B. Code-level 合約（必留）

### 入口點

**CLI Commands** (✅ 已實作):
```python
# life_capital/commands/capture_cmd.py
def capture(
    text: Optional[str] = None,           # 自然語言輸入
    batch: Optional[Path] = None,         # 批次檔案路徑
    source: str = "cli",                  # 來源標記
    path: Optional[str] = None            # 資料目錄
) -> None:
    """捕捉零散支出輸入至 staging"""

# life_capital/commands/staging_cmd.py
def list(status: Optional[str] = None, path: Optional[str] = None) -> None:
def show(entry_id: str, path: Optional[str] = None) -> None:
def parse(confirm: bool = False, path: Optional[str] = None) -> None:
def approve(entry_id: str, path: Optional[str] = None) -> None:
def reject(entry_id: str, reason: str, path: Optional[str] = None) -> None:
def ignore(entry_id: str, reason: str = "", path: Optional[str] = None) -> None:
```

**核心服務** (✅ 已實作):
```python
# life_capital/capture/staging_service.py
class StagingService:
    def add_entry(self, text: str, source: str = "cli", batch_id: Optional[str] = None) -> StagingEntry
    def list_entries(self, status: Optional[str] = None) -> list[StagingEntry]
    def get_entry(self, entry_id: str) -> StagingEntry
    def parse_entry(self, entry_id: str) -> ParseResult
    def parse_all_pending(self) -> list[tuple[str, str, Optional[str]]]  # (entry_id, new_status, error)
    def approve_entry(self, entry_id: str) -> StagingEntry  # ⚠️ Proposal 整合待完成
    def reject_entry(self, entry_id: str, reason: str) -> StagingEntry
    def ignore_entry(self, entry_id: str, reason: str = "") -> StagingEntry
    def mark_duplicate(self, entry_id: str, duplicate_of: str, reason: str) -> StagingEntry
```

**解析器** (✅ 已實作):
```python
# life_capital/capture/expense_parser.py
class ExpenseParser:
    def parse(self, text: str) -> ParseResult:
        """解析自然語言支出描述"""
```

### 關鍵 Types

**1. StagingEntry** (`capture/models.py`) - ✅ 已實作（26 欄位）:
```python
@dataclass
class StagingEntry:
    # 基本欄位
    entry_id: str                    # UUID
    raw_text: str                    # 原始輸入
    created_at: datetime             # 輸入時間

    # 解析結果（Optional）
    parsed_date: Optional[date]
    parsed_amount: Optional[Decimal]
    parsed_category: Optional[str]
    parsed_merchant: Optional[str]
    parsed_note: Optional[str]

    # 狀態與信心度
    status: StagingStatus            # Enum（8 狀態）
    confidence: float = 0.0          # 0.0-1.0
    confidence_breakdown: Optional[dict] = None

    # V4.1.1 追蹤欄位
    proposal_id: Optional[str] = None          # approved 時寫入
    canonical_record_id: Optional[str] = None  # applied 時寫入

    # 去重
    duplicate_of: Optional[str] = None
    duplicate_reason: Optional[str] = None  # DuplicateReason enum

    # Metadata
    parser_version: str = "1.0"
    batch_id: Optional[str] = None
    source: str = "cli"
    raw_locale: str = "zh-TW"
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    error_message: Optional[str] = None
```

**2. 5 個 Enum** (✅ 已實作):
```python
class StagingStatus(str, Enum):
    PENDING = "pending"      # 待解析
    PARSED = "parsed"        # 已解析，待確認
    ERROR = "error"          # 解析失敗
    APPROVED = "approved"    # 已批准，proposal 已建立
    REJECTED = "rejected"    # 已拒絕
    IGNORED = "ignored"      # 非支出
    DUPLICATE = "duplicate"  # 重複輸入
    APPLIED = "applied"      # 終態：已進入 canonical

class AmountSource(str, Enum):
    EXACT = "exact"         # 明確數字
    RANGE = "range"         # 範圍取值
    INFERRED = "inferred"   # 推斷
    MISSING = "missing"     # 無法抽取

class DateSource(str, Enum):
    BUILTIN_EXACT = "builtin_exact"         # 內建規則精確
    BUILTIN_INFERRED = "builtin_inferred"   # 內建規則推斷
    DATEPARSER = "dateparser"               # dateparser fallback
    RELATIVE = "relative"                   # 相對日期
    MISSING = "missing"

class CategorySource(str, Enum):
    EXACT = "exact"   # 完全匹配
    FUZZY = "fuzzy"   # 模糊匹配
    MISSING = "missing"

class DuplicateReason(str, Enum):
    DUP_KEY_EXACT = "exact_key_match"           # 完全匹配
    DUP_DATE_FUZZ = "date_fuzzy_match"          # 日期 ±2 天
    DUP_AMOUNT_MISSING = "amount_missing_fuzzy" # 金額缺失
```

**3. ParseResult** (`capture/expense_parser.py`) - ✅ 已實作:
```python
@dataclass
class ParseResult:
    # 抽取結果
    amount: Optional[Decimal]
    date: Optional[date]
    category: Optional[str]
    merchant: Optional[str]
    note: Optional[str]

    # 信心度
    confidence: float
    confidence_breakdown: dict[str, float]

    # V4.1.1: 來源枚舉（確定性判斷）
    amount_source: AmountSource
    date_source: DateSource
    category_source: CategorySource

    # Derived properties
    @property
    def amount_certain(self) -> bool:
        return self.amount_source == AmountSource.EXACT

    @property
    def date_certain(self) -> bool:
        return self.date_source == DateSource.BUILTIN_EXACT

    @property
    def category_certain(self) -> bool:
        return self.category_source == CategorySource.EXACT
```

**4. Protocols** (✅ 已實作):
```python
# life_capital/interfaces/staging_store.py
class StagingStore(Protocol):
    def write_entry(self, entry: StagingEntry) -> None: ...
    def read_current_state(self) -> dict[str, StagingEntry]: ...
    def read_entry(self, entry_id: str) -> StagingEntry: ...
```

### I/O 合約

**輸入**:
- 自然語言文字（CLI argument 或批次檔案，每行一筆）
- 現有資料：`expense_policy.yaml`（類別清單）、`canonical/expenses/`（判重用）

**輸出檔案**: `~/.life-capital/staging/entries.jsonl`

**格式規範** (✅ 已實作):
```jsonl
{"entry_id": "uuid", "raw_text": "...", "status": "pending", "_seq": 1, "created_at": "...", ...}
{"entry_id": "uuid", "status": "parsed", "_seq": 2, "parsed_amount": "320", ...}
```

**寫入策略** (✅ 已實作):
- Append-only log（不修改既有行）
- `_seq` 遞增序號（O(1) 演算法：讀取最後一行 + 1）
- Last-write-wins 讀取語意

**_seq 生成規則** (✅ 已實作):
```python
def _get_next_seq(self) -> int:
    """O(1) 讀取最後一行的 _seq + 1"""
    if not self._jsonl_path.exists():
        return 1
    # 實際實作：讀取最後一行 JSON 並解析
```

**並發護欄** (✅ 已實作):
- threading.Lock（同進程保護）
- ⏳ fcntl.flock（跨進程，P2 增強）

**Proposal 輸出** (⏳ 待整合):
- 路徑: `~/.life-capital/proposals/pending/`
- 透過 `proposals_handler.create_expense_proposals()` 寫入
- 在 `approve_entry()` 中呼叫（TODO）

### 錯誤處理策略

**1. 解析失敗** (✅ 已實作):
```python
# 狀態: pending → error
# error_message: "無法抽取金額"
# 用戶可重新 parse
```

**2. 狀態機違規** (✅ 已實作):
```python
class InvalidStateTransition(Exception):
    """非法狀態轉移"""
# 拒絕操作 + raise exception
```

**3. Parse 原子性** (✅ 已實作):
```python
# 原子單位: entry-by-entry（非 batch transaction）
# 部分成功: 允許（parse_all_pending 返回成功/失敗清單）
# Exit code: 0 = 全成功, 1 = 部分失敗, 2 = 全失敗
```

**4. 判重處理** (✅ 已實作):
```python
def compute_duplicate_key(entry: StagingEntry) -> Optional[str]:
    """保守判重：需 date + amount + normalized_text"""
    if not (entry.parsed_date and entry.parsed_amount):
        return None  # 資訊不足，無法可靠判重

    normalized_text = normalize_text_without_date_amount(entry.raw_text)
    return f"{entry.parsed_date}|{entry.parsed_amount}|{normalized_text}"
```

**5. 不一致檢測** (⏳ 待實作 - Week 4):
```python
# lc staging repair 偵測：
# - status=approved 但 proposal_id=None
# - proposal_id 存在但 status≠approved/applied
# - status=applied 但 canonical_record_id=None
```

---

## C. 檔案清單（必留）

### 新增檔案（✅ 已實作）

**核心模組**:
```
life_capital/capture/
├── __init__.py                  # ✅
├── models.py                    # ✅ StagingEntry + 5 Enums（26 欄位）
├── entity_extractor.py          # ✅ 實體抽取（金額/日期/類別/商家）
├── date_adapter.py              # ✅ 日期解析（內建規則 + dateparser fallback）
├── expense_parser.py            # ✅ 解析器核心 + ParseResult + ConfidenceConfig
└── staging_service.py           # ✅ 8 狀態狀態機 + 保守判重
```

**Interface 層**:
```
life_capital/interfaces/
└── staging_store.py             # ✅ StagingStore Protocol
```

**IO 層**:
```
life_capital/io/
└── staging_store.py             # ✅ StagingStoreImpl（JSONL 讀寫 + _seq）
```

**CLI 層**:
```
life_capital/commands/
├── capture_cmd.py               # ✅ lc capture
└── staging_cmd.py               # ✅ lc staging（8 個子指令）
```

**測試（⚠️ 部分完成）**:
```
tests/capture/
├── test_date_adapter.py         # ✅ 37 tests
├── test_staging_service.py      # ✅ 48 tests
├── test_entity_extractor.py     # ⏳ 待補（26 邊緣情境）
└── test_expense_parser.py       # ⏳ 待補

tests/commands/
├── test_capture_cmd.py          # ⏳ 待補
└── test_staging_cmd.py          # ⏳ 待補（38 tests）

tests/contracts/
├── test_capture_isolation.py    # ⏳ 待補（隔離規則驗證）
└── test_staging_state_machine.py # ⏳ 待補（狀態機轉移規則）
```

### 修改檔案（✅ 已完成）

**CLI 註冊**:
```
life_capital/cli.py              # ✅ 註冊 capture/staging 指令
```

**Baseline 更新**:
```
tests/contracts/baselines/StagingEntry.json  # ✅ 已建立（dataclass baseline）
```

### 刪除檔案

無（純新增功能）

---

## D. 仍未完成（必留）

### TODO（按優先級，含檔案位置）

**Week 3 - P1（重要功能）**:
- [ ] **Proposal 整合** - `capture/staging_service.py:approve_entry()`
  - 整合 `proposals_handler.create_expense_proposals()`
  - 在 approve() 成功後寫入 `proposal_id`
  - 預期行為: StagingEntry.proposal_id 指向實際 proposal 檔案
  - 檔案: `life_capital/capture/staging_service.py:294`（標註 TODO）

- [ ] **契約測試 - 隔離規則** - `tests/contracts/test_capture_isolation.py`
  - 驗證 capture/ 不 import models/
  - 驗證只依賴 interfaces/
  - 預期: CI 自動檢查，違反時 build 失敗

- [ ] **契約測試 - 狀態機** - `tests/contracts/test_staging_state_machine.py`
  - 驗證 8 狀態轉移規則
  - 驗證防護規則（approved 不可直接編輯）
  - 預期: 所有非法轉移拋出 InvalidStateTransition

- [ ] **單元測試 - 實體抽取** - `tests/capture/test_entity_extractor.py`
  - 26 個 V3 邊緣情境（分隔符、全形、負數、相對日期等）
  - 預期: 覆蓋 entity_extractor.py 所有分支

- [ ] **單元測試 - 解析器** - `tests/capture/test_expense_parser.py`
  - 信心度計算、auto-approve 護欄
  - Source enum 與 *_certain derived properties
  - 預期: 覆蓋 expense_parser.py 所有分支

- [ ] **整合測試 - 端到端** - `tests/capture/test_staging_workflow.py`
  - capture → parse → approve → apply 完整流程
  - 狀態機轉移驗證
  - 預期: 真實 staging.jsonl 檔案互動

**Week 4 - P2（增強功能）**:
- [ ] **lc staging repair** - `commands/staging_cmd.py`
  - 偵測 3 種不一致（approved_without_proposal, proposal_without_approved, applied_without_canonical）
  - Deterministic repair 策略
  - 預期行為: 自動修復或提示用戶手動處理

- [ ] **lc staging compact** - `commands/staging_cmd.py`（可選，預留契約）
  - Dry-run 模式
  - 只保留最新狀態（壓縮 JSONL）
  - 預期: 減少 staging/entries.jsonl 檔案大小

- [ ] **CLI 測試** - `tests/commands/test_capture_cmd.py`, `test_staging_cmd.py`
  - 38 個 staging 子指令測試
  - capture 批次匯入測試
  - 預期: 覆蓋所有 CLI 互動路徑

- [ ] **文件更新** - `README.md`, `CLAUDE.md`
  - README 新增 Phase 4 使用範例
  - CLAUDE.md 更新 capture/ 模組說明
  - 預期: 用戶可依文件獨立使用 Phase 4 功能

- [ ] **驗收測試** - 端到端驗收
  - 功能驗收：capture → parse → apply
  - 隔離驗收：capture/ 不依賴 models/
  - 測試驗收：所有測試通過
  - 契約驗收：Schema baseline 一致

### 需要補測的案例

**單元測試（高優先級）**:
- [ ] `entity_extractor.py` - 26 個 V2/V3 邊緣情境
  - 金額: 分隔符 `1,200`, 全形 `１２３`, 負數 `-120`, 約略 `約 120`, 範圍 `100-120`
  - 日期: 相對 `上週五`, 只有月份 `8月`, 不完整 `8/1`, 節慶 `中秋`（不支援）
  - 異常: 空字串, 超長文本 >500, 非支出 `收入 1200`, emoji `☕️ 120`

- [ ] `expense_parser.py` - 信心度計算與護欄
  - ConfidenceConfig 可配置性
  - 三欄位確定性檢查（amount_certain AND date_certain AND category_certain）
  - Source enum 正確性

- [ ] `capture_cmd.py`, `staging_cmd.py` - CLI 互動
  - 批次匯入檔案驗證
  - Rich 輸出格式驗證
  - 錯誤處理與提示

**契約測試（CI 護欄）**:
- [ ] `test_capture_isolation.py` - 隔離規則
- [ ] `test_staging_state_machine.py` - 狀態機轉移
- [ ] Schema baseline 驗證（已建立 baseline，需加入 CI）

**整合測試（端到端）**:
- [ ] capture → parse → approve → apply 完整流程
- [ ] 並發寫入測試（多進程 _seq 衝突，P2）
- [ ] Parse 中斷恢復測試（部分成功場景）
- [ ] Repair 邏輯測試（3 種不一致情境，P2）

### 可能的 Regression 點

**1. Interface 隔離破壞** (高風險):
- **風險**: capture/ 直接 import models/，破壞隔離規則
- **檢測**: 契約測試 `test_capture_isolation.py`（待實作）
- **預防**: Code review + CI 自動檢查

**2. Proposal 工作流程變更** (中風險):
- **風險**: approve() 建立 proposal 邏輯與現有 proposals_handler 衝突
- **檢測**: 整合測試 + `lc apply` 驗證
- **預防**: 透過 proposals_handler 統一入口（待整合）

**3. JSONL 並發衝突** (低風險):
- **風險**: 多進程寫入導致 _seq 重複或逆序
- **檢測**: threading.Lock 已實作，跨進程需 fcntl.flock（P2）
- **預防**: 目前單進程使用，併發測試待補（P2）

**4. 狀態機不一致** (中風險):
- **風險**: 終態追蹤遺失（proposal_id/canonical_record_id 未寫入）
- **檢測**: `lc staging repair` 自動偵測（待實作）
- **預防**: 原子操作 + 狀態機驗證測試（待補）

**5. 判重誤判** (低風險):
- **風險**: 保守策略過於嚴格（false negative）
- **檢測**: 整合測試 + 用戶回饋
- **預防**: V4.1.1 保守策略已實作（需 date + amount + normalized_text）

**6. Auto-approve 誤判** (中風險):
- **風險**: 信心度高但實際錯誤的 entry 自動進入 approved
- **檢測**: 用戶手動檢查 proposals/（Proposal 整合後）
- **預防**: V4.1 三欄位確定性護欄已實作

---

## E. 下一步（必留）

### 立即下一步（Week 3 - P1）

按優先級排序：

1. **Proposal 整合** (P1 - 阻塞 apply 流程)
   - 位置: `life_capital/capture/staging_service.py:approve_entry()`
   - 任務: 整合 `proposals_handler.create_expense_proposals()`
   - 交付: approve() 成功後寫入 `proposal_id`，可執行 `lc apply`

2. **契約測試 - 隔離規則** (P1 - CI 護欄)
   - 位置: `tests/contracts/test_capture_isolation.py`
   - 任務: 驗證 capture/ 不 import models/，只依賴 interfaces/
   - 交付: CI 自動檢查，違反時 build 失敗

3. **契約測試 - 狀態機** (P1 - 一致性保證)
   - 位置: `tests/contracts/test_staging_state_machine.py`
   - 任務: 驗證 8 狀態轉移規則
   - 交付: 所有非法轉移拋出 InvalidStateTransition

4. **單元測試 - 實體抽取** (P1 - 邊緣情境覆蓋)
   - 位置: `tests/capture/test_entity_extractor.py`
   - 任務: 26 個 V3 邊緣情境
   - 交付: entity_extractor.py 完整測試覆蓋

5. **單元測試 - 解析器** (P1 - 核心邏輯驗證)
   - 位置: `tests/capture/test_expense_parser.py`
   - 任務: 信心度計算、auto-approve 護欄、Source enum
   - 交付: expense_parser.py 完整測試覆蓋

6. **整合測試 - 端到端** (P1 - 流程驗證)
   - 位置: `tests/capture/test_staging_workflow.py`
   - 任務: capture → parse → approve → apply 完整流程
   - 交付: 真實 staging.jsonl 檔案互動測試

### Week 4 任務（P2 - 增強與驗收）

7. **lc staging repair** (P2 - 不一致修復)
8. **lc staging compact** (P2 - 可選，預留契約)
9. **CLI 測試** (P2 - 指令覆蓋)
10. **文件更新** (P2 - 用戶指南)
11. **驗收測試** (P2 - 完整驗收)

### Phase 5 前置準備（凍結中）

**Phase 5: AI 顧問整合** 需等 Phase 4 完成後解凍。

**預計 Phase 5 任務**:
- AI 輸出至 proposals/（雙選項 + 風險說明）
- Wiki 為決策脈絡庫（Assumption/Decision/Scenario Pages）
- `lc advisor context --redacted` - 輸出已去識別上下文
- `lc advisor suggest "買房"` - 生成建議

**Phase 4 → Phase 5 銜接點**:
- staging/ 已穩定，可作為 AI 輸入來源（✅ Week 1-2 完成）
- proposals/ 工作流程需完成整合（⏳ Week 3 P1）
- Interface 隔離經驗可應用於 advisor/ 模組

---

## 保留合約列表（不可變更）

以下合約為**不可變更的系統約束**，任何違反需經過 Schema 遷移流程：

### 1. 隔離合約（✅ 已實作 + 驗證）
- ✅ `capture/` 只能依賴 `interfaces/`，不可直接依賴 `models/`
- ✅ StagingEntry 定義於 `capture/models.py`（dataclass，非 Pydantic）
- ⏳ CI 自動檢查隔離規則（待實作 contract-check）

### 2. 狀態機合約（✅ 已實作）
- ✅ 8 個狀態（pending/parsed/error/approved/rejected/ignored/duplicate/applied）
- ✅ applied 為終態（已進入 canonical，不可回退）
- ⏳ approved 狀態保證 proposal_id 存在（待整合 Proposal）
- ⏳ applied 狀態保證 proposal_id + canonical_record_id 存在（待整合）

### 3. JSONL 合約（✅ 已實作）
- ✅ Append-only log（不修改既有行）
- ✅ Last-write-wins 讀取語意
- ✅ _seq 遞增序號（O(1) 生成演算法）
- ✅ 並發護欄：threading.Lock（已實作）+ fcntl.flock（P2 增強）

### 4. 解析合約（✅ 已實作）
- ✅ ParseResult 包含 Source enums（AmountSource/DateSource/CategorySource）
- ✅ *_certain derived properties（amount_certain, date_certain, category_certain）
- ✅ Auto-approve 護欄：三欄位皆確定才 auto-approve
- ✅ 信心度公式：R×0.35 + F×0.30 + A×0.20 + Cr×0.15

### 5. 判重合約（✅ 已實作）
- ✅ 保守策略：需 date + amount + normalized_text
- ✅ duplicate_key = f"{date}|{amount}|{normalized_text}"
- ✅ 資訊不足 → None（無法判重）
- ✅ DuplicateReason enum（DUP_KEY_EXACT/DUP_DATE_FUZZ/DUP_AMOUNT_MISSING）

### 6. 原子性合約（✅ 已實作）
- ✅ 原子單位：entry-by-entry（非 batch transaction）
- ✅ 部分成功：允許（parse_all_pending 返回清單）
- ⏳ Repair 契約：偵測 3 種不一致 + deterministic 修復（待實作）

### 7. Proposal 生命週期合約（⏳ 部分實作）
```
lc capture     → proposal_id=None, canonical_record_id=None, status=pending  ✅
lc staging parse → proposal_id=None, canonical_record_id=None, status=parsed  ✅
approve()      → proposal_id=寫入,  canonical_record_id=None, status=approved  ⏳ 待整合
lc apply       → proposal_id=不變,  canonical_record_id=寫入, status=applied  ⏳ 待整合
```

---

## 實作狀態摘要

| 分類 | 完成度 | 說明 |
|------|--------|------|
| **核心模組** | 100% (6/6) | capture/ 所有 .py 檔案已實作 |
| **CLI 指令** | 100% (2/2) | capture_cmd.py, staging_cmd.py 已實作 |
| **單元測試** | 40% (2/5) | date_adapter (37), staging_service (48)，其他待補 |
| **契約測試** | 0% (0/2) | 隔離規則、狀態機測試待實作 |
| **整合測試** | 0% (0/1) | 端到端測試待實作 |
| **Proposal 整合** | 0% | approve() 建立 proposal 待整合 |

**總測試數**: 85 (37 + 48)
**總任務進度**: 50% (10/20 tasks)

**Week 1-2 P0 已完成** ✅
**Week 3-4 待開始** ⏳

---

## 需要決策/確認

以下項目需要用戶決策或確認：

### 1. Proposal 整合優先級
**問題**: approve() 整合 proposals_handler 是否應該優先於其他測試？
**影響**: 阻塞 `lc apply` 流程，用戶無法完整使用 Phase 4
**建議**: **優先完成**（Week 3 第一項任務）

### 2. 契約測試 vs 單元測試優先級
**問題**: 先補契約測試（隔離規則、狀態機）還是先補單元測試（entity_extractor, expense_parser）？
**影響**: 契約測試是 CI 護欄，單元測試是功能驗證
**建議**: **契約測試優先**（防止隔離破壞）

### 3. lc staging repair 實作時機
**問題**: Week 4 實作 repair 還是等到發現實際不一致時再實作？
**影響**: Repair 需要有真實不一致案例才能驗證
**建議**: **Week 4 實作基本框架**，真實場景再補強

### 4. fcntl.flock 跨進程鎖時機
**問題**: 是否需要在 Phase 4 實作跨進程併發鎖？
**影響**: 目前單進程使用，threading.Lock 已足夠
**建議**: **延後至 P2 或 Phase 5**（當前無跨進程需求）

---

**完整計劃**: `plan.md` (V4.1.1, 40K tokens, 3 輪審查 + P0 收斂 + 契約釐清)
**使用指南**: `docs/commands/capture-staging.md`
