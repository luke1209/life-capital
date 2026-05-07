"""測試 SeedDataBuilder

驗證測試資料建構器的功能與護欄規則遵守情況。
"""

import csv
import json
import stat

import pytest
import yaml

from tests.fixtures.seed_data import SeedDataBuilder


@pytest.fixture
def temp_data_dir(tmp_path):
    """提供臨時資料目錄"""
    return tmp_path / "test_data"


class TestSeedDataBuilder:
    """SeedDataBuilder 測試套件"""

    def test_init(self, temp_data_dir):
        """測試初始化"""
        builder = SeedDataBuilder(temp_data_dir)
        assert builder.base_dir == temp_data_dir
        assert builder.months == 1

    def test_with_months_valid(self, temp_data_dir):
        """測試設定月份數量（有效範圍）"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.with_months(3)
        assert result is builder  # Fluent API
        assert builder.months == 3

    def test_with_months_invalid(self, temp_data_dir):
        """測試設定月份數量（無效範圍）"""
        builder = SeedDataBuilder(temp_data_dir)
        with pytest.raises(ValueError, match="months 必須在 1-12 之間"):
            builder.with_months(0)
        with pytest.raises(ValueError, match="months 必須在 1-12 之間"):
            builder.with_months(13)

    def test_build_minimal_structure(self, temp_data_dir):
        """測試最小資料集結構"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_minimal()

        # 驗證目錄結構
        assert (result / "canonical").is_dir()
        assert (result / "canonical" / "expenses").is_dir()
        assert (result / "raw" / "imports").is_dir()

        # 驗證配置檔案（在 base_dir 下，不在 canonical/）
        assert (result / "life_assumptions.yaml").is_file()
        assert (result / "monthly_income.yaml").is_file()
        assert (result / "expense_policy.yaml").is_file()
        assert (result / "lifetime_targets.yaml").is_file()

        # 驗證月度支出（1 個月）
        assert (result / "canonical" / "expenses" / "expenses_2024_12.csv").is_file()

        # 驗證 manifest 與 log
        assert (result / "raw" / "raw_manifest.json").is_file()
        assert (result / "canonical" / ".operation_log.jsonl").is_file()

    def test_build_full_structure(self, temp_data_dir):
        """測試完整資料集結構（7 個月）"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_full()

        # 驗證 7 個月份 CSV
        for month in range(6, 13):
            csv_file = result / "canonical" / "expenses" / f"expenses_2024_{month:02d}.csv"
            assert csv_file.is_file(), f"Missing {csv_file}"

    def test_schema_version(self, temp_data_dir):
        """測試所有 YAML 檔案的 schema_version 符合 CURRENT_SCHEMA_VERSION"""
        from life_capital.io.registry import CURRENT_SCHEMA_VERSION

        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_minimal()

        yaml_files = [
            "life_assumptions.yaml",
            "monthly_income.yaml",
            "expense_policy.yaml",
            "lifetime_targets.yaml",
        ]

        for yaml_file in yaml_files:
            with open(result / yaml_file) as f:
                data = yaml.safe_load(f)
                assert data["schema_version"] == CURRENT_SCHEMA_VERSION, \
                    f"{yaml_file} schema_version 應為 {CURRENT_SCHEMA_VERSION}"

    def test_monthly_income_owner(self, temp_data_dir):
        """測試 monthly_income 包含 owner 欄位"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_minimal()

        with open(result / "monthly_income.yaml") as f:
            data = yaml.safe_load(f)
            sources = data["sources"]
            assert len(sources) == 2

            person_a = [s for s in sources if s["owner"] == "person_a"][0]
            assert person_a["amount"] == 60000
            assert person_a["frequency"] == "monthly"

            person_b = [s for s in sources if s["owner"] == "person_b"][0]
            assert person_b["amount"] == 55000
            assert person_b["frequency"] == "monthly"

    def test_csv_payer_field(self, temp_data_dir):
        """測試 CSV 包含 payer 欄位"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_minimal()

        with open(result / "canonical" / "expenses" / "expenses_2024_12.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) > 0
            assert "payer" in rows[0]
            assert rows[0]["payer"] in ["person_a", "person_b", "shared"]

    def test_december_special_data(self, temp_data_dir):
        """測試 12 月特殊資料（保險 39K + 禮物 5K + 退款 -500）"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_minimal()

        with open(result / "canonical" / "expenses" / "expenses_2024_12.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            amounts = [row["amount"] for row in rows]

            assert "39000" in amounts, "缺少保險 39K"
            assert "5000" in amounts, "缺少聖誕禮物 5K"
            assert "-500" in amounts, "缺少退款 -500"

    def test_july_special_data(self, temp_data_dir):
        """測試 7 月特殊資料（暑假旅遊 8K）"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_full()

        with open(result / "canonical" / "expenses" / "expenses_2024_07.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            vacation = [r for r in rows if r.get("note") == "Summer vacation"]

            assert len(vacation) == 1, "缺少暑假旅遊"
            assert vacation[0]["amount"] == "8000"
            assert vacation[0]["category"] == "entertainment"

    def test_raw_imports_readonly(self, temp_data_dir):
        """測試 raw/imports 檔案為 read-only (chmod 444)"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_full()

        raw_files = list((result / "raw" / "imports").glob("*.csv"))
        assert len(raw_files) == 7, "raw/imports CSV 數量錯誤"

        for raw_file in raw_files:
            mode = raw_file.stat().st_mode
            assert not (mode & stat.S_IWUSR), f"{raw_file} 不是 read-only"

    def test_operation_log(self, temp_data_dir):
        """測試 operation log 記錄"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_full()

        log_path = result / "canonical" / ".operation_log.jsonl"
        assert log_path.is_file()

        with open(log_path) as f:
            lines = f.readlines()
            assert len(lines) == 7, "operation log 記錄數量錯誤"

            # 驗證每行都是有效的 JSON
            for line in lines:
                entry = json.loads(line)
                assert "operation" in entry
                assert entry["operation"]["actor"] == "seed_builder"
                assert entry["operation"]["operation_type"] == "import"

    def test_raw_manifest(self, temp_data_dir):
        """測試 raw_manifest.json 生成"""
        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_full()

        manifest_path = result / "raw" / "raw_manifest.json"
        assert manifest_path.is_file()

        with open(manifest_path) as f:
            manifest = json.load(f)
            assert "generated_at" in manifest
            assert "files" in manifest
            assert len(manifest["files"]) == 7  # 7 個 CSV 檔案

            # 驗證每個檔案記錄
            for file_info in manifest["files"]:
                assert "path" in file_info
                assert "sha256" in file_info
                assert "size" in file_info
                assert "mtime" in file_info

    def test_payer_distribution(self, temp_data_dir):
        """測試支付者分布（person_a≈30%, person_b≈25%, shared≈45%）"""
        from decimal import Decimal

        builder = SeedDataBuilder(temp_data_dir)
        result = builder.build_full()

        payer_amounts = {"person_a": Decimal("0"), "person_b": Decimal("0"), "shared": Decimal("0")}

        for month in range(6, 13):
            csv_file = result / "canonical" / "expenses" / f"expenses_2024_{month:02d}.csv"
            with open(csv_file) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    payer = row["payer"]
                    amount = Decimal(row["amount"])
                    payer_amounts[payer] += amount

        total = sum(payer_amounts.values())
        luke_ratio = float(payer_amounts["person_a"] / total * 100)
        freya_ratio = float(payer_amounts["person_b"] / total * 100)
        shared_ratio = float(payer_amounts["shared"] / total * 100)

        # 允許 ±7% 誤差
        assert 23 <= luke_ratio <= 37, f"Person A 比例 {luke_ratio:.1f}% 不在預期範圍"
        assert 18 <= freya_ratio <= 32, f"Person B 比例 {freya_ratio:.1f}% 不在預期範圍"
        assert 38 <= shared_ratio <= 52, f"Shared 比例 {shared_ratio:.1f}% 不在預期範圍"
