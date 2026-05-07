"""Phase 4 CAPTURE - capture 指令測試"""


import pytest
from typer.testing import CliRunner

from life_capital.cli import app
from life_capital.io.staging_store import StagingStoreImpl


@pytest.fixture
def runner():
    """CLI runner"""
    return CliRunner()


@pytest.fixture
def init_data_dir(tmp_path):
    """初始化資料目錄結構"""
    # 建立必要的目錄結構
    (tmp_path / "staging").mkdir(parents=True, exist_ok=True)
    (tmp_path / "canonical" / "expenses").mkdir(parents=True, exist_ok=True)
    (tmp_path / "canonical" / "config").mkdir(parents=True, exist_ok=True)

    # 建立最小 config.yaml（供 CanonicalReaderImpl 使用）
    config_file = tmp_path / "canonical" / "config" / "config.yaml"
    config_file.write_text(
        """schema_version: "1.1"
expense_policy:
  食物:
    monthly_limit: 20000
    items: ["餐費", "食材"]
  交通:
    monthly_limit: 3000
    items: ["捷運", "公車"]
  購物:
    monthly_limit: 5000
    items: ["服飾", "日用品"]
rates:
  mode: "real"
  nominal_investment_return: "0.07"
  real_investment_return: "0.04"
  inflation: "0.03"
monthly_income: "50000"
""",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def batch_file(tmp_path):
    """建立批次匯入測試檔案"""
    file_path = tmp_path / "batch_expenses.txt"
    file_path.write_text(
        """昨天吃了 320 元拉麵
12/25 聖誕禮物 1500
捷運加值 500 交通
""",
        encoding="utf-8",
    )
    return file_path


class TestCaptureCommand:
    """測試 lc capture 指令"""

    def test_capture_single_text(self, runner, init_data_dir):
        """測試單筆文字捕捉"""
        result = runner.invoke(
            app,
            [
                "capture",
                "昨天吃了 320 元拉麵",
                "--path",
                str(init_data_dir),
            ],
        )

        # 驗證成功
        assert result.exit_code == 0
        assert "✅ 已加入 staging" in result.stdout
        assert "Entry ID:" in result.stdout
        assert "昨天吃了 320 元拉麵" in result.stdout
        assert "status: pending" in result.stdout

        # 驗證檔案已建立
        store = StagingStoreImpl(init_data_dir)
        entries = store.read_entries()
        assert len(entries) == 1
        assert entries[0].raw_text == "昨天吃了 320 元拉麵"

    def test_capture_batch_file(self, runner, init_data_dir, batch_file):
        """測試批次檔案匯入"""
        result = runner.invoke(
            app,
            [
                "capture",
                "--batch",
                str(batch_file),
                "--path",
                str(init_data_dir),
            ],
        )

        # 驗證成功
        assert result.exit_code == 0
        assert "✅ 批次匯入完成" in result.stdout
        assert "成功: 3/3 筆" in result.stdout
        assert f"Batch ID: batch_{batch_file.stem}" in result.stdout

        # 驗證檔案已建立
        store = StagingStoreImpl(init_data_dir)
        entries = store.read_entries()
        assert len(entries) == 3

        # 驗證 batch_id
        for entry in entries:
            assert entry.batch_id == f"batch_{batch_file.stem}"

    def test_capture_custom_source(self, runner, init_data_dir):
        """測試自訂來源標記"""
        result = runner.invoke(
            app,
            [
                "capture",
                "捷運加值 500",
                "--source",
                "api",
                "--path",
                str(init_data_dir),
            ],
        )

        assert result.exit_code == 0
        assert "✅ 已加入 staging" in result.stdout

        # 驗證 source
        store = StagingStoreImpl(init_data_dir)
        entries = store.read_entries()
        assert entries[0].source == "api"

    def test_capture_no_arguments_error(self, runner, init_data_dir):
        """測試未提供參數的錯誤"""
        result = runner.invoke(
            app,
            [
                "capture",
                "--path",
                str(init_data_dir),
            ],
        )

        assert result.exit_code == 1
        assert "錯誤: 必須提供 TEXT 或 --batch 參數" in result.stdout

    def test_capture_both_text_and_batch_error(self, runner, init_data_dir, batch_file):
        """測試同時提供 TEXT 與 --batch 的錯誤"""
        result = runner.invoke(
            app,
            [
                "capture",
                "測試文字",
                "--batch",
                str(batch_file),
                "--path",
                str(init_data_dir),
            ],
        )

        assert result.exit_code == 1
        assert "錯誤: TEXT 與 --batch 不可同時使用" in result.stdout

    def test_capture_batch_file_not_found(self, runner, init_data_dir):
        """測試批次檔案不存在的錯誤"""
        result = runner.invoke(
            app,
            [
                "capture",
                "--batch",
                "nonexistent.txt",
                "--path",
                str(init_data_dir),
            ],
        )

        assert result.exit_code == 1
        assert "錯誤: 檔案不存在" in result.stdout

    def test_capture_batch_empty_file(self, runner, init_data_dir, tmp_path):
        """測試空白批次檔案"""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "capture",
                "--batch",
                str(empty_file),
                "--path",
                str(init_data_dir),
            ],
        )

        # 應該顯示警告但不失敗
        assert result.exit_code == 0
        assert "警告: 檔案為空" in result.stdout

    def test_capture_batch_with_partial_failures(self, runner, init_data_dir, tmp_path):
        """測試批次匯入部分失敗的情況"""
        # 建立包含空行的批次檔案
        partial_file = tmp_path / "partial.txt"
        partial_file.write_text(
            """昨天吃了 320 元拉麵

捷運加值 500 交通
""",
            encoding="utf-8",
        )

        result = runner.invoke(
            app,
            [
                "capture",
                "--batch",
                str(partial_file),
                "--path",
                str(init_data_dir),
            ],
        )

        # 應該成功（空行會被 strip 過濾）
        assert result.exit_code == 0
        assert "✅ 批次匯入完成" in result.stdout

        # 驗證只有 2 筆（空行被過濾）
        store = StagingStoreImpl(init_data_dir)
        entries = store.read_entries()
        assert len(entries) == 2

    def test_capture_multiple_sequential_calls(self, runner, init_data_dir):
        """測試連續多次捕捉"""
        # 第 1 次捕捉
        result1 = runner.invoke(
            app,
            [
                "capture",
                "早餐 100",
                "--path",
                str(init_data_dir),
            ],
        )
        assert result1.exit_code == 0

        # 第 2 次捕捉
        result2 = runner.invoke(
            app,
            [
                "capture",
                "午餐 150",
                "--path",
                str(init_data_dir),
            ],
        )
        assert result2.exit_code == 0

        # 驗證兩筆都存在
        store = StagingStoreImpl(init_data_dir)
        entries = store.read_entries()
        assert len(entries) == 2
        texts = {e.raw_text for e in entries}
        assert texts == {"早餐 100", "午餐 150"}
