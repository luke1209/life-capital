# Canonical Handler 模組說明

## 概述

`canonical_handler.py` 提供 canonical 資料的唯一寫入入口與 operation_id 追蹤機制，確保所有 canonical/ 資料變更都經過完整追蹤。

## 核心功能

### 1. write_canonical() - 唯一寫入入口

```python
from life_capital.io.canonical_handler import write_canonical
from life_capital.models.operation import Operation, OperationType

operation = Operation(
    actor="user_id",
    operation_type=OperationType.IMPORT,
    target_path=Path("canonical/expenses/2024_12.csv"),
    description="Import December expenses",
)

operation_id = write_canonical(
    data=expense_model,
    target_path=data_root / "canonical" / "expenses" / "2024_12.csv",
    operation=operation,
)
```

**護欄機制**:
- ✅ 強制檢查 `operation_id` 存在（自動由 Pydantic 生成）
- ✅ 確保目標路徑在 `canonical/` 內
- ✅ 原子寫入（tempfile + rename）
- ✅ 自動記錄 operation log

### 2. read_canonical() - 標準讀取

```python
from life_capital.io.canonical_handler import read_canonical
from life_capital.models.expense import ExpenseRecord

expense = read_canonical(
    file_path=data_root / "canonical" / "expenses" / "2024_12.csv",
    model_class=ExpenseRecord,
)
```

### 3. append_operation_log() - 追加日誌

```python
from life_capital.io.canonical_handler import append_operation_log
from life_capital.models.operation import OperationLogEntry

log_entry = OperationLogEntry(operation=operation)
append_operation_log(log_entry)
```

**日誌格式**: JSONL（每行一個 JSON）
**位置**: `canonical/.operation_log.jsonl`

### 4. read_operation_log() - 讀取日誌

```python
from life_capital.io.canonical_handler import read_operation_log
from life_capital.models.operation import OperationType
from datetime import datetime, timedelta

# 讀取最近一天的匯入操作
entries = read_operation_log(
    since=datetime.now() - timedelta(days=1),
    operation_type=OperationType.IMPORT,
)
```

### 5. detect_bypass() - 偵測繞過

```python
from life_capital.io.canonical_handler import detect_bypass

# 偵測可能的直接修改（未經 canonical_handler）
bypass_files = detect_bypass(data_root)

if bypass_files:
    print("警告：偵測到繞過寫入的檔案：")
    for file_path in bypass_files:
        print(f"  - {file_path}")
```

**偵測邏輯**:
- 比對檔案修改時間與 operation log 記錄
- 容差範圍：5 秒（考慮檔案系統時間精度）

## 整合範例

### 完整匯入流程

```python
from pathlib import Path
from life_capital.io.canonical_handler import write_canonical
from life_capital.models.operation import Operation, OperationType, Provenance, SourceType
from life_capital.models.expense import ExpenseRecord

# 1. 建立 operation
operation = Operation(
    actor="user_id",
    operation_type=OperationType.IMPORT,
    target_path=Path("canonical/expenses/2024_12.csv"),
    description="Import December 2024 expenses from CSV",
    metadata={
        "records_count": 42,
        "source_file": "raw/imports/bank_statement.csv",
    },
)

# 2. 寫入 canonical 資料
operation_id = write_canonical(
    data=expense_record,
    target_path=data_root / "canonical" / "expenses" / "2024_12.csv",
    operation=operation,
)

print(f"匯入完成，operation_id: {operation_id}")

# 3. 驗證（可選）
from life_capital.io.canonical_handler import detect_bypass
bypass_files = detect_bypass(data_root)
if bypass_files:
    raise RuntimeError(f"偵測到繞過寫入: {bypass_files}")
```

### lc doctor 整合

```python
from life_capital.io.canonical_handler import detect_bypass

def check_canonical_integrity(data_root: Path) -> list[str]:
    """檢查 canonical 資料完整性"""
    issues = []

    # 偵測繞過寫入
    bypass_files = detect_bypass(data_root)
    if bypass_files:
        issues.append(f"偵測到 {len(bypass_files)} 個繞過寫入的檔案")
        for file in bypass_files:
            issues.append(f"  - {file.relative_to(data_root)}")

    return issues
```

## 測試覆蓋

執行測試：
```bash
pytest tests/io/test_canonical_handler.py -v
```

**測試範圍**:
- ✅ 正常寫入流程
- ✅ 路徑護欄（非 canonical/ 路徑）
- ✅ 原子寫入正確性
- ✅ Operation log 記錄
- ✅ 繞過偵測（直接修改、時間不一致）
- ✅ JSON/YAML 格式支援

## 技術限制

1. **時間精度**：macOS HFS+ 時間精度約 1 秒，容差設為 5 秒
2. **Python 版本**：需 Python 3.9+（使用字串型別標註相容性）
3. **執行緒安全**：不保證多執行緒安全（需外部鎖機制）

## 未來擴展

- [ ] 支援批次寫入
- [ ] 增加 rollback 功能
- [ ] 整合到 `lc doctor` 指令
- [ ] 增加效能監控（寫入時間、log 大小）
