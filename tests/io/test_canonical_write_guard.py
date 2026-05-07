"""測試 canonical/ 寫入防線

Phase 1 V4.1: 掃描程式碼確保沒有繞過 canonical_handler 的直接寫入。

此測試作為護欄，防止開發者不小心繞過 canonical_handler 直接寫入。
"""

import re
from pathlib import Path

import pytest

# 專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent.parent


def get_python_files() -> list[Path]:
    """取得所有 Python 原始碼檔案（排除測試與虛擬環境）"""
    source_dir = PROJECT_ROOT / "life_capital"
    return list(source_dir.rglob("*.py"))


def get_file_content(file_path: Path) -> str:
    """讀取檔案內容"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


# === 禁止的模式 ===
FORBIDDEN_PATTERNS = [
    # 直接 open() 寫入 canonical/
    (
        r'open\s*\([^)]*["\'].*canonical.*["\'][^)]*["\']w',
        "禁止直接 open() 寫入 canonical/",
    ),
    # Path.write_text() 寫入 canonical/
    (
        r'Path\s*\([^)]*["\'].*canonical.*["\']\s*\)\.write_text',
        "禁止 Path().write_text() 寫入 canonical/",
    ),
    (
        r'Path\s*\([^)]*["\'].*canonical.*["\']\s*\)\.write_bytes',
        "禁止 Path().write_bytes() 寫入 canonical/",
    ),
    # 變數形式的 open 寫入（更寬鬆的匹配）
    (
        r'open\s*\([^)]+,\s*["\']w["\']',
        "可能繞過 canonical_handler 的 open() 寫入（需人工審查）",
    ),
]

# 允許的白名單（這些檔案可以合法地直接寫入）
WHITELIST_FILES = {
    "canonical_handler.py",  # 唯一入口，允許直接 open
    "yaml_handler.py",  # 底層 YAML 工具，被 canonical_handler 調用
}


class TestCanonicalWriteGuard:
    """Canonical 寫入防線測試"""

    def test_no_direct_canonical_write(self):
        """確保沒有繞過 canonical_handler 的直接寫入"""
        violations: list[tuple[Path, str, str]] = []

        for file_path in get_python_files():
            # 跳過白名單
            if file_path.name in WHITELIST_FILES:
                continue

            content = get_file_content(file_path)

            # 檢查每個禁止的模式
            for pattern, description in FORBIDDEN_PATTERNS[:3]:  # 只檢查前三個（canonical 專用）
                if re.search(pattern, content, re.IGNORECASE):
                    violations.append((file_path, pattern, description))

        if violations:
            msg = "偵測到可能繞過 canonical_handler 的直接寫入:\n"
            for file_path, pattern, desc in violations:
                rel_path = file_path.relative_to(PROJECT_ROOT)
                msg += f"  - {rel_path}: {desc}\n"
            pytest.fail(msg)

    def test_canonical_handler_has_all_guard(self):
        """確保 canonical_handler.py 有 __all__ 定義"""
        handler_path = PROJECT_ROOT / "life_capital" / "io" / "canonical_handler.py"

        if not handler_path.exists():
            pytest.fail("canonical_handler.py 不存在")

        content = get_file_content(handler_path)

        # 檢查 __all__ 是否存在
        if "__all__" not in content:
            pytest.fail("canonical_handler.py 應該定義 __all__ 來限制暴露的 API")

        # 檢查 __all__ 包含必要的函式
        required_exports = [
            "read_canonical",
            "write_canonical",
            "append_operation_log",
        ]

        for export in required_exports:
            if f'"{export}"' not in content and f"'{export}'" not in content:
                pytest.fail(f"canonical_handler.py __all__ 應該包含 '{export}'")

    def test_canonical_handler_api_exposed(self):
        """測試 canonical_handler 暴露的 API 是否完整"""
        from life_capital.io import canonical_handler

        # 檢查 __all__ 屬性
        assert hasattr(canonical_handler, "__all__"), "__all__ 應該被定義"

        # 驗證 __all__ 中的項目都存在
        for name in canonical_handler.__all__:
            assert hasattr(canonical_handler, name), f"{name} 應該存在於 canonical_handler"

        # 驗證核心函式都在 __all__ 中
        required = ["read_canonical", "write_canonical", "append_operation_log"]
        for name in required:
            assert name in canonical_handler.__all__, f"{name} 應該在 __all__ 中"

    def test_no_raw_open_in_commands(self):
        """確保 commands/ 模組沒有直接 open() 寫入

        注意：apply_cmd.py 和 undo_cmd.py 目前有遺留的直接寫入，
        將在 Phase 1.3 中遷移到使用 canonical_handler。
        """
        commands_dir = PROJECT_ROOT / "life_capital" / "commands"

        if not commands_dir.exists():
            pytest.skip("commands/ 目錄不存在")

        # Phase 1.3 待遷移的檔案（暫時白名單）
        # TODO: Phase 1.3 完成後移除此白名單
        legacy_whitelist = {
            "apply_cmd.py",  # Phase 1.3 遷移
            "undo_cmd.py",  # Phase 1.3 遷移
        }

        # 允許寫入 derived/ 的檔案（CLAUDE.md: commands/ 可直接寫入 derived/）
        derived_writers_whitelist = {
            "project_cmd.py",  # 寫入 derived/scenarios/projection_baseline.json
            "scenario_cmd.py",  # 寫入 derived/scenarios/comparison.json
        }

        violations: list[tuple[Path, str]] = []

        for file_path in commands_dir.rglob("*.py"):
            # 跳過白名單
            if file_path.name in legacy_whitelist:
                continue
            if file_path.name in derived_writers_whitelist:
                continue

            content = get_file_content(file_path)

            # 檢查寫入模式的 open（排除讀取）
            # 匹配 open(..., "w"), open(..., "a"), open(..., 'w'), etc.
            write_pattern = r'open\s*\([^)]+,\s*["\'][wa]'

            if re.search(write_pattern, content):
                violations.append((file_path, "發現直接 open() 寫入"))

        if violations:
            msg = "commands/ 模組應該使用 canonical_handler 而非直接 open():\n"
            for file_path, desc in violations:
                rel_path = file_path.relative_to(PROJECT_ROOT)
                msg += f"  - {rel_path}: {desc}\n"
            pytest.fail(msg)


class TestRawManifestGuard:
    """Raw Manifest 防線測試"""

    def test_raw_handler_has_manifest_functions(self):
        """確保 raw_handler.py 有 manifest 相關函式"""
        from life_capital.io import raw_handler

        required_functions = [
            "generate_raw_manifest",
            "save_raw_manifest",
            "load_raw_manifest",
            "verify_raw_manifest",
        ]

        for func_name in required_functions:
            assert hasattr(raw_handler, func_name), f"raw_handler 應該有 {func_name}"

    def test_raw_manifest_file_defined_in_registry(self):
        """確保 RAW_MANIFEST_FILE 在 registry 中定義"""
        from life_capital.io.registry import RAW_MANIFEST_FILE

        assert RAW_MANIFEST_FILE == "raw/raw_manifest.json"


class TestDedupeConstantsGuard:
    """Dedupe 常數防線測試"""

    def test_dedupe_thresholds_defined(self):
        """確保去重閾值在 registry 中定義"""
        from life_capital.io.registry import (
            AUTO_MERGE_THRESHOLD,
            MANUAL_REVIEW_THRESHOLD,
            WINDOW_OCCURRED_DAYS,
            WINDOW_POSTED_DAYS,
        )

        # 驗證閾值範圍
        assert 0 < AUTO_MERGE_THRESHOLD <= 1.0
        assert 0 < MANUAL_REVIEW_THRESHOLD < AUTO_MERGE_THRESHOLD
        assert WINDOW_OCCURRED_DAYS > 0
        assert WINDOW_POSTED_DAYS > 0

    def test_dedupe_key_versions_defined(self):
        """確保去重版本在 registry 中定義"""
        from life_capital.io.registry import (
            ALLOWED_DEDUPE_KEY_VERSIONS,
            DEFAULT_DEDUPE_KEY_VERSION,
        )

        # 驗證版本集合
        assert isinstance(ALLOWED_DEDUPE_KEY_VERSIONS, set)
        assert len(ALLOWED_DEDUPE_KEY_VERSIONS) > 0
        assert DEFAULT_DEDUPE_KEY_VERSION in ALLOWED_DEDUPE_KEY_VERSIONS

    def test_transaction_has_dedupe_key_version(self):
        """確保 Transaction 模型有 dedupe_key_version 欄位"""
        from datetime import date
        from decimal import Decimal

        from life_capital.models.transaction import Transaction

        # 建立測試 Transaction
        t = Transaction(
            occurred_at=date(2024, 12, 1),
            amount=Decimal("100"),
            category="food",
        )

        # 驗證欄位存在且有預設值
        assert hasattr(t, "dedupe_key_version")
        assert t.dedupe_key_version is not None


class TestOperationTypeGuard:
    """OperationType 防線測試"""

    def test_phase1_operation_types_exist(self):
        """確保 Phase 1 新增的操作類型存在"""
        from life_capital.models.operation import OperationType

        # 驗證 Phase 1 新增的操作類型
        assert hasattr(OperationType, "DEDUPE_MERGE")
        assert hasattr(OperationType, "DEDUPE_REVERSAL")
        assert hasattr(OperationType, "MIGRATE")

        # 驗證值
        assert OperationType.DEDUPE_MERGE.value == "dedupe_merge"
        assert OperationType.DEDUPE_REVERSAL.value == "dedupe_reversal"
        assert OperationType.MIGRATE.value == "migrate"
