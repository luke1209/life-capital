"""Seed Data Integration Tests

驗證 seed 資料通過所有 CLI 驗證檢查。

測試範圍:
    - 資料完整性：所有配置檔案存在、月度支出檔案正確
    - CLI validate：schema 版本正確、資料格式正確、業務規則符合
    - CLI doctor：檔案權限、operation log、raw manifest 正確
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from life_capital.cli import app
from life_capital.io.registry import (
    CANONICAL_DIR,
    CURRENT_SCHEMA_VERSION,
    EXPENSE_FILE_PATTERN,
    OPERATION_LOG_FILE,
    RAW_DIR,
    RAW_IMPORTS_DIR,
    RAW_MANIFEST_FILE,
)


class TestSeedDataStructure:
    """測試 seed 資料目錄結構與檔案完整性"""

    def test_directory_structure_exists(self, seed_data_dir: Path):
        """驗證三層目錄結構存在"""
        # canonical/
        assert (seed_data_dir / CANONICAL_DIR).is_dir(), "canonical/ 目錄不存在"
        assert (
            seed_data_dir / CANONICAL_DIR / "expenses"
        ).is_dir(), "canonical/expenses/ 目錄不存在"

        # raw/
        assert (seed_data_dir / RAW_DIR).is_dir(), "raw/ 目錄不存在"
        assert (
            seed_data_dir / RAW_DIR / "imports"
        ).is_dir(), "raw/imports/ 目錄不存在"

    def test_config_files_exist(self, seed_data_dir: Path):
        """驗證所有配置檔案存在"""
        required_configs = [
            "life_assumptions.yaml",
            "monthly_income.yaml",
            "expense_policy.yaml",
            "lifetime_targets.yaml",
        ]

        for config in required_configs:
            config_path = seed_data_dir / config
            assert config_path.exists(), f"配置檔案不存在: {config}"
            assert config_path.is_file(), f"配置檔案不是檔案: {config}"

    def test_monthly_expenses_exist(self, seed_data_dir: Path):
        """驗證月度支出檔案存在（7 個月：2024-06 ~ 2024-12）"""
        expenses_dir = seed_data_dir / CANONICAL_DIR / "expenses"

        expected_months = [
            (2024, 6),
            (2024, 7),
            (2024, 8),
            (2024, 9),
            (2024, 10),
            (2024, 11),
            (2024, 12),
        ]

        for year, month in expected_months:
            expense_file = expenses_dir / EXPENSE_FILE_PATTERN.format(
                year=year, month=month
            )
            assert (
                expense_file.exists()
            ), f"月度支出檔案不存在: {year}-{month:02d}"
            assert (
                expense_file.is_file()
            ), f"月度支出檔案不是檔案: {year}-{month:02d}"

    def test_raw_manifest_exists(self, seed_data_dir: Path):
        """驗證 raw_manifest.json 存在"""
        manifest_path = seed_data_dir / RAW_MANIFEST_FILE
        assert manifest_path.exists(), "raw_manifest.json 不存在"
        assert manifest_path.is_file(), "raw_manifest.json 不是檔案"

    def test_operation_log_exists(self, seed_data_dir: Path):
        """驗證 operation log 存在"""
        log_path = seed_data_dir / OPERATION_LOG_FILE
        assert log_path.exists(), "operation log 不存在"
        assert log_path.is_file(), "operation log 不是檔案"


class TestSeedDataValidation:
    """測試 seed 資料通過 CLI validate 檢查"""

    def test_validate_passes(self, seed_data_dir: Path, cli_runner: CliRunner):
        """驗證 lc validate 通過"""
        result = cli_runner.invoke(
            app, ["validate", "--path", str(seed_data_dir)]
        )
        assert result.exit_code == 0, f"validate 失敗:\n{result.stdout}"

    def test_schema_versions_correct(self, seed_data_dir: Path):
        """驗證所有 YAML 檔案的 schema_version 正確"""
        config_files = [
            "life_assumptions.yaml",
            "monthly_income.yaml",
            "expense_policy.yaml",
            "lifetime_targets.yaml",
        ]

        for config_file in config_files:
            config_path = seed_data_dir / config_file
            assert config_path.exists(), f"配置檔案不存在: {config_file}"

            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            assert (
                "schema_version" in data
            ), f"{config_file} 缺少 schema_version"
            assert (
                data["schema_version"] == CURRENT_SCHEMA_VERSION
            ), f"{config_file} schema_version 不正確"

    def test_expense_csv_format_correct(self, seed_data_dir: Path):
        """驗證 CSV 欄位格式正確"""
        expenses_dir = seed_data_dir / CANONICAL_DIR / "expenses"
        csv_files = list(expenses_dir.glob("*.csv"))

        assert len(csv_files) == 7, f"應有 7 個月度支出檔案，實際: {len(csv_files)}"

        # 驗證第一個 CSV 檔案格式
        import csv

        first_csv = csv_files[0]
        with open(first_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames

            # 必須包含的欄位
            required_fields = {"date", "amount", "category", "payer"}
            assert required_fields.issubset(
                set(fieldnames or [])
            ), f"CSV 欄位不完整: {fieldnames}"

    def test_payer_values_valid(self, seed_data_dir: Path):
        """驗證 payer 欄位值合法（person_a/person_b/shared）"""
        expenses_dir = seed_data_dir / CANONICAL_DIR / "expenses"
        csv_files = list(expenses_dir.glob("*.csv"))

        valid_payers = {"person_a", "person_b", "shared"}

        import csv

        for csv_file in csv_files:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    payer = row.get("payer", "shared")
                    assert (
                        payer in valid_payers
                    ), f"payer 值不合法: {payer} in {csv_file.name}"


class TestSeedDataDoctor:
    """測試 seed 資料通過 CLI doctor 檢查"""

    def test_doctor_passes(self, seed_data_dir: Path, cli_runner: CliRunner):
        """驗證 lc doctor 通過"""
        result = cli_runner.invoke(app, ["doctor", "--path", str(seed_data_dir)])
        assert result.exit_code == 0, f"doctor 檢查失敗:\n{result.stdout}"

    def test_raw_files_readonly(self, seed_data_dir: Path):
        """驗證 raw/ 檔案為唯讀（chmod 444）"""
        raw_imports_dir = seed_data_dir / RAW_IMPORTS_DIR
        csv_files = list(raw_imports_dir.glob("*.csv"))

        assert len(csv_files) > 0, "raw/imports/ 中無 CSV 檔案"

        import os
        import stat

        for csv_file in csv_files:
            file_stat = os.stat(csv_file)
            mode = file_stat.st_mode

            # 驗證為唯讀（無寫入權限）
            assert not (
                mode & stat.S_IWUSR
            ), f"{csv_file.name} 不是唯讀（owner 有寫入權限）"
            assert not (
                mode & stat.S_IWGRP
            ), f"{csv_file.name} 不是唯讀（group 有寫入權限）"
            assert not (
                mode & stat.S_IWOTH
            ), f"{csv_file.name} 不是唯讀（other 有寫入權限）"

    def test_operation_log_valid_jsonl(self, seed_data_dir: Path):
        """驗證 operation log 為有效的 JSONL 格式"""
        log_path = seed_data_dir / OPERATION_LOG_FILE
        assert log_path.exists(), "operation log 不存在"

        import json

        with open(log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    assert "operation" in entry, f"第 {line_num} 行缺少 operation 欄位"
                except json.JSONDecodeError as e:
                    pytest.fail(f"operation log 第 {line_num} 行不是有效 JSON: {e}")

    def test_raw_manifest_valid_json(self, seed_data_dir: Path):
        """驗證 raw_manifest.json 為有效 JSON"""
        manifest_path = seed_data_dir / RAW_MANIFEST_FILE
        assert manifest_path.exists(), "raw_manifest.json 不存在"

        import json

        with open(manifest_path, "r", encoding="utf-8") as f:
            try:
                manifest = json.load(f)
                assert "files" in manifest, "manifest 缺少 files 欄位"
                assert isinstance(manifest["files"], list), "files 必須是 list"
            except json.JSONDecodeError as e:
                pytest.fail(f"raw_manifest.json 不是有效 JSON: {e}")


class TestSeedDataBusinessRules:
    """測試 seed 資料符合業務規則"""

    def test_expense_categories_in_policy(self, seed_data_dir: Path):
        """驗證所有支出類別都在 expense_policy 中定義"""
        import csv

        import yaml

        # 讀取 expense_policy
        policy_path = seed_data_dir / "expense_policy.yaml"
        with open(policy_path, "r", encoding="utf-8") as f:
            policy_data = yaml.safe_load(f)

        # 提取所有定義的類別
        defined_categories = set()
        for group_categories in policy_data["categories"].values():
            defined_categories.update(group_categories.keys())

        # 檢查所有 CSV 中的類別
        expenses_dir = seed_data_dir / CANONICAL_DIR / "expenses"
        csv_files = list(expenses_dir.glob("*.csv"))

        for csv_file in csv_files:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    category = row["category"]
                    assert (
                        category in defined_categories
                    ), f"未定義的類別: {category} in {csv_file.name}"

    def test_amounts_are_decimal_compatible(self, seed_data_dir: Path):
        """驗證所有金額可轉換為 Decimal"""
        import csv
        from decimal import Decimal, InvalidOperation

        expenses_dir = seed_data_dir / CANONICAL_DIR / "expenses"
        csv_files = list(expenses_dir.glob("*.csv"))

        for csv_file in csv_files:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):  # header = 1
                    amount_str = row["amount"]
                    try:
                        amount = Decimal(amount_str)
                        # 驗證非零
                        assert (
                            amount != 0
                        ), f"金額為零: {csv_file.name} 第 {row_num} 行"
                    except InvalidOperation:
                        pytest.fail(
                            f"金額格式錯誤: {amount_str} in {csv_file.name} 第 {row_num} 行"
                        )

    def test_dates_are_valid_format(self, seed_data_dir: Path):
        """驗證所有日期為有效的 YYYY-MM-DD 格式"""
        import csv
        from datetime import datetime

        expenses_dir = seed_data_dir / CANONICAL_DIR / "expenses"
        csv_files = list(expenses_dir.glob("*.csv"))

        for csv_file in csv_files:
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_num, row in enumerate(reader, start=2):
                    date_str = row["date"]
                    try:
                        datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        pytest.fail(
                            f"日期格式錯誤: {date_str} in {csv_file.name} 第 {row_num} 行"
                        )


class TestSeedDataConsistency:
    """測試 seed 資料內部一致性"""

    def test_raw_and_canonical_match_count(self, seed_data_dir: Path):
        """驗證 raw 與 canonical 月份數量一致"""
        raw_imports_dir = seed_data_dir / RAW_IMPORTS_DIR
        canonical_expenses_dir = seed_data_dir / CANONICAL_DIR / "expenses"

        raw_csv_count = len(list(raw_imports_dir.glob("*.csv")))
        canonical_csv_count = len(list(canonical_expenses_dir.glob("*.csv")))

        assert (
            raw_csv_count == canonical_csv_count
        ), f"raw ({raw_csv_count}) 與 canonical ({canonical_csv_count}) 檔案數量不一致"

    def test_operation_log_has_entries(self, seed_data_dir: Path):
        """驗證 operation log 有記錄"""
        log_path = seed_data_dir / OPERATION_LOG_FILE

        with open(log_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        assert len(lines) > 0, "operation log 為空"
        assert (
            len(lines) == 7
        ), f"operation log 應有 7 條記錄（7 個月匯入），實際: {len(lines)}"

    def test_raw_manifest_has_entries(self, seed_data_dir: Path):
        """驗證 raw_manifest.json 有記錄"""
        manifest_path = seed_data_dir / RAW_MANIFEST_FILE

        import json

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        files = manifest.get("files", [])
        assert len(files) > 0, "raw_manifest.json 無檔案記錄"
        assert (
            len(files) == 7
        ), f"raw_manifest.json 應有 7 個檔案記錄，實際: {len(files)}"
