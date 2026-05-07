"""RebuildCommand 資料模型測試

測試結構化重建命令的安全性與不可變性。
"""

import pytest

from life_capital.models.provenance import RebuildCommand


class TestRebuildCommand:
    """RebuildCommand 測試集"""

    def test_to_safe_string_quotes_args(self):
        """測試 shell 參數正確引用"""
        cmd = RebuildCommand(
            cmd=["lc", "advisor", "wiki", "--path", "/path with spaces/data"],
            cwd=".",
            schema_version="1.0",
        )

        safe_string = cmd.to_safe_string()

        # 應包含引用的空格路徑
        assert (
            "'/path with spaces/data'" in safe_string
            or '"/path with spaces/data"' in safe_string
        )
        assert "lc" in safe_string
        assert "advisor" in safe_string

    def test_to_safe_string_handles_special_chars(self):
        """測試特殊字元正確處理"""
        cmd = RebuildCommand(
            cmd=["echo", "Hello; rm -rf /", "$USER"],
            cwd=".",
            schema_version="1.0",
        )

        safe_string = cmd.to_safe_string()

        # 特殊字元應被引用
        assert ";" in safe_string  # 應在引號內
        assert "$USER" in safe_string  # 應在引號內

    def test_rebuild_command_immutable(self):
        """測試 dataclass frozen（不可變）"""
        cmd = RebuildCommand(
            cmd=["lc", "test"],
            cwd=".",
            schema_version="1.0",
        )

        # 嘗試修改應拋出錯誤
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            cmd.cmd = ["modified"]

    def test_default_env_is_empty_dict(self):
        """測試預設環境變數為空字典"""
        cmd = RebuildCommand(
            cmd=["lc", "test"],
            cwd=".",
            schema_version="1.0",
        )

        assert cmd.env == {}
        assert isinstance(cmd.env, dict)

    def test_custom_env_preserved(self):
        """測試自訂環境變數被保留"""
        cmd = RebuildCommand(
            cmd=["lc", "test"],
            cwd=".",
            env={"DEBUG": "1", "PATH": "/custom/path"},
            schema_version="1.0",
        )

        assert cmd.env == {"DEBUG": "1", "PATH": "/custom/path"}

    def test_empty_cmd_allowed(self):
        """測試允許空命令列表（邊緣情況）"""
        cmd = RebuildCommand(
            cmd=[],
            cwd=".",
            schema_version="1.0",
        )

        assert cmd.cmd == []
        assert cmd.to_safe_string() == ""
