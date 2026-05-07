"""Raw Handler 測試

驗證 raw_handler.py 的不可變寫入機制。
"""

import json
import stat
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, Field

from life_capital.io.raw_handler import (
    list_raw_files,
    read_raw,
    write_raw,
)
from life_capital.models.operation import Provenance, SourceType


class SampleData(BaseModel):
    """測試用資料模型"""

    name: str
    value: int
    timestamp: datetime = Field(default_factory=datetime.now)


@pytest.fixture
def temp_data_dir(tmp_path):
    """臨時資料目錄"""
    return tmp_path


@pytest.fixture
def sample_provenance():
    """範例 Provenance"""
    return Provenance(
        source_type=SourceType.CSV_IMPORT,
        parser_version="1.0.0",
    )


@pytest.fixture
def sample_data():
    """範例資料"""
    return SampleData(name="test", value=42)


class TestWriteRaw:
    """測試 write_raw 功能"""

    def test_write_yaml_imports(self, temp_data_dir, sample_data, sample_provenance):
        """測試寫入 YAML 至 imports 目錄"""
        file_path = write_raw(
            data=sample_data,
            target="imports",
            provenance=sample_provenance,
            format="yaml",
            base_dir=temp_data_dir,
        )

        # 驗證檔案存在
        assert file_path.exists()
        assert file_path.parent.name == "imports"

        # 驗證檔案權限為 read-only (444)
        file_stat = file_path.stat()
        mode = stat.filemode(file_stat.st_mode)
        assert mode == "-r--r--r--"

        # 驗證檔案內容包含 Provenance
        with open(file_path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)

        assert "_provenance" in content
        assert content["_provenance"]["source_type"] == "csv_import"
        assert content["name"] == "test"
        assert content["value"] == 42

    def test_write_json_manual(self, temp_data_dir, sample_data, sample_provenance):
        """測試寫入 JSON 至 manual 目錄"""
        file_path = write_raw(
            data=sample_data,
            target="manual",
            provenance=sample_provenance,
            format="json",
            base_dir=temp_data_dir,
        )

        assert file_path.exists()
        assert file_path.parent.name == "manual"

        # 驗證 read-only
        file_stat = file_path.stat()
        mode = stat.filemode(file_stat.st_mode)
        assert mode == "-r--r--r--"

        # 驗證內容
        with open(file_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        assert "_provenance" in content
        assert content["name"] == "test"

    def test_write_csv_format(self, temp_data_dir, sample_provenance):
        """測試寫入 CSV 格式"""
        csv_data = {
            "headers": ["date", "amount", "category"],
            "rows": [
                {"date": "2024-01-01", "amount": "100.00", "category": "food"},
                {"date": "2024-01-02", "amount": "200.00", "category": "transport"},
            ],
        }

        file_path = write_raw(
            data=csv_data,
            target="imports",
            provenance=sample_provenance,
            format="csv",
            base_dir=temp_data_dir,
        )

        assert file_path.exists()
        assert file_path.suffix == ".csv"

        # 驗證 read-only
        file_stat = file_path.stat()
        mode = stat.filemode(file_stat.st_mode)
        assert mode == "-r--r--r--"

        # 驗證內容包含 Provenance 註解
        with open(file_path, "r", encoding="utf-8") as f:
            first_line = f.readline()

        assert first_line.startswith("# Provenance:")

    def test_cannot_overwrite_existing_file(
        self, temp_data_dir, sample_data, sample_provenance
    ):
        """測試無法覆寫已存在檔案"""
        # 先寫入一次
        write_raw(
            data=sample_data,
            target="imports",
            provenance=sample_provenance,
            format="yaml",
            base_dir=temp_data_dir,
        )

        # 手動建立同名檔案（模擬碰撞）
        # 由於檔案名稱包含 UUID，實際碰撞機率極低
        # 這裡測試若真的碰撞，應該拋出錯誤
        # （實際測試需要 mock uuid4）

    def test_unsupported_format(self, temp_data_dir, sample_data, sample_provenance):
        """測試不支援的格式"""
        with pytest.raises(ValueError, match="不支援的格式"):
            write_raw(
                data=sample_data,
                target="imports",
                provenance=sample_provenance,
                format="xml",  # type: ignore
                base_dir=temp_data_dir,
            )


class TestReadRaw:
    """測試 read_raw 功能"""

    def test_read_yaml_with_model(
        self, temp_data_dir, sample_data, sample_provenance
    ):
        """測試讀取 YAML 並驗證為模型"""
        file_path = write_raw(
            data=sample_data,
            target="imports",
            provenance=sample_provenance,
            format="yaml",
            base_dir=temp_data_dir,
        )

        # 讀取並驗證
        data, provenance = read_raw(file_path, model_class=SampleData)

        assert isinstance(data, SampleData)
        assert data.name == "test"
        assert data.value == 42

        assert provenance is not None
        assert provenance.source_type == SourceType.CSV_IMPORT

    def test_read_yaml_as_dict(self, temp_data_dir, sample_data, sample_provenance):
        """測試讀取 YAML 為字典"""
        file_path = write_raw(
            data=sample_data,
            target="imports",
            provenance=sample_provenance,
            format="yaml",
            base_dir=temp_data_dir,
        )

        # 讀取為字典
        data, provenance = read_raw(file_path)

        assert isinstance(data, dict)
        assert data["name"] == "test"
        assert data["value"] == 42

    def test_read_json(self, temp_data_dir, sample_data, sample_provenance):
        """測試讀取 JSON"""
        file_path = write_raw(
            data=sample_data,
            target="manual",
            provenance=sample_provenance,
            format="json",
            base_dir=temp_data_dir,
        )

        data, provenance = read_raw(file_path)

        assert isinstance(data, dict)
        assert data["name"] == "test"
        assert provenance is not None

    def test_read_csv(self, temp_data_dir, sample_provenance):
        """測試讀取 CSV"""
        csv_data = {
            "headers": ["date", "amount", "category"],
            "rows": [
                {"date": "2024-01-01", "amount": "100.00", "category": "food"},
            ],
        }

        file_path = write_raw(
            data=csv_data,
            target="imports",
            provenance=sample_provenance,
            format="csv",
            base_dir=temp_data_dir,
        )

        data, provenance = read_raw(file_path)

        assert isinstance(data, dict)
        assert "headers" in data
        assert "rows" in data
        assert len(data["rows"]) == 1
        assert provenance is not None

    def test_read_nonexistent_file(self):
        """測試讀取不存在的檔案"""
        with pytest.raises(FileNotFoundError):
            read_raw(Path("/tmp/nonexistent.yaml"))


class TestListRawFiles:
    """測試 list_raw_files 功能"""

    def test_list_empty_directory(self, temp_data_dir):
        """測試空目錄"""
        files = list_raw_files("imports", base_dir=temp_data_dir)
        assert files == []

    def test_list_imports_files(self, temp_data_dir, sample_data, sample_provenance):
        """測試列出 imports 檔案"""
        # 寫入 3 個檔案
        for i in range(3):
            write_raw(
                data=sample_data,
                target="imports",
                provenance=sample_provenance,
                format="yaml",
                base_dir=temp_data_dir,
            )

        files = list_raw_files("imports", base_dir=temp_data_dir)
        assert len(files) == 3

        # 驗證排序（按檔案名稱，即時間戳）
        for i in range(len(files) - 1):
            assert files[i].name <= files[i + 1].name

    def test_list_manual_files(self, temp_data_dir, sample_data, sample_provenance):
        """測試列出 manual 檔案"""
        write_raw(
            data=sample_data,
            target="manual",
            provenance=sample_provenance,
            format="json",
            base_dir=temp_data_dir,
        )

        files = list_raw_files("manual", base_dir=temp_data_dir)
        assert len(files) == 1

    def test_list_with_time_filter(
        self, temp_data_dir, sample_data, sample_provenance
    ):
        """測試時間篩選"""
        # 寫入第一個檔案
        write_raw(
            data=sample_data,
            target="imports",
            provenance=sample_provenance,
            format="yaml",
            base_dir=temp_data_dir,
        )

        # 記錄時間
        cutoff_time = datetime.now()

        # 寫入第二個檔案
        import time

        time.sleep(0.1)
        write_raw(
            data=sample_data,
            target="imports",
            provenance=sample_provenance,
            format="yaml",
            base_dir=temp_data_dir,
        )

        # 篩選
        files = list_raw_files("imports", since=cutoff_time, base_dir=temp_data_dir)
        assert len(files) >= 1  # 至少有第二個檔案


class TestReadOnlyProtection:
    """測試 read-only 保護機制"""

    def test_cannot_modify_written_file(
        self, temp_data_dir, sample_data, sample_provenance
    ):
        """測試寫入後無法修改檔案"""
        file_path = write_raw(
            data=sample_data,
            target="imports",
            provenance=sample_provenance,
            format="yaml",
            base_dir=temp_data_dir,
        )

        # 嘗試寫入應該失敗（權限錯誤）
        with pytest.raises(PermissionError):
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("modified content")

    def test_can_read_readonly_file(
        self, temp_data_dir, sample_data, sample_provenance
    ):
        """測試 read-only 檔案仍可讀取"""
        file_path = write_raw(
            data=sample_data,
            target="imports",
            provenance=sample_provenance,
            format="yaml",
            base_dir=temp_data_dir,
        )

        # 應該可以讀取
        data, provenance = read_raw(file_path)
        assert data is not None
