"""Pytest 全域 Fixtures

提供測試用的資料目錄與 CLI runner，遵守 CLAUDE.md 護欄規則。

Fixtures:
    - seed_data_session: Session 級別唯讀資料（所有測試共用）
    - seed_data_dir: Function 級別完整資料副本（每個測試獨立）
    - minimal_data_dir: 最小資料集（1 個月）
    - empty_data_dir: 空目錄結構（測試 lc init）
    - cli_runner: Typer CLI runner
    - freeze_base_year: 凍結 datetime.now() 為指定年份（年齡動態計算測試用）
"""

import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

import pytest
from typer.testing import CliRunner

from life_capital.io.registry import (
    CANONICAL_DIR,
    DERIVED_DIR,
    PROPOSALS_DIR,
    RAW_DIR,
)
from tests.fixtures.seed_data import SeedDataBuilder

# === Session 級別 Fixtures (所有測試共用) ===


@pytest.fixture(scope="session")
def seed_data_session(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session 級別的完整 seed 資料（所有測試共用，唯讀）

    Args:
        tmp_path_factory: pytest 提供的 session 級別臨時目錄工廠

    Returns:
        包含完整 7 個月資料的目錄路徑
    """
    base_dir = tmp_path_factory.mktemp("seed_data_session")
    builder = SeedDataBuilder(base_dir=base_dir)
    return builder.build_full()  # 7 個月資料：2024-06 ~ 2024-12


# === Function 級別 Fixtures (每個測試獨立) ===


@pytest.fixture
def seed_data_dir(tmp_path: Path, seed_data_session: Path) -> Path:
    """Function 級別的完整資料副本（每個測試獨立）

    從 seed_data_session 複製資料，確保測試隔離。

    Args:
        tmp_path: pytest 提供的 function 級別臨時目錄
        seed_data_session: Session 級別唯讀資料

    Returns:
        包含完整 7 個月資料的獨立副本
    """
    data_dir = tmp_path / "data"
    shutil.copytree(seed_data_session, data_dir)
    return data_dir


@pytest.fixture
def minimal_data_dir(tmp_path: Path) -> Path:
    """最小資料集（1 個月：2024-12）

    適用於測試基本功能，不需完整歷史資料的場景。

    Args:
        tmp_path: pytest 提供的臨時目錄

    Returns:
        包含 1 個月資料的目錄路徑
    """
    base_dir = tmp_path / "minimal_data"
    builder = SeedDataBuilder(base_dir=base_dir)
    return builder.build_minimal()


@pytest.fixture
def empty_data_dir(tmp_path: Path) -> Path:
    """空目錄結構（僅建立三層目錄，無資料檔案）

    適用於測試 lc init、資料遷移等初始化場景。

    目錄結構:
        raw/
        canonical/
        derived/
        proposals/

    Args:
        tmp_path: pytest 提供的臨時目錄

    Returns:
        空的資料目錄路徑
    """
    base_dir = tmp_path / "empty_data"
    base_dir.mkdir(parents=True, exist_ok=True)

    # 建立三層目錄結構
    (base_dir / RAW_DIR).mkdir(exist_ok=True)
    (base_dir / CANONICAL_DIR).mkdir(exist_ok=True)
    (base_dir / DERIVED_DIR).mkdir(exist_ok=True)
    (base_dir / PROPOSALS_DIR).mkdir(exist_ok=True)

    return base_dir


# === CLI Runner Fixtures ===


@pytest.fixture
def cli_runner() -> CliRunner:
    """Typer CLI runner

    用於測試 CLI 指令的執行結果。

    Returns:
        CliRunner 實例
    """
    return CliRunner()


# === 時間凍結 Fixtures (年齡動態計算測試用) ===


class FrozenDateTime:
    """凍結的 datetime，只覆寫 now()"""

    def __init__(self, frozen_year: int):
        self.frozen_year = frozen_year
        self._original_datetime = datetime

    def now(self, tz=None):
        """返回凍結年份的固定時間（6 月 15 日避免邊界問題）"""
        return self._original_datetime(self.frozen_year, 6, 15, 12, 0, 0)

    def today(self):
        """返回凍結年份的固定日期"""
        return self.now().date()

    def __getattr__(self, name):
        """其他 datetime 屬性轉發至原始 datetime"""
        return getattr(self._original_datetime, name)

    def __call__(self, *args, **kwargs):
        """支援 datetime(...) 建構呼叫"""
        return self._original_datetime(*args, **kwargs)


@pytest.fixture
def freeze_base_year(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], int]:
    """凍結 datetime.now() 為指定年份

    凍結以下模組的 datetime：
        - life_capital.models.assumptions (Metadata.base_year 預設值)
        - tests.fixtures.factory (make_life_assumptions 預設值)

    Args:
        monkeypatch: pytest monkeypatch fixture (自動清理)

    Returns:
        凍結函式，呼叫 freeze(year) 後返回該年份

    使用範例:
        >>> def test_age_2024(freeze_base_year):
        ...     year = freeze_base_year(2024)
        ...     assumptions = make_life_assumptions()
        ...     assert assumptions.metadata.base_year == 2024
        ...     assert assumptions.get_current_age() == 2024 - 1981  # 43
    """
    modules_to_patch = [
        "life_capital.models.assumptions",
        "tests.fixtures.factory",
    ]

    def _freeze(year: int) -> int:
        """凍結 datetime.now() 為指定年份"""
        frozen = FrozenDateTime(year)
        for module_path in modules_to_patch:
            monkeypatch.setattr(f"{module_path}.datetime", frozen)
        return year

    return _freeze
