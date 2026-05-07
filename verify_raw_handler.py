#!/usr/bin/env python3
"""驗證 raw_handler 功能的獨立腳本"""

import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from life_capital.io.raw_handler import (
    list_raw_files,
    read_raw,
    write_raw,
)
from life_capital.models.operation import Provenance, SourceType


class TestData(BaseModel):
    """測試資料模型"""

    name: str
    value: int
    timestamp: datetime = Field(default_factory=datetime.now)


def main():
    """主驗證流程"""
    print("🧪 驗證 raw_handler.py 功能\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        print(f"📁 臨時目錄: {base_dir}\n")

        # 建立 Provenance
        provenance = Provenance(
            source_type=SourceType.CSV_IMPORT,
            parser_version="1.0.0",
        )

        # 建立測試資料
        test_data = TestData(name="test_record", value=42)

        # === Test 1: 寫入 YAML ===
        print("✅ Test 1: 寫入 YAML 至 imports")
        yaml_file = write_raw(
            data=test_data,
            target="imports",
            provenance=provenance,
            format="yaml",
            base_dir=base_dir,
        )
        print(f"   檔案: {yaml_file.name}")

        # 驗證權限
        import stat
        mode = stat.filemode(yaml_file.stat().st_mode)
        assert mode == "-r--r--r--", f"權限錯誤: {mode}"
        print(f"   權限: {mode} ✅")

        # === Test 2: 讀取 YAML ===
        print("\n✅ Test 2: 讀取 YAML")
        data, prov = read_raw(yaml_file, model_class=TestData)
        assert isinstance(data, TestData)
        assert data.name == "test_record"
        assert data.value == 42
        assert prov is not None
        assert prov.source_type == SourceType.CSV_IMPORT
        print(f"   資料: name={data.name}, value={data.value}")
        print(f"   Provenance: {prov.source_type.value}")

        # === Test 3: 寫入 JSON ===
        print("\n✅ Test 3: 寫入 JSON 至 manual")
        json_file = write_raw(
            data=test_data,
            target="manual",
            provenance=provenance,
            format="json",
            base_dir=base_dir,
        )
        print(f"   檔案: {json_file.name}")

        # === Test 4: 寫入 CSV ===
        print("\n✅ Test 4: 寫入 CSV")
        csv_data = {
            "headers": ["date", "amount", "category"],
            "rows": [
                {"date": "2024-01-01", "amount": "100.00", "category": "food"},
                {"date": "2024-01-02", "amount": "200.00", "category": "transport"},
            ],
        }
        csv_file = write_raw(
            data=csv_data,
            target="imports",
            provenance=provenance,
            format="csv",
            base_dir=base_dir,
        )
        print(f"   檔案: {csv_file.name}")

        # === Test 5: 列出檔案 ===
        print("\n✅ Test 5: 列出 imports 檔案")
        files = list_raw_files("imports", base_dir=base_dir)
        assert len(files) == 2  # YAML + CSV
        print(f"   找到 {len(files)} 個檔案:")
        for f in files:
            print(f"   - {f.name}")

        # === Test 6: Read-only 保護 ===
        print("\n✅ Test 6: Read-only 保護測試")
        try:
            with open(yaml_file, "w") as f:
                f.write("should fail")
            print("   ❌ 錯誤：應該無法寫入！")
        except PermissionError:
            print("   ✅ 正確：無法修改 read-only 檔案")

        # === Test 7: 讀取 CSV ===
        print("\n✅ Test 7: 讀取 CSV")
        csv_content, csv_prov = read_raw(csv_file)
        assert isinstance(csv_content, dict)
        assert "headers" in csv_content
        assert "rows" in csv_content
        assert len(csv_content["rows"]) == 2
        assert csv_prov is not None
        print(f"   表頭: {csv_content['headers']}")
        print(f"   記錄數: {len(csv_content['rows'])}")

    print("\n🎉 所有測試通過！\n")


if __name__ == "__main__":
    main()
