"""import 指令測試"""

import csv

import pytest
from typer.testing import CliRunner

from life_capital.cli import app
from life_capital.io.raw_handler import list_raw_files


@pytest.fixture
def runner():
    """CLI runner"""
    return CliRunner()


@pytest.fixture
def sample_csv(tmp_path):
    """建立範例 CSV 檔案"""
    csv_file = tmp_path / "test_expenses.csv"

    with open(csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "amount", "category", "note", "merchant"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "date": "2024-12-01",
                "amount": "1000",
                "category": "食物",
                "note": "午餐",
                "merchant": "餐廳A",
            }
        )
        writer.writerow(
            {
                "date": "2024-12-02",
                "amount": "500",
                "category": "交通",
                "note": "",
                "merchant": "",
            }
        )
        # 重複記錄（用於測試去重）
        writer.writerow(
            {
                "date": "2024-12-01",
                "amount": "1000",
                "category": "食物",
                "note": "午餐",
                "merchant": "餐廳A",
            }
        )

    return csv_file


class TestImportCommand:
    """測試 lc import 指令"""

    def test_import_csv_basic(self, runner, sample_csv, tmp_path):
        """測試基本匯入功能"""
        # 使用臨時資料目錄
        result = runner.invoke(
            app,
            [
                "import",
                str(sample_csv),
                "--data-dir",
                str(tmp_path),
            ],
        )

        # 驗證指令成功
        assert result.exit_code == 0

        # 驗證輸出訊息
        assert "匯入成功" in result.stdout
        assert "2 筆記錄" in result.stdout  # 扣除重複的 1 筆
        assert "跳過重複: 1" in result.stdout

        # 驗證檔案已寫入 raw/imports/
        raw_files = list_raw_files("imports", base_dir=tmp_path)
        assert len(raw_files) == 1

        # 驗證檔案為 read-only
        raw_file = raw_files[0]
        assert raw_file.exists()
        assert not raw_file.stat().st_mode & 0o200  # 寫入權限應為關閉

    def test_import_csv_with_key_dedupe(self, runner, sample_csv, tmp_path):
        """測試使用 key-based 去重"""
        result = runner.invoke(
            app,
            [
                "import",
                str(sample_csv),
                "--dedupe",
                "key",
                "--data-dir",
                str(tmp_path),
            ],
        )

        assert result.exit_code == 0
        assert "去重模式: key" in result.stdout

    def test_import_csv_file_not_found(self, runner, tmp_path):
        """測試檔案不存在的錯誤處理"""
        result = runner.invoke(
            app,
            [
                "import",
                "nonexistent.csv",
                "--data-dir",
                str(tmp_path),
            ],
        )

        assert result.exit_code == 1
        assert "檔案不存在" in result.stdout

    def test_import_csv_custom_parser_version(self, runner, sample_csv, tmp_path):
        """測試自定義 parser-version"""
        result = runner.invoke(
            app,
            [
                "import",
                str(sample_csv),
                "--parser-version",
                "1.1",
                "--data-dir",
                str(tmp_path),
            ],
        )

        assert result.exit_code == 0
        assert "匯入成功" in result.stdout

    def test_import_csv_empty_after_dedupe(self, runner, tmp_path):
        """測試去重後沒有資料的情況"""
        # 建立只有重複記錄的 CSV
        csv_file = tmp_path / "duplicates.csv"

        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["date", "amount", "category", "note", "merchant"]
            )
            writer.writeheader()
            # 同樣的記錄寫兩次
            for _ in range(2):
                writer.writerow(
                    {
                        "date": "2024-12-01",
                        "amount": "1000",
                        "category": "食物",
                        "note": "午餐",
                        "merchant": "餐廳A",
                    }
                )

        result = runner.invoke(
            app,
            [
                "import",
                str(csv_file),
                "--data-dir",
                str(tmp_path),
            ],
        )

        # 應該只匯入 1 筆（第 1 筆），第 2 筆被去重
        assert result.exit_code == 0
        assert "1 筆記錄" in result.stdout
