"""測試 conftest.py fixtures 是否正常工作"""


from life_capital.io.registry import (
    CANONICAL_DIR,
    CANONICAL_EXPENSES_DIR,
    DERIVED_DIR,
    PROPOSALS_DIR,
    RAW_DIR,
)


def test_seed_data_session_structure(seed_data_session):
    """測試 seed_data_session 目錄結構"""
    assert seed_data_session.exists()
    assert (seed_data_session / RAW_DIR).exists()
    assert (seed_data_session / CANONICAL_DIR).exists()
    assert (seed_data_session / CANONICAL_EXPENSES_DIR).exists()


def test_seed_data_dir_isolation(seed_data_dir):
    """測試 seed_data_dir 提供獨立副本"""
    assert seed_data_dir.exists()
    assert (seed_data_dir / "life_assumptions.yaml").exists()

    # 修改檔案不應影響其他測試
    test_file = seed_data_dir / "test_marker.txt"
    test_file.write_text("modified")
    assert test_file.exists()


def test_seed_data_dir_has_7_months(seed_data_dir):
    """測試 seed_data_dir 包含 7 個月資料"""
    expenses_dir = seed_data_dir / CANONICAL_EXPENSES_DIR
    csv_files = list(expenses_dir.glob("expenses_*.csv"))
    assert len(csv_files) == 7  # 2024-06 ~ 2024-12


def test_minimal_data_dir_has_1_month(minimal_data_dir):
    """測試 minimal_data_dir 包含 1 個月資料"""
    expenses_dir = minimal_data_dir / CANONICAL_EXPENSES_DIR
    csv_files = list(expenses_dir.glob("expenses_*.csv"))
    assert len(csv_files) == 1  # 2024-12


def test_empty_data_dir_structure(empty_data_dir):
    """測試 empty_data_dir 只有目錄結構，無資料檔案"""
    assert empty_data_dir.exists()
    assert (empty_data_dir / RAW_DIR).exists()
    assert (empty_data_dir / CANONICAL_DIR).exists()
    assert (empty_data_dir / DERIVED_DIR).exists()
    assert (empty_data_dir / PROPOSALS_DIR).exists()

    # 不應包含任何資料檔案
    assert not (empty_data_dir / "life_assumptions.yaml").exists()


def test_cli_runner_available(cli_runner):
    """測試 cli_runner 可用"""
    assert cli_runner is not None
    # 簡單測試 runner 是否可執行
    from life_capital.cli import app

    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Life Capital" in result.stdout
