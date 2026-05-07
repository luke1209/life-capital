"""測試 factory.py 工廠函式

驗證所有工廠函式提供的預設值與覆寫功能。
"""

from datetime import date, datetime
from decimal import Decimal

import pytest

from life_capital.io.registry import CURRENT_SCHEMA_VERSION
from life_capital.models.assumptions import (
    Currency,
    RatesMode,
    RoundingMethod,
    RoundingStage,
)
from life_capital.models.expense import ExpenseRecord, MonthlyExpenses
from life_capital.models.income import IncomeSource, MonthlyIncome
from tests.fixtures.factory import (
    make_basic,
    make_calculation,
    make_child,
    make_expense_record,
    make_income_source,
    make_life_assumptions,
    make_monthly_expenses,
    make_monthly_income,
    make_rates,
)


class TestMakeExpenseRecord:
    """測試 make_expense_record 工廠函式"""

    def test_default_values(self):
        """預設值應正確"""
        record = make_expense_record()

        assert record.date == date.today()
        assert record.amount == Decimal("1000")
        assert record.category == "food"
        assert record.payer == "shared"
        assert record.note is None
        assert record.merchant is None

    def test_partial_override(self):
        """部分覆寫應正確"""
        record = make_expense_record(
            amount=Decimal("500"),
            payer="person_a",
        )

        assert record.amount == Decimal("500")
        assert record.payer == "person_a"
        # 其他欄位保持預設值
        assert record.date == date.today()
        assert record.category == "food"

    def test_full_override(self):
        """完全覆寫應正確"""
        custom_date = date(2024, 6, 15)
        record = make_expense_record(
            date=custom_date,
            amount=Decimal("28000"),
            category="housing",
            payer="person_b",
            note="房租",
            merchant="房東",
        )

        assert record.date == custom_date
        assert record.amount == Decimal("28000")
        assert record.category == "housing"
        assert record.payer == "person_b"
        assert record.note == "房租"
        assert record.merchant == "房東"

    def test_is_valid_expense_record(self):
        """建立的記錄應為有效的 ExpenseRecord 實例"""
        record = make_expense_record()
        assert isinstance(record, ExpenseRecord)

    def test_amount_validation(self):
        """金額驗證應生效（不能為 0）"""
        with pytest.raises(ValueError, match="不能為 0"):
            make_expense_record(amount=Decimal("0"))


class TestMakeMonthlyExpenses:
    """測試 make_monthly_expenses 工廠函式"""

    def test_default_values(self):
        """預設值應正確"""
        expenses = make_monthly_expenses()

        assert expenses.schema_version == CURRENT_SCHEMA_VERSION
        assert expenses.year == datetime.now().year
        assert expenses.month == 12
        assert expenses.records == []

    def test_override_with_records(self):
        """覆寫 records 應正確"""
        records = [
            make_expense_record(category="housing", amount=Decimal("28000")),
            make_expense_record(category="food", amount=Decimal("20000")),
        ]
        expenses = make_monthly_expenses(
            year=2024,
            month=6,
            records=records,
        )

        assert expenses.year == 2024
        assert expenses.month == 6
        assert len(expenses.records) == 2
        assert expenses.total() == Decimal("48000")

    def test_is_valid_monthly_expenses(self):
        """建立的實例應為有效的 MonthlyExpenses"""
        expenses = make_monthly_expenses()
        assert isinstance(expenses, MonthlyExpenses)


class TestMakeMonthlyIncome:
    """測試 make_monthly_income 工廠函式"""

    def test_default_values(self):
        """預設值應正確"""
        income = make_monthly_income()

        assert income.schema_version == CURRENT_SCHEMA_VERSION
        assert len(income.sources) == 2
        assert income.total_monthly() == 80000.0  # 60000 + 20000

    def test_default_sources_content(self):
        """預設收入來源內容應正確"""
        income = make_monthly_income()

        # 主要薪資
        main_salary = income.sources[0]
        assert main_salary.name == "主要薪資"
        assert main_salary.amount == 60000.0
        assert main_salary.frequency == "monthly"
        assert main_salary.owner == "person_a"

        # 副業收入
        side_income = income.sources[1]
        assert side_income.name == "副業收入"
        assert side_income.amount == 20000.0
        assert side_income.frequency == "monthly"
        assert side_income.owner == "person_b"

    def test_override_sources(self):
        """覆寫 sources 應正確"""
        custom_sources = [
            IncomeSource(name="Salary", amount=100000, owner="person_a"),
        ]
        income = make_monthly_income(sources=custom_sources)

        assert len(income.sources) == 1
        assert income.total_monthly() == 100000.0

    def test_is_valid_monthly_income(self):
        """建立的實例應為有效的 MonthlyIncome"""
        income = make_monthly_income()
        assert isinstance(income, MonthlyIncome)


class TestMakeLifeAssumptions:
    """測試 make_life_assumptions 工廠函式"""

    def test_default_values(self):
        """預設值應正確"""
        assumptions = make_life_assumptions()

        assert assumptions.schema_version == CURRENT_SCHEMA_VERSION
        assert assumptions.metadata.currency == Currency.TWD
        assert assumptions.metadata.base_year == datetime.now().year
        # V1.2: 使用 members 結構
        assert assumptions.basic.primary_member == "person_a"
        assert "person_a" in assumptions.members
        assert assumptions.members["person_a"].birth_year == 1981
        assert assumptions.get_current_age() == datetime.now().year - 1981  # 動態年齡
        assert assumptions.get_retirement_age() == 65
        assert assumptions.get_expected_lifespan() == 85
        assert assumptions.rates.mode == RatesMode.NOMINAL
        assert assumptions.rates.annual_inflation == 0.02
        assert assumptions.rates.nominal_investment_return == 0.05
        assert assumptions.calculation.scale == 0
        assert assumptions.calculation.rounding == RoundingMethod.ROUND_HALF_UP
        assert assumptions.calculation.rounding_stage == RoundingStage.FINAL
        assert assumptions.family.children == []

    def test_override_members(self):
        """覆寫 members 應正確（V1.2）"""
        from tests.fixtures.factory import make_member

        custom_members = {
            "person_a": make_member(
                display_name="Custom Person A",
                birth_year=1984,
                retirement_age=60,
                expected_lifespan=90,
            ),
        }
        assumptions = make_life_assumptions(members=custom_members)

        assert assumptions.get_current_age() == datetime.now().year - 1984  # 覆寫為 1984
        assert assumptions.get_retirement_age() == 60
        assert assumptions.get_expected_lifespan() == 90
        assert assumptions.members["person_a"].display_name == "Custom Person A"

    def test_override_rates_to_real_mode(self):
        """覆寫 rates 為 real mode 應正確"""
        from life_capital.models.assumptions import Rates

        custom_rates = Rates(
            mode=RatesMode.REAL,
            annual_inflation=0.025,
            real_investment_return=0.03,
        )
        assumptions = make_life_assumptions(rates=custom_rates)

        assert assumptions.rates.mode == RatesMode.REAL
        assert assumptions.rates.annual_inflation == 0.025
        assert assumptions.rates.real_investment_return == 0.03


class TestMakeIncomeSource:
    """測試 make_income_source 工廠函式"""

    def test_default_values(self):
        """預設值應正確"""
        source = make_income_source()

        assert source.name == "預設收入"
        assert source.amount == 50000.0
        assert source.frequency == "monthly"
        assert source.owner == "shared"
        assert source.notes is None

    def test_override_values(self):
        """覆寫值應正確"""
        source = make_income_source(
            name="年終獎金",
            amount=120000,
            frequency="yearly",
            owner="person_a",
            notes="固定",
        )

        assert source.name == "年終獎金"
        assert source.amount == 120000
        assert source.frequency == "yearly"
        assert source.owner == "person_a"
        assert source.notes == "固定"


class TestMakeChild:
    """測試 make_child 工廠函式"""

    def test_default_values(self):
        """預設值應正確"""
        child = make_child()

        assert child.name == "子女"
        assert child.birth_year == datetime.now().year - 5  # 預設 5 歲
        assert child.university_start_age == 18
        assert child.financial_independence_age == 25

    def test_override_values(self):
        """覆寫值應正確"""
        child = make_child(
            name="Alice",
            birth_year=2015,
            university_start_age=19,
            financial_independence_age=26,
        )

        assert child.name == "Alice"
        assert child.birth_year == 2015
        assert child.university_start_age == 19
        assert child.financial_independence_age == 26


class TestMakeBasic:
    """測試 make_basic 工廠函式（V1.2 結構）"""

    def test_default_values(self):
        """預設值應正確（V1.2: 只有 primary_member）"""
        basic = make_basic()

        assert basic.primary_member == "person_a"
        # V1.2 結構不應有 legacy 欄位
        assert basic.current_age is None
        assert basic.retirement_age is None
        assert basic.expected_lifespan is None

    def test_override_values(self):
        """覆寫值應正確"""
        basic = make_basic(primary_member="person_b")

        assert basic.primary_member == "person_b"


class TestMakeBasicLegacy:
    """測試 make_basic_legacy 工廠函式（V1.1 結構，用於遷移測試）"""

    def test_default_values(self):
        """預設值應正確（V1.1 legacy 結構）"""
        from tests.fixtures.factory import make_basic_legacy

        basic = make_basic_legacy()

        assert basic.current_age == 35
        assert basic.retirement_age == 65
        assert basic.expected_lifespan == 85
        assert basic.primary_member is None

    def test_override_values(self):
        """覆寫值應正確"""
        from tests.fixtures.factory import make_basic_legacy

        basic = make_basic_legacy(
            current_age=40,
            retirement_age=60,
            expected_lifespan=90,
        )

        assert basic.current_age == 40
        assert basic.retirement_age == 60
        assert basic.expected_lifespan == 90


class TestMakeRates:
    """測試 make_rates 工廠函式"""

    def test_default_values(self):
        """預設值應正確"""
        rates = make_rates()

        assert rates.mode == RatesMode.NOMINAL
        assert rates.annual_inflation == 0.02
        assert rates.nominal_investment_return == 0.05
        assert rates.real_investment_return is None

    def test_override_to_real_mode(self):
        """覆寫為 real mode 應正確"""
        rates = make_rates(
            mode=RatesMode.REAL,
            real_investment_return=0.03,
        )

        assert rates.mode == RatesMode.REAL
        assert rates.real_investment_return == 0.03


class TestMakeCalculation:
    """測試 make_calculation 工廠函式"""

    def test_default_values(self):
        """預設值應正確"""
        calc = make_calculation()

        assert calc.scale == 0
        assert calc.rounding == RoundingMethod.ROUND_HALF_UP
        assert calc.rounding_stage == RoundingStage.FINAL

    def test_override_values(self):
        """覆寫值應正確"""
        calc = make_calculation(
            scale=2,
            rounding_stage=RoundingStage.PER_PERIOD,
        )

        assert calc.scale == 2
        assert calc.rounding_stage == RoundingStage.PER_PERIOD
