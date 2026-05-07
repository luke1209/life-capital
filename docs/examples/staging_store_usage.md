# StagingStore 使用範例

## 概述

StagingStore 提供 Phase 4 CAPTURE 的 StagingEntry 持久化介面，支援：
- **Append-only log** 語意（所有更新追加新行）
- **Last-write-wins** 讀取語意（自動去重）
- **並發安全**（threading.Lock 保護）
- **_seq 自動遞增**（O(1) 生成）

## 基本使用

### 1. 初始化

```python
from pathlib import Path
from life_capital.io.staging_store import get_staging_store

# 建立 StagingStore 實例
data_path = Path("~/.life-capital").expanduser()
store = get_staging_store(data_path)
```

### 2. 寫入 Entry（Append-only）

```python
from datetime import datetime
from decimal import Decimal
from life_capital.capture.models import (
    StagingEntry,
    StagingStatus,
    AmountSource,
    DateSource,
    CategorySource
)

# 建立新 entry
entry = StagingEntry(
    entry_id="uuid-001",
    raw_text="午餐 120 元",
    created_at=datetime.now(),
    parsed_amount=Decimal("120"),
    parsed_date=date.today(),
    parsed_category="food",
    amount_source=AmountSource.EXACT,
    date_source=DateSource.BUILTIN_EXACT,
    category_source=CategorySource.EXACT,
    status=StagingStatus.PENDING
)

# 寫入（自動分配 _seq）
store.write_entry(entry)
```

### 3. 更新 Entry（Append-only）

```python
# 建立更新版本（相同 entry_id）
entry_updated = StagingEntry(
    entry_id="uuid-001",  # 相同 entry_id
    raw_text="午餐 120 元",
    created_at=datetime.now(),
    parsed_amount=Decimal("120"),
    status=StagingStatus.APPROVED  # 狀態變更
)

# 寫入新版本（追加至 JSONL，不修改既有行）
store.write_entry(entry_updated)
```

### 4. 讀取單筆 Entry（Last-write-wins）

```python
# 讀取最新版本
entry = store.read_entry("uuid-001")
if entry:
    print(f"狀態: {entry.status}")  # 輸出: APPROVED
    print(f"金額: {entry.parsed_amount}")
```

### 5. 讀取所有 Entries（含歷史版本）

```python
# 讀取所有 entries（不去重）
all_entries = store.read_entries()
print(f"總記錄數（含歷史版本）: {len(all_entries)}")

# 依狀態過濾
pending_entries = store.read_entries(status="pending")
print(f"待處理數: {len(pending_entries)}")
```

### 6. 讀取當前狀態（Last-write-wins 去重）

```python
# 取得所有 entry 的最新版本
current_state = store.read_current_state()
print(f"唯一 entries 數: {len(current_state)}")

# 迭代最新狀態
for entry_id, entry in current_state.items():
    print(f"{entry_id}: {entry.status}")
```

## 進階使用

### 1. 批次寫入

```python
entries = [
    StagingEntry(
        entry_id=f"batch-{i}",
        raw_text=f"Entry {i}",
        created_at=datetime.now(),
        status=StagingStatus.PENDING
    )
    for i in range(100)
]

for entry in entries:
    store.write_entry(entry)
```

### 2. 錯誤處理

```python
try:
    entry = store.read_entry("non-existent")
    if entry is None:
        print("Entry 不存在")
except FileNotFoundError:
    print("entries.jsonl 尚未建立")
```

### 3. Protocol 依賴注入

```python
from life_capital.interfaces.staging_store import StagingStore

def process_entries(store: StagingStore):
    """此函式只依賴 Protocol，不依賴實作"""
    entries = store.read_entries(status="pending")
    for entry in entries:
        # 處理邏輯...
        pass

# 可注入任何實作了 StagingStore Protocol 的實例
process_entries(store)
```

## 儲存格式

### JSONL 範例

```jsonl
{"_seq": 1, "entry_id": "uuid-001", "raw_text": "午餐 120 元", "status": "pending", ...}
{"_seq": 2, "entry_id": "uuid-002", "raw_text": "晚餐 200 元", "status": "pending", ...}
{"_seq": 3, "entry_id": "uuid-001", "raw_text": "午餐 120 元", "status": "approved", ...}
```

### 特性

- **Append-only**: 第 3 行更新 uuid-001，不修改第 1 行
- **_seq 遞增**: 1, 2, 3, ...（O(1) 生成）
- **Last-write-wins**: `read_entry("uuid-001")` 返回 _seq=3 的版本

## 並發安全

StagingStore 使用 `threading.Lock` 保證並發安全：

```python
import threading

def worker(thread_id: int):
    store = get_staging_store(data_path)
    for i in range(10):
        entry = StagingEntry(
            entry_id=f"thread-{thread_id}-{i}",
            raw_text=f"Thread {thread_id}",
            created_at=datetime.now(),
            status=StagingStatus.PENDING
        )
        store.write_entry(entry)  # 並發安全

threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

## 效能特性

| 操作 | 時間複雜度 | 說明 |
|------|------------|------|
| `write_entry()` | O(1) | 追加寫入 + O(1) _seq 生成 |
| `read_entries()` | O(n) | 全檔案掃描 |
| `read_entry(id)` | O(n) | 全檔案掃描（未建立索引） |
| `read_current_state()` | O(n) | 全檔案掃描 + 去重 |

**注意**: 當前實作未建立索引，適合小規模資料（<10K entries）。若需高效查詢，可擴展實作層加入記憶體索引。

## 參考資料

- Protocol 定義: `life_capital/interfaces/staging_store.py`
- 實作層: `life_capital/io/staging_store.py`
- 資料模型: `life_capital/capture/models.py`
- Phase 4 規劃: `docs/roadmap/V2.5.md`
