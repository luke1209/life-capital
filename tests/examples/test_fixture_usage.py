"""範例：如何使用 conftest.py 提供的 fixtures

這個檔案展示不同測試場景如何使用不同的 fixtures。
"""

from pathlib import Path

from life_capital.io.registry import CANONICAL_DIR, CANONICAL_EXPENSES_DIR


class TestFixtureUsageExamples:
    """測試 fixture 使用範例"""

    def test_with_full_data(self, seed_data_dir: Path):
        """範例：使用完整資料集（7 個月）

        適用於：
        - 需要完整歷史資料的測試
        - 驗證趨勢分析、報表生成等功能
        """
        # seed_data_dir 是獨立副本，可以安全修改
        assert seed_data_dir.exists()

        # 驗證包含 7 個月資料
        expenses_dir = seed_data_dir / CANONICAL_EXPENSES_DIR
        csv_files = list(expenses_dir.glob("expenses_*.csv"))
        assert len(csv_files) == 7

        # 可以安全修改檔案，不影響其他測試
        test_file = seed_data_dir / "test_marker.txt"
        test_file.write_text("modified")

    def test_with_minimal_data(self, minimal_data_dir: Path):
        """範例：使用最小資料集（1 個月）

        適用於：
        - 測試基本功能
        - 不需要完整歷史資料的場景
        - 快速測試（效能考量）
        """
        # minimal_data_dir 只有 1 個月資料（2024-12）
        assert minimal_data_dir.exists()

        expenses_dir = minimal_data_dir / CANONICAL_EXPENSES_DIR
        csv_files = list(expenses_dir.glob("expenses_*.csv"))
        assert len(csv_files) == 1

    def test_with_empty_dir(self, empty_data_dir: Path):
        """範例：使用空目錄結構

        適用於：
        - 測試初始化指令（lc init）
        - 測試資料遷移
        - 測試從零開始建立資料
        """
        # empty_data_dir 只有目錄結構，無資料檔案
        assert empty_data_dir.exists()
        assert (empty_data_dir / CANONICAL_DIR).exists()

        # 不應包含任何資料檔案
        yaml_files = list(empty_data_dir.glob("**/*.yaml"))
        assert len(yaml_files) == 0

    def test_with_cli_runner(self, cli_runner, seed_data_dir: Path):
        """範例：使用 CLI runner 測試指令

        適用於：
        - 測試 CLI 指令執行
        - 驗證指令輸出與退出碼
        """
        from life_capital.cli import app

        # 測試 --help 指令（最簡單的測試）
        result = cli_runner.invoke(app, ["--help"])

        # 驗證執行成功
        assert result.exit_code == 0
        assert "Life Capital" in result.stdout

    def test_session_data_readonly(self, seed_data_session: Path):
        """範例：使用 session 級別唯讀資料

        適用於：
        - 只讀操作（不修改資料）
        - 需要共用資料的測試（效能優化）

        注意：
        - seed_data_session 在所有測試間共用
        - 不應修改這個目錄的內容
        """
        # 只能進行讀取操作
        assert seed_data_session.exists()

        expenses_dir = seed_data_session / CANONICAL_EXPENSES_DIR
        csv_files = list(expenses_dir.glob("expenses_*.csv"))
        assert len(csv_files) == 7

        # ⚠️ 不應該修改 seed_data_session 的內容
        # 如果需要修改，使用 seed_data_dir 替代
