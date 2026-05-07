# 測試套件說明

## 全域 Fixtures (`conftest.py`)

`tests/conftest.py` 提供了所有測試共用的 pytest fixtures。

### 可用 Fixtures

#### Session 級別（所有測試共用）

**`seed_data_session`**
- **用途**: Session 級別的唯讀完整資料（7 個月：2024-06 ~ 2024-12）
- **特性**: 所有測試共用同一份資料，**效能優化**
- **限制**: ⚠️ 不應修改，僅供讀取操作
- **適用**: 大量唯讀測試場景

```python
def test_read_only_operation(seed_data_session):
    # 只能讀取，不能修改
    expenses_dir = seed_data_session / CANONICAL_EXPENSES_DIR
    csv_files = list(expenses_dir.glob("expenses_*.csv"))
    assert len(csv_files) == 7
```

#### Function 級別（每個測試獨立）

**`seed_data_dir`**
- **用途**: 完整資料副本（7 個月：2024-06 ~ 2024-12）
- **特性**: 每個測試獨立副本，**完全隔離**
- **限制**: 無，可以自由修改
- **適用**: 需要修改資料的測試場景

```python
def test_with_modification(seed_data_dir):
    # 可以安全修改，不影響其他測試
    test_file = seed_data_dir / "test.txt"
    test_file.write_text("modified")
```

**`minimal_data_dir`**
- **用途**: 最小資料集（1 個月：2024-12）
- **特性**: 快速測試，**效能優化**
- **適用**: 基本功能測試，不需完整歷史資料

```python
def test_basic_feature(minimal_data_dir):
    # 只有 1 個月資料，測試更快
    expenses_dir = minimal_data_dir / CANONICAL_EXPENSES_DIR
    csv_files = list(expenses_dir.glob("expenses_*.csv"))
    assert len(csv_files) == 1
```

**`empty_data_dir`**
- **用途**: 空目錄結構（僅建立三層目錄，無資料檔案）
- **適用**: 測試 `lc init`、資料遷移等初始化場景

```python
def test_initialization(empty_data_dir):
    # 只有目錄結構，無資料檔案
    assert empty_data_dir.exists()
    assert (empty_data_dir / CANONICAL_DIR).exists()
    yaml_files = list(empty_data_dir.glob("**/*.yaml"))
    assert len(yaml_files) == 0
```

**`cli_runner`**
- **用途**: Typer CLI runner
- **適用**: 測試 CLI 指令執行

```python
def test_cli_command(cli_runner, seed_data_dir):
    from life_capital.cli import app

    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
```

### 使用建議

| 場景 | 建議 Fixture | 原因 |
|------|--------------|------|
| 唯讀操作（大量測試） | `seed_data_session` | 效能最佳，所有測試共用 |
| 需要修改資料 | `seed_data_dir` | 測試隔離，安全修改 |
| 基本功能測試 | `minimal_data_dir` | 快速執行，資料最小 |
| 初始化測試 | `empty_data_dir` | 從零開始 |
| CLI 指令測試 | `cli_runner` + 資料 fixture | 完整 CLI 測試 |

### 範例

完整使用範例請參考 `tests/examples/test_fixture_usage.py`。

## 測試資料

測試資料由 `tests/fixtures/seed_data.py` 的 `SeedDataBuilder` 生成。

### 資料內容

**完整資料集**（`build_full()`）：
- 7 個月資料：2024-06 ~ 2024-12
- 包含所有配置檔案：life_assumptions.yaml, monthly_income.yaml, expense_policy.yaml, lifetime_targets.yaml
- 每月支出資料：10 個基礎類別 + 特殊月份（12 月保險、7 月旅遊）
- 完整 provenance 追蹤

**最小資料集**（`build_minimal()`）：
- 1 個月資料：2024-12
- 相同的配置檔案
- 基本支出資料

## 執行測試

```bash
# 執行所有測試
uv run pytest tests/

# 執行特定測試檔案
uv run pytest tests/test_conftest_fixtures.py -v

# 執行特定測試
uv run pytest tests/test_conftest_fixtures.py::test_seed_data_dir_has_7_months -v

# 查看 fixtures 可用性
uv run pytest --fixtures tests/
```

## 測試組織

```
tests/
├── conftest.py                     # 全域 fixtures
├── README.md                       # 本文件
├── fixtures/                       # 測試資料建構器
│   ├── seed_data.py
│   └── test_seed_data.py
├── examples/                       # 使用範例
│   └── test_fixture_usage.py
├── commands/                       # CLI 指令測試
├── integration/                    # 整合測試
└── test_*/                         # 各模組單元測試
```
