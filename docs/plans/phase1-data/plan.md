# Phase 1: DATA 強化規劃 (V4 Final)

> **狀態**: 結構性收斂完成
> **版本**: V4 (Final)
> **審查歷程**: V1 → Round 1 → V2 → Round 2 → V3 → Round 4 結構性收斂

---

## 審查歷程摘要

| 輪次 | 焦點 | 關鍵發現 |
|------|------|----------|
| Round 1 | 結構性修正 | Transaction 模型已存在、canonical 應用 JSONL |
| Round 2 | 邊緣情境 | 退款誤合併、跨月重複、同日同額 |
| Round 3 | 護欄設計 | CLI 確認機制、寫入邊界強制、回滾支援 |
| **Round 4** | **結構性收斂** | 命名統一、介面定型、執行順序優化 |

---

## 1. 不可變約束（鐵則）

```
┌─────────────────────────────────────────────────────────────┐
│  raw/      → 最終來源，永遠不動                              │
│  canonical/ → 可演進狀態，所有寫入必須透過 canonical_handler │
│  derived/  → 可丟棄重算，lc rebuild 100% 重建               │
└─────────────────────────────────────────────────────────────┘
```

**migrate 契約**:
- migrate 只改 canonical 結構與版本，**raw 永遠不動**
- migrate 必須產生 migration_log / operation_id
- migrate 完成後，`lc rebuild` 仍可從 raw + canonical 重建 derived

---

## 2. 模型設計收斂（V4 優化）

### 2.1 欄位命名收斂

**問題**: V3 使用 `dedupe_version`，易被誤解為「被 dedupe 過幾次」

**解決**: 改用 `dedupe_key_version`，明確表示「去重策略版本」

```python
# models/transaction.py - V4 欄位設計
class Transaction(BaseModel):
    # 身份欄位
    stable_id: UUID = Field(default_factory=uuid4)  # immutable
    dedupe_key: str = Field(default="")              # versioned hash
    dedupe_key_version: str = Field(default="v1")    # ← V4 修正

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

    # 關聯欄位（已存在，退款支援）
    is_transfer: bool = False
    reversal_of: Optional[UUID] = None  # 模型層退款支援

    # 追蹤欄位
    source_row_ref: Optional[SourceRowRef] = None
    schema_version: str = CURRENT_SCHEMA_VERSION
    created_at: datetime
    updated_at: datetime
```

### 2.2 DedupeResult 枚舉（明確介面）

**問題**: V3 的去重結果在各模組各自解讀

**解決**: 定義明確的 `DedupeResult` 枚舉，所有模組共用

```python
# io/dedupe.py - V4 明確介面
from enum import Enum

class DedupeResult(str, Enum):
    """去重判定結果 - 各模組共用此介面

    三態定義：
    - AUTO_MERGE: 高相似度，自動合併
    - MANUAL_REVIEW: 中相似度或退款，需人工裁決
    - KEEP_BOTH: 低相似度，保留兩筆
    """
    AUTO_MERGE = "auto_merge"        # 相似度 ≥95%
    MANUAL_REVIEW = "manual_review"  # 70-95% 或退款
    KEEP_BOTH = "keep_both"          # <70%
```

### 2.3 退款處理分層（V4 優化）

**問題**: V3 在 dedupe.py 裡塞太多退款特判

**解決**: 分離關注點，模型層與 dedupe 層各司其職

```
┌─────────────────────────────────────────────────────────────┐
│ 模型層：Transaction.reversal_of 欄位（可選）                │
│         交易可標記為某筆交易的退款/沖正                      │
├─────────────────────────────────────────────────────────────┤
│ dedupe 層：偵測一正一負同金額 → MANUAL_REVIEW               │
│            不自動配對，交由人工確認                          │
├─────────────────────────────────────────────────────────────┤
│ CLI 層：lc dedupe --resolve 提示 [R]eversal 選項           │
│         用戶可選擇標記為退款關係                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 技術設計（V4 Final）

### 3.1 去重策略設計

```python
# io/dedupe.py（新建）
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import List, Tuple
from life_capital.models.transaction import Transaction

# === 版本與窗口配置 ===
DEDUPE_KEY_VERSION = "v1"
WINDOW_OCCURRED_DAYS = 1   # occurred_at ±1 天
WINDOW_POSTED_DAYS = 7     # posted_at ±7 天（跨月緩衝）

# === 相似度閾值 ===
SIMILARITY_THRESHOLD_AUTO = 0.95    # 95% 以上自動合併
SIMILARITY_THRESHOLD_REVIEW = 0.70  # 70% 以上需人工裁決


class DedupeResult(str, Enum):
    """去重判定結果 - 各模組共用此介面"""
    AUTO_MERGE = "auto_merge"
    MANUAL_REVIEW = "manual_review"
    KEEP_BOTH = "keep_both"


def find_candidates(
    record: Transaction,
    existing: List[Transaction],
) -> List[Transaction]:
    """在雙窗口內找出候選重複項

    V4 強化：雙窗口策略
    - occurred_at ±1 天（主要，以 occurred_at 優先）
    - posted_at ±7 天（跨月緩衝）
    """
    candidates = []
    for t in existing:
        # 跳過自己
        if t.stable_id == record.stable_id:
            continue

        # 檢查 occurred_at 窗口（優先）
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


def is_potential_reversal(a: Transaction, b: Transaction) -> bool:
    """偵測是否為潛在退款/沖正配對

    條件：一正一負，金額絕對值相同
    """
    if (a.amount > 0 and b.amount < 0) or (a.amount < 0 and b.amount > 0):
        return abs(a.amount) == abs(b.amount)
    return False


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
) -> Tuple[DedupeResult, List[Transaction], bool]:
    """判定去重結果

    Returns:
        (result, matched_transactions, is_reversal_candidate)
    """
    if not candidates:
        return DedupeResult.KEEP_BOTH, [], False

    high_similarity = []
    medium_similarity = []
    reversal_detected = False

    for c in candidates:
        # V4: 退款偵測優先
        if is_potential_reversal(record, c):
            reversal_detected = True
            medium_similarity.append((c, 0.75))  # 強制進入 MANUAL_REVIEW
            continue

        sim = compute_similarity(record, c)
        if sim >= SIMILARITY_THRESHOLD_AUTO:
            high_similarity.append((c, sim))
        elif sim >= SIMILARITY_THRESHOLD_REVIEW:
            medium_similarity.append((c, sim))

    if high_similarity and not reversal_detected:
        return DedupeResult.AUTO_MERGE, [c for c, _ in high_similarity], False
    elif medium_similarity or reversal_detected:
        all_matches = high_similarity + medium_similarity
        return DedupeResult.MANUAL_REVIEW, [c for c, _ in all_matches], reversal_detected
    else:
        return DedupeResult.KEEP_BOTH, [], False
```

### 3.2 寫入邊界強制

```python
# commands/dedupe_cmd.py - 合併操作必須透過 canonical_handler

def merge_duplicates(
    winner: Transaction,
    loser: Transaction,
    data_dir: Path,
    actor: str = "cli",
    is_reversal: bool = False,
) -> None:
    """合併重複項目

    V4 護欄：必須透過 canonical_handler 寫入
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

    # 處理退款關係
    if is_reversal:
        # 標記 reversal_of 而非合併
        for t in collection.transactions:
            if t.stable_id == loser.stable_id:
                t.reversal_of = winner.stable_id
                break
        operation_type = OperationType.DEDUPE_REVERSAL
    else:
        # 移除 loser，保留 winner
        collection.transactions = [
            t for t in collection.transactions
            if t.stable_id != loser.stable_id
        ]
        operation_type = OperationType.DEDUPE_MERGE

    # 透過 canonical_handler 寫入（記錄 operation_id）
    write_canonical(
        data=collection,
        target_path=month_file,
        data_dir=data_dir,
    )

    # 記錄操作
    operation = Operation(
        operation_type=operation_type,
        target_path=str(month_file.relative_to(data_dir)),
        description=f"Dedupe: {loser.stable_id[:8]} → {winner.stable_id[:8]}",
        actor=actor,
        metadata={
            "winner_id": str(winner.stable_id),
            "loser_id": str(loser.stable_id),
            "is_reversal": is_reversal,
        },
        rollback_data={
            "loser_transaction": loser.model_dump(mode="json"),
        },
    )
    append_operation_log(operation, data_dir)
```

### 3.3 遷移機制設計

```python
# io/migration.py（新建）
from pathlib import Path
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from typing import Optional
from pydantic import BaseModel, Field

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
    backup_path: Optional[str] = None


def migrate_schema(
    data_root: Path,
    target_version: str,
    actor: str = "migration",
    dry_run: bool = False,
) -> MigrationLog:
    """執行 Schema 遷移

    V4 契約：
    - raw 永遠不動
    - 必須產生 migration_log / operation_id
    - migrate 後 lc rebuild 仍可從 raw + canonical 重建 derived
    """
    from life_capital.io.canonical_handler import append_operation_log
    from life_capital.models.operation import Operation, OperationType

    # 1. 驗證 raw 不會被修改（V4 契約）
    raw_dir = data_root / "raw"
    raw_hash_before = compute_dir_hash(raw_dir) if raw_dir.exists() else None

    # 2. 掃描需遷移檔案（只在 canonical/）
    affected = scan_migration_targets(data_root / "canonical", target_version)

    if dry_run:
        return MigrationLog(
            from_version=get_current_version(data_root),
            to_version=target_version,
            affected_files=[str(f) for f in affected],
            rollback_available=False,
        )

    # 3. 遷移前備份
    backup_dir = create_backup(data_root, affected)

    # 4. 執行遷移
    for file_path in affected:
        migrate_file(file_path, target_version)

    # 5. 驗證 raw 未被修改（V4 契約）
    if raw_dir.exists():
        raw_hash_after = compute_dir_hash(raw_dir)
        if raw_hash_before != raw_hash_after:
            # 回滾並報錯
            restore_backup(backup_dir, data_root)
            raise MigrationError("raw/ was modified during migration - rolled back")

    # 6. 記錄遷移日誌
    log = MigrationLog(
        from_version=get_current_version(data_root),
        to_version=target_version,
        affected_files=[str(f) for f in affected],
        backup_path=str(backup_dir),
    )

    # 7. 記錄到 operation_log
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
```

---

## 4. 命令設計

### 4.1 lc dedupe

```bash
# 掃描並顯示去重衝突（低風險）
lc dedupe --path ~/.life-capital

# 互動式裁決（中風險）
lc dedupe --resolve --path ~/.life-capital

# 自動處理（高風險，需確認）
lc dedupe --auto --path ~/.life-capital
lc dedupe --auto --yes --path ~/.life-capital  # 跳過確認
```

**輸出格式（V4 使用 DedupeResult 三態）**:
```
掃描完成: 發現 3 組潛在重複

組 1: AUTO_MERGE (相似度 98%)
  [A] 2024-12-05 | ¥1,200 | transportation | person_a
  [B] 2024-12-06 | ¥1,200 | transportation | person_a
  → 建議自動合併

組 2: MANUAL_REVIEW (相似度 75%, 疑似退款)
  [A] 2024-12-10 | ¥2,800 | food | person_b
  [B] 2024-12-10 | -¥2,800 | food | person_b
  → ⚠️ 偵測到一正一負同金額，可能是退款

組 3: KEEP_BOTH (相似度 45%)
  [A] 2024-12-15 | ¥500 | food | person_a
  [B] 2024-12-15 | ¥500 | transportation | person_b
  → 保留兩筆（不同類別/支付者）

選擇操作: [M]erge / [K]eep both / [R]eversal / [S]kip
```

### 4.2 lc migrate

```bash
# 檢查遷移狀態
lc migrate --status --path ~/.life-capital

# Dry-run（顯示影響範圍，不執行）
lc migrate --to v2 --dry-run --path ~/.life-capital

# 執行遷移（需確認）
lc migrate --to v2 --path ~/.life-capital
```

---

## 5. 新增/修改檔案

| 檔案 | 動作 | 說明 |
|------|------|------|
| `models/transaction.py` | 修改 | 新增 `dedupe_key_version` 欄位 |
| `models/operation.py` | 修改 | 新增 OperationType.DEDUPE_MERGE, DEDUPE_REVERSAL, MIGRATE |
| `io/dedupe.py` | **新建** | DedupeResult 枚舉 + 雙窗口策略 + 退款檢測 |
| `io/migration.py` | **新建** | Schema 遷移（含備份、raw 不動驗證） |
| `commands/dedupe_cmd.py` | **新建** | lc dedupe 命令（含護欄） |
| `commands/migrate_cmd.py` | **新建** | lc migrate 命令 |
| `validators/dedupe_validator.py` | **新建** | 錯誤分類（hard/soft） |
| `io/registry.py` | 修改 | 新增 DEDUPE_CONFLICTS_DIR 等常數 |
| `commands/apply_cmd.py` | 修改 | CSV→Transaction 轉換 |
| `commands/doctor.py` | 修改 | 新增檢查項（含 migrate 契約驗證） |

---

## 6. 實施順序（V4 優化：先鎖寫入邊界）

### Phase 1.1: 寫入邊界先行（Day 1）⭐ 關鍵

**目標**: 讓 dedupe/migrate 都自然落在同一套寫入框架上

```
1. io/canonical_handler.py - 確認寫入邊界與 operation_log 產生
2. models/operation.py - 新增 OperationType.DEDUPE_MERGE, DEDUPE_REVERSAL, MIGRATE
3. io/registry.py - 新增 DEDUPE_CONFLICTS_DIR 等常數
4. models/transaction.py - 新增 dedupe_key_version（非 dedupe_version）
```

### Phase 1.2: 去重實作（Day 2-3）

```
1. io/dedupe.py - DedupeResult 枚舉 + 雙窗口策略 + 退款檢測
2. validators/dedupe_validator.py - 錯誤分類（hard/soft）
3. commands/dedupe_cmd.py - CLI（含護欄確認）
```

### Phase 1.3: Apply/Format 轉換（Day 4）

```
1. commands/apply_cmd.py - CSV→Transaction 轉換
2. 建立遷移腳本（備份 + 轉換）
```

### Phase 1.4: 遷移機制（Day 5-6）

```
migrate 契約驗證：
- raw 永遠不動（migrate 前後 hash 相同）
- migrate 必須產生 migration_log / operation_id
- migrate 後 lc rebuild 仍可從 raw + canonical 重建 derived

1. io/migration.py - Schema 遷移（含備份、raw 不動驗證）
2. commands/migrate_cmd.py - CLI
3. commands/doctor.py - 新增檢查項（含 migrate 契約驗證）
```

### Phase 1.5: 整合測試（Day 7）

```
1. 測試護欄生效
2. 驗證 migrate 契約（raw 不動、rebuild 可行）
3. 更新文件
```

---

## 7. doctor 新增檢查項

```python
# commands/doctor.py - V4 新增檢查項

PHASE1_CHECKS = [
    # 寫入邊界
    ("canonical_via_handler", "canonical/ 變更都透過 canonical_handler"),
    ("operation_log_complete", "所有變更都有 operation_id"),

    # 去重
    ("dedupe_key_version_consistent", "所有 Transaction 的 dedupe_key_version 一致"),
    ("no_duplicate_stable_id", "無重複的 stable_id"),
    ("no_orphan_source_ref", "SourceRowRef 指向的 raw 檔案存在"),

    # migrate 契約
    ("raw_immutable", "raw/ 內容未被修改"),
    ("rebuild_possible", "lc rebuild 可從 raw + canonical 重建 derived"),
    ("migration_log_valid", "遷移日誌格式正確"),
    ("backup_exists", "最近遷移有備份"),
]
```

---

## 8. 錯誤分類表

| 錯誤 | 分類 | `lc doctor` 輸出 | 處理方式 |
|------|------|------------------|----------|
| Schema 版本不一致 | Hard Fail | ❌ FAIL | 拒絕操作 |
| 繞過 canonical_handler | Hard Fail | ❌ FAIL | 拒絕 + 記錄違規 |
| 重複 stable_id | Hard Fail | ❌ FAIL | 需人工修復 |
| raw 被修改 | Hard Fail | ❌ FAIL | 回滾 + 報警 |
| 未知 payer | Soft Warning | ⚠️ WARN | 使用 "shared" |
| 遺失 merchant | Soft Warning | ⚠️ WARN | 允許為空 |
| 疑似退款未標記 | Soft Warning | ⚠️ WARN | 建議檢查 |

---

## 9. 驗收標準（V4 Final）

```bash
# 1. 去重可判定（DedupeResult 三態輸出）
lc dedupe --path ~/.life-capital
# → 顯示 AUTO_MERGE / MANUAL_REVIEW / KEEP_BOTH

# 2. 護欄生效（高風險操作需確認）
lc dedupe --auto --path ~/.life-capital
# → 需 --yes 或互動確認

# 3. 可重建（migrate 契約核心）
lc rebuild --path ~/.life-capital
# → raw + canonical 100% 重建 derived

# 4. JSONL 格式
ls ~/.life-capital/canonical/expenses/
# → 2024-12.jsonl

# 5. 回滾可用
lc undo --latest --path ~/.life-capital

# 6. raw 永不動（migrate 契約）
lc migrate --to v2 --path ~/.life-capital
ls ~/.life-capital/raw/  # 內容不變
```

---

## 10. Backlog（可延後至 Phase 2+）

| 項目 | 說明 | 優先級 |
|------|------|--------|
| dedupe_conflicts 資料結構 | 每個 conflict 存成 `operation_id.json` | P2 |
| occurred_at vs posted_at 優先序 | 比對規則明確化 | P2 |
| 2-of-2 權限模型 | 高風險操作需雙重確認 | P3 |

---

## 11. 參考資料

- V2.5 路線圖: `docs/roadmap/V2.5.md`
- 現有 Transaction 模型: `life_capital/models/transaction.py`
- Canonical Handler: `life_capital/io/canonical_handler.py`
- 護欄規則: `CLAUDE.md`

---

## 驗收報告

> **狀態**: ✅ 通過
> **日期**: 2025-12-27
> **Commit**: 02b894c (Phase 1.5 補丁完成)

### 驗收標準

| # | 標準 | 結果 | 驗證 |
|---|------|------|------|
| 1 | 所有測試通過 | ✅ | `pytest tests/` - 116 passed |
| 2 | lc doctor 無 hard fail | ✅ | `lc doctor` |
| 3 | 三層結構完整 | ✅ | raw/canonical/derived 正常運作 |
| 4 | import/apply/undo 流程 | ✅ | CLI 指令可正常執行 |

### 依賴項目

| 依賴 | 來源 | 狀態 |
|------|------|------|
| 三層結構 | Phase 0 | ✅ |
| Pydantic Models | 初始架構 | ✅ |

### 後續 Backlog

- dedupe_conflicts 資料結構（P2）
- occurred_at vs posted_at 優先序（P2）
- 2-of-2 權限模型（P3）
