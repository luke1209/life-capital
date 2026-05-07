"""AdvisorDerivedHandler 測試

測試路徑安全驗證與原子寫入功能。
"""

from datetime import datetime
from pathlib import Path

import pytest

from life_capital.io.advisor_derived_handler import AdvisorDerivedHandler
from life_capital.io.errors import PathSecurityError
from life_capital.models.provenance import (
    AdvisorDerivedProvenance,
    RebuildCommand,
)


@pytest.fixture
def temp_data_dir(tmp_path):
    """建立臨時資料目錄"""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()
    (data_dir / "derived" / "advisor").mkdir(parents=True)
    return data_dir


@pytest.fixture
def handler(temp_data_dir):
    """建立 handler 實例"""
    return AdvisorDerivedHandler(data_path=temp_data_dir)


@pytest.fixture
def sample_provenance():
    """建立範例 provenance"""
    return AdvisorDerivedProvenance(
        artifact_type="decision_wiki",
        schema_version="1.0",
        calc_version="wiki_v1.0",
        canonicalization_version="1.0",
        input_hash="a" * 64,  # 64 字元 hash
        canonical_sources=["canonical/decisions/decisions.yaml"],
        generated_at=datetime.now().isoformat(),
        rebuild_command=RebuildCommand(
            cmd=["lc", "advisor", "wiki", "--force"],
            cwd=".",
            schema_version="1.0",
        ),
        content_hash="b" * 64,  # 64 字元 hash
        redaction_profile_version="1.0",
    )


class TestPathValidation:
    """路徑安全驗證測試"""

    def test_path_traversal_blocked(self, handler):
        """測試 ../ 攻擊被阻擋"""
        malicious_path = Path("derived/advisor/../../secrets.txt")

        with pytest.raises(PathSecurityError) as exc_info:
            handler._validate_path(malicious_path)

        assert "路徑超出允許範圍" in str(exc_info.value)

    def test_absolute_path_outside_base_blocked(self, handler):
        """測試絕對路徑超出範圍被阻擋"""
        malicious_path = Path("/tmp/evil.md")

        with pytest.raises(PathSecurityError) as exc_info:
            handler._validate_path(malicious_path)

        assert "路徑超出允許範圍" in str(exc_info.value)

    def test_allowed_extensions_only(self, handler):
        """測試只允許白名單副檔名"""
        disallowed_extensions = [".sh", ".exe", ".py", ".bat"]

        for ext in disallowed_extensions:
            malicious_path = Path(f"derived/advisor/script{ext}")

            with pytest.raises(PathSecurityError) as exc_info:
                handler._validate_path(malicious_path)

            assert "不允許的副檔名" in str(exc_info.value)

    def test_space_prefix_blocked(self, handler):
        """測試空格開頭的路徑成分被阻擋"""
        # 建立實際路徑以通過 resolve()
        malicious_path = Path("derived/advisor/ hidden.md")

        with pytest.raises(PathSecurityError) as exc_info:
            handler._validate_path(malicious_path)

        assert "路徑成分不可以空格開頭" in str(exc_info.value)

    def test_allowed_path_passes(self, handler, temp_data_dir):
        """測試允許的路徑通過驗證"""
        valid_path = Path("derived/advisor/test_wiki.md")
        validated = handler._validate_path(valid_path)

        # 應返回絕對路徑
        assert validated.is_absolute()
        assert validated.suffix == ".md"
        assert str(validated).startswith(str(temp_data_dir))


class TestWriteWithProvenance:
    """原子寫入測試"""

    def test_write_markdown_with_provenance(
        self, handler, sample_provenance, temp_data_dir
    ):
        """測試 Markdown 寫入 + provenance sidecar"""
        content = "# Decision Wiki\n\nTest content"

        content_path, meta_path = handler.write_with_provenance(
            artifact_type="decision_wiki",
            content=content,
            provenance=sample_provenance,
            format="md",
        )

        # 驗證檔案存在
        assert content_path.exists()
        assert meta_path.exists()

        # 驗證內容
        assert content_path.read_text(encoding="utf-8") == content

        # 驗證 provenance
        import json

        meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta_data["artifact_type"] == "decision_wiki"
        assert meta_data["schema_version"] == "1.0"

    def test_write_json_with_provenance(
        self, handler, sample_provenance, temp_data_dir
    ):
        """測試 JSON 寫入 + provenance sidecar"""
        # 修改 provenance 為 risk_matrix
        provenance = AdvisorDerivedProvenance(
            artifact_type="risk_matrix",
            schema_version="1.0",
            calc_version="risk_v1.0",
            canonicalization_version="1.0",
            input_hash="c" * 64,
            canonical_sources=["canonical/decisions/decisions.yaml"],
            generated_at=datetime.now().isoformat(),
            rebuild_command=RebuildCommand(
                cmd=["lc", "advisor", "risk", "--force"],
                cwd=".",
                schema_version="1.0",
            ),
            content_hash="d" * 64,
            redaction_profile_version="1.0",
        )

        content = {"risk_level": "high", "factors": ["market", "liquidity"]}

        content_path, meta_path = handler.write_with_provenance(
            artifact_type="risk_matrix",
            content=content,
            provenance=provenance,
            format="json",
        )

        # 驗證檔案存在
        assert content_path.exists()
        assert meta_path.exists()

        # 驗證 JSON 內容
        import json

        loaded_content = json.loads(content_path.read_text(encoding="utf-8"))
        assert loaded_content == content

    def test_artifact_type_mismatch_raises(self, handler, sample_provenance):
        """測試 artifact_type 不一致時拋出錯誤"""
        with pytest.raises(ValueError) as exc_info:
            handler.write_with_provenance(
                artifact_type="risk_matrix",  # 與 provenance 不一致
                content="test",
                provenance=sample_provenance,  # artifact_type="decision_wiki"
                format="md",
            )

        assert "artifact_type 不一致" in str(exc_info.value)


class TestContentHash:
    """內容 hash 測試"""

    def test_compute_string_hash(self, handler):
        """測試字串內容 hash"""
        content = "Hello, World!"
        hash_value = handler._compute_content_hash(content)

        # 應為 SHA-256（64 hex）
        assert len(hash_value) == 64
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_compute_dict_hash(self, handler):
        """測試字典內容 hash"""
        content = {"key": "value", "number": 42}
        hash_value = handler._compute_content_hash(content)

        # 應為 SHA-256
        assert len(hash_value) == 64

        # 相同內容應產生相同 hash
        hash_value2 = handler._compute_content_hash({"number": 42, "key": "value"})
        assert hash_value == hash_value2  # sort_keys=True 應確保順序
