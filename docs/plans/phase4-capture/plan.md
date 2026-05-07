# Phase 4 CAPTURE 自動化實作計劃

> **目標**: 實作自然語言支出記錄功能，從零散輸入自動轉換為結構化資料
> **策略**: Interface 隔離 + 漸進式解析 + Proposal 工作流程
> **狀態**: V4.1.1 契約釐清完成 ✅ 可長期演進 🎯

---

## LLM 閱讀順序建議（不分拆文件）

1. **目標功能 + 架構總覽**（了解核心流程）
2. **V4.1.1 Contract Clarifications**（最終契約定義）
3. **Staging 資料結構 + 生命週期**（資料主軸）
4. **解析核心（抽取器/解析器/auto-approve）**（關鍵技術路徑）
5. **狀態機 + 判重 + 原子性/修復**（一致性與護欄）
6. **CLI + 測試 + 驗收**（落地與驗證）
7. **實作順序 + 風險**（規劃與風險控管）
8. **版本歷程**（背景與決策來源）

---

## 目標功能

```bash
# 捕捉零散輸入
lc capture "昨天吃了 320 元拉麵"
lc capture "12/25 聖誕禮物 1500"
lc capture "捷運加值 500 交通"

# 列出待處理項目
lc staging list

# 解析並轉換為 proposals（V4.1: 唯一解析路徑）
lc staging parse --confirm

# 最後進入正式流程
lc apply --confirm
```

---

## 架構總覽

```
用戶輸入 (自然語言)
    ↓ capture/
staging/ (待解析)
    ↓ parse/
proposals/pending/ (待確認)
    ↓ apply (現有流程)
canonical/expenses/
```

### 模組分層（V2 修正：命名衝突解決）

| 層級 | 模組 | 職責 | 依賴規則 |
|------|------|------|----------|
| CLI | `commands/capture_cmd.py` | 參數解析、使用者互動 | 可依賴 capture/ |
| CLI | `commands/staging_cmd.py` | staging 管理 | 可依賴 capture/ |
| 邏輯 | `capture/expense_parser.py` | 自然語言→結構化 | 只依賴 interfaces/ |
| 邏輯 | `capture/entity_extractor.py` | 實體抽取（日期、金額、類別）| 只依賴 interfaces/ |
| 邏輯 | `capture/staging_service.py` | staging 業務邏輯 | 依賴 interfaces/ + StagingStore Protocol |
| IO | `io/staging_store.py` | staging JSONL 讀寫 | 現有 io 層 |
| Adapter | `capture/date_adapter.py` | 日期解析封裝 | 封裝 dateparser，提供穩定 API |

> **V2 修正**:
> - `staging_handler` → `staging_service` (邏輯層) + `staging_store` (IO 層)
> - 新增 `date_adapter.py` 封裝第三方日期解析庫，維持分層清晰

---

## §12 V4.1.1 Contract Clarifications（最後一哩收斂）

> **目的**: 將規格與程式落點再收斂一階，避免測試、資料一致性、apply 串接出現灰區
> **狀態**: 6 個契約釐清完成 ✅

### 已完成的契約釐清 (6/6)

| # | 釐清項目 | 問題 | 解法 | 狀態 |
|---|----------|------|------|------|
| 1 | 狀態機圖表一致 | 圖表停在 canonical，未列 applied | 狀態圖 + 表格更新 | ✅ |
| 2 | proposal_id 生命週期 | 何時寫入不明確 | 明確定義：approve() 寫入 | ✅ |
| 3 | _seq 持久化規則 | 跨進程撞號風險 | 讀取最後一行 + 併發鎖 | ✅ |
| 4 | Duplicate 規則升級 | 舊版容易誤判 | 保守判重 + DuplicateReason enum | ✅ |
| 5 | ParseResult certain 對齊 | 手寫判斷地獄 | Source enum + derived properties | ✅ |
| 6 | Parse 原子性定義 | 中斷時不一致 | Entry 原子單位 + repair 契約 | ✅ |

### 關鍵改善總結

**1. 狀態機完整性**:
- ✅ 狀態轉移圖：`apply` → `applied`（終態）
- ✅ 狀態定義表：新增 `applied` 列（允許 show，不建議 delete）
- ✅ 文件與實作對齊，避免測試用例失真

**2. Proposal 生命週期契約**:
```
lc capture     → proposal_id=None, canonical_record_id=None, status=pending
lc staging parse → proposal_id=None, canonical_record_id=None, status=parsed
approve()      → proposal_id=寫入,  canonical_record_id=None, status=approved
lc apply       → proposal_id=不變,  canonical_record_id=寫入, status=applied
```
- ✅ `status=approved` **保證** `proposal_id` 存在
- ✅ `status=applied` **保證** 兩個 id 皆存在
- ✅ 回溯鏈路完整：staging → proposal → canonical

**3. JSONL 並發安全**:
```python
# _seq 生成：O(1) 讀取最後一行 + 1
# 並發護欄：threading.Lock（最小）→ fcntl.flock（建議）
# 異常恢復：_seq 逆序/重複 → lc staging repair 重建
```

**4. 判重精準化**:
```python
# 優先策略：duplicate_key = f"{date}|{amount}|{normalized_text}"
# 退回策略：amount 缺失 → possible_duplicate + DuplicateReason enum
# 用戶體驗：精準判重自動 duplicate，模糊判重留 warning
```

**5. Certain 判定清晰化**:
```python
# 來源枚舉：AmountSource / DateSource / CategorySource
# Derived properties：amount_certain = (amount_source == EXACT)
# Auto-approve 護欄：三個 *_certain 全為 True 才 approve
```

**6. Parse 原子性保證**:
```python
# 原子單位：entry-by-entry（非 batch transaction）
# 部分成功：允許，輸出成功/失敗清單 + exit code
# Repair 契約：偵測 3 種不一致 + deterministic 修復策略
```

### 長期演進保證

這 6 個契約釐清確保：

| 面向 | V4.1 | V4.1.1 | Phase 5/6 相容性 |
|------|------|--------|------------------|
| 狀態機 | 有終態 | 圖表完整對齊 | ✅ 可擴展新狀態 |
| 追溯性 | proposal_id | 生命週期明確 | ✅ 串接穩定 |
| 並發 | append-only | _seq + lock | ✅ 可升級分散式鎖 |
| 判重 | 基本規則 | 保守 + enum | ✅ 可加 ML 判重 |
| 確定性 | bool 欄位 | Source enum | ✅ 可擴展來源類型 |
| 原子性 | 未定義 | Entry 原子 + repair | ✅ 可加 SAGA 模式 |

**結論**: V4.1.1 從「可直接開工」提升至「做完不會成為負債核心」✅

---

## §1 V1 規劃

### Step 1: Staging 資料結構（1 小時）

**目的**: 定義待解析資料的儲存格式

**V4.1 修正：解決隔離矛盾**

> **問題**: 若 StagingEntry 在 `models/`，capture/ 無法 import（違反隔離規則）
> **解法**: 移至 `life_capital/capture/models.py`（capture 內部模型）

**輸出檔案**: `life_capital/capture/models.py`

```python
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from enum import Enum

class StagingStatus(str, Enum):
    """Staging 狀態枚舉（V4.1 新增）"""
    PENDING = "pending"
    PARSED = "parsed"
    ERROR = "error"
    APPROVED = "approved"
    REJECTED = "rejected"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"
    APPLIED = "applied"  # V4.1 新增：已進入 canonical

@dataclass
class StagingEntry:
    """待解析的消費記錄（capture 內部模型）"""
    entry_id: str                    # UUID
    raw_text: str                    # 原始輸入文字
    created_at: datetime             # 輸入時間

    # V2 新增：版本追蹤
    parser_version: str = "1.0"      # 解析器版本
    batch_id: Optional[str] = None   # 批次 ID（支援批次匯入）
    source: str = "cli"              # 來源：cli / file / api

    # 解析結果（可選）
    parsed_date: Optional[date] = None
    parsed_amount: Optional[Decimal] = None
    parsed_category: Optional[str] = None
    parsed_merchant: Optional[str] = None
    parsed_note: Optional[str] = None

    # 狀態
    confidence: float = 0.0          # 解析信心度 0-1
    status: StagingStatus = StagingStatus.PENDING  # V4.1: 使用 Enum
    error_message: Optional[str] = None

    # V2 新增：決策記錄
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None  # actor
    rejection_reason: Optional[str] = None

    # V3 新增：稽核與可追溯欄位
    confidence_breakdown: Optional[dict] = None  # {"amount": 0.4, "date": 0.3, ...}
    raw_locale: str = "zh-TW"        # 日期解析依據
    duplicate_of: Optional[str] = None  # 若為 duplicate，指向原始 entry_id
    duplicate_reason: Optional[str] = None  # V4.1: 為何判重

    # V4.1 新增：終態追蹤
    proposal_id: Optional[str] = None  # V4.1.1: 在建立 proposal 時寫入（approved 狀態）
    canonical_record_id: Optional[str] = None  # V4.1.1: 在 apply 成功後寫入（applied 狀態）
```

**V4.1.1 Proposal 生命週期釐清**:

| 時機 | 動作 | proposal_id | canonical_record_id | status |
|------|------|-------------|---------------------|--------|
| lc capture | 輸入捕捉 | None | None | pending |
| lc staging parse | 解析 | None | None | parsed |
| approve() | 批准 + 建立 proposal | **寫入** | None | approved |
| lc apply | 寫入 canonical | 不變 | **寫入** | applied |

**關鍵契約**:
- `status=approved` **保證** `proposal_id` 已存在（在 approve() 中建立）
- `status=applied` **保證** `proposal_id` 與 `canonical_record_id` 皆存在
- 回溯鏈路：`staging entry` → `proposal` → `canonical record`（完整可追溯）

**儲存位置**: `~/.life-capital/staging/entries.jsonl`

**V4.1 修正：JSONL 寫入與讀取規格**

**寫入策略**:
- Append-only log：每次更新追加新行（不修改既有行）
- 每行格式：`{"entry_id": "...", "status": "...", "_seq": 123, ...}`
- `_seq`：遞增序號（防止同 timestamp 衝突）

**V4.1.1 _seq 持久化生成規則**:

**生成規則**（防止跨進程撞號）:
```python
def _get_next_seq(jsonl_path: Path) -> int:
    """O(1) 讀取最後一行的 _seq + 1"""
    if not jsonl_path.exists():
        return 1

    # 讀取最後一行（可用 tail -n 1 或 seek from end）
    last_line = read_last_line(jsonl_path)
    if not last_line:
        return 1

    last_entry = json.loads(last_line)
    return last_entry.get("_seq", 0) + 1
```

**並發護欄**:
- **最小要求**: 同進程內部鎖（threading.Lock）
- **建議**: OS-level file lock（fcntl.flock on Unix, msvcrt.locking on Windows）
- **未來擴展**: 若需支援多進程 batch，需要實作 advisory lock

**異常恢復**:
- 若偵測到 `_seq` 逆序或重複 → `lc staging repair` 重建序號
- Repair 策略：使用檔案 offset 作為 tie-break（deterministic）

**讀取策略（last-write-wins）**:
```python
def read_current_state() -> dict[str, StagingEntry]:
    """讀取當前狀態"""
    entries: dict[str, StagingEntry] = {}
    for line in entries_jsonl:
        entry = parse_line(line)
        entries[entry.entry_id] = entry  # 後寫入覆蓋
    return entries
```

**Compact 機制**（Phase 4 可不實作，但預留契約）:
```bash
lc staging compact --dry-run  # 預覽會刪除的舊版本
lc staging compact             # 執行 compact（只保留最新狀態）
```

---

### Step 2: 實體抽取器（2 小時）

**目的**: 從自然語言抽取結構化欄位

**輸出檔案**:
- `life_capital/capture/entity_extractor.py`
- `life_capital/capture/date_adapter.py` (V2 新增)

**抽取規則**:

| 實體 | 模式範例 | 優先順序 |
|------|----------|----------|
| 金額 | `320元`, `$1500`, `NT$200`, `1000` | 數字 + 可選貨幣符號 |
| 日期 | `昨天`, `12/25`, `2024-12-25`, `上週五` | 相對日期 > 絕對日期 |
| 類別 | `交通`, `食物`, `娛樂` | 完全匹配 expense_policy |
| 商家 | `拉麵店`, `捷運` | 上下文推斷（類別優先於商家）|

**依賴**: 透過 `CanonicalReader.get_categories()` 取得有效類別清單

**V2 新增：日期解析分層策略**

```python
# date_adapter.py
class DateAdapter:
    """封裝日期解析，維持分層清晰"""

    LOCALE = "zh-TW"  # 固定 locale

    def parse(self, text: str, reference_date: date) -> Optional[date]:
        # 第一層：內建規則（穩定）
        if result := self._builtin_parse(text, reference_date):
            return result
        # 第二層：dateparser（fallback）
        return self._dateparser_fallback(text, reference_date)

    def _builtin_parse(self, text: str, ref: date) -> Optional[date]:
        """處理常見格式：今天、昨天、MM/DD、YYYY-MM-DD"""
        ...
```

**V2/V3 邊緣情境處理（完整版）**

| 類別 | 情境 | 處理策略 | 狀態 | V3 |
|------|------|----------|------|-----|
| **金額** | 無金額 | 標記為 error | `error` | V2 |
| | 多筆金額 (「午餐 120，咖啡 80」) | 不拆分，pending | `pending` | V2 |
| | 外幣 (`USD`, `¥`) | 不支援 | `error` | V2 |
| | 含分隔符 (`1,200`) | 正規化後解析 | - | V3 |
| | 全形數字 (`１２３`) | 正規化後解析 | - | V3 |
| | 中文數字 (`一百二十`) | 不支援 | `error` | V3 |
| | 約略/範圍 (`約 120`, `100-120`) | 取單一值或 error | `pending` | V3 |
| | 負數/退款 (`-120`, `退款 120`) | 識別為退款，金額負值 | `parsed` | V3 |
| **日期** | 相對日期 (上週五) | dateparser + 低信心 | `parsed` | V2 |
| | 只有月份 (`8月`) | 預設該月 1 日 + 低信心 | `parsed` | V3 |
| | 節慶 (`中秋`) | 不支援 | `error` | V3 |
| | 週期性 (`每週五`) | 不支援 | `error` | V3 |
| | 不完整 (`8/1`) | 推斷當前/去年 | `parsed` | V3 |
| **類別** | 類別/商家衝突 | 類別優先 | - | V2 |
| | 商家當類別 (`星巴克 120`) | 模糊匹配類別 | `pending` | V3 |
| **輸入** | 空字串 | 拒絕 | (直接 reject) | V3 |
| | 超長文本 (>500 chars) | 截斷 + 警告 | `pending` | V3 |
| | 非支出 (`收入 1200`) | 識別並標記 | `ignored` | V3 |
| | emoji (`☕️ 120`) | 忽略 emoji，解析數字 | - | V3 |
| | 中英混雜 (`lunch 120`) | 嘗試解析 | - | V3 |

---

### Step 3: 解析器核心（2 小時）

**目的**: 組合抽取結果，計算信心度

**輸出檔案**: `life_capital/capture/expense_parser.py`

```python
from life_capital.interfaces import CanonicalReader
from dataclasses import dataclass
from decimal import Decimal
from datetime import date
from typing import Optional

@dataclass
class ConfidenceConfig:
    """V2 新增：可配置信心度權重"""
    amount_weight: float = 0.4
    date_weight: float = 0.3
    category_weight: float = 0.2
    merchant_weight: float = 0.1
    auto_approve_threshold: float = 0.7

    @classmethod
    def default(cls) -> "ConfidenceConfig":
        return cls()

class AmountSource(str, Enum):
    """V4.1.1: 金額來源枚舉"""
    EXACT = "exact"         # 明確數字（320, 1200）
    RANGE = "range"         # 範圍取值（100-120 → 110）
    INFERRED = "inferred"   # 推斷（"約 120" → 120）
    MISSING = "missing"     # 無法抽取

class DateSource(str, Enum):
    """V4.1.1: 日期來源枚舉"""
    BUILTIN_EXACT = "builtin_exact"         # 內建規則精確（2024-12-25, 12/25）
    BUILTIN_INFERRED = "builtin_inferred"   # 內建規則推斷（今天、昨天）
    DATEPARSER = "dateparser"               # dateparser fallback
    RELATIVE = "relative"                   # 相對日期（上週五）
    MISSING = "missing"                     # 無法抽取

class CategorySource(str, Enum):
    """V4.1.1: 類別來源枚舉"""
    EXACT = "exact"   # 完全匹配 expense_policy
    FUZZY = "fuzzy"   # 模糊匹配
    MISSING = "missing"

@dataclass
class ParseResult:
    """解析結果（V4.1.1 使用 source enum）"""
    # 抽取結果
    amount: Optional[Decimal]
    date: Optional[date]
    category: Optional[str]
    merchant: Optional[str]
    note: Optional[str]

    # 信心度
    confidence: float
    confidence_breakdown: dict[str, float]

    # V4.1.1: 來源枚舉（取代 bool certain 欄位）
    amount_source: AmountSource = AmountSource.MISSING
    date_source: DateSource = DateSource.MISSING
    category_source: CategorySource = CategorySource.MISSING

    # V4.1.1: 確定性 derived properties
    @property
    def amount_certain(self) -> bool:
        return self.amount_source == AmountSource.EXACT

    @property
    def date_certain(self) -> bool:
        return self.date_source == DateSource.BUILTIN_EXACT

    @property
    def category_certain(self) -> bool:
        return self.category_source == CategorySource.EXACT

class ExpenseParser:
    def __init__(
        self,
        reader: CanonicalReader,
        config: ConfidenceConfig | None = None
    ):
        self._reader = reader
        self._categories = reader.get_categories()
        self._config = config or ConfidenceConfig.default()

    def parse(self, text: str) -> ParseResult:
        """解析自然語言支出描述"""
        # 1. 抽取實體
        # 2. 驗證類別是否存在
        # 3. 計算信心度（使用 config）
        # 4. 檢查 auto-approve 護欄（V4.1）
        # 5. 回傳結果

    def _should_auto_approve(self, result: ParseResult) -> bool:
        """V4.1: 僅當三欄位皆確定才 auto-approve

        護欄條件：
        1. 總信心度 ≥ threshold
        2. 金額確定（非 None，非推斷）
        3. 日期確定（非 None，非 fallback，非相對日期推斷）
        4. 類別確定（非 None，非模糊匹配）
        """
        if result.confidence < self._config.auto_approve_threshold:
            return False

        # 三欄位皆確定才可 auto-approve
        if not (result.amount_certain and
                result.date_certain and
                result.category_certain):
            return False

        return True
```

**信心度計算（V2：可配置）**:
- 金額已抽取: +0.4 (預設，可調整)
- 日期已抽取: +0.3 (預設，可調整)
- 類別匹配: +0.2 (預設，可調整)
- 商家識別: +0.1 (預設，可調整)
- 總分 ≥0.7 → 高信心（但需額外護欄，見下方）

**V4.1 Auto-approve 護欄**:
- **護欄邏輯**: 僅當「三欄位皆確定」才進 `approved`，否則留在 `parsed`
- **確定性定義**:
  - `amount_certain`: 金額非推斷、非約略範圍
  - `date_certain`: 日期非 fallback、非相對日期
  - `category_certain`: 類別非模糊匹配、完全匹配 expense_policy
- **預設行為**: 不滿足護欄條件 → `parsed` 狀態（需人工確認）

**V2 新增：信心度降級規則**
| 情境 | 信心度調整 |
|------|------------|
| 使用 dateparser fallback | -0.1 |
| 日期為相對日期（非明確日期） | -0.05 |
| 類別為模糊匹配 | -0.1 |

---

### Step 4: Staging 管理（1.5 小時）

**目的**: 管理待解析資料的 CRUD

**輸出檔案**: `life_capital/capture/staging_service.py` (V2 更名)

**API**:
```python
class StagingService:
    def __init__(self, store: StagingStore):
        self._store = store

    def add_entry(self, text: str, reader: CanonicalReader) -> StagingEntry
    def list_entries(self, status: Optional[str] = None) -> list[StagingEntry]
    def update_entry(self, entry_id: str, updates: dict) -> StagingEntry
    def delete_entry(self, entry_id: str) -> None
    def clear_all(self) -> int
    def approve_entry(self, entry_id: str, actor: str) -> StagingEntry  # V2 新增
    def reject_entry(self, entry_id: str, actor: str, reason: str) -> StagingEntry  # V2 新增
```

**儲存格式**: JSONL（每行一筆，便於追加）

---

### V2 新增：狀態機設計

**Staging Entry 狀態轉移圖（V4.1.1 修正）**

```
         ┌───────────────────────────────────────┐
         │                                       │
         v                                       │
    ┌─────────┐     parse()     ┌─────────┐    │
    │ pending │ ───────────────>│ parsed  │    │
    └─────────┘                 └─────────┘    │
         │                           │          │
         │ error                     │ approve()│
         v                           v          │
    ┌─────────┐              ┌───────────┐     │
    │  error  │              │ approved  │     │
    └─────────┘              └───────────┘     │
         │                           │          │
         │ fix + re-parse            │ apply   │
         │                           v          │
         │                   ┌───────────┐     │
         └──────────────────>│  applied  │     │
                             └───────────┘     │
                                   │           │
                                   │ reject()  │
                                   v           │
                             ┌───────────┐     │
                             │ rejected  │ ────┘
                             └───────────┘
                                   │
                                   │ re-edit
                                   v
                              (回到 pending)
```

**V4.1.1 修正**: `canonical` 改為 `applied`（終態），因為 canonical 不是 staging 狀態

**狀態定義（V4.1.1 更新）**

| 狀態 | 說明 | 允許操作 | 版本 |
|------|------|----------|------|
| `pending` | 待解析 | parse, delete | V2 |
| `parsed` | 已解析，待確認 | approve, reject, edit, delete | V2 |
| `error` | 解析失敗 | edit, delete | V2 |
| `approved` | 已確認，proposal 已建立，待 apply | apply, reject | V2 |
| `rejected` | 已拒絕 | edit (回到 pending), delete | V2 |
| `ignored` | 非支出/重複 | delete, restore (回到 pending) | V3 |
| `duplicate` | 重複輸入 | delete, force-approve | V3 |
| `applied` | **終態**：已成功進入 canonical | show, (不建議 delete，避免稽核斷鏈) | **V4.1** |

**防護規則**
- ❌ `approved` 狀態不可直接編輯（需先 reject）
- ❌ 已進入 `canonical` 的資料不可從 staging 修改
- ✅ `rejected` 可重新編輯並觸發重新解析
- ✅ `ignored` 可還原為 `pending` 重新處理
- ⚠️ `duplicate` 需要 force-approve 才能強制進入 proposals

---

### V4.1.1 重複偵測規則（保守判重）

**優先策略**（抽取後比對，降低誤判）:
```python
def compute_duplicate_key(entry: StagingEntry) -> Optional[str]:
    """計算去重 key（需抽取成功）"""
    if not (entry.parsed_date and entry.parsed_amount):
        return None  # 資訊不足，無法可靠判重

    # 正規化文字：移除金額、日期、空白
    normalized_text = normalize_text_without_date_amount(entry.raw_text)

    return f"{entry.parsed_date}|{entry.parsed_amount}|{normalized_text}"
```

**判重邏輯**:
1. **優先**: 使用 `duplicate_key` 完全匹配（需 date + amount + normalized_text）
2. **退回**: 若 amount 缺失 → 標記 `possible_duplicate`（confidence 降級 -0.2）+ `duplicate_reason="AMOUNT_MISSING_FUZZY_MATCH"`
3. **日期容錯**: ±1 天僅在明確為「同一消費的補登」時使用（如重複匯入檢測）

**duplicate_reason 枚舉**（V4.1.1 新增）:
```python
class DuplicateReason(str, Enum):
    DUP_KEY_EXACT = "exact_key_match"           # 完全匹配（日期+金額+文字）
    DUP_DATE_FUZZ = "date_fuzzy_match"          # 日期 ±1 天模糊匹配
    DUP_AMOUNT_MISSING = "amount_missing_fuzzy" # 金額缺失，使用較鬆策略
```

**用戶體驗改善**:
- 精準判重 → 自動標記 `duplicate`（可 force-approve）
- 模糊判重 → 標記 `possible_duplicate` + warning（讓用戶決定）

---

### Step 5: CLI 指令（2 小時）

**輸出檔案**: `life_capital/commands/capture_cmd.py`, `life_capital/commands/staging_cmd.py`

**capture 指令**:
```bash
lc capture "昨天吃了 320 元拉麵"
# 輸出: ✅ 已加入 staging (ID: abc123)
#       📅 日期: 2024-12-27 (信心: 0.9)
#       💰 金額: 320 (信心: 1.0)
#       📂 類別: food (信心: 0.8)
#       📝 總信心度: 0.9

lc capture --batch file.txt
# 從檔案批次讀取
```

**staging 指令**:
```bash
lc staging list [--status pending|parsed|error]
lc staging show <entry_id>
lc staging edit <entry_id> --category food --amount 350
lc staging delete <entry_id>
lc staging clear
lc staging parse [--confirm]  # 解析 pending entries（V4.1: 唯一解析路徑）
lc staging approve <entry_id>  # 手動批准
lc staging reject <entry_id> --reason "..."  # 拒絕並說明
```

**V4.1 CLI 收斂**:
- **唯一解析路徑**: `lc staging parse` 為唯一解析入口
- **移除混淆**: 不再有獨立的 `lc parse` 指令
- **清晰職責**:
  - `lc capture "..."` → 捕捉輸入至 staging
  - `lc staging parse --confirm` → 解析並轉為 proposals
  - `lc apply --confirm` → proposals 進入 canonical

---

### Step 6: 整合測試（1.5 小時）

**測試檔案**: `tests/capture/`

| 測試類型 | 檔案 | 涵蓋範圍 |
|----------|------|----------|
| 單元測試 | `test_entity_extractor.py` | 各類型實體抽取 |
| 單元測試 | `test_expense_parser.py` | 解析邏輯、信心度計算 |
| 整合測試 | `test_staging_workflow.py` | 端到端流程 |
| 契約測試 | `test_interface_isolation.py` | 隔離規則驗證 |

---

## §2 實作順序（V2 更新）

| 優先級 | Step | 內容 | 時間 | 依賴 | V2 變更 |
|--------|------|------|------|------|---------|
| **P0** | 1 | Staging 資料結構 | 1h | 無 | +版本追蹤欄位 |
| **P0** | 2 | 實體抽取器 + DateAdapter | 2.5h | Step 1 | +日期分層策略 |
| **P1** | 3 | 解析器核心 + ConfidenceConfig | 2h | Step 2 | +可配置信心度 |
| **P1** | 4 | Staging Service + 狀態機 | 2h | Step 1 | +approve/reject |
| **P2** | 5 | CLI 指令 | 2h | Step 3, 4 | - |
| **P2** | 6 | 整合測試 | 1.5h | Step 5 | +邊緣情境測試 |
| **P2** | 7 | IO Layer: StagingStore | 1h | - | V2 新增 |

**總時間**: 約 12 小時（V2 增加 2 小時：狀態機 + IO 分離）

---

## §3 隔離規則驗證

### CI 檢查

```bash
# capture/ 不可直接依賴 models/
grep -r "from life_capital.models" life_capital/capture/
# 預期結果: 空

# capture/ 只能依賴 interfaces/
grep -r "from life_capital.interfaces" life_capital/capture/
# 預期結果: 有結果
```

### 測試驗證

```python
def test_capture_isolation():
    """驗證 capture 模組不直接依賴 models"""
    import ast
    from pathlib import Path

    capture_dir = Path("life_capital/capture")
    for py_file in capture_dir.glob("*.py"):
        content = py_file.read_text()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if hasattr(node, 'module') and node.module:
                    assert not node.module.startswith("life_capital.models"), \
                        f"{py_file}: 禁止直接 import models/"
```

---

## §4 風險評估（V2 更新）

| 風險 | 機率 | 影響 | 緩解措施 | V2 狀態 |
|------|------|------|----------|---------|
| 自然語言解析準確度不足 | 中 | UX 差 | 信心度機制 + 人工確認 | ✅ 已設計 |
| 類別匹配困難 | 低 | 手動修正 | CanonicalReader 類別清單 | ✅ 已設計 |
| Interface 不足 | 中 | 需擴展 | Compatible Change 規則 | ⏳ 待確認 |
| 日期解析複雜 | 高 | 相對日期錯誤 | 分層策略 + locale 固定 | ✅ 已設計 |
| 模組命名衝突 | 中 | 依賴混亂 | staging_service + staging_store | ✅ 已解決 |
| 狀態轉移不清 | 高 | 資料不可追溯 | 狀態機設計 | ✅ 已設計 |

---

## §5 待審查問題（V2 解答）

| 問題 | V1 狀態 | V2 決策 |
|------|---------|---------|
| 日期解析策略 | ❓ | ✅ 分層策略：內建規則優先，dateparser 為 fallback |
| 信心度閾值 0.7 | ❓ | ✅ 可作為預設值，但透過 ConfidenceConfig 可調整 |
| 批次解析 | ❓ | ⏳ Phase 4 不實作，但 StagingEntry 已預留 batch_id 欄位 |
| Interface 擴展 | ❓ | ✅ 暫不擴展，維持 5 個方法，避免過早耦合 |

**V2 新增待審查**:
1. **外幣處理**: 完全不支援是否合適？（建議維持不支援，Phase 5 再考慮）
2. **多筆交易拆分**: 目前不拆分，未來是否需要 LLM 輔助？

---

## §6 預期成果

### MVP 功能

1. ✅ `lc capture "..."` - 捕捉自然語言輸入
2. ✅ `lc staging list` - 列出待處理項目
3. ✅ `lc staging parse --confirm` - 解析並轉為 proposals
4. ✅ 隔離規則：capture/ 只依賴 interfaces/
5. ✅ 信心度機制：低信心需人工確認

### 驗收標準

```bash
# 功能驗收
lc capture "昨天吃了 320 元拉麵"
lc staging list
lc staging parse --confirm
lc apply --confirm

# 隔離驗收
grep -r "from life_capital.models" life_capital/capture/  # 空

# 測試驗收
uv run pytest tests/capture/ -v
```

---

## §9 V4 專業審查：護欄與容錯設計

### 護欄機制（Guardrails）

#### 寫入邊界強化

| 層級 | 寫入限制 | 護欄 |
|------|----------|------|
| `staging/` | capture/ 可寫 | 透過 StagingStore Protocol |
| `proposals/` | staging_service 可寫 | 透過 CanonicalReader.save_proposal() |
| `canonical/` | 只有 `lc apply` | 現有護欄維持 |

**新增護欄**:
```python
# io/staging_store.py
class StagingStore(Protocol):
    """IO 層 Protocol - 只有 capture/ 可依賴"""

    def write_entry(self, entry: StagingEntry) -> None:
        """寫入時自動記錄 created_at + entry_id"""

    def read_entries(self, status: Optional[str] = None) -> list[StagingEntry]:
        """讀取時驗證 schema_version"""
```

#### 隔離規則強化

```bash
# CI 檢查（已在 contract-check.yml 中）
capture/ ─X→ models/      # 禁止
capture/ ─X→ io/          # 禁止（除了 StagingStore Protocol）
capture/ ───→ interfaces/ # 允許
```

**新增契約測試**:
```python
# tests/contracts/test_capture_isolation.py
def test_capture_module_isolation():
    """驗證 capture/ 不直接依賴 models/ 或 io/"""
    ...
```

### 錯誤恢復機制

#### 失敗場景處理（V4.1.1 補充原子性契約）

| 場景 | 症狀 | 恢復方式 |
|------|------|----------|
| parse 中斷 | 部分 entry 狀態不一致 | `lc staging repair` |
| JSONL 損壞 | 讀取失敗 | 備份 + 逐行恢復 |
| 狀態機違規 | 非法轉移 | 拒絕操作 + 警告 |
| 重複 apply | 同一 entry 多次進入 canonical | `duplicate_of` 檢測 |

**V4.1.1 Parse 原子性契約**:

**原子單位**: 以 **entry** 為原子單位（非 batch transaction）

**成功路徑**（entry-by-entry）:
```python
def parse_entry(entry_id: str) -> ParseResult:
    """原子操作：解析單筆 entry"""
    # 1. 讀取 entry（pending 狀態）
    entry = store.read_entry(entry_id)

    # 2. 抽取實體 + 計算信心度
    result = parser.parse(entry.raw_text)

    # 3a. 若信心度足夠且三欄位確定 → 建立 proposal + 更新為 approved
    if should_auto_approve(result):
        proposal = create_proposal(result)
        entry.proposal_id = proposal.id
        entry.status = "approved"

    # 3b. 否則 → 更新為 parsed（等待人工確認）
    else:
        entry.status = "parsed"

    # 4. 寫回 entry（原子操作）
    entry.parsed_date = result.date
    entry.parsed_amount = result.amount
    # ... 其他欄位
    store.write_entry(entry)

    return result
```

**部分成功策略**（批次 parse）:
```bash
$ lc staging parse --confirm

解析中...
✅ entry_1: approved (proposal abc123 已建立)
✅ entry_2: parsed (信心度不足，需人工確認)
❌ entry_3: error (無法抽取金額)

成功: 2/3 | 失敗: 1/3
```

**不一致檢測與修復**:
```python
# lc staging repair 偵測以下不一致：
inconsistency_rules = {
    "approved_without_proposal": "status=approved 但 proposal_id=None",
    "proposal_without_approved": "proposal_id 存在但 status≠approved/applied",
    "applied_without_canonical": "status=applied 但 canonical_record_id=None",
}

# Repair 策略：
# 1. approved_without_proposal → 降級為 parsed（proposal 已遺失，需重建）
# 2. proposal_without_approved → 檢查 proposal 是否存在，決定升級或刪除 proposal_id
# 3. applied_without_canonical → 檢查 canonical 是否存在，決定降級或補寫 id
```

**Exit Code 契約**:
- `0`: 全部成功
- `1`: 部分失敗（但有成功項）
- `2`: 全部失敗

#### 回滾設計

```python
# capture/staging_service.py
class StagingService:
    def approve_entry(self, entry_id: str, actor: str) -> StagingEntry:
        """V4: 加入事務保護"""
        entry = self._store.read_entry(entry_id)

        # 狀態機驗證
        if entry.status not in ["parsed"]:
            raise InvalidStateTransition(
                f"Cannot approve entry in '{entry.status}' state"
            )

        # 更新狀態（原子操作）
        entry.status = "approved"
        entry.reviewed_at = datetime.now()
        entry.reviewed_by = actor

        self._store.write_entry(entry)
        return entry
```

### 契約測試整合

#### 新增測試項目

| 測試 | 檔案 | 涵蓋 |
|------|------|------|
| Schema 穩定性 | `test_schema_stability.py` | StagingEntry baseline |
| 隔離驗證 | `test_capture_isolation.py` | import 規則 |
| 狀態機 | `test_staging_state_machine.py` | 狀態轉移規則 |
| 邊緣情境 | `test_entity_extractor_edge_cases.py` | 所有 V3 情境 |

#### Baseline 更新

```bash
# 新增 StagingEntry baseline
python scripts/update_schema_baseline.py --model StagingEntry
```

### 與現有架構整合

#### 遵循 CLAUDE.md 護欄

1. ✅ **寫入邊界**: staging/ 由 StagingStore 管理，不直接操作檔案
2. ✅ **Decimal 強制**: 金額解析後立即 `to_decimal()`
3. ✅ **Schema 版本**: StagingEntry 包含 `parser_version`
4. ✅ **驗證優先**: 所有狀態轉移前驗證

#### 遵循 DEVELOPMENT.md 流程

1. ✅ **契約測試**: 新增 tests/contracts/test_capture_*.py
2. ✅ **隔離層**: interfaces/staging_store.py Protocol
3. ✅ **CI 護欄**: 加入 contract-check.yml

### 實作順序（V4 最終版）

| 優先級 | Step | 內容 | 時間 | 依賴 |
|--------|------|------|------|------|
| **P0** | 1 | StagingEntry model + baseline | 1h | 無 |
| **P0** | 2 | StagingStore Protocol + impl | 1h | Step 1 |
| **P0** | 3 | 實體抽取器 + DateAdapter | 2.5h | Step 1 |
| **P1** | 4 | 解析器核心 + ConfidenceConfig | 2h | Step 3 |
| **P1** | 5 | Staging Service + 狀態機 | 2h | Step 2, 4 |
| **P2** | 6 | CLI 指令 | 2h | Step 5 |
| **P2** | 7 | 契約測試 + 邊緣情境測試 | 2h | Step 6 |

**總時間**: 約 12.5 小時

### 關鍵檔案清單

**新增檔案（V4.1 修正）**:
```
life_capital/
├── capture/
│   ├── __init__.py               # 已存在
│   ├── models.py                 # StagingEntry + StagingStatus（V4.1: 內部模型）
│   ├── entity_extractor.py       # 實體抽取
│   ├── date_adapter.py           # 日期解析封裝
│   ├── expense_parser.py         # 解析器核心 + ParseResult
│   └── staging_service.py        # 業務邏輯
├── interfaces/staging_store.py    # StagingStore Protocol
├── io/staging_store.py            # StagingStore 實作
└── commands/
    ├── capture_cmd.py             # lc capture
    └── staging_cmd.py             # lc staging

tests/
├── contracts/
│   ├── test_capture_isolation.py  # 隔離驗證
│   ├── test_staging_state_machine.py # 狀態機
│   └── baselines/StagingEntry.json # 新增 baseline（V4.1: 移除 models/ 依賴）
└── capture/
    ├── test_entity_extractor.py
    ├── test_expense_parser.py
    └── test_staging_workflow.py
```

**V4.1 關鍵變更**:
- ❌ 移除 `life_capital/models/staging.py`（違反隔離規則）
- ✅ 改為 `life_capital/capture/models.py`（capture 內部模型）

---

## §10 驗收標準（V4 最終版）

### 功能驗收

```bash
# 基本流程
lc capture "昨天吃了 320 元拉麵"
lc staging list
lc staging parse --confirm
lc apply --confirm

# 邊緣情境
lc capture "1,200 元"          # 分隔符正規化
lc capture "退款 200"          # 負數識別
lc capture ""                  # 空字串拒絕
lc capture "收入 1000"         # ignored 狀態
```

### 隔離驗收（V4.1 更新）

```bash
# capture/ 不依賴 models/（V4.1: 完全隔離）
grep -r "from life_capital.models" life_capital/capture/
# 預期結果: 空（無例外）

# capture/ 只依賴 interfaces/
grep -r "from life_capital.interfaces" life_capital/capture/
# 預期結果: 有結果（CanonicalReader, StagingStore）
```

### 測試驗收

```bash
uv run pytest tests/capture/ -v
uv run pytest tests/contracts/test_capture_*.py -v
lc doctor --path ./data
```

### 契約驗收

```bash
python scripts/check_schema_diff.py
# 預期: StagingEntry baseline 存在且一致
```

---

## §11 V4.1 結構性收斂總結

### 已完成的 P0 修正 (5/5)

| # | 修正項目 | 問題 | 解法 | 狀態 |
|---|----------|------|------|------|
| 1 | 隔離矛盾解決 | StagingEntry 在 models/ 違反 capture/ 隔離 | 移至 `capture/models.py` | ✅ |
| 2 | 終態追蹤 | 缺少 applied 狀態 + proposal_id | 新增 APPLIED + proposal_id/canonical_record_id | ✅ |
| 3 | JSONL 規格 | last-write-wins 不明確 | 明確讀取邏輯 + compact 契約 | ✅ |
| 4 | CLI 收斂 | lc parse vs lc staging parse 混淆 | 只保留 lc staging parse | ✅ |
| 5 | Auto-approve 護欄 | 自動批准條件不嚴謹 | 三欄位確定性檢查 + ParseResult.*_certain | ✅ |

### 核心改善

**架構層面**:
- ✅ 完全隔離：capture/ 不再依賴 models/
- ✅ 終態追蹤：staging → proposals → canonical 全程可追溯
- ✅ 單一路徑：lc capture → lc staging parse → lc apply

**資料層面**:
- ✅ JSONL 語意：last-write-wins 明確定義
- ✅ Compact 契約：預留重整機制，避免無限增長

**品質層面**:
- ✅ 自動批准護欄：三欄位確定性檢查，降低誤判
- ✅ 確定性標記：amount_certain / date_certain / category_certain

### 可直接開工確認

| 檢查項 | 狀態 | 備註 |
|--------|------|------|
| 隔離規則清晰 | ✅ | capture/models.py 完全內部 |
| 狀態機完整 | ✅ | 8 個狀態 + APPLIED 終態 |
| CLI 無混淆 | ✅ | 單一解析路徑 |
| 資料可追溯 | ✅ | proposal_id 串接 |
| 自動批准安全 | ✅ | 三欄位護欄 |

**結論**: V4.1 已達「可直接開工」狀態，所有 P0 結構性問題已解決。

---

## §0 背景與現狀

### 已就緒的基礎設施

| 項目 | 狀態 | 說明 |
|------|------|------|
| Interface 隔離層 | ✅ | `life_capital/interfaces/canonical_reader.py` |
| CanonicalReader Protocol | ✅ | 5 個方法（get_categories, get_expense_policy, get_monthly_income, save_proposal, get_version）|
| 實作類別 | ✅ | `CanonicalReaderImpl` in `canonical_reader_impl.py` |
| capture/ 模組骨架 | ✅ | `life_capital/capture/__init__.py` |
| proposals 處理 | ✅ | `io/proposals_handler.py`（create_expense_proposals, list_pending_proposals）|
| 契約測試 | ✅ | 318 tests，Schema/Golden/CI 護欄就緒 |

---

## §7 V2 改善摘要（Codex 審查 #1）

### 結構性修正
1. ✅ **命名衝突解決**: `staging_handler` → `staging_service` + `staging_store`
2. ✅ **狀態機設計**: 定義 5 個狀態 + 轉移規則
3. ✅ **日期解析分層**: DateAdapter 封裝，內建規則優先
4. ✅ **信心度可配置**: ConfidenceConfig dataclass

### 邊緣情境規範
- 無金額 → error
- 多筆金額 → 不拆分，pending
- 外幣 → 不支援，error
- 相對日期 → dateparser + 降級信心度

### 可持續性改進
- parser_version 追蹤
- batch_id 預留
- 決策記錄（reviewed_at, reviewed_by, rejection_reason）

---

## §8 V3 改善摘要（Codex 審查 #2）

### 新增邊緣情境處理

**金額格式**:
- ✅ 含分隔符 (`1,200`) → 正規化
- ✅ 全形數字 (`１２３`) → 正規化
- ❌ 中文數字 (`一百二十`) → 不支援
- ⚠️ 約略/範圍 → 取單值或 pending
- ✅ 負數/退款 → 識別為退款

**日期格式**:
- ✅ 只有月份 → 預設 1 日
- ❌ 節慶 → 不支援
- ❌ 週期性 → 不支援
- ✅ 不完整日期 → 推斷年份

**異常輸入**:
- ✅ 空字串 → 直接拒絕
- ✅ 超長文本 → 截斷 + 警告
- ✅ 非支出 → `ignored` 狀態
- ✅ emoji → 忽略後解析

### 狀態機補充
- 新增 `ignored` 狀態（非支出/明確忽略）
- 新增 `duplicate` 狀態（重複偵測）
- 新增 `force-approve` 操作

### 欄位優化
- `confidence_breakdown` → 四項分數明細
- `raw_locale` → 日期解析依據
- `duplicate_of` → 重複關聯

---

## 版本歷程

| 版本 | 改善重點 | 來源 |
|------|----------|------|
| V1 | 初版架構 | 原始規劃 |
| V2 | 命名衝突修正 + 狀態機設計 + 邊緣情境規範 | Codex 審查 #1 |
| V3 | 完整邊緣情境 + 狀態機補充 + 欄位優化 | Codex 審查 #2 |
| V4 | 護欄機制 + 錯誤恢復 + 契約測試整合 | 專業審查 ✅ |
| V4.1 | **P0 修正**: 隔離矛盾解決 + 終態追蹤 + JSONL 規格 + CLI 收斂 + auto-approve 護欄 | 結構性收斂 |
| V4.1.1 | **契約釐清**: 狀態機對齊 + proposal 生命週期 + _seq 並發 + 判重升級 + Source enum + Parse 原子性 | 最後一哩收斂 ✅ |

---

*V4.1.1 最終版 - 3 輪審查 + P0 收斂 + 契約釐清完成*

---

## 驗收報告

> **狀態**: ✅ 通過
> **日期**: 2025-12-29
> **Commit**: 367335c

### 驗收標準

| # | 標準 | 結果 | 驗證 |
|---|------|------|------|
| 1 | 所有測試通過 | ✅ 608 passed | `uv run pytest tests/ -x` |
| 2 | lc doctor 無 hard fail | ✅ 通過 | `lc doctor --path ./data` |
| 3 | 21/21 tasks 完成 | ✅ | Manual checklist |
| 4 | 契約測試通過 | ✅ 119 passed | `uv run pytest tests/contracts/` |
| 5 | 隔離規則符合 | ✅ 14 passed | `test_capture_isolation.py` |
| 6 | CLI 整合通過 | ✅ 30 passed | `test_capture_cmd.py + test_staging_cmd.py` |
| 7 | 邊緣情境通過 | ✅ 32 passed | 並發/repair/invalid 測試 |

### 依賴項目

| 依賴 | 來源 | 狀態 |
|------|------|------|
| 三層結構 | Phase 0 | ✅ |
| Schema 穩定性 | Phase 1 | ✅ |
| Scenario 計算 | Phase 2 | ✅ |
| Report 生成 | Phase 3 | ✅ |

### Evidence

```
Quick Gate:
- pytest: 608 passed, 1 skipped, 0 failed (7.85s)
- lc doctor: ✓ 所有檢查通過

Full Gate:
- contracts/: 119 passed (0.24s)
- capture_isolation: 14 passed (0.06s)
- CLI tests: 30 passed (0.59s)
- Edge cases: 32 passed (0.08s)
```

### 後續 Backlog

- staging 定期備份（可選）
- 批次 parse 進度條（可選）
- 錯誤分類統計（Backlog）
