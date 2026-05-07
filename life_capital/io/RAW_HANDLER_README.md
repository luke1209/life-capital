# raw_handler.py - 不可變資料寫入模組

## 快速開始

```python
from life_capital.io import write_raw, read_raw, list_raw_files
from life_capital.models.operation import Provenance, SourceType

# 1. 建立 Provenance
provenance = Provenance(
    source_type=SourceType.CSV_IMPORT,
    parser_version="1.0.0",
)

# 2. 寫入資料（自動設為 read-only）
file_path = write_raw(
    data={"name": "test", "value": 42},
    target="imports",  # or "manual"
    provenance=provenance,
    format="yaml",  # or "json", "csv"
)

# 3. 讀取資料
data, prov = read_raw(file_path)
print(data, prov.source_type)

# 4. 列出檔案
files = list_raw_files("imports")
```

## 核心特性

| 特性 | 說明 |
|------|------|
| **不可變寫入** | 寫入後自動設為 read-only (chmod 444) |
| **唯一檔名** | 格式: `{timestamp}_{uuid}.{ext}` |
| **來源追溯** | 嵌入 Provenance 資訊 |
| **多格式支援** | YAML, JSON, CSV |
| **防覆寫** | 不允許覆寫已存在檔案 |

## 目錄結構

```
~/.life-capital/
└── raw/
    ├── imports/        # 外部匯入（CSV, API）
    │   └── 20250127_120530_abc12345.yaml
    └── manual/         # 手動輸入
        └── 20250127_200000_def67890.json
```

## Provenance 格式

**YAML/JSON**:
```yaml
_provenance:
  source_id: "uuid"
  source_type: "csv_import"
  import_time: "2025-01-27T12:05:30"
  parser_version: "1.0.0"
data_field_1: value1
data_field_2: value2
```

**CSV**:
```csv
# Provenance: {"source_id": "uuid", "source_type": "csv_import", ...}
header1,header2
value1,value2
```

## API 簡表

| 函式 | 用途 |
|------|------|
| `write_raw(data, target, provenance, format)` | 寫入不可變資料 |
| `read_raw(file_path, model_class=None)` | 讀取資料 + Provenance |
| `list_raw_files(raw_type, since=None)` | 列出檔案（按時間排序） |

## 錯誤處理

```python
from life_capital.io import RawHandlerError, RawFileExistsError

try:
    write_raw(data, "imports", provenance)
except RawFileExistsError:
    print("檔案已存在（極少見）")
except RawHandlerError as e:
    print(f"寫入失敗: {e}")
```

## 完整文件

- 使用指南: `docs/raw_handler_usage.md`
- 測試: `tests/io/test_raw_handler.py`
- 驗證腳本: `verify_raw_handler.py`
