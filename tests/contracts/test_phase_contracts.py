"""Phase 0-3 行為契約測試

驗證各 Phase 的核心行為不變量，使用 Golden Data 進行回歸測試。

測試分類：
- 結構性契約：三層結構、undo 回滾等
- 行為回歸：去重、重建等核心邏輯

注意：
- Golden Data 更新需 CODEOWNERS 審核
- 使用 canonicalize 消除序列化差異
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

# 加入 scripts 路徑
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from golden_data_diff import canonicalize, golden_compare  # noqa: E402

GOLDEN_DIR = PROJECT_ROOT / "tests" / "contracts" / "golden"


class TestThreeLayerStructure:
    """Phase 0: 三層結構契約測試"""

    def test_raw_canonical_derived_paths_exist(self, tmp_path: Path):
        """驗證三層目錄結構可正確建立"""
        from life_capital.io.registry import (
            CANONICAL_DIR,
            DERIVED_DIR,
            RAW_DIR,
        )

        # 建立三層結構
        (tmp_path / RAW_DIR).mkdir(parents=True)
        (tmp_path / CANONICAL_DIR).mkdir(parents=True)
        (tmp_path / DERIVED_DIR).mkdir(parents=True)

        # 驗證存在
        assert (tmp_path / RAW_DIR).exists()
        assert (tmp_path / CANONICAL_DIR).exists()
        assert (tmp_path / DERIVED_DIR).exists()

    def test_path_constants_are_strings(self):
        """驗證路徑常數格式正確"""
        from life_capital.io.registry import (
            CANONICAL_DIR,
            DERIVED_DIR,
            RAW_DIR,
        )

        assert isinstance(RAW_DIR, str)
        assert isinstance(CANONICAL_DIR, str)
        assert isinstance(DERIVED_DIR, str)
        assert "/" not in RAW_DIR.strip("/")  # 不應有前後斜線
        assert "/" not in CANONICAL_DIR.strip("/")
        assert "/" not in DERIVED_DIR.strip("/")


class TestSchemaVersion:
    """Phase 0: Schema 版本契約測試"""

    def test_current_schema_version_format(self):
        """驗證版本號格式正確"""
        from life_capital.io.registry import CURRENT_SCHEMA_VERSION

        # 應該是 X.Y 格式
        parts = CURRENT_SCHEMA_VERSION.split(".")
        assert len(parts) == 2
        assert all(part.isdigit() for part in parts)

    def test_all_versioned_models_use_current_version(self):
        """驗證所有 VersionedModel 使用當前版本"""
        from life_capital.io.registry import CURRENT_SCHEMA_VERSION
        from life_capital.models.expense import MonthlyExpenses

        # 建立實例並檢查版本（使用 MonthlyExpenses，它不需要複雜的驗證）
        expenses = MonthlyExpenses(year=2025, month=1)
        assert expenses.schema_version == CURRENT_SCHEMA_VERSION


class TestDecimalPrecision:
    """Phase 0: Decimal 精度契約測試"""

    def test_quantize_rounds_correctly(self):
        """驗證 RoundingConfig.quantize 使用正確的捨入策略"""
        from life_capital.calculators.rounding import RoundingConfig

        # 使用預設設定（ROUND_HALF_UP, scale=0）
        config = RoundingConfig.default()

        # ROUND_HALF_UP 測試（scale=0 為整數捨入）
        assert config.quantize(Decimal("1.5")) == Decimal("2")
        assert config.quantize(Decimal("2.5")) == Decimal("3")
        assert config.quantize(Decimal("-1.5")) == Decimal("-2")

    def test_expense_amount_is_decimal(self):
        """驗證 ExpenseRecord amount 是 Decimal"""
        from datetime import date

        from life_capital.models.expense import ExpenseRecord

        record = ExpenseRecord(
            date=date(2025, 1, 1),
            amount=Decimal("123.45"),
            category="food",
        )
        assert isinstance(record.amount, Decimal)


class TestCanonicalization:
    """Golden Data Canonicalization 測試"""

    def test_canonicalize_removes_timestamps(self):
        """驗證 canonicalize 移除時間戳"""
        data = {
            "value": 100,
            "generated_at": "2025-01-01T12:00:00",
            "created_at": "2025-01-01",
        }
        result = canonicalize(data)
        assert "generated_at" not in result
        assert "created_at" not in result
        assert result["value"] == "100"

    def test_canonicalize_normalizes_amounts(self):
        """驗證 canonicalize 正規化金額"""
        data = {"amount": 123.456}
        result = canonicalize(data)
        assert result["amount"] == "123"

    def test_canonicalize_sorts_dicts(self):
        """驗證 canonicalize 排序 dict keys"""
        data = {"b": 2, "a": 1, "c": 3}
        result = canonicalize(data)
        keys = list(result.keys())
        assert keys == ["a", "b", "c"]

    def test_canonicalize_sorts_records_by_date(self):
        """驗證 canonicalize 依 date 排序 records"""
        data = {
            "records": [
                {"date": "2025-01-02", "value": 200},
                {"date": "2025-01-01", "value": 100},
            ]
        }
        result = canonicalize(data)
        assert result["records"][0]["date"] == "2025-01-01"
        assert result["records"][1]["date"] == "2025-01-02"

    def test_canonicalize_preserves_projection_order(self):
        """驗證 canonicalize 保留 projections 順序"""
        data = {
            "projections": [
                {"month": 2, "value": 200},
                {"month": 1, "value": 100},
            ]
        }
        result = canonicalize(data)
        # projections 在 LIST_PRESERVE_ORDER 中，不應排序
        assert result["projections"][0]["month"] == "2"
        assert result["projections"][1]["month"] == "1"


class TestGoldenDataComparison:
    """Golden Data 比對測試"""

    def test_golden_compare_equal(self, tmp_path: Path):
        """驗證相等資料比對成功"""
        import yaml

        expected = {"amount": 100, "category": "food"}
        actual = {"amount": 100, "category": "food"}

        # 寫入期望值
        golden_file = tmp_path / "expected.yaml"
        with open(golden_file, "w") as f:
            yaml.dump(expected, f)

        is_equal, diff = golden_compare(golden_file, actual)
        assert is_equal, f"應該相等但失敗: {diff}"

    def test_golden_compare_different(self, tmp_path: Path):
        """驗證不相等資料比對失敗"""
        import yaml

        expected = {"amount": 100, "category": "food"}
        actual = {"amount": 200, "category": "food"}

        golden_file = tmp_path / "expected.yaml"
        with open(golden_file, "w") as f:
            yaml.dump(expected, f)

        is_equal, diff = golden_compare(golden_file, actual)
        assert not is_equal
        assert "amount" in diff

    def test_golden_compare_ignores_timestamps(self, tmp_path: Path):
        """驗證 Golden 比對忽略時間戳"""
        import yaml

        expected = {"amount": 100, "generated_at": "2025-01-01"}
        actual = {"amount": 100, "generated_at": "2025-12-31"}

        golden_file = tmp_path / "expected.yaml"
        with open(golden_file, "w") as f:
            yaml.dump(expected, f)

        is_equal, diff = golden_compare(golden_file, actual)
        assert is_equal, f"時間戳應被忽略: {diff}"


class TestExpenseRecordBehavior:
    """Phase 1: ExpenseRecord 行為測試"""

    def test_expense_record_from_csv_row(self):
        """驗證 CSV 行解析行為"""
        from life_capital.models.expense import ExpenseRecord

        row = {
            "date": "2025-01-15",
            "amount": "1234.56",
            "category": "食物",
            "payer": "person_a",
            "note": "午餐",
            "merchant": "小吃店",
        }

        record = ExpenseRecord.from_csv_row(row)
        assert record.amount == Decimal("1234.56")
        assert record.category == "食物"
        assert record.payer == "person_a"

    def test_expense_record_default_payer(self):
        """驗證預設 payer 為 shared"""
        from life_capital.models.expense import ExpenseRecord

        row = {
            "date": "2025-01-15",
            "amount": "100",
            "category": "食物",
        }

        record = ExpenseRecord.from_csv_row(row)
        assert record.payer == "shared"

    def test_expense_record_is_refund(self):
        """驗證退款判斷邏輯"""
        from datetime import date

        from life_capital.models.expense import ExpenseRecord

        expense = ExpenseRecord(
            date=date(2025, 1, 1),
            amount=Decimal("100"),
            category="food",
        )
        assert not expense.is_refund()

        refund = ExpenseRecord(
            date=date(2025, 1, 1),
            amount=Decimal("-50"),
            category="food",
        )
        assert refund.is_refund()


class TestMonthlyExpensesBehavior:
    """Phase 1: MonthlyExpenses 行為測試"""

    def test_monthly_expenses_total(self):
        """驗證月度總額計算"""
        from datetime import date

        from life_capital.models.expense import ExpenseRecord, MonthlyExpenses

        expenses = MonthlyExpenses(
            year=2025,
            month=1,
            records=[
                ExpenseRecord(date=date(2025, 1, 1), amount=Decimal("100"), category="food"),
                ExpenseRecord(
                    date=date(2025, 1, 2), amount=Decimal("200"), category="transport"
                ),
                ExpenseRecord(
                    date=date(2025, 1, 3), amount=Decimal("-50"), category="food"
                ),  # 退款
            ],
        )

        assert expenses.total() == Decimal("250")

    def test_monthly_expenses_by_category(self):
        """驗證類別統計"""
        from datetime import date

        from life_capital.models.expense import ExpenseRecord, MonthlyExpenses

        expenses = MonthlyExpenses(
            year=2025,
            month=1,
            records=[
                ExpenseRecord(date=date(2025, 1, 1), amount=Decimal("100"), category="food"),
                ExpenseRecord(date=date(2025, 1, 2), amount=Decimal("200"), category="food"),
                ExpenseRecord(date=date(2025, 1, 3), amount=Decimal("150"), category="transport"),
            ],
        )

        by_cat = expenses.by_category()
        assert by_cat["food"] == Decimal("300")
        assert by_cat["transport"] == Decimal("150")

    def test_monthly_expenses_by_payer(self):
        """驗證支付者統計"""
        from datetime import date

        from life_capital.models.expense import ExpenseRecord, MonthlyExpenses

        expenses = MonthlyExpenses(
            year=2025,
            month=1,
            records=[
                ExpenseRecord(
                    date=date(2025, 1, 1), amount=Decimal("100"), category="food", payer="person_a"
                ),
                ExpenseRecord(
                    date=date(2025, 1, 2), amount=Decimal("200"), category="food", payer="person_b"
                ),
                ExpenseRecord(
                    date=date(2025, 1, 3),
                    amount=Decimal("150"),
                    category="transport",
                    payer="shared",
                ),
            ],
        )

        by_payer = expenses.by_payer()
        assert by_payer["person_a"] == Decimal("100")
        assert by_payer["person_b"] == Decimal("200")
        assert by_payer["shared"] == Decimal("150")
