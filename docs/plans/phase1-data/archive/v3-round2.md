# Phase 1: DATA 強化規劃 (V3 Final)

> **狀態**: 審查完成
> **版本**: V3 (Final)
> **審查歷程**: V1 → Round 1 修正 → V2 → Round 2 邊緣情境 → V3 護欄設計

---

## 審查歷程摘要

| 輪次 | 焦點 | 關鍵發現 |
|------|------|----------|
| Round 1 | 結構性修正 | Transaction 模型已存在、canonical 應用 JSONL |
| Round 2 | 邊緣情境 | 退款誤合併、跨月重複、同日同額 |
| Round 3 | 護欄設計 | CLI 確認機制、寫入邊界強制、回滾支援 |

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

### 1.2 Phase 1 需新增功能

| 功能 | 現狀 | Phase 1 需新增 |
|------|------|----------------|
| dedupe_version | ❌ 無 | 需新增欄位 |
| 窗口去重 | ❌ 精確匹配 | 需新增 dedupe.py |
| 人工裁決 | ❌ 無 | 需新增 dedupe_cmd.py |
| 版本遷移 | ❌ 無 | 需新增 migration.py |
| canonical 格式 | ❌ 未統一 | JSONL + canonical_handler |

---

## 2. 技術設計（V3 Final）

### 2.1 模型擴展（非新建）

```python
# models/transaction.py - 新增欄位
class Transaction(BaseModel):
    # ... 現有欄位保留 ...

    # === Phase 1 新增 ===
    dedupe_version: str = "1.0"  # 去重策略版本
```

### 2.2 Canonical 格式決策

**決策**: canonical/expenses 使用 **JSONL** 格式

| 格式 | 優點 | 缺點 |
|------|------|------|
| CSV | 人類可讀 | 不支援巢狀結構、無法走 canonical_handler |
| JSONL | 支援完整模型、走 canonical_handler | 較不人類可讀 |

**理由**:
1. `Transaction` 包含 `SourceRowRef`（巢狀結構），CSV 無法表達
2. `canonical_handler.py` 只支援 JSON/YAML，走 CSV 會被 `lc doctor` 視為 bypass
3. JSONL 支援追加寫入，適合交易記錄

**檔案結構**:
```
canonical/expenses/
├── 2024-12.jsonl
└── 2025-01.jsonl
```

### 2.3 去重策略設計（V3 強化）

```python
# io/dedupe.py（新建）
from datetime import date, timedelta
from typing import List, Tuple
from life_capital.models.transaction import Transaction

DEDUPE_VERSION = "1.0"

# === 窗口配置 ===
WINDOW_OCCURRED_DAYS = 1   # occurred_at ±1 天
WINDOW_POSTED_DAYS = 7     # posted_at ±7 天（跨月緩衝）

# === 相似度閾值 ===
SIMILARITY_THRESHOLD_AUTO = 0.95    # 95% 以上自動合併
SIMILARITY_THRESHOLD_REVIEW = 0.70  # 70% 以上需人工裁決

class DedupeResult:
    AUTO_MERGE = "auto_merge"
    MANUAL_REVIEW = "manual_review"
    KEEP_BOTH = "keep_both"

def find_candidates(
    record: Transaction,
    existing: List[Transaction],
) -> List[Transaction]:
    """在雙窗口內找出候選重複項

    V3 強化：雙窗口策略
    - occurred_at ±1 天（主要）
    - posted_at ±7 天（跨月緩衝）
    """
    candidates = []
    for t in existing:
        # 檢查 occurred_at 窗口
        occurred_match = (
            abs((record.occurred_at - t.occurred_at).days)
            <= WINDOW_OCCURRED_DAYS
        )

        # 檢查 posted_at 窗口（若有）
        posted_match = False
        if record.posted_at and t.posted_at:
            posted_match = (
                abs((record.posted_at - t.posted_at).days)
                <= WINDOW_POSTED_DAYS
            )

        if occurred_match or posted_match:
            candidates.append(t)

    return candidates

def compute_similarity(a: Transaction, b: Transaction) -> float:
    """計算兩筆交易的相似度 (0.0-1.0)

    V3 強化：退款/沖正檢測
    """
    # === V3 新增：退款檢測 ===
    # 一正一負同金額 → 強制 MANUAL_REVIEW
    if (a.amount > 0 and b.amount < 0) or (a.amount < 0 and b.amount > 0):
        if abs(a.amount) == abs(b.amount):
            return 0.75  # 落入 MANUAL_REVIEW 區間

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
        return DedupeResult.AUTO_MERGE, [c for c, _ in high_similarity]
    elif medium_similarity:
        return DedupeResult.MANUAL_REVIEW, [c for c, _ in medium_similarity]
    else:
        return DedupeResult.KEEP_BOTH, []
```

### 2.4 護欄設計（V3 新增）

#### 2.4.1 CLI 操作分級

```python
# commands/dedupe_cmd.py - 護欄實作

# 風險等級定義
OPERATION_RISK = {
    "dedupe --auto": "high",
    "dedupe --resolve": "medium",
    "dedupe": "low",  # 僅掃描
}

def dedupe(
    path: Path = typer.Option(...),
    auto: bool = typer.Option(False, help="自動合併高相似度項目"),
    resolve: bool = typer.Option(False, help="互動式裁決"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳過確認"),
):
    """去重掃描與裁決"""

    # === V3 護欄：高風險操作需確認 ===
    if auto and not yes:
        # 先掃描顯示影響範圍
        conflicts = scan_conflicts(path)
        if conflicts:
            typer.echo(f"發現 {len(conflicts)} 組潛在重複")
            typer.echo("將自動合併相似度 ≥95% 的項目")
            if not typer.confirm("確定執行？"):
                raise typer.Abort()

    # ... 實作邏輯 ...
```

#### 2.4.2 寫入邊界強制

```python
# commands/dedupe_cmd.py - 合併操作

def merge_duplicates(
    winner: Transaction,
    loser: Transaction,
    data_dir: Path,
    actor: str = "cli",
) -> None:
    """合併重複項目

    V3 護欄：必須透過 canonical_handler 寫入
    """
    from life_capital.io.canonical_handler import (
        read_canonical,
        write_canonical,
        append_operation_log,
    )
    from life_capital.models.operation import Operation, OperationType

    # 讀取現有資料
    month_file = get_month_file(winner.occurred_at, data_dir)
    collection = read_canonical(month_file, TransactionCollection)

    # 移除 loser，保留 winner
    collection.transactions = [
        t for t in collection.transactions
        if t.stable_id != loser.stable_id
    ]

    # 透過 canonical_handler 寫入（記錄 operation_id）
    write_canonical(
        data=collection,
        target_path=month_file,
        data_dir=data_dir,
    )

    # 記錄操作（V3 新增：人工裁決也要記錄）
    operation = Operation(
        operation_type=OperationType.DEDUPE_MERGE,
        target_path=str(month_file.relative_to(data_dir)),
        description=f"Merge duplicate: {loser.stable_id[:8]} → {winner.stable_id[:8]}",
        actor=actor,
        metadata={
            "winner_id": str(winner.stable_id),
            "loser_id": str(loser.stable_id),
            "similarity": compute_similarity(winner, loser),
        },
        rollback_data={  # V3 新增：回滾資料
            "loser_transaction": loser.model_dump(mode="json"),
        },
    )
    append_operation_log(operation, data_dir)
```

#### 2.4.3 錯誤分類表

```python
# validators/dedupe_validator.py（新建）

class DedupeError(Exception):
    """去重錯誤基類"""
    pass

class HardFailError(DedupeError):
    """硬失敗：拒絕操作"""
    pass

class SoftWarningError(DedupeError):
    """軟警告：記錄但允許繼續"""
    pass

# 錯誤分類
HARD_FAIL_CONDITIONS = [
    ("schema_version_mismatch", "Schema 版本不一致"),
    ("zero_amount", "金額為 0"),
    ("canonical_bypass", "繞過 canonical_handler 直接寫入"),
    ("missing_stable_id", "缺少 stable_id"),
]

SOFT_WARNING_CONDITIONS = [
    ("unknown_payer", "未知支付者，使用 shared"),
    ("missing_merchant", "缺少商家資訊"),
    ("duplicate_dedupe_key", "dedupe_key 已存在（可能是有意重複）"),
]
```

### 2.5 遷移機制設計（V3 強化）

```python
# io/migration.py（新建）
from pathlib import Path
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from life_capital.io.registry import MIGRATION_LOG_DIR, CURRENT_SCHEMA_VERSION
from life_capital.io.canonical_handler import append_operation_log
from life_capital.models.operation import Operation, OperationType

# V3 新增：回滾過期時間
ROLLBACK_EXPIRES_DAYS = 7

class MigrationLog(BaseModel):
    """遷移日誌"""
    migration_id: UUID = Field(default_factory=uuid4)
    from_version: str
    to_version: str
    executed_at: datetime = Field(default_factory=datetime.now)
    affected_files: list[str] = Field(default_factory=list)
    rollback_available: bool = True
    rollback_expires_at: datetime = Field(
        default_factory=lambda: datetime.now() + timedelta(days=ROLLBACK_EXPIRES_DAYS)
    )
    # V3 新增：備份路徑
    backup_path: Optional[str] = None

def migrate_schema(
    data_root: Path,
    target_version: str,
    actor: str = "migration",
    dry_run: bool = False,
) -> MigrationLog:
    """執行 Schema 遷移

    V3 護欄：
    - dry_run 預設顯示影響範圍
    - 自動備份原始檔案
    - 透過 canonical_handler 寫入
    """
    # 1. 掃描需遷移檔案
    affected = scan_migration_targets(data_root, target_version)

    if dry_run:
        return MigrationLog(
            from_version=get_current_version(data_root),
            to_version=target_version,
            affected_files=[str(f) for f in affected],
            rollback_available=False,  # dry_run 不需回滾
        )

    # 2. V3 護欄：遷移前備份
    backup_dir = create_backup(data_root, affected)

    # 3. 執行遷移（透過 canonical_handler）
    for file_path in affected:
        migrate_file(file_path, target_version, data_root)

    # 4. 記錄遷移日誌
    log = MigrationLog(
        from_version=get_current_version(data_root),
        to_version=target_version,
        affected_files=[str(f) for f in affected],
        backup_path=str(backup_dir),
    )

    # 5. 記錄到 operation_log
    operation = Operation(
        operation_type=OperationType.MIGRATE,
        target_path="canonical/",
        description=f"Schema migration: {log.from_version} → {log.to_version}",
        actor=actor,
        metadata={
            "migration_id": str(log.migration_id),
            "affected_count": len(affected),
        },
        rollback_data={
            "backup_path": str(backup_dir),
            "from_version": log.from_version,
        },
    )
    append_operation_log(operation, data_root)

    return log

def create_backup(data_root: Path, files: list[Path]) -> Path:
    """建立備份

    V3 護欄：遷移前自動備份
    """
    import shutil
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = data_root / ".backups" / f"migration_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    for f in files:
        relative = f.relative_to(data_root)
        dest = backup_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)

    return backup_dir
```

---

## 3. 命令設計（V3 Final）

### 3.1 lc dedupe

```bash
# 掃描並顯示去重衝突（低風險）
lc dedupe --path ~/.life-capital

# 互動式裁決（中風險）
lc dedupe --resolve --path ~/.life-capital

# 自動處理（高風險，需確認）
lc dedupe --auto --path ~/.life-capital
lc dedupe --auto --yes --path ~/.life-capital  # 跳過確認
```

**輸出格式**:
```
掃描完成: 發現 3 組潛在重複

組 1: 相似度 98% → 建議自動合併
  [A] 2024-12-05 | ¥1,200 | transportation | person_a
  [B] 2024-12-06 | ¥1,200 | transportation | person_a

組 2: 相似度 75% → ⚠️ 疑似退款，需人工裁決
  [A] 2024-12-10 | ¥2,800 | food | person_b
  [B] 2024-12-10 | -¥2,800 | food | person_b

選擇操作: [M]erge / [K]eep both / [S]kip / [R]eversal
```

### 3.2 lc migrate

```bash
# 檢查遷移狀態
lc migrate --status --path ~/.life-capital

# Dry-run（顯示影響範圍）
lc migrate --to 1.2 --dry-run --path ~/.life-capital

# 執行遷移（需確認）
lc migrate --to 1.2 --path ~/.life-capital
```

---

## 4. 新增/修改檔案

| 檔案 | 動作 | 說明 |
|------|------|------|
| `models/transaction.py` | 修改 | 新增 `dedupe_version` 欄位 |
| `models/operation.py` | 修改 | 新增 `OperationType.DEDUPE_MERGE`, `MIGRATE` |
| `io/dedupe.py` | 新建 | 窗口去重策略 |
| `io/migration.py` | 新建 | Schema 遷移（整合備份） |
| `commands/dedupe_cmd.py` | 新建 | lc dedupe 命令 |
| `commands/migrate_cmd.py` | 新建 | lc migrate 命令 |
| `validators/dedupe_validator.py` | 新建 | 錯誤分類（hard/soft） |
| `io/registry.py` | 修改 | 新增 DEDUPE_CONFLICTS_DIR 等常數 |
| `commands/apply_cmd.py` | 修改 | 新增 CSV→Transaction 轉換 |
| `commands/doctor.py` | 修改 | 新增去重與遷移檢查項 |

---

## 5. 護欄檢查清單

### 5.1 lc doctor 新增檢查項

```python
# commands/doctor.py - V3 新增檢查項

PHASE1_CHECKS = [
    # 去重相關
    ("dedupe_version_consistent", "所有 Transaction 的 dedupe_version 一致"),
    ("no_duplicate_stable_id", "無重複的 stable_id"),
    ("no_orphan_source_ref", "SourceRowRef 指向的 raw 檔案存在"),

    # 遷移相關
    ("migration_log_valid", "遷移日誌格式正確"),
    ("backup_exists", "最近遷移有備份"),

    # 寫入邊界
    ("canonical_via_handler", "canonical/ 變更都透過 canonical_handler"),
    ("operation_log_complete", "所有變更都有 operation_id"),
]
```

### 5.2 錯誤處理矩陣

| 錯誤 | 分類 | `lc doctor` 輸出 | 處理方式 |
|------|------|------------------|----------|
| Schema 版本不一致 | Hard Fail | ❌ FAIL | 拒絕操作 |
| 繞過 canonical_handler | Hard Fail | ❌ FAIL | 拒絕 + 記錄違規 |
| 重複 stable_id | Hard Fail | ❌ FAIL | 需人工修復 |
| 未知 payer | Soft Warning | ⚠️ WARN | 使用 "shared" |
| 遺失 merchant | Soft Warning | ⚠️ WARN | 允許為空 |
| 疑似退款未標記 | Soft Warning | ⚠️ WARN | 建議檢查 |

---

## 6. 開放問題（V3 決議）

| 問題 | 決定 | 理由 |
|------|------|------|
| canonical 格式 | JSONL | 支援巢狀、走 canonical_handler |
| stable_id 何時生成 | apply 時 | 避免 raw 污染 |
| 去重窗口大小 | 雙窗口（±1/±7） | 解決跨月問題 |
| 退款處理 | 強制 MANUAL_REVIEW | 避免誤合併 |
| CSV 遷移策略 | 一次性遷移 + 備份 | 簡化邏輯 |
| 回滾過期時間 | 7 天 | 平衡儲存與安全 |

---

## 7. 實施計劃（V3 Final）

### Phase 1.1: 模型擴展（Day 1）
- [ ] 更新 transaction.py 新增 dedupe_version
- [ ] 更新 operation.py 新增 OperationType
- [ ] 更新 registry.py 新增常數

### Phase 1.2: 去重實作（Day 2-3）
- [ ] 建立 io/dedupe.py（雙窗口 + 退款檢測）
- [ ] 建立 validators/dedupe_validator.py
- [ ] 建立 commands/dedupe_cmd.py（含護欄）

### Phase 1.3: Canonical 格式遷移（Day 4）
- [ ] 更新 apply_cmd.py 支援 CSV→Transaction
- [ ] 建立 expenses 格式遷移腳本
- [ ] 遷移前備份現有資料

### Phase 1.4: 遷移機制（Day 5-6）
- [ ] 建立 io/migration.py（含備份）
- [ ] 建立 commands/migrate_cmd.py
- [ ] 更新 lc doctor 新增檢查項

### Phase 1.5: 整合測試（Day 7）
- [ ] 整合測試（護欄驗證）
- [ ] 更新文件 README/CLAUDE.md

---

## 8. 驗收標準（V3 Final）

```bash
# 標準 1: 去重可判定
lc dedupe --path ~/.life-capital
# 顯示潛在重複項，雙窗口 + 退款檢測

# 標準 2: 護欄生效
lc dedupe --auto --path ~/.life-capital
# 需確認或 --yes，高風險操作有提示

# 標準 3: 可重建
lc rebuild --path ~/.life-capital
# raw → canonical → derived 完整重建

# 標準 4: Schema 一致
lc doctor --path ~/.life-capital
# schema_version 一致，無 bypass 偵測

# 標準 5: JSONL 格式
ls ~/.life-capital/canonical/expenses/
# 輸出 2024-12.jsonl 而非 .csv

# 標準 6: 回滾可用
lc undo --latest --path ~/.life-capital
# dedupe 合併可回滾
```

---

## 9. 參考資料

- V2.5 路線圖: `docs/roadmap/V2.5.md`
- 現有 Transaction 模型: `life_capital/models/transaction.py`
- Canonical Handler: `life_capital/io/canonical_handler.py`
- 護欄規則: `CLAUDE.md`
