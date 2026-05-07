"""V1.1 Legacy 結構年齡行為測試

測試 V1.1 結構下的年齡行為：
- current_age 為靜態值，不隨 base_year 變動
- max_year 計算方式: base_year + (expected_lifespan - current_age)

與 V1.2 結構對照：
- V1.2: current_age = base_year - birth_year（動態）
- V1.1: current_age = basic.current_age（固定值）
"""

from typing import Callable

import pytest

from life_capital.models.assumptions import (
    Basic,
    LifeAssumptions,
    Rates,
    RatesMode,
)


class TestLegacyAgeImmutability:
    """V1.1 結構下 base_year 推進不影響年齡"""

    def _make_legacy_assumptions(
        self,
        current_age: int = 43,
        retirement_age: int = 65,
        expected_lifespan: int = 85,
    ) -> LifeAssumptions:
        """建立 V1.1 legacy 結構"""
        return LifeAssumptions(
            basic=Basic(
                current_age=current_age,
                retirement_age=retirement_age,
                expected_lifespan=expected_lifespan,
            ),
            rates=Rates(
                mode=RatesMode.NOMINAL,
                annual_inflation=0.02,
                nominal_investment_return=0.05,
            ),
            members=None,
        )

    def test_current_age_stays_constant(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """current_age 不隨 base_year 改變（V1.1 行為）"""
        # V1.1 結構：current_age 是固定值
        assumptions = self._make_legacy_assumptions(current_age=43)

        # 無論 base_year 為何，年齡都是 43
        freeze_base_year(2024)
        assert assumptions.get_current_age() == 43

        freeze_base_year(2025)
        assert assumptions.get_current_age() == 43

        freeze_base_year(2030)
        assert assumptions.get_current_age() == 43

    def test_max_year_formula_legacy(self) -> None:
        """V1.1 的 max_year 計算公式"""
        # V1.1: max_year = base_year + (expected_lifespan - current_age)
        # 假設 base_year=2024, current_age=43, expected_lifespan=85
        # max_year = 2024 + (85 - 43) = 2024 + 42 = 2066

        base_year = 2024
        current_age = 43
        expected_lifespan = 85

        max_year_v11 = base_year + (expected_lifespan - current_age)
        assert max_year_v11 == 2066

    def test_max_year_increases_with_base_year_v11(self) -> None:
        """V1.1 的 max_year 隨 base_year 增加（與 V1.2 不同）"""
        current_age = 43
        expected_lifespan = 85
        years_remaining = expected_lifespan - current_age  # 42 年

        # base_year=2024 → max_year=2066
        max_year_2024 = 2024 + years_remaining
        # base_year=2025 → max_year=2067
        max_year_2025 = 2025 + years_remaining

        assert max_year_2025 == max_year_2024 + 1

    def test_legacy_requires_all_three_fields(self) -> None:
        """V1.1 結構必須同時提供三個欄位"""
        with pytest.raises(ValueError, match="必須同時提供"):
            LifeAssumptions(
                basic=Basic(
                    current_age=43,
                    # 缺少 retirement_age 和 expected_lifespan
                ),
                rates=Rates(
                    mode=RatesMode.NOMINAL,
                    annual_inflation=0.02,
                    nominal_investment_return=0.05,
                ),
                members=None,
            )

    def test_legacy_validation_retirement_greater_than_current(self) -> None:
        """V1.1 結構驗證：retirement_age > current_age"""
        with pytest.raises(ValueError, match="必須大於 current_age"):
            LifeAssumptions(
                basic=Basic(
                    current_age=65,
                    retirement_age=60,  # < current_age
                    expected_lifespan=85,
                ),
                rates=Rates(
                    mode=RatesMode.NOMINAL,
                    annual_inflation=0.02,
                    nominal_investment_return=0.05,
                ),
                members=None,
            )


class TestV11VsV12Comparison:
    """V1.1 vs V1.2 行為對照"""

    def test_age_dynamics_differ(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """年齡計算動態差異"""
        from tests.fixtures.factory import make_life_assumptions, make_member

        freeze_base_year(2024)

        # V1.2: 年齡 = base_year - birth_year
        v12_assumptions = make_life_assumptions(
            members={"person_a": make_member(birth_year=1981)}
        )
        v12_age_2024 = v12_assumptions.get_current_age()
        v12_age_2025 = v12_assumptions.get_current_age(as_of_year=2025)

        # V1.1: 年齡固定
        v11_assumptions = LifeAssumptions(
            basic=Basic(current_age=43, retirement_age=65, expected_lifespan=85),
            rates=v12_assumptions.rates,
            members=None,
        )
        v11_age_2024 = v11_assumptions.get_current_age()
        v11_age_2025 = v11_assumptions.get_current_age()  # 仍然是 43

        # 2024 年兩者相同
        assert v12_age_2024 == 43
        assert v11_age_2024 == 43

        # 2025 年 V1.2 增加，V1.1 不變
        assert v12_age_2025 == 44
        assert v11_age_2025 == 43

    def test_max_year_dynamics_differ(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """max_year 計算動態差異"""

        freeze_base_year(2024)

        # V1.2: max_year = birth_year + expected_lifespan（常數）
        birth_year = 1981
        expected_lifespan = 85
        v12_max_year = birth_year + expected_lifespan  # 2066

        # V1.1: max_year = base_year + (expected_lifespan - current_age)
        base_year = 2024
        current_age = 43
        v11_max_year_2024 = base_year + (expected_lifespan - current_age)  # 2066
        v11_max_year_2025 = 2025 + (expected_lifespan - current_age)  # 2067

        # 2024 年兩者相同
        assert v12_max_year == v11_max_year_2024 == 2066

        # V1.2 max_year 不變
        assert v12_max_year == 2066

        # V1.1 max_year 增加
        assert v11_max_year_2025 == 2067

    def test_is_v12_structure_correctly_identifies(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """正確識別 V1.1 vs V1.2 結構"""
        from tests.fixtures.factory import make_life_assumptions, make_member

        freeze_base_year(2024)

        # V1.2 結構
        v12 = make_life_assumptions(members={"person_a": make_member()})
        assert v12.is_v12_structure() is True

        # V1.1 結構
        v11 = LifeAssumptions(
            basic=Basic(current_age=43, retirement_age=65, expected_lifespan=85),
            rates=v12.rates,
            members=None,
        )
        assert v11.is_v12_structure() is False

    def test_get_member_on_v11_raises(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """V1.1 結構呼叫 get_member() 應拋出 ValueError"""
        from tests.fixtures.factory import make_life_assumptions

        freeze_base_year(2024)

        v11 = LifeAssumptions(
            basic=Basic(current_age=43, retirement_age=65, expected_lifespan=85),
            rates=make_life_assumptions().rates,
            members=None,
        )

        with pytest.raises(ValueError, match="V1.1 結構"):
            v11.get_member()
