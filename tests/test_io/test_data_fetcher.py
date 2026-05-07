"""Data Fetcher 資料取得模組測試

測試歷史支出資料的取得功能。
"""

from decimal import Decimal

import pytest

from life_capital.io.data_fetcher import (
    _subtract_months,
    fetch_expense_range,
    fetch_historical_expenses,
    list_expense_months,
    parse_expense_filename,
)

# =============================================================================
# Filename Parsing Tests
# =============================================================================


class TestParseExpenseFilename:
    """支出檔名解析測試"""

    def test_valid_filename(self):
        """有效檔名解析"""
        result = parse_expense_filename("expenses_2024_12.csv")
        assert result == (2024, 12)

    def test_valid_filename_january(self):
        """一月檔名解析"""
        result = parse_expense_filename("expenses_2025_01.csv")
        assert result == (2025, 1)

    def test_invalid_format(self):
        """無效格式回傳 None"""
        assert parse_expense_filename("invalid.csv") is None
        assert parse_expense_filename("expenses_2024.csv") is None
        assert parse_expense_filename("expenses_2024_1.csv") is None
        assert parse_expense_filename("2024_12.csv") is None

    def test_wrong_extension(self):
        """錯誤副檔名回傳 None"""
        assert parse_expense_filename("expenses_2024_12.xlsx") is None


# =============================================================================
# Subtract Months Tests
# =============================================================================


class TestSubtractMonths:
    """月份減法測試"""

    def test_same_year(self):
        """同年內減法"""
        assert _subtract_months(2024, 12, 3) == (2024, 9)
        assert _subtract_months(2024, 6, 3) == (2024, 3)

    def test_cross_year(self):
        """跨年減法"""
        assert _subtract_months(2024, 3, 6) == (2023, 9)
        assert _subtract_months(2024, 1, 1) == (2023, 12)

    def test_zero_months(self):
        """減 0 個月"""
        assert _subtract_months(2024, 12, 0) == (2024, 12)

    def test_multiple_years(self):
        """跨多年減法"""
        assert _subtract_months(2024, 6, 18) == (2022, 12)


# =============================================================================
# List Expense Months Tests
# =============================================================================


class TestListExpenseMonths:
    """支出月份列表測試"""

    def test_empty_directory(self, tmp_path):
        """空目錄回傳空列表"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "canonical" / "expenses").mkdir(parents=True)

        result = list_expense_months(str(data_dir))
        assert result == []

    def test_nonexistent_directory(self, tmp_path):
        """不存在的目錄回傳空列表"""
        result = list_expense_months(str(tmp_path / "nonexistent"))
        assert result == []

    def test_sorted_months(self, tmp_path):
        """月份按時間排序"""
        data_dir = tmp_path / "data"
        expenses_dir = data_dir / "canonical" / "expenses"
        expenses_dir.mkdir(parents=True)

        # 建立測試檔案（順序打亂）
        (expenses_dir / "expenses_2024_12.csv").write_text("date,amount,category\n")
        (expenses_dir / "expenses_2024_01.csv").write_text("date,amount,category\n")
        (expenses_dir / "expenses_2023_06.csv").write_text("date,amount,category\n")

        result = list_expense_months(str(data_dir))
        assert result == [(2023, 6), (2024, 1), (2024, 12)]


# =============================================================================
# Fetch Historical Expenses Tests
# =============================================================================


class TestFetchHistoricalExpenses:
    """歷史支出取得測試"""

    @pytest.fixture
    def setup_expense_files(self, tmp_path):
        """建立測試支出檔案"""
        data_dir = tmp_path / "data"
        expenses_dir = data_dir / "canonical" / "expenses"
        expenses_dir.mkdir(parents=True)

        # 建立 2024 年 6 個月的資料
        for month in range(7, 13):  # 7-12 月
            filepath = expenses_dir / f"expenses_2024_{month:02d}.csv"
            filepath.write_text(
                f"date,amount,category,payer,note,merchant\n"
                f"2024-{month:02d}-15,{month * 100},food,shared,測試,店家{month}\n"
            )

        return data_dir

    def test_fetch_latest_months(self, setup_expense_files):
        """取得最新 N 個月"""
        result = fetch_historical_expenses(
            str(setup_expense_files),
            months_back=3,
        )

        assert len(result) == 3
        # 應該是 10, 11, 12 月
        assert result[0].month == 10
        assert result[-1].month == 12

    def test_fetch_all_available(self, setup_expense_files):
        """取得所有可用資料"""
        result = fetch_historical_expenses(
            str(setup_expense_files),
            months_back=12,  # 超過實際可用數量
        )

        # 只有 6 個月的資料
        assert len(result) == 6
        assert result[0].month == 7
        assert result[-1].month == 12

    def test_fetch_with_end_date(self, setup_expense_files):
        """指定結束月份"""
        result = fetch_historical_expenses(
            str(setup_expense_files),
            months_back=3,
            end_year=2024,
            end_month=10,
        )

        assert len(result) == 3
        # 應該是 8, 9, 10 月
        assert result[0].month == 8
        assert result[-1].month == 10

    def test_empty_result(self, tmp_path):
        """無資料時回傳空列表"""
        data_dir = tmp_path / "empty"
        data_dir.mkdir()
        (data_dir / "canonical" / "expenses").mkdir(parents=True)

        result = fetch_historical_expenses(str(data_dir))
        assert result == []

    def test_expenses_contain_records(self, setup_expense_files):
        """確認載入的資料包含記錄"""
        result = fetch_historical_expenses(
            str(setup_expense_files),
            months_back=1,
        )

        assert len(result) == 1
        assert len(result[0].records) == 1
        assert result[0].records[0].amount == Decimal("1200")  # 12 月 = 1200


# =============================================================================
# Fetch Expense Range Tests
# =============================================================================


class TestFetchExpenseRange:
    """支出範圍取得測試"""

    @pytest.fixture
    def setup_expense_files(self, tmp_path):
        """建立測試支出檔案"""
        data_dir = tmp_path / "data"
        expenses_dir = data_dir / "canonical" / "expenses"
        expenses_dir.mkdir(parents=True)

        # 建立 2024 年 1-6 月的資料
        for month in range(1, 7):
            filepath = expenses_dir / f"expenses_2024_{month:02d}.csv"
            filepath.write_text(
                f"date,amount,category\n"
                f"2024-{month:02d}-15,{month * 1000},food\n"
            )

        return data_dir

    def test_fetch_full_range(self, setup_expense_files):
        """取得指定範圍"""
        result = fetch_expense_range(
            str(setup_expense_files),
            start_year=2024,
            start_month=2,
            end_year=2024,
            end_month=5,
        )

        assert len(result) == 4
        assert result[0].month == 2
        assert result[-1].month == 5

    def test_fetch_default_range(self, setup_expense_files):
        """預設取得所有資料"""
        result = fetch_expense_range(str(setup_expense_files))

        assert len(result) == 6
        assert result[0].month == 1
        assert result[-1].month == 6

    def test_fetch_partial_match(self, setup_expense_files):
        """範圍超出實際資料"""
        result = fetch_expense_range(
            str(setup_expense_files),
            start_year=2023,
            start_month=12,
            end_year=2024,
            end_month=3,
        )

        # 只有 2024/1-3 存在
        assert len(result) == 3
        assert result[0].month == 1
        assert result[-1].month == 3
