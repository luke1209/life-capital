"""Factory pattern 輔助函式

提供快速建立測試用 Pydantic 模型實例的工廠函式。
所有函式提供合理預設值，可透過 kwargs 部分或完全覆寫。
"""

from datetime import date, datetime
from decimal import Decimal

from life_capital.io.registry import CURRENT_SCHEMA_VERSION
from life_capital.models.assumptions import (
    Basic,
    Calculation,
    Child,
    Currency,
    Family,
    LifeAssumptions,
    Member,
    Metadata,
    Rates,
    RatesMode,
    RoundingMethod,
    RoundingStage,
)
from life_capital.models.expense import ExpenseRecord, MonthlyExpenses
from life_capital.models.income import IncomeSource, MonthlyIncome


def make_expense_record(**kwargs) -> ExpenseRecord:
    """建立單筆支出記錄

    預設值:
        - date: 今天
        - amount: 1000
        - category: "food"
        - payer: "shared"
        - note: None
        - merchant: None

    使用範例:
        >>> record = make_expense_record()
        >>> record = make_expense_record(amount=Decimal("500"), payer="person_a")
        >>> record = make_expense_record(category="housing", amount=Decimal("28000"))

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        ExpenseRecord 實例
    """
    defaults = {
        "date": date.today(),
        "amount": Decimal("1000"),
        "category": "food",
        "payer": "shared",
        "note": None,
        "merchant": None,
    }
    defaults.update(kwargs)
    return ExpenseRecord(**defaults)


def make_monthly_expenses(**kwargs) -> MonthlyExpenses:
    """建立月度支出集合

    預設值:
        - schema_version: CURRENT_SCHEMA_VERSION (from registry)
        - year: 當前年份
        - month: 12
        - records: [] (空列表)

    使用範例:
        >>> expenses = make_monthly_expenses()
        >>> expenses = make_monthly_expenses(
        ...     year=2024, month=6,
        ...     records=[
        ...         make_expense_record(category="housing", amount=Decimal("28000")),
        ...         make_expense_record(category="food", amount=Decimal("20000")),
        ...     ]
        ... )

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        MonthlyExpenses 實例
    """
    defaults = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "year": datetime.now().year,
        "month": 12,
        "records": [],
    }
    defaults.update(kwargs)
    return MonthlyExpenses(**defaults)


def make_monthly_income(**kwargs) -> MonthlyIncome:
    """建立月收入資料

    預設值:
        - schema_version: CURRENT_SCHEMA_VERSION (from registry)
        - sources: [主要薪資 60000 (person_a), 副業收入 20000 (person_b)]

    使用範例:
        >>> income = make_monthly_income()
        >>> income = make_monthly_income(sources=[
        ...     IncomeSource(name="Salary", amount=100000, owner="person_a"),
        ... ])

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        MonthlyIncome 實例
    """
    default_sources = [
        IncomeSource(
            name="主要薪資",
            amount=60000.0,
            frequency="monthly",
            owner="person_a",
            notes="全職工作",
        ),
        IncomeSource(
            name="副業收入",
            amount=20000.0,
            frequency="monthly",
            owner="person_b",
            notes="兼職/接案",
        ),
    ]

    defaults = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "sources": default_sources,
    }
    defaults.update(kwargs)
    return MonthlyIncome(**defaults)


def make_member(**kwargs) -> Member:
    """建立成員資料（V1.2 新增）

    預設值:
        - display_name: "Person A"
        - birth_year: 1990 (base_year 2024 時 43 歲)
        - retirement_age: 65
        - expected_lifespan: 85
        - birth_year_estimated: False

    使用範例:
        >>> member = make_member()
        >>> member = make_member(display_name="Person B", birth_year=1993)
        >>> member = make_member(retirement_age=90, expected_lifespan=95)

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        Member 實例
    """
    defaults = {
        "display_name": "Person A",
        "birth_year": 1981,
        "retirement_age": 65,
        "expected_lifespan": 85,
        "birth_year_estimated": False,
    }
    defaults.update(kwargs)
    return Member(**defaults)


def make_life_assumptions(**kwargs) -> LifeAssumptions:
    """建立生活假設資料（V1.2 members 結構）

    預設值:
        - schema_version: CURRENT_SCHEMA_VERSION (from registry)
        - metadata: Currency.TWD, base_year=當前年份（動態）
        - basic: primary_member="person_a"
        - members: person_a (birth_year=1981, 65歲退休, 85歲壽命)
        - rates: mode=nominal, annual_inflation=0.02, nominal_investment_return=0.05
        - calculation: scale=0, rounding=ROUND_HALF_UP, rounding_stage=FINAL
        - family: children=[]

    注意：base_year 為動態當前年份，current_age 會隨時間增加
    - 2024 年執行：current_age = 35
    - 2025 年執行：current_age = 36

    使用範例:
        >>> assumptions = make_life_assumptions()
        >>> assumptions = make_life_assumptions(
        ...     members={"person_a": make_member(retirement_age=90)}
        ... )
        >>> assumptions = make_life_assumptions(
        ...     rates=Rates(
        ...         mode=RatesMode.REAL,
        ...         annual_inflation=0.025,
        ...         real_investment_return=0.03
        ...     )
        ... )

    Args:
        **kwargs: 覆寫預設值的欄位（可覆寫整個子模型或個別欄位）

    Returns:
        LifeAssumptions 實例
    """
    defaults = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "metadata": Metadata(
            currency=Currency.TWD,
            base_year=datetime.now().year,  # 動態：當前年份
        ),
        "basic": Basic(
            primary_member="person_a",
        ),
        "members": {
            "person_a": Member(
                display_name="Person A",
                birth_year=1981,  # 固定：真實出生年份
                retirement_age=65,
                expected_lifespan=85,
            ),
        },
        "rates": Rates(
            mode=RatesMode.NOMINAL,
            annual_inflation=0.02,
            nominal_investment_return=0.05,
        ),
        "calculation": Calculation(
            scale=0,
            rounding=RoundingMethod.ROUND_HALF_UP,
            rounding_stage=RoundingStage.FINAL,
        ),
        "family": Family(children=[]),
    }
    defaults.update(kwargs)
    return LifeAssumptions(**defaults)


def make_income_source(**kwargs) -> IncomeSource:
    """建立單一收入來源

    預設值:
        - name: "預設收入"
        - amount: 50000.0
        - frequency: "monthly"
        - owner: "shared"
        - notes: None

    使用範例:
        >>> source = make_income_source()
        >>> source = make_income_source(name="年終獎金", amount=120000, frequency="yearly")

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        IncomeSource 實例
    """
    defaults = {
        "name": "預設收入",
        "amount": 50000.0,
        "frequency": "monthly",
        "owner": "shared",
        "notes": None,
    }
    defaults.update(kwargs)
    return IncomeSource(**defaults)


def make_child(**kwargs) -> Child:
    """建立子女資訊

    預設值:
        - name: "子女"
        - birth_year: 當前年份 - 5 (5歲)
        - university_start_age: 18
        - financial_independence_age: 25

    使用範例:
        >>> child = make_child()
        >>> child = make_child(name="Alice", birth_year=2015)

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        Child 實例
    """
    defaults = {
        "name": "子女",
        "birth_year": datetime.now().year - 5,  # 預設 5 歲
        "university_start_age": 18,
        "financial_independence_age": 25,
    }
    defaults.update(kwargs)
    return Child(**defaults)


def make_basic(**kwargs) -> Basic:
    """建立基本資訊（V1.2 結構）

    預設值:
        - primary_member: "person_a"

    使用範例:
        >>> basic = make_basic()
        >>> basic = make_basic(primary_member="person_b")

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        Basic 實例
    """
    defaults = {
        "primary_member": "person_a",
    }
    defaults.update(kwargs)
    return Basic(**defaults)


def make_basic_legacy(**kwargs) -> Basic:
    """建立基本資訊（V1.1 legacy 結構，用於遷移測試）

    預設值:
        - current_age: 35
        - retirement_age: 65
        - expected_lifespan: 85

    使用範例:
        >>> basic = make_basic_legacy()
        >>> basic = make_basic_legacy(current_age=40, retirement_age=60)

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        Basic 實例（V1.1 結構）
    """
    defaults = {
        "current_age": 35,
        "retirement_age": 65,
        "expected_lifespan": 85,
    }
    defaults.update(kwargs)
    return Basic(**defaults)


def make_rates(**kwargs) -> Rates:
    """建立利率設定

    預設值:
        - mode: RatesMode.NOMINAL
        - annual_inflation: 0.02
        - nominal_investment_return: 0.05
        - real_investment_return: None

    使用範例:
        >>> rates = make_rates()
        >>> rates = make_rates(mode=RatesMode.REAL, real_investment_return=0.03)

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        Rates 實例
    """
    defaults = {
        "mode": RatesMode.NOMINAL,
        "annual_inflation": 0.02,
        "nominal_investment_return": 0.05,
        "real_investment_return": None,
    }
    defaults.update(kwargs)
    return Rates(**defaults)


def make_calculation(**kwargs) -> Calculation:
    """建立計算設定

    預設值:
        - scale: 0 (元)
        - rounding: ROUND_HALF_UP
        - rounding_stage: FINAL

    使用範例:
        >>> calc = make_calculation()
        >>> calc = make_calculation(scale=2, rounding_stage=RoundingStage.PER_PERIOD)

    Args:
        **kwargs: 覆寫預設值的欄位

    Returns:
        Calculation 實例
    """
    defaults = {
        "scale": 0,
        "rounding": RoundingMethod.ROUND_HALF_UP,
        "rounding_stage": RoundingStage.FINAL,
    }
    defaults.update(kwargs)
    return Calculation(**defaults)
