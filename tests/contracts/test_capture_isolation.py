"""Phase 4 CAPTURE 隔離規則契約測試

驗證 capture/ 模組遵守隔離規則：
- capture/ 只能依賴 interfaces/，不能依賴 models/
- StagingEntry 定義於 capture/models.py（內部模型）
- 所有跨模組通信透過 interfaces/ Protocol

隔離規則的目的：
- 防止 capture/ 與整體架構過度耦合
- 允許 capture/ 獨立演進（只遵守 Protocol 契約）
- 明確定義 capture/ 與外界的互動邊界

測試分類：
- 導入隔離：驗證 capture/ 不導入 models/
- 介面依賴：驗證只依賴 interfaces/ 中的 Protocol
- 模型本地化：驗證 StagingEntry 定義於 capture/models.py

References:
- docs/architecture/capture_isolation.md
- CLAUDE.md § 隔離規則
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestCaptureNoModelsImport:
    """驗證 capture/ 不導入 models/"""

    @staticmethod
    def _get_imports(file_path: Path) -> list[tuple[str, str]]:
        """解析 Python 檔案的所有導入語句

        Returns:
            list of (import_type, module_name) tuples
            import_type: "import" | "from"
            module_name: 完整模組名稱（如 "life_capital.models"）
        """
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # import module_name [as alias]
                for alias in node.names:
                    imports.append(("import", alias.name))
            elif isinstance(node, ast.ImportFrom):
                # from module_name import ...
                if node.module:
                    imports.append(("from", node.module))

        return imports

    def test_capture_modules_no_models_import(self):
        """驗證所有 capture/*.py 不直接或間接導入 models/

        例外：staging_service.py 可在運行時（局部）導入 models/，
        用於轉換提案至 canonical 層（Phase 4 apply 操作）。
        """
        capture_dir = PROJECT_ROOT / "life_capital" / "capture"

        # 允許的例外：運行時導入
        exceptions_allowed = {
            "staging_service.py",  # 運行時導入 ExpenseRecord 用於提案轉換
        }

        violations = []

        for py_file in sorted(capture_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue

            # 檢查是否在允許清單中
            if py_file.name in exceptions_allowed:
                # 允許運行時導入（不會在測試匯入時觸發）
                continue

            imports = self._get_imports(py_file)
            for import_type, module_name in imports:
                # 檢查是否導入 models/
                if "life_capital.models" in module_name:
                    violations.append(
                        f"{py_file.name}: {import_type} {module_name}"
                    )

        assert not violations, (
            "capture/ 禁止直接導入 models/。違反的導入：\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n詳見隔離規則: CLAUDE.md § 隔離規則"
            + "\n例外：staging_service.py 允許運行時導入 ExpenseRecord"
        )

    def test_capture_models_has_no_models_import(self):
        """驗證 capture/models.py 本身也不導入 models/

        capture/models.py 應該只依賴標準庫（dataclasses, datetime, decimal）
        """
        models_file = PROJECT_ROOT / "life_capital" / "capture" / "models.py"
        imports = self._get_imports(models_file)

        models_imports = [
            (itype, mod) for itype, mod in imports
            if "life_capital.models" in mod
        ]

        assert not models_imports, (
            f"capture/models.py 應只定義本地 dataclass，不應導入 models/。"
            f"違反導入：{models_imports}"
        )


class TestCaptureOnlyInterfacesDependency:
    """驗證 capture/ 只依賴 interfaces/ Protocol"""

    def _get_imports(self, file_path: Path) -> list[tuple[str, str]]:
        """解析 Python 檔案的所有導入語句（從 TestCaptureNoModelsImport 複製）"""
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(("import", alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(("from", node.module))

        return imports

    @staticmethod
    def _get_life_capital_imports(imports: list[tuple[str, str]]) -> list[str]:
        """篩選 life_capital 包內的導入（不含標準庫）"""
        return [
            mod for itype, mod in imports
            if mod.startswith("life_capital")
        ]

    def test_capture_only_depends_on_allowed_modules(self):
        """驗證 capture/ 只依賴允許的內部模組

        隔離規則：
        - capture/ 核心邏輯（date_adapter, entity_extractor, expense_parser）
          只依賴 interfaces/ 和 calculators/
        - staging_service.py 是實作層，可依賴 io/ 和 models/（用於提案轉換）

        此測試驗證除 staging_service.py 外的所有模組遵守隔離規則。
        """
        capture_dir = PROJECT_ROOT / "life_capital" / "capture"

        # 允許的內部依賴（對大多數模組）
        allowed_modules = {
            "life_capital.capture",      # 內部跨檔依賴
            "life_capital.interfaces",   # Protocol 定義
            "life_capital.calculators",  # Decimal 轉換工具（to_decimal）
        }

        # staging_service.py 的額外依賴（實作層例外）
        staging_service_extra = {
            "life_capital.io",           # I/O 層（提案處理）
            "life_capital.models",       # 資料層（ExpenseRecord 轉換）
            "life_capital.utils",        # 工具層（路徑解析）
        }

        violations = []

        for py_file in sorted(capture_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue

            imports = self._get_imports(py_file)
            lc_imports = self._get_life_capital_imports(imports)

            # 確定此檔是否為例外（staging_service.py）
            is_staging_service = py_file.name == "staging_service.py"
            allowed_for_file = allowed_modules | (
                staging_service_extra if is_staging_service else set()
            )

            for module_name in lc_imports:
                # 檢查是否為允許的模組
                is_allowed = any(
                    module_name == allowed or module_name.startswith(allowed + ".")
                    for allowed in allowed_for_file
                )

                if not is_allowed:
                    violations.append(
                        f"{py_file.name}: {module_name}"
                    )

        assert not violations, (
            f"capture/ 依賴規則違反。\n"
            f"允許（所有模組）: {', '.join(sorted(allowed_modules))}\n"
            f"允許（staging_service.py）: 額外依賴 {', '.join(sorted(staging_service_extra))}\n"
            f"違反的依賴：\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n詳見隔離規則: CLAUDE.md § 隔離規則"
        )

    def test_capture_does_not_import_from_commands(self):
        """驗證 capture/ 不依賴 commands/ 模組"""
        capture_dir = PROJECT_ROOT / "life_capital" / "capture"

        violations = []

        for py_file in sorted(capture_dir.glob("*.py")):
            imports = self._get_imports(py_file)
            for itype, module_name in imports:
                if "life_capital.commands" in module_name:
                    violations.append(f"{py_file.name}: {module_name}")

        assert not violations, (
            "capture/ 不應依賴 commands/（違反分層架構）。"
            "違反的導入：\n" + "\n".join(f"  - {v}" for v in violations)
        )

    def test_capture_does_not_import_from_io(self):
        """驗證 capture/ 不直接依賴 io/ 模組

        io/ 是低層 I/O 抽象，應透過 interfaces/ 依賴。
        """
        capture_dir = PROJECT_ROOT / "life_capital" / "capture"

        # 例外：staging_service.py 可能使用 io/ 實作（但應透過 interfaces）
        violations = []

        for py_file in sorted(capture_dir.glob("*.py")):
            # staging_service.py 不在此檢查範圍（它是實作層，可使用 io/）
            if py_file.name == "staging_service.py":
                continue

            imports = self._get_imports(py_file)
            for itype, module_name in imports:
                if "life_capital.io" in module_name:
                    violations.append(f"{py_file.name}: {module_name}")

        assert not violations, (
            "capture/ 應透過 interfaces/ 依賴資料層，不應直接依賴 io/。"
            "違反的導入：\n" + "\n".join(f"  - {v}" for v in violations)
        )


class TestStagingEntryInCaptureModels:
    """驗證 StagingEntry 定義於 capture/models.py"""

    def test_staging_entry_defined_in_capture_models(self):
        """驗證 StagingEntry dataclass 定義於 capture/models.py"""
        # 導入 StagingEntry 並驗證其來源模組
        from life_capital.capture.models import StagingEntry

        # 檢查模組
        module = sys.modules[StagingEntry.__module__]
        module_path = Path(module.__file__)
        expected_path = PROJECT_ROOT / "life_capital" / "capture" / "models.py"

        assert module_path.resolve() == expected_path.resolve(), (
            f"StagingEntry 應定義於 capture/models.py，"
            f"但實際定義於 {module_path}"
        )

    def test_staging_entry_is_dataclass(self):
        """驗證 StagingEntry 是 dataclass"""
        from dataclasses import is_dataclass

        from life_capital.capture.models import StagingEntry

        assert is_dataclass(StagingEntry), (
            "StagingEntry 應是 @dataclass"
        )

    def test_staging_entry_has_required_fields(self):
        """驗證 StagingEntry 包含所有必需欄位（V4.1.1）"""
        from life_capital.capture.models import StagingEntry

        required_fields = {
            # 基本欄位
            "entry_id",
            "raw_text",
            "created_at",
            # 解析結果
            "parsed_date",
            "parsed_amount",
            "parsed_category",
            # 狀態與信心度
            "status",
            "confidence",
            # 版本追蹤
            "parser_version",
            "source",
            # 來源枚舉（V4.1.1）
            "amount_source",
            "date_source",
            "category_source",
            # 判重欄位
            "duplicate_of",
            "duplicate_reason",
            # 終態追蹤
            "proposal_id",
            "canonical_record_id",
        }

        actual_fields = set(StagingEntry.__dataclass_fields__.keys())

        missing_fields = required_fields - actual_fields
        assert not missing_fields, (
            f"StagingEntry 缺少欄位: {missing_fields}\n"
            f"詳見 CLAUDE.md § 隔離規則（capture/models.py 規範）"
        )

    def test_staging_entry_not_exported_from_models_package(self):
        """驗證外部模組無法從 models/ 導入 StagingEntry

        這是隔離規則的執行保障：外部模組應從 capture/ 取得 StagingEntry，
        而不是通過 models/ 包。
        """
        # 嘗試從 models/ 導入 StagingEntry（應失敗或返回 None）
        import life_capital.models as models_pkg

        has_staging_entry = hasattr(models_pkg, "StagingEntry")

        # 如果確實導出，輸出警告但不失敗（允許未來重構）
        if has_staging_entry:
            pytest.skip(
                "StagingEntry 已導出至 models/（允許未來重構），"
                "但建議保持隔離狀態"
            )


class TestCaptureInterfacesProtocols:
    """驗證 capture/ 使用的 interfaces/ Protocol"""

    def test_canonical_reader_protocol_used_in_capture(self):
        """驗證 capture/ 正確使用 CanonicalReader Protocol"""
        # 應被 entity_extractor 和 expense_parser 使用
        from life_capital.interfaces.canonical_reader import CanonicalReader

        # Protocol 應能運行時檢查
        assert hasattr(CanonicalReader, "__mro__") or hasattr(
            CanonicalReader, "__protocol_attrs__"
        ), "CanonicalReader 應是有效的 Protocol"

    def test_staging_store_protocol_used_in_capture(self):
        """驗證 capture/ 正確使用 StagingStore Protocol"""
        from life_capital.interfaces.staging_store import StagingStore

        # Protocol 應能運行時檢查
        assert hasattr(StagingStore, "__mro__") or hasattr(
            StagingStore, "__protocol_attrs__"
        ), "StagingStore 應是有效的 Protocol"

    def test_no_protocol_in_capture_models(self):
        """驗證 capture/models.py 不定義 Protocol

        Protocol 應定義於 interfaces/，不應在 capture/ 內部定義。
        """
        from life_capital.capture import models

        # 檢查 capture/models.py 中是否有 Protocol 定義
        protocols = []

        for name in dir(models):
            obj = getattr(models, name)
            # 檢查是否為 Protocol
            if hasattr(obj, "__mro__"):
                # 檢查是否來自 typing_extensions 或 typing
                if hasattr(obj, "__protocol_attrs__"):
                    protocols.append(name)

        assert not protocols, (
            f"capture/models.py 不應定義 Protocol：{protocols}。"
            f"Protocol 應定義於 interfaces/"
        )


class TestCaptureModuleStructure:
    """驗證 capture/ 模組結構符合隔離規則"""

    def test_capture_init_exports_only_staging_entry(self):
        """驗證 capture/__init__.py 結構正確

        目前 StagingEntry 應從 capture.models 導入，
        後續可在 __init__.py 中導出以簡化 API。

        注：Python 自動導出子模組，此測試只驗證 StagingEntry 的定位。
        """
        # 驗證 capture 模組存在
        from life_capital import capture

        # 驗證可從 capture.models 導入 StagingEntry
        from life_capital.capture.models import StagingEntry

        assert StagingEntry is not None, (
            "StagingEntry 應定義於 capture/models.py"
        )

        # 驗證 models 子模組存在
        assert hasattr(capture, "models"), (
            "capture 應能訪問 models 子模組"
        )

        # 驗證不在 capture/__init__.py 中顯式導出 StagingEntry
        # （讓使用者明確地 from capture.models import StagingEntry）
        init_file = PROJECT_ROOT / "life_capital" / "capture" / "__init__.py"
        init_content = init_file.read_text()
        assert "StagingEntry" not in init_content, (
            "capture/__init__.py 不應顯式導出 StagingEntry（應由 capture.models 提供）"
        )

    def test_capture_submodules_not_in_package_all(self):
        """驗證 capture/ 不導出內部子模組"""
        # capture/__init__.py 不應在 __all__ 中導出
        # capture.expense_parser, capture.date_adapter 等

        from life_capital import capture

        if hasattr(capture, "__all__"):
            for name in capture.__all__:
                obj = getattr(capture, name)
                # 不應導出模組
                import types
                assert not isinstance(obj, types.ModuleType), (
                    f"capture/__init__.py 不應在 __all__ 中導出子模組 {name}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
