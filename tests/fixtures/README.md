# Test Fixtures

測試資料建構器與 fixtures，用於快速生成符合 CLAUDE.md 護欄規則的測試資料。

## 目錄

- [Factory Pattern](#factory-pattern) - 快速建立單一模型實例
- [SeedDataBuilder](#seeddatabuilder) - 建立完整測試資料集

---

## Factory Pattern

`factory.py` 提供快速建立測試用 Pydantic 模型實例的工廠函式。

### 核心功能

- **合理預設值**: 所有工廠函式提供開箱即用的預設值
- **部分覆寫**: 透過 `**kwargs` 靈活覆寫任意欄位
- **型別安全**: 使用 Decimal 處理金額，確保精度
- **版本一致**: 自動使用 `CURRENT_SCHEMA_VERSION`

### 快速開始

#### 基本使用

```python
from tests.fixtures.factory import make_expense_record
from decimal import Decimal

# 使用預設值
record = make_expense_record()
# ExpenseRecord(date=今天, amount=1000, category="food", payer="shared")

# 部分覆寫
record = make_expense_record(amount=Decimal("500"), payer="person_a")
```

#### 建立月度支出

```python
from tests.fixtures.factory import make_monthly_expenses, make_expense_record

expenses = make_monthly_expenses(
    year=2024, month=6,
    records=[
        make_expense_record(category="housing", amount=Decimal("28000")),
        make_expense_record(category="food", amount=Decimal("20000")),
    ]
)
assert expenses.total() == Decimal("43000")
```

#### 建立月收入

```python
from tests.fixtures.factory import make_monthly_income

# 使用預設值（主要薪資 85K + 副業 15K）
income = make_monthly_income()
assert income.total_monthly() == 100000.0
```

#### 建立生活假設

```python
from tests.fixtures.factory import make_life_assumptions, make_rates
from life_capital.models.assumptions import RatesMode

# 切換為實質模式
assumptions = make_life_assumptions(
    rates=make_rates(
        mode=RatesMode.REAL,
        real_investment_return=0.03
    )
)
```

### 可用的工廠函式

| 函式 | 回傳類型 | 主要預設值 |
|------|----------|-----------|
| `make_expense_record()` | ExpenseRecord | amount=1000, category="food", payer="shared" |
| `make_monthly_expenses()` | MonthlyExpenses | year=當前年, month=12, records=[] |
| `make_monthly_income()` | MonthlyIncome | 主要薪資 85K + 副業 15K |
| `make_life_assumptions()` | LifeAssumptions | age=35, retirement=65, nominal mode |
| `make_income_source()` | IncomeSource | amount=50000, frequency="monthly" |
| `make_child()` | Child | birth_year=當前年-5, university_age=18 |
| `make_basic()` | Basic | current_age=35, retirement_age=65 |
| `make_rates()` | Rates | mode=nominal, inflation=0.02 |
| `make_calculation()` | Calculation | scale=0, rounding=ROUND_HALF_UP |

詳細使用範例請見 `tests/fixtures/test_factory.py`。

---

## SeedDataBuilder

`SeedDataBuilder` 提供 Fluent API 來建立測試資料集。

### 特性

- ✅ 完全遵守 CLAUDE.md 護欄規則
- ✅ 使用 `io/yaml_handler.py` 與 `io/raw_handler.py`
- ✅ 自動生成 `operation_id` 追蹤
- ✅ raw/imports 檔案設為 read-only (chmod 444)
- ✅ 自動生成 `raw_manifest.json`
- ✅ schema_version = 1.1
- ✅ 支付者分布：person_a≈30%, person_b≈25%, shared≈45%

### 使用方式

#### 最小資料集（1 個月）

```python
from pathlib import Path
from tests.fixtures.seed_data import SeedDataBuilder

# 建立 1 個月測試資料（2024-12）
builder = SeedDataBuilder(Path("./test_data"))
data_dir = builder.build_minimal()

# 資料結構：
# test_data/
# ├── canonical/
# │   ├── life_assumptions.yaml
# │   ├── monthly_income.yaml
# │   ├── expense_policy.yaml
# │   ├── lifetime_targets.yaml
# │   ├── expenses/
# │   │   └── expenses_2024_12.csv
# │   └── .operation_log.jsonl
# └── raw/
#     ├── imports/
#     │   └── 20241228_*.csv (read-only)
#     └── raw_manifest.json
```

#### 完整資料集（7 個月）

```python
# 建立 7 個月測試資料（2024-06 ~ 2024-12）
builder = SeedDataBuilder(Path("./test_data"))
data_dir = builder.build_full()

# 或使用 Fluent API
data_dir = builder.with_months(7).build_full()
```

#### 自訂月份數量

```python
# 建立 3 個月測試資料
builder = SeedDataBuilder(Path("./test_data"))
data_dir = builder.with_months(3).build_full()
```

### 資料內容

#### 配置檔案

| 檔案 | 內容 |
|------|------|
| `life_assumptions.yaml` | 年齡 35, 退休 65, 預期壽命 85, 通膨 2%, 報酬率 5% |
| `monthly_income.yaml` | Person A 85K, Person B 55K（包含 owner 欄位）|
| `expense_policy.yaml` | 10 個類別，3 個群組（必要、選擇性、儲蓄投資）|
| `lifetime_targets.yaml` | 4 個目標（緊急基金、購車、房屋頭期款、退休基金）|

#### 月度支出

**基準模板**（每月固定）:
- housing: 28,000 TWD (shared)
- food: 15,000 TWD (person_a 7K + person_b 8K)
- transportation: 1,800 TWD (person_a)
- utilities: 2,650 TWD (shared)
- entertainment: 500 TWD (shared)
- dining_out: 1,800 TWD (shared)
- shopping: 2,500 TWD (person_b)
- savings: 15,000 TWD (person_a)
- investment: 15,000 TWD (person_b)

**特殊月份**:
- **12 月**: +保險 39,000 TWD (shared) + 聖誕禮物 5,000 TWD (shared) + 退款 -500 TWD (shared)
- **7 月**: +暑假旅遊 8,000 TWD (shared)

#### 支付者分布

| 支付者 | 比例 | 說明 |
|--------|------|------|
| person_a | ~30% | Person A 個人支出 |
| person_b | ~25% | Person B 個人支出 |
| shared | ~45% | 共同支出 |

### 測試範例

```python
import pytest
from pathlib import Path
from tests.fixtures.seed_data import SeedDataBuilder

@pytest.fixture
def seed_data(tmp_path):
    """提供測試資料"""
    builder = SeedDataBuilder(tmp_path / "data")
    return builder.build_full()

def test_with_seed_data(seed_data):
    """使用 seed data 的測試"""
    # seed_data 為資料目錄 Path 物件
    assert (seed_data / "canonical" / "life_assumptions.yaml").exists()

    # 驗證資料
    from life_capital.io.yaml_handler import load_model
    from life_capital.models import LifeAssumptions

    assumptions = load_model(
        seed_data / "canonical" / "life_assumptions.yaml",
        LifeAssumptions
    )
    assert assumptions.basic.current_age == 35
```

### 護欄規則遵守情況

所有生成的資料完全遵守 CLAUDE.md 護欄規則：

1. ✅ **寫入邊界**: canonical/ 透過 operation_id 追蹤，raw/ 為不可變
2. ✅ **不可逆操作**: raw/ 檔案 chmod 444
3. ✅ **Decimal 強制**: 使用 Pydantic 模型確保 Decimal 類型
4. ✅ **Schema 版本**: 所有 YAML 檔案 schema_version = 1.1
5. ✅ **Operation Log**: 每次匯入都記錄到 .operation_log.jsonl
6. ✅ **Raw Manifest**: 自動生成 SHA-256 manifest
7. ✅ **Provenance**: raw/imports 檔案包含完整來源追溯

### 開發筆記

- 使用 `io/yaml_handler.save_model()` 寫入 Pydantic 模型
- 使用 `io/yaml_handler.save_yaml()` 寫入一般 dict
- 使用 `io/raw_handler.save_raw_manifest()` 生成 manifest
- CSV 寫入後手動 chmod 444（`io/raw_handler` 已處理）
- operation_id 使用 uuid4() 生成
