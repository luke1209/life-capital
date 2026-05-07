# Raw Handler 使用指南

## 概述

`raw_handler.py` 提供不可變寫入機制，用於 `raw/imports` 和 `raw/manual` 目錄的資料管理。

**核心特性**:
- ✅ 寫入後檔案自動設為 read-only (chmod 444)
- ✅ 自動生成唯一檔名（時間戳 + UUID）
- ✅ 嵌入 Provenance 資訊（來源追溯）
- ✅ 支援 YAML/JSON/CSV 多格式
- ✅ 不允許覆寫已存在檔案

---

## API 參考

### `write_raw()`

寫入不可變資料至 raw 目錄。

**參數**:
```python
def write_raw(
    data: BaseModel | dict[str, Any],  # 資料內容
    target: Literal["imports", "manual"],  # 目標目錄
    provenance: Provenance,  # 來源追溯資訊
    format: Literal["yaml", "json", "csv"] = "yaml",  # 檔案格式
    base_dir: Optional[Path] = None,  # 資料根目錄（預設使用環境變數）
) -> Path:  # 返回寫入的檔案路徑
```

**範例**:
```python
from life_capital.io import write_raw
from life_capital.models.operation import Provenance, SourceType

# 建立 Provenance
provenance = Provenance(
    source_type=SourceType.CSV_IMPORT,
    parser_version="1.0.0",
)

# 寫入 YAML 至 imports 目錄
file_path = write_raw(
    data={"name": "test", "value": 42},
    target="imports",
    provenance=provenance,
    format="yaml",
)

print(f"寫入: {file_path}")
# 輸出: /path/to/.life-capital/raw/imports/20250127_120530_abc12345.yaml
```

**特性**:
- 檔案名稱格式: `{timestamp}_{uuid}.{ext}`
- 檔案權限: 444 (read-only)
- Provenance 嵌入: YAML/JSON 使用 `_provenance` 欄位，CSV 使用註解

---

### `read_raw()`

讀取 raw 目錄的資料。

**參數**:
```python
def read_raw(
    file_path: Path,  # 檔案路徑
    model_class: Optional[type[BaseModel]] = None,  # 驗證用模型（可選）
) -> tuple[dict[str, Any] | BaseModel, Optional[Provenance]]:
    # 返回 (資料, Provenance)
```

**範例**:
```python
from life_capital.io import read_raw
from pydantic import BaseModel

class MyData(BaseModel):
    name: str
    value: int

# 讀取並驗證為模型
data, provenance = read_raw(file_path, model_class=MyData)
print(f"Name: {data.name}, Value: {data.value}")
print(f"來源: {provenance.source_type}")

# 讀取為字典
data_dict, provenance = read_raw(file_path)
print(data_dict)
```

**支援格式**:
- `.yaml`, `.yml` → 自動解析為 dict
- `.json` → 自動解析為 dict
- `.csv` → 返回 `{"headers": [...], "rows": [...]}`

---

### `list_raw_files()`

列出 raw 目錄的檔案。

**參數**:
```python
def list_raw_files(
    raw_type: Literal["imports", "manual"],  # 目錄類型
    since: Optional[datetime] = None,  # 篩選時間（可選）
    base_dir: Optional[Path] = None,  # 資料根目錄
) -> list[Path]:  # 返回檔案路徑列表（按時間排序）
```

**範例**:
```python
from life_capital.io import list_raw_files
from datetime import datetime, timedelta

# 列出所有 imports 檔案
files = list_raw_files("imports")
print(f"共 {len(files)} 個檔案")

# 列出最近 24 小時的檔案
cutoff = datetime.now() - timedelta(hours=24)
recent_files = list_raw_files("imports", since=cutoff)
```

---

## Provenance 資訊

Provenance 用於追溯資料來源，記錄在每個 raw 檔案中。

**定義**:
```python
from life_capital.models.operation import Provenance, SourceType

provenance = Provenance(
    source_id=uuid4(),  # 自動生成
    source_type=SourceType.CSV_IMPORT,  # 必填
    import_time=datetime.now(),  # 自動生成
    parser_version="1.0.0",  # 必填
    prompt_hash=None,  # 可選（AI 生成時使用）
    model_version=None,  # 可選（AI 生成時使用）
)
```

**SourceType 選項**:
- `CSV_IMPORT`: CSV 檔案匯入
- `MANUAL_ENTRY`: 手動輸入
- `MIGRATION`: 資料遷移
- `AI_GENERATED`: AI 生成

**儲存方式**:
- **YAML/JSON**: 使用 `_provenance` 欄位
  ```yaml
  _provenance:
    source_id: "abc-def-123"
    source_type: "csv_import"
    import_time: "2025-01-27T12:05:30"
    parser_version: "1.0.0"
  name: test
  value: 42
  ```

- **CSV**: 使用第一行註解
  ```csv
  # Provenance: {"source_id": "abc-def-123", "source_type": "csv_import", ...}
  date,amount,category,payer,note,merchant
  2024-01-01,100.00,food,person_a,午餐,7-11
  ```

---

## CSV 格式特別說明

CSV 格式需要特定的資料結構：

```python
csv_data = {
    "headers": ["date", "amount", "category"],
    "rows": [
        {"date": "2024-01-01", "amount": "100.00", "category": "food"},
        {"date": "2024-01-02", "amount": "200.00", "category": "transport"},
    ],
}

write_raw(
    data=csv_data,
    target="imports",
    provenance=provenance,
    format="csv",
)
```

讀取時返回相同格式：
```python
data, prov = read_raw(csv_file_path)
# data = {"headers": [...], "rows": [...]}
```

---

## 安全機制

### Read-Only 保護

所有寫入的檔案自動設為 444 權限：

```python
file_path = write_raw(data, "imports", provenance)

# 嘗試修改會失敗
with open(file_path, "w") as f:  # ❌ PermissionError
    f.write("new content")

# 但可以讀取
with open(file_path, "r") as f:  # ✅ OK
    content = f.read()
```

### 不可覆寫

檔案名稱包含時間戳 + UUID，理論上不會碰撞。若真的碰撞：

```python
# 會拋出 RawFileExistsError
try:
    write_raw(data, "imports", provenance)
except RawFileExistsError as e:
    print(f"檔案已存在: {e.path}")
```

---

## 目錄結構

```
~/.life-capital/
├── raw/
│   ├── imports/             # CSV 匯入等外部來源
│   │   ├── 20250127_120530_abc12345.yaml
│   │   ├── 20250127_123045_def67890.csv
│   │   └── 20250127_140000_ghi11111.json
│   └── manual/              # 手動輸入資料
│       ├── 20250127_200000_jkl22222.yaml
│       └── 20250127_160000_mno33333.json
├── canonical/               # 已驗證資料（可編輯）
└── derived/                 # 衍生資料
```

---

## 錯誤處理

### 常見錯誤

```python
from life_capital.io import (
    RawHandlerError,
    RawFileExistsError,
    write_raw,
    read_raw,
)

# 1. 檔案已存在（極少見）
try:
    write_raw(data, "imports", provenance)
except RawFileExistsError as e:
    print(f"碰撞: {e.path}")

# 2. 寫入失敗
try:
    write_raw(data, "imports", provenance)
except RawHandlerError as e:
    print(f"寫入錯誤: {e}")

# 3. 讀取失敗
try:
    data, prov = read_raw(Path("/invalid/path.yaml"))
except FileNotFoundError:
    print("檔案不存在")
except RawHandlerError as e:
    print(f"讀取錯誤: {e}")
```

---

## 最佳實踐

### 1. 始終提供 Provenance

```python
# ✅ 好：明確記錄來源
provenance = Provenance(
    source_type=SourceType.CSV_IMPORT,
    parser_version="1.0.0",
)
write_raw(data, "imports", provenance)

# ❌ 壞：無法追溯來源
# （Provenance 是必填參數）
```

### 2. 使用正確的目標目錄

```python
# ✅ imports: 外部匯入（CSV, API）
write_raw(csv_data, "imports", provenance)

# ✅ manual: 手動輸入
write_raw(manual_entry, "manual", provenance)
```

### 3. 驗證讀取結果

```python
# ✅ 使用 model_class 驗證
data, prov = read_raw(file_path, model_class=MyModel)

# 檢查 Provenance
if prov and prov.source_type == SourceType.CSV_IMPORT:
    print("來自 CSV 匯入")
```

### 4. 時間篩選

```python
# 只處理最近的檔案
from datetime import datetime, timedelta

recent = list_raw_files(
    "imports",
    since=datetime.now() - timedelta(days=7)
)
```

---

## 測試

完整測試範例：`tests/io/test_raw_handler.py`

執行測試：
```bash
pytest tests/io/test_raw_handler.py -v
```

驗證腳本：
```bash
python3 verify_raw_handler.py
```

---

## 版本歷史

- **V1.0** (2025-01-27): 初始版本
  - 不可變寫入機制
  - Provenance 嵌入
  - YAML/JSON/CSV 支援
  - Read-only 保護
