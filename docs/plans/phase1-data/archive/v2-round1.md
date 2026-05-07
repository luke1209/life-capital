# Phase 1: DATA 強化規劃 (V2)

> **狀態**: Round 1 修正版
> **版本**: V2
> **變更**: 修正 V1 結構性錯誤，對齊現有架構

---

## Round 1 修正摘要

| 問題 | 嚴重度 | 修正 |
|------|--------|------|
| Transaction 模型已存在 | 高 | 改為「擴展現有模型」而非新建 |
| canonical 格式不一致 | 高 | 統一使用 JSONL 格式 + canonical_handler |
| 去重策略與 pipeline 脫節 | 中 | 定義 CSV→Transaction 轉換流程 |
| SourceRowRef 生成規則未定義 | 中 | 在 import 時固化 per-row hash |
| migration_log 與 registry 脫節 | 中 | 整合現有 MIGRATION_LOG_DIR |

---

## 1. 現有架構盤點

### 1.1 已存在的模型（不需新建）

```python
# models/transaction.py - 已存在！
class SourceRowRef(BaseModel):
    source_id: UUID
    row_index: int
    raw_hash: str

class Transaction(BaseModel):
    # 身份欄位
    stable_id: UUID = Field(default_factory=uuid4)
    dedupe_key: str = Field(default="")

    # 時間欄位
    occurred_at: date  # 必填
    posted_at: Optional[date] = None

    # 金額欄位
    amount: Decimal
    currency: str = "TWD"

    # 分類欄位
    category: str
    payer: Payer = "shared"

    # 描述欄位
    note: Optional[str] = None
    merchant: Optional[str] = None

    # 關聯欄位
    is_transfer: bool = False
    reversal_of: Optional[UUID] = None

    # 追蹤欄位
    source_row_ref: Optional[SourceRowRef] = None
    schema_version: str = CURRENT_SCHEMA_VERSION
    created_at: datetime
    updated_at: datetime

class TransactionCollection(BaseModel):
    transactions: list[Transaction]
    schema_version: str
```

### 1.2 缺失功能

| 功能 | 現狀 | Phase 1 需新增 |
|------|------|----------------|
| dedupe_version | ❌ 無 | 需新增欄位 |
| 窗口去重 | ❌ 精確匹配 | 需新增 dedupe.py |
| 人工裁決 | ❌ 無 | 需新增 dedupe_cmd.py |
| 版本遷移 | ❌ 無 | 需新增 migration.py |
| canonical 格式 | ❌ 未統一 | JSONL + canonical_handler |

---

## 2. 技術設計（V2 修正）

### 2.1 模型擴展（非新建）

```python
# models/transaction.py - 新增欄位
class Transaction(BaseModel):
    # ... 現有欄位保留 ...

    # === Phase 1 新增 ===
    dedupe_version: str = "1.0"  # 去重策略版本
```

### 2.2 Canonical 格式決策

**決策**: canonical/expenses 改用 **JSONL** 格式

| 格式 | 優點 | 缺點 |
|------|------|------|
| CSV | 人類可讀 | 不支援巢狀結構、無法走 canonical_handler |
| JSONL | 支援完整模型、走 canonical_handler | 較不人類可讀 |

**理由**:
1. `Transaction` 包含 `SourceRowRef`（巢狀結構），CSV 無法表達
2. `canonical_handler.py` 只支援 JSON/YAML，走 CSV 會被 `lc doctor` 視為 bypass
3. JSONL 支援追加寫入，適合交易記錄

**檔案結構變更**:
```
canonical/expenses/
├── 2024-12.jsonl    # 改為 JSONL 格式
└── 2025-01.jsonl
```

### 2.3 Import/Apply 流程整合

```
raw/imports/xxx.csv
    ↓ lc import（保留現有 raw 流程）
raw/imports/xxx.csv + _provenance.yaml
    ↓ lc apply（新增 CSV→Transaction 轉換）
proposals/pending/xxx.json
    ↓ canonical_handler.write_canonical()
canonical/expenses/2024-12.jsonl
```

**CSV→Transaction 轉換規則**:
```python
# 在 apply_cmd.py 中新增
def csv_row_to_transaction(
    row: dict,
    source_id: UUID,
    row_index: int,
) -> Transaction:
    """將 CSV 行轉換為 Transaction"""
    return Transaction(
        occurred_at=parse_date(row["date"]),
        amount=parse_amount(row["amount"]),
        category=row["category"],
        payer=normalize_payer(row.get("payer", "")),
        note=row.get("note"),
        merchant=row.get("merchant"),
        source_row_ref=SourceRowRef(
            source_id=source_id,
            row_index=row_index,
            raw_hash=compute_row_hash(row),
        ),
    )
```

### 2.4 去重策略設計

```python
# io/dedupe.py（新建）
from datetime import date, timedelta
from typing import List, Tuple
from life_capital.models.transaction import Transaction

DEDUPE_VERSION = "1.0"
DEFAULT_WINDOW_DAYS = 1
SIMILARITY_THRESHOLD_AUTO = 0.95  # 95% 以上自動合併
SIMILARITY_THRESHOLD_REVIEW = 0.70  # 70% 以上需人工裁決

class DedupeResult:
    AUTO_MERGE = "auto_merge"
    MANUAL_REVIEW = "manual_review"
    KEEP_BOTH = "keep_both"

def find_candidates(
    record: Transaction,
    existing: List[Transaction],
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> List[Transaction]:
    """在 ±window_days 窗口內找出候選重複項"""
    candidates = []
    for t in existing:
        date_diff = abs((record.occurred_at - t.occurred_at).days)
        if date_diff <= window_days:
            candidates.append(t)
    return candidates

def compute_similarity(a: Transaction, b: Transaction) -> float:
    """計算兩筆交易的相似度 (0.0-1.0)"""
    score = 0.0

    # 金額完全相同: +40%
    if a.amount == b.amount:
        score += 0.4

    # 類別相同: +25%
    if a.category.lower() == b.category.lower():
        score += 0.25

    # 支付者相同: +15%
    if a.payer == b.payer:
        score += 0.15

    # 商家相同（若有）: +20%
    if a.merchant and b.merchant:
        if a.merchant.lower() == b.merchant.lower():
            score += 0.2
    elif not a.merchant and not b.merchant:
        score += 0.1  # 都沒有商家，部分分數

    return score

def resolve(
    record: Transaction,
    candidates: List[Transaction],
) -> Tuple[str, List[Transaction]]:
    """判定去重結果"""
    if not candidates:
        return DedupeResult.KEEP_BOTH, []

    high_similarity = []
    medium_similarity = []

    for c in candidates:
        sim = compute_similarity(record, c)
        if sim >= SIMILARITY_THRESHOLD_AUTO:
            high_similarity.append((c, sim))
        elif sim >= SIMILARITY_THRESHOLD_REVIEW:
            medium_similarity.append((c, sim))

    if high_similarity:
        # 高相似度：自動合併
        return DedupeResult.AUTO_MERGE, [c for c, _ in high_similarity]
    elif medium_similarity:
        # 中相似度：需人工裁決
        return DedupeResult.MANUAL_REVIEW, [c for c, _ in medium_similarity]
    else:
        # 低相似度：保留兩筆
        return DedupeResult.KEEP_BOTH, []
```

### 2.5 遷移機制設計

```python
# io/migration.py（新建）
from pathlib import Path
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from life_capital.io.registry import MIGRATION_LOG_DIR, CURRENT_SCHEMA_VERSION
from life_capital.io.canonical_handler import append_operation_log
from life_capital.models.operation import Operation, OperationType

class MigrationLog(BaseModel):
    """遷移日誌"""
    migration_id: UUID = Field(default_factory=uuid4)
    from_version: str
    to_version: str
    executed_at: datetime = Field(default_factory=datetime.now)
    affected_files: list[str] = Field(default_factory=list)
    rollback_available: bool = True

def migrate_schema(
    data_root: Path,
    target_version: str,
    actor: str = "migration",
) -> MigrationLog:
    """執行 Schema 遷移

    透過 canonical_handler 寫入，確保 operation log 記錄。
    """
    # 實作遷移邏輯...
    pass

def get_current_version(data_root: Path) -> str:
    """取得目前 schema 版本"""
    return CURRENT_SCHEMA_VERSION
```

---

## 3. 命令設計（V2 修正）

### 3.1 lc dedupe（獨立命令）

```bash
# 掃描並顯示去重衝突
lc dedupe --path ~/.life-capital

# 互動式裁決
lc dedupe --resolve --path ~/.life-capital

# 自動處理（高相似度自動合併）
lc dedupe --auto --path ~/.life-capital
```

**CLI 註冊**（對齊現有風格）:
```python
# cli.py 新增
from life_capital.commands import dedupe_cmd
app.command("dedupe")(dedupe_cmd.dedupe)
```

### 3.2 lc migrate（獨立命令）

```bash
# 檢查遷移狀態
lc migrate --status --path ~/.life-capital

# 執行遷移（透過 canonical_handler）
lc migrate --to 1.2 --path ~/.life-capital
```

---

## 4. 新增/修改檔案

| 檔案 | 動作 | 說明 |
|------|------|------|
| `models/transaction.py` | 修改 | 新增 `dedupe_version` 欄位 |
| `io/dedupe.py` | 新建 | 窗口去重策略 |
| `io/migration.py` | 新建 | Schema 遷移（整合 MIGRATION_LOG_DIR） |
| `commands/dedupe_cmd.py` | 新建 | lc dedupe 命令 |
| `commands/migrate_cmd.py` | 新建 | lc migrate 命令 |
| `io/registry.py` | 修改 | 新增 DEDUPE_CONFLICTS_DIR 等常數 |
| `commands/apply_cmd.py` | 修改 | 新增 CSV→Transaction 轉換 |

---

## 5. 開放問題（V2 更新）

### 5.1 已決定

| 問題 | 決定 |
|------|------|
| canonical 格式 | JSONL（走 canonical_handler） |
| stable_id 何時生成 | apply 到 canonical 時（不在 import 時） |
| dedupe_version 是否寫入 | 是，納入 Transaction 模型 |

### 5.2 待決定

1. **現有 CSV expenses 如何遷移至 JSONL？**
   - 選項 A: 一次性 migration 命令
   - 選項 B: 漸進式（新資料用 JSONL，舊資料保留 CSV）

2. **去重窗口大小是否可配置？**
   - 建議: 固定 ±1 天（簡化複雜度）

3. **人工裁決的衝突如何儲存？**
   - 建議: 儲存到 `proposals/dedupe_conflicts/`

---

## 6. 實施計劃（V2 修正）

### Phase 1.1: 模型擴展（Day 1）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 更新 transaction.py 新增 dedupe_version | 30min | 單元測試通過 |
| 更新 registry.py 新增常數 | 30min | 無 hardcode |

### Phase 1.2: 去重實作（Day 2-3）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 建立 dedupe.py | 2h | ±1 天窗口判定 |
| 建立 dedupe_cmd.py | 2h | 互動式裁決 |
| 整合至 CLI | 30min | lc dedupe 可執行 |

### Phase 1.3: Canonical 格式遷移（Day 4）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 更新 apply_cmd.py 支援 CSV→Transaction | 2h | JSONL 輸出 |
| 建立 expenses 格式遷移腳本 | 2h | 現有資料可轉換 |

### Phase 1.4: 遷移機制（Day 5-6）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 建立 migration.py | 2h | 遷移日誌記錄 |
| 建立 migrate_cmd.py | 2h | lc migrate 可執行 |
| 更新 lc doctor | 1h | 新檢查項目 |

### Phase 1.5: 整合測試（Day 7）

| 任務 | 預估 | 驗收 |
|------|------|------|
| 整合測試 | 2h | 全部通過 |
| 更新文件 | 1h | README/CLAUDE.md |

---

## 7. 驗收標準（V2 修正）

```bash
# 標準 1: 去重可判定
lc dedupe --path ~/.life-capital
# 顯示潛在重複項，±1 天窗口

# 標準 2: 可重建
lc rebuild --path ~/.life-capital
# raw → canonical → derived 完整重建

# 標準 3: Schema 一致
lc doctor --path ~/.life-capital
# schema_version 一致，無 bypass 偵測

# 標準 4: JSONL 格式
ls ~/.life-capital/canonical/expenses/
# 輸出 2024-12.jsonl 而非 .csv
```

---

## 8. 參考資料

- V2.5 路線圖: `docs/roadmap/V2.5.md`
- 現有 Transaction 模型: `life_capital/models/transaction.py`
- Canonical Handler: `life_capital/io/canonical_handler.py`
- 護欄規則: `CLAUDE.md`
