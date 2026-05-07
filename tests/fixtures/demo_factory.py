"""Factory 模組使用示範

展示如何使用 factory.py 中的工廠函式快速建立測試資料。
"""

from decimal import Decimal

from tests.fixtures.factory import (
    make_expense_record,
    make_life_assumptions,
    make_monthly_expenses,
    make_monthly_income,
    make_rates,
)


def demo_expense_record():
    """示範建立支出記錄"""
    print("\n=== 示範 1: 建立支出記錄 ===")

    # 使用預設值
    record1 = make_expense_record()
    print(f"預設記錄: {record1.date}, {record1.category}, ${record1.amount}, {record1.payer}")

    # 部分覆寫
    record2 = make_expense_record(
        category="housing",
        amount=Decimal("28000"),
        payer="shared",
    )
    print(f"房租記錄: {record2.date}, {record2.category}, ${record2.amount}, {record2.payer}")

    # 包含退款
    record3 = make_expense_record(
        category="shopping",
        amount=Decimal("-500"),
        note="退款",
    )
    print(
        f"退款記錄: {record3.date}, {record3.category}, "
        f"${record3.amount}, 是否退款={record3.is_refund()}"
    )


def demo_monthly_expenses():
    """示範建立月度支出"""
    print("\n=== 示範 2: 建立月度支出 ===")

    expenses = make_monthly_expenses(
        year=2024,
        month=6,
        records=[
            make_expense_record(category="housing", amount=Decimal("28000"), payer="shared"),
            make_expense_record(category="food", amount=Decimal("12000"), payer="person_a"),
            make_expense_record(category="food", amount=Decimal("8000"), payer="person_b"),
            make_expense_record(category="utilities", amount=Decimal("2650"), payer="shared"),
            make_expense_record(category="shopping", amount=Decimal("-500"), payer="shared"),
        ],
    )

    print("2024-06 支出統計:")
    print(f"  總支出: ${expenses.total()}")
    print(f"  支出筆數: {expenses.expense_count()}")
    print(f"  退款筆數: {expenses.refund_count()}")

    print("\n  依類別統計:")
    for category, amount in expenses.by_category().items():
        print(f"    {category}: ${amount}")

    print("\n  依支付者統計:")
    for payer, amount in expenses.by_payer().items():
        print(f"    {payer}: ${amount}")


def demo_monthly_income():
    """示範建立月收入"""
    print("\n=== 示範 3: 建立月收入 ===")

    # 使用預設值
    income1 = make_monthly_income()
    print(f"預設月收入: ${income1.total_monthly():.0f}")
    print(f"  來源數量: {len(income1.sources)}")
    for source in income1.sources:
        print(f"    {source.name}: ${source.amount:.0f} ({source.owner})")

    print("\n  依擁有者統計:")
    for owner, amount in income1.by_owner().items():
        print(f"    {owner}: ${amount:.0f}")


def demo_life_assumptions():
    """示範建立生活假設"""
    print("\n=== 示範 4: 建立生活假設 ===")

    # 使用預設值（nominal mode）
    assumptions1 = make_life_assumptions()
    print("預設假設 (nominal mode):")
    print(f"  當前年齡: {assumptions1.basic.current_age}")
    print(f"  退休年齡: {assumptions1.basic.retirement_age}")
    print(f"  預期壽命: {assumptions1.basic.expected_lifespan}")
    print(f"  通膨率: {assumptions1.rates.annual_inflation * 100}%")
    print(f"  投資報酬率: {assumptions1.rates.get_investment_return() * 100}%")
    print(f"  捨入精度: {assumptions1.calculation.scale} 位小數")

    # 切換為 real mode
    from life_capital.models.assumptions import RatesMode

    assumptions2 = make_life_assumptions(
        rates=make_rates(
            mode=RatesMode.REAL,
            annual_inflation=0.025,
            real_investment_return=0.03,
        )
    )
    print("\n實質模式 (real mode):")
    print(f"  模式: {assumptions2.rates.mode.value}")
    print(f"  通膨率: {assumptions2.rates.annual_inflation * 100}%")
    print(f"  實質報酬率: {assumptions2.rates.get_investment_return() * 100}%")


def main():
    """執行所有示範"""
    print("=" * 60)
    print("Factory 模組使用示範")
    print("=" * 60)

    demo_expense_record()
    demo_monthly_expenses()
    demo_monthly_income()
    demo_life_assumptions()

    print("\n" + "=" * 60)
    print("示範完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
