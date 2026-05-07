# Capture 模組隔離契約

> 定義 `life_capital/capture/` 模組的隔離規則與依賴約束

## 目的

Capture 模組（Phase 4）提供自然語言支出記錄功能。為確保模組可獨立演進且不與核心架構過度耦合，需嚴格遵守隔離規則。

**隔離的好處**:
- 防止 `capture/` 與整體架構過度耦合
- 允許 `capture/` 獨立演進（只遵守 Protocol 契約）
- 明確定義 `capture/` 與外界的互動邊界
- 簡化測試（可 mock interfaces/ 層）

## 依賴規則

### 允許的依賴

| 模組 | 允許 | 說明 |
|------|------|------|
| `life_capital.interfaces` | ✅ | Protocol 定義（唯一對外介面） |
| `life_capital.calculators` | ✅ | `to_decimal()` 轉換工具 |
| `life_capital.capture.*` | ✅ | 內部跨檔依賴 |
| 標準庫 | ✅ | `dataclasses`, `datetime`, `decimal` 等 |

### 禁止的依賴（核心模組）

| 模組 | 禁止 | 正確做法 |
|------|------|----------|
| `life_capital.models` | ❌ | 使用 `capture/models.py` 內部 dataclass |
| `life_capital.io` | ❌ | 透過 `interfaces/staging_store.py` Protocol |
| `life_capital.commands` | ❌ | 違反分層架構 |
| `life_capital.validators` | ❌ | 在 `capture/` 內部實作驗證邏輯 |

### 例外：staging_service.py

`staging_service.py` 是實作層（不是核心邏輯層），允許額外依賴：

| 依賴 | 用途 |
|------|------|
| `life_capital.io` | 提案處理（proposals_handler） |
| `life_capital.models` | `ExpenseRecord` 轉換（運行時導入） |
| `life_capital.utils` | 路徑解析工具 |

**注意**：這些依賴必須是**運行時導入**（在函式內部），而非模組層級導入。

## 模型定義

### StagingEntry 規範

`StagingEntry` 必須定義於 `capture/models.py`（不是 `models/` 包）：

```python
# capture/models.py（26 欄位 + 5 Enums）
@dataclass
class StagingEntry:
    # 基本欄位
    entry_id: str
    raw_text: str
    created_at: str

    # 解析結果
    parsed_date: str | None
    parsed_amount: Decimal | None
    parsed_category: str | None

    # 狀態與信心度
    status: StagingStatus
    confidence: ConfidenceScore | None

    # 來源追蹤
    parser_version: str
    source: str
    amount_source: AmountSource | None
    date_source: DateSource | None
    category_source: CategorySource | None

    # 判重欄位
    duplicate_of: str | None
    duplicate_reason: str | None

    # 終態追蹤
    proposal_id: str | None
    canonical_record_id: str | None
    # ... 其他欄位
```

### 為何不使用 models/？

1. **隔離性**：`models/` 使用 Pydantic，而 `capture/` 使用 dataclass
2. **演進自由**：`StagingEntry` 可獨立於核心 schema 演進
3. **簡化依賴**：避免 Pydantic 版本升級影響 `capture/`

## 介面依賴

### CanonicalReader Protocol

用於讀取 canonical 層資料（支出政策、類別定義）：

```python
# interfaces/canonical_reader.py
class CanonicalReader(Protocol):
    def get_categories(self) -> list[str]: ...
    def get_expense_policy(self) -> ExpensePolicy: ...
```

**使用者**：`entity_extractor.py`, `expense_parser.py`

### StagingStore Protocol

用於 staging 資料持久化：

```python
# interfaces/staging_store.py
class StagingStore(Protocol):
    def read_entries(self) -> list[StagingEntry]: ...
    def write_entry(self, entry: StagingEntry) -> None: ...
    def update_entry(self, entry: StagingEntry) -> None: ...
```

**使用者**：`staging_service.py`

## CI 驗證

### 隔離檢查腳本

```bash
# 驗證 capture/ 不導入 models/（應為空）
grep -r "from life_capital.models" life_capital/capture/ \
  --include="*.py" | grep -v staging_service

# 驗證正確依賴 interfaces/（應有結果）
grep -r "from life_capital.interfaces" life_capital/capture/
```

### 契約測試

```bash
# 執行隔離契約測試
uv run pytest tests/contracts/test_capture_isolation.py -v
```

**測試類別**：
- `TestCaptureNoModelsImport`：驗證不導入 `models/`
- `TestCaptureOnlyInterfacesDependency`：驗證只依賴允許的模組
- `TestStagingEntryInCaptureModels`：驗證 `StagingEntry` 定義位置
- `TestCaptureInterfacesProtocols`：驗證 Protocol 使用正確
- `TestCaptureModuleStructure`：驗證模組結構符合規範

## 變更審核

| 變更類型 | 審核要求 | Label |
|----------|----------|-------|
| 新增 Protocol 方法 | CODEOWNERS 審核 | `interface-approved` |
| 新增允許依賴 | 雙人審核 | `isolation-approved` |
| 修改 StagingEntry 欄位 | 單人審核 | `capture-approved` |

## 檔案結構

```
life_capital/
├── capture/                    # Phase 4 模組（隔離邊界）
│   ├── __init__.py
│   ├── models.py              # StagingEntry + Enums（內部模型）
│   ├── date_adapter.py        # 日期解析
│   ├── entity_extractor.py    # 實體抽取
│   ├── expense_parser.py      # 解析器
│   └── staging_service.py     # 狀態機服務（實作層）
├── interfaces/                 # Protocol 定義
│   ├── canonical_reader.py    # CanonicalReader Protocol
│   └── staging_store.py       # StagingStore Protocol
└── io/
    └── staging_store.py       # StagingStore 實作（JSONL）

docs/contracts/
├── capture_isolation_contract.md  # 此文件
└── interface_policy.md            # Interface 版本策略

tests/contracts/
└── test_capture_isolation.py      # 隔離規則契約測試
```

## 版本歷程

| 版本 | 日期 | 變更 |
|------|------|------|
| 1.0 | 2025-12-29 | 初版：Phase 4 CAPTURE 隔離規則 |

## 參考資料

- Interface 版本策略：`docs/contracts/interface_policy.md`
- 隔離規則測試：`tests/contracts/test_capture_isolation.py`
- CLAUDE.md：§ 模組架構
