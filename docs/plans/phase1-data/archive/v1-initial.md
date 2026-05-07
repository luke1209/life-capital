# Phase 1: DATA 強化規劃 (V1)

> **狀態**: 初版規劃
> **版本**: V1
> **目標**: stable_id + dedupe_key + migration 機制

---

## 1. 目標與範圍

### 1.1 Phase 1 目標

實作 V2.5 路線圖中的 DATA 強化層，包括：

1. **stable_id**: 每筆交易的永久 UUID（一旦創建永不改）
2. **dedupe_key**: 版本化去重 hash（允許策略更新）
3. **migration_log**: Schema 版本變更歷程追蹤
4. **lc dedupe --resolve**: 人工裁決去重衝突的命令

### 1.2 驗收標準

```bash
# 標準 1: 去重可判定
lc dedupe --resolve              # ±1 天窗口內可判定

# 標準 2: 可重建
lc rebuild                       # raw 可重建 canonical/derived

# 標準 3: Schema 一致
lc doctor                        # schema_version 一致，無 hard fail
```

### 1.3 範圍邊界

**包含**:
- canonical 交易模型擴展
- 去重策略與人工裁決
- Schema 版本遷移機制

**不包含**（Phase 2+）:
- Scenario 計算
- Generation 報表
- CAPTURE 自動化

---

## 2. 現有架構分析

### 2.1 現有模型

```python
# models/expense.py - 現有欄位
class ExpenseRecord(BaseModel):
    date: date
    amount: Decimal
    category: str
    payer: Payer = "shared"  # V1.1 新增
    note: Optional[str] = None
    merchant: Optional[str] = None
```

### 2.2 現有去重

```python
# io/csv_handler.py - 現有去重
def compute_row_hash(row):  # exact: 完整 SHA-256
def compute_row_key(row):   # key: date+amount+category+payer+merchant
```

### 2.3 缺失能力

| 能力 | 現狀 | Phase 1 目標 |
|------|------|--------------|
| stable_id | ❌ 無 | UUID 永久識別 |
| dedupe_key | ❌ 無版本 | 含策略版本的 hash |
| 去重窗口 | ❌ 精確匹配 | ±1 天窗口判定 |
| 衝突裁決 | ❌ 自動跳過 | 人工裁決機制 |
| 版本遷移 | ❌ 無 | migration_log |

---

## 3. 技術設計

### 3.1 新增欄位設計

```python
# models/transaction.py（新建）
class Transaction(BaseModel):
    """Canonical 交易模型（Phase 1）"""

    # === 核心欄位（從 ExpenseRecord 繼承）===
    date: date
    amount: Decimal
    category: str
    payer: Payer = "shared"
    note: Optional[str] = None
    merchant: Optional[str] = None

    # === Phase 1 新增欄位 ===
    stable_id: UUID = Field(default_factory=uuid4)  # 永久識別碼
    dedupe_key: str  # 版本化去重 hash
    dedupe_version: str = "1.0"  # 去重策略版本

    # === 來源追溯 ===
    source_row_ref: Optional[SourceRowRef] = None  # 指回 raw
    occurred_at: Optional[date] = None  # 消費日（優先）
    posted_at: Optional[date] = None    # 入帳日

    # === 關聯欄位（預留）===
    is_transfer: bool = False           # 轉帳標記
    reversal_of: Optional[UUID] = None  # 退款/沖正關聯
```

### 3.2 去重策略設計

```python
# io/dedupe.py（新建）
class DedupeStrategy:
    """去重策略基類"""
    version: str = "1.0"
    window_days: int = 1  # ±1 天窗口

    def compute_key(self, record: Transaction) -> str:
        """計算去重 key"""

    def find_candidates(self, record: Transaction, existing: list) -> list:
        """在窗口內找出候選重複項"""

    def resolve(self, record: Transaction, candidates: list) -> DedupeResult:
        """判定結果: auto_merge | manual_review | keep_both"""

class DedupeResult(Enum):
    AUTO_MERGE = "auto_merge"        # 自動合併（高相似度）
    MANUAL_REVIEW = "manual_review"  # 需人工裁決
    KEEP_BOTH = "keep_both"          # 保留兩筆
```

### 3.3 遷移機制設計

```python
# io/migration.py（新建）
class MigrationLog(BaseModel):
    """遷移日誌"""
    migration_id: UUID
    from_version: str
    to_version: str
    executed_at: datetime
    affected_files: list[Path]
    rollback_available: bool

def migrate_schema(data_root: Path, target_version: str) -> MigrationLog:
    """執行 Schema 遷移"""

def rollback_migration(data_root: Path, migration_id: UUID) -> bool:
    """回滾遷移"""
```

---

## 4. 新增檔案結構

```
life_capital/
├── models/
│   └── transaction.py        # [新建] Canonical 交易模型
├── io/
│   ├── dedupe.py             # [新建] 去重策略
│   └── migration.py          # [新建] 版本遷移
├── commands/
│   └── dedupe_cmd.py         # [新建] lc dedupe 命令
└── io/registry.py            # [擴展] 新增常數

~/.life-capital/
├── canonical/
│   ├── .migrations/          # [新建] 遷移日誌目錄
│   │   └── migration_log.jsonl
│   └── expenses/             # [現有] 按月份切檔
└── proposals/
    └── dedupe_conflicts/     # [新建] 待裁決項目
```

---

## 5. 命令設計

### 5.1 lc dedupe

```bash
# 掃描並顯示去重衝突
lc dedupe --path ~/.life-capital

# 互動式裁決
lc dedupe --resolve --path ~/.life-capital

# 自動處理（高相似度自動合併）
lc dedupe --auto --path ~/.life-capital

# 強制保留所有（標記但不合併）
lc dedupe --keep-all --path ~/.life-capital
```

**輸出格式**:
```
掃描完成: 發現 3 組潛在重複

組 1: 相似度 95% → 建議合併
  [A] 2024-12-05 | ¥1,200 | transportation | person_a
  [B] 2024-12-06 | ¥1,200 | transportation | person_a

組 2: 相似度 70% → 需人工裁決
  [A] 2024-12-10 | ¥2,800 | food | person_b
  [B] 2024-12-10 | ¥2,850 | food | person_b

選擇操作: [M]erge / [K]eep both / [S]kip
```

### 5.2 lc migrate（新增）

```bash
# 檢查遷移狀態
lc migrate --status --path ~/.life-capital

# 執行遷移
lc migrate --to 1.2 --path ~/.life-capital

# 回滾遷移
lc migrate --rollback <migration_id> --path ~/.life-capital
```

---

## 6. 實施計劃

### Phase 1.1: 模型擴展（Day 1-2）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 建立 transaction.py | 2h | 單元測試通過 |
| 擴展 registry.py 常數 | 30min | 無 hardcode |
| 更新 ExpenseRecord 向後相容 | 1h | 現有測試通過 |

### Phase 1.2: 去重實作（Day 3-4）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 建立 dedupe.py 策略 | 3h | ±1 天窗口判定 |
| 實作相似度計算 | 2h | 閾值可配置 |
| 建立 dedupe_cmd.py | 2h | 互動式裁決 |

### Phase 1.3: 遷移機制（Day 5-6）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 建立 migration.py | 3h | 遷移日誌記錄 |
| 實作版本檢查邏輯 | 2h | doctor 可驗證 |
| 實作回滾機制 | 2h | 可回滾最近遷移 |

### Phase 1.4: 整合測試（Day 7）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 整合測試 | 2h | 全部通過 |
| 更新 lc doctor | 1h | 新檢查項目 |
| 更新文件 | 1h | README/CLAUDE.md |

---

## 7. 風險評估

| 風險 | 機率 | 影響 | 緩解措施 |
|------|------|------|----------|
| 現有資料遷移失敗 | 中 | 高 | 先備份、提供回滾 |
| 去重誤判 | 中 | 中 | 高相似度才自動合併 |
| stable_id 衝突 | 低 | 高 | UUID 碰撞機率極低 |
| 效能問題（大量資料）| 低 | 中 | 分批處理、索引優化 |

---

## 8. 開放問題

1. **dedupe_key 版本升級時，是否需要重算所有記錄？**
   - 選項 A: 全量重算
   - 選項 B: 只對新記錄使用新策略

2. **stable_id 何時生成？**
   - 選項 A: import 時生成
   - 選項 B: apply 到 canonical 時生成

3. **去重窗口大小是否可配置？**
   - 選項 A: 固定 ±1 天
   - 選項 B: 可在 config 中配置

---

## 9. 參考資料

- V2.5 路線圖: `docs/roadmap/V2.5.md`
- 現有資料模型: `life_capital/models/expense.py`
- 現有去重邏輯: `life_capital/io/csv_handler.py`
- 護欄規則: `CLAUDE.md`
