"""Lifetime 計算模組測試

測試範圍:
- FV (Future Value) 公式
- PV (Present Value) 公式
- PMT (Payment) 公式
- 名目/實質模式計算
- 邊緣情境 (r=0, n=0, 負利率)
"""

from decimal import Decimal

import pytest

from life_capital.calculators.lifetime import (
    LifetimeCalculation,
    TargetCalculation,
    annual_to_monthly_rate,
    calculate_fv,
    calculate_lifetime_needs,
    calculate_pmt,
    calculate_pmt_for_pv,
    calculate_pv,
    calculate_target,
    monthly_to_annual_rate,
    months_between,
    years_between,
)
from life_capital.calculators.rounding import RoundingConfig
from life_capital.models.assumptions import (
    Basic,
    Calculation,
    LifeAssumptions,
    Metadata,
    Rates,
    RatesMode,
)
from life_capital.models.targets import Priority, Target


class TestCalculateFV:
    """FV = PV × (1 + r)^n 測試"""

    def test_basic_calculation(self):
        """基本計算"""
        # 1,000,000 @ 2% for 10 years
        pv = Decimal("1000000")
        rate = Decimal("0.02")
        periods = 10
        result = calculate_fv(pv, rate, periods)

        # 預期: 1,000,000 × 1.02^10 ≈ 1,218,994.42
        # 使用近似比較，因 Decimal 精度可能因 Python 版本而異
        assert abs(result - Decimal("1218994.42")) < Decimal("0.01")

    def test_zero_rate(self):
        """零利率：FV = PV"""
        pv = Decimal("1000000")
        result = calculate_fv(pv, Decimal("0"), 10)
        assert result == pv

    def test_zero_periods(self):
        """零期數：FV = PV"""
        pv = Decimal("1000000")
        result = calculate_fv(pv, Decimal("0.05"), 0)
        assert result == pv

    def test_negative_periods(self):
        """負期數：FV = PV"""
        pv = Decimal("1000000")
        result = calculate_fv(pv, Decimal("0.05"), -5)
        assert result == pv

    def test_one_period(self):
        """單期：FV = PV × (1 + r)"""
        pv = Decimal("1000000")
        rate = Decimal("0.05")
        result = calculate_fv(pv, rate, 1)
        assert result == Decimal("1050000")

    def test_high_rate(self):
        """高利率（20%）"""
        pv = Decimal("1000000")
        rate = Decimal("0.20")
        periods = 5
        result = calculate_fv(pv, rate, periods)
        # 1,000,000 × 1.20^5 = 2,488,320
        expected = Decimal("2488320")
        assert result == expected

    def test_negative_rate(self):
        """負利率（通縮情境）"""
        pv = Decimal("1000000")
        rate = Decimal("-0.02")
        periods = 10
        result = calculate_fv(pv, rate, periods)
        # 1,000,000 × 0.98^10 ≈ 817,073.08...
        assert result < pv
        assert result > Decimal("0")


class TestCalculatePV:
    """PV = FV / (1 + r)^n 測試"""

    def test_basic_calculation(self):
        """基本計算"""
        # FV = 1,218,994.42, r = 2%, n = 10 → PV ≈ 1,000,000
        fv = Decimal("1218994.4199943574839281336200")
        rate = Decimal("0.02")
        periods = 10
        result = calculate_pv(fv, rate, periods)
        # 應該接近 1,000,000
        assert abs(result - Decimal("1000000")) < Decimal("0.01")

    def test_zero_rate(self):
        """零利率：PV = FV"""
        fv = Decimal("1000000")
        result = calculate_pv(fv, Decimal("0"), 10)
        assert result == fv

    def test_zero_periods(self):
        """零期數：PV = FV"""
        fv = Decimal("1000000")
        result = calculate_pv(fv, Decimal("0.05"), 0)
        assert result == fv

    def test_fv_pv_inverse(self):
        """FV 與 PV 互為反函數"""
        pv = Decimal("1000000")
        rate = Decimal("0.03")
        periods = 15

        fv = calculate_fv(pv, rate, periods)
        pv_back = calculate_pv(fv, rate, periods)

        assert abs(pv_back - pv) < Decimal("0.01")


class TestCalculatePMT:
    """PMT = FV × r / ((1 + r)^n - 1) 測試"""

    def test_basic_calculation(self):
        """基本計算"""
        # 目標 1,000,000，年利率 5%，10 年（120 個月）
        fv = Decimal("1000000")
        monthly_rate = Decimal("0.05") / Decimal("12")
        periods = 120  # 10 years

        result = calculate_pmt(fv, monthly_rate, periods)

        # 預期每月約 6,439.88
        assert result > Decimal("6000")
        assert result < Decimal("7000")

    def test_zero_rate(self):
        """零利率：PMT = FV / n"""
        fv = Decimal("1000000")
        periods = 120
        result = calculate_pmt(fv, Decimal("0"), periods)

        expected = fv / Decimal(periods)  # 8,333.33...
        assert result == expected

    def test_zero_periods(self):
        """零期數：需立即準備全額"""
        fv = Decimal("1000000")
        result = calculate_pmt(fv, Decimal("0.05"), 0)
        assert result == fv

    def test_negative_periods(self):
        """負期數：需立即準備全額"""
        fv = Decimal("1000000")
        result = calculate_pmt(fv, Decimal("0.05"), -5)
        assert result == fv

    def test_one_period(self):
        """單期：PMT = FV"""
        fv = Decimal("1000000")
        rate = Decimal("0.05")
        result = calculate_pmt(fv, rate, 1)
        assert result == fv

    def test_accumulation_verification(self):
        """驗證：PMT 累積應達到 FV"""
        fv = Decimal("1000000")
        monthly_rate = Decimal("0.05") / Decimal("12")
        periods = 120

        pmt = calculate_pmt(fv, monthly_rate, periods)

        # 模擬每月儲蓄累積
        accumulated = Decimal("0")
        for _ in range(periods):
            accumulated = accumulated * (1 + monthly_rate) + pmt

        # 應該接近目標 FV
        assert abs(accumulated - fv) < Decimal("0.01")

    def test_high_rate_short_period(self):
        """高利率短期"""
        fv = Decimal("100000")
        monthly_rate = Decimal("0.10") / Decimal("12")  # 年化 10%
        periods = 12  # 1 year

        result = calculate_pmt(fv, monthly_rate, periods)
        # 高利率讓 PMT 降低
        assert result < fv / Decimal(periods)


class TestCalculatePmtForPV:
    """貸款 PMT 公式測試"""

    def test_basic_loan(self):
        """基本貸款計算"""
        # 貸款 1,000,000，月利率 0.5%，120 期
        pv = Decimal("1000000")
        monthly_rate = Decimal("0.005")
        periods = 120

        result = calculate_pmt_for_pv(pv, monthly_rate, periods)

        # 應該是正數，比簡單除法大
        assert result > Decimal("0")
        assert result > pv / Decimal(periods)

    def test_zero_rate(self):
        """零利率：PMT = PV / n"""
        pv = Decimal("1000000")
        periods = 120
        result = calculate_pmt_for_pv(pv, Decimal("0"), periods)
        assert result == pv / Decimal(periods)

    def test_loan_payoff_verification(self):
        """驗證：PMT 還款應清償貸款"""
        pv = Decimal("1000000")
        monthly_rate = Decimal("0.005")
        periods = 120

        pmt = calculate_pmt_for_pv(pv, monthly_rate, periods)

        # 模擬還款
        balance = pv
        for _ in range(periods):
            interest = balance * monthly_rate
            principal = pmt - interest
            balance = balance - principal

        # 餘額應接近 0
        assert abs(balance) < Decimal("0.01")


class TestCalculateTarget:
    """單一目標計算測試"""

    def test_nominal_mode(self):
        """名目模式：通膨調整至目標年"""
        target = Target(
            name="測試目標",
            category="other",  # 使用有效的 category
            priority=Priority.HIGH,
            amount=1000000,
            target_year=2035,  # 使用未來年份
        )

        result = calculate_target(
            target=target,
            base_year=2025,
            inflation_rate=Decimal("0.02"),
            investment_return=Decimal("0.05"),
            mode=RatesMode.NOMINAL,
        )

        assert result.years_to_goal == 10
        assert result.months_to_goal == 120
        assert result.base_amount == Decimal("1000000")
        assert result.mode == RatesMode.NOMINAL

        # FV 應該大於 base_amount（通膨調整）
        assert result.future_value > result.base_amount

        # PMT 應該為正
        assert result.monthly_payment > Decimal("0")

    def test_real_mode(self):
        """實質模式：不調整通膨"""
        target = Target(
            name="測試目標",
            category="other",  # 使用有效的 category
            priority=Priority.HIGH,
            amount=1000000,
            target_year=2035,  # 使用未來年份
        )

        result = calculate_target(
            target=target,
            base_year=2025,
            inflation_rate=Decimal("0.02"),
            investment_return=Decimal("0.03"),  # 實質報酬率
            mode=RatesMode.REAL,
        )

        assert result.mode == RatesMode.REAL

        # FV 等於 base_amount（不調整通膨）
        assert result.future_value == result.base_amount

    def test_zero_years_to_goal(self):
        """目標年等於基準年：需立即準備全額"""
        # 直接建立 TargetCalculation 來測試邊緣情境
        # 因為 Target 模型會驗證 target_year > current_year
        target = Target(
            name="近期目標",
            category="other",
            priority=Priority.HIGH,
            amount=1000000,
            target_year=2026,  # 需要是未來年份
        )

        result = calculate_target(
            target=target,
            base_year=2026,  # 設定 base_year = target_year
            inflation_rate=Decimal("0.02"),
            investment_return=Decimal("0.05"),
            mode=RatesMode.NOMINAL,
        )

        assert result.years_to_goal == 0
        assert result.months_to_goal == 0
        # PMT = FV（需立即準備）
        assert result.monthly_payment == result.future_value


class TestCalculateLifetimeNeeds:
    """終身需求計算測試"""

    @pytest.fixture
    def sample_assumptions(self):
        """範例假設"""
        return LifeAssumptions(
            schema_version="1.1",
            metadata=Metadata(currency="TWD", base_year=2025),
            basic=Basic(
                current_age=35,
                expected_lifespan=90,
                retirement_age=65,
            ),
            rates=Rates(
                mode=RatesMode.NOMINAL,
                annual_inflation=0.02,
                nominal_investment_return=0.05,
            ),
            calculation=Calculation(
                scale=0,
                rounding="ROUND_HALF_UP",
                rounding_stage="final",
            ),
        )

    @pytest.fixture
    def sample_targets(self):
        """範例目標"""
        return [
            Target(
                name="房屋頭期款",
                category="housing",
                priority=Priority.HIGH,
                amount=3000000,
                target_year=2029,  # 4 years from 2025
            ),
            Target(
                name="退休金",
                category="retirement",
                priority=Priority.HIGH,
                amount=10000000,
                target_year=2055,  # 30 years from 2025
            ),
        ]

    def test_basic_calculation(self, sample_assumptions, sample_targets):
        """基本計算"""
        result = calculate_lifetime_needs(
            targets=sample_targets,
            assumptions=sample_assumptions,
        )

        assert isinstance(result, LifetimeCalculation)
        assert len(result.target_results) == 2
        assert result.mode == RatesMode.NOMINAL
        assert result.base_year == 2025

        # 彙總應為正數
        assert result.total_base_amount > Decimal("0")
        assert result.total_future_value > Decimal("0")
        assert result.total_monthly_payment > Decimal("0")

    def test_with_rounding(self, sample_assumptions, sample_targets):
        """套用 rounding"""
        rounding_config = RoundingConfig(scale=0)

        result = calculate_lifetime_needs(
            targets=sample_targets,
            assumptions=sample_assumptions,
            rounding_config=rounding_config,
        )

        # 結果應該是整數（scale=0）
        assert result.total_monthly_payment == result.total_monthly_payment.to_integral_value()

    def test_empty_targets(self, sample_assumptions):
        """空目標列表"""
        result = calculate_lifetime_needs(
            targets=[],
            assumptions=sample_assumptions,
        )

        assert len(result.target_results) == 0
        assert result.total_base_amount == Decimal("0")
        assert result.total_future_value == Decimal("0")
        assert result.total_monthly_payment == Decimal("0")

    def test_get_by_priority(self, sample_assumptions):
        """依優先級篩選"""
        targets = [
            Target(
                name="高優先",
                category="housing",  # 使用有效的 category
                priority=Priority.HIGH,
                amount=1000000,
                target_year=2030,
            ),
            Target(
                name="中優先",
                category="education",  # 使用有效的 category
                priority=Priority.MEDIUM,
                amount=500000,
                target_year=2035,
            ),
            Target(
                name="低優先",
                category="travel",  # 使用有效的 category
                priority=Priority.LOW,
                amount=200000,
                target_year=2040,
            ),
        ]

        result = calculate_lifetime_needs(
            targets=targets,
            assumptions=sample_assumptions,
        )

        high = result.get_by_priority("high")
        assert len(high) == 1
        assert high[0].target.name == "高優先"

        medium = result.get_by_priority("medium")
        assert len(medium) == 1

        low = result.get_by_priority("low")
        assert len(low) == 1

    def test_real_mode_calculation(self, sample_targets):
        """實質模式計算"""
        assumptions = LifeAssumptions(
            schema_version="1.1",
            metadata=Metadata(currency="TWD", base_year=2025),
            basic=Basic(
                current_age=35,
                expected_lifespan=90,
                retirement_age=65,
            ),
            rates=Rates(
                mode=RatesMode.REAL,
                annual_inflation=0.02,
                real_investment_return=0.03,
            ),
            calculation=Calculation(),
        )

        result = calculate_lifetime_needs(
            targets=sample_targets,
            assumptions=assumptions,
        )

        assert result.mode == RatesMode.REAL

        # 實質模式：FV = base_amount
        for tr in result.target_results:
            assert tr.future_value == tr.base_amount


class TestUtilityFunctions:
    """輔助函式測試"""

    def test_years_between(self):
        """年數計算"""
        assert years_between(2024, 2034) == 10
        assert years_between(2024, 2024) == 0
        assert years_between(2030, 2024) == 0  # 負數回傳 0

    def test_months_between(self):
        """月數計算"""
        assert months_between(2024, 2034) == 120
        assert months_between(2024, 2024) == 0
        assert months_between(2030, 2024) == 0

    def test_annual_to_monthly_rate(self):
        """年利率轉月利率"""
        annual = Decimal("0.12")
        monthly = annual_to_monthly_rate(annual)
        assert monthly == Decimal("0.01")

    def test_monthly_to_annual_rate(self):
        """月利率轉年利率"""
        monthly = Decimal("0.01")
        annual = monthly_to_annual_rate(monthly)
        assert annual == Decimal("0.12")


class TestTargetCalculationValidation:
    """TargetCalculation 驗證測試"""

    def test_negative_pmt_raises_error(self):
        """負 PMT 應拋出錯誤"""
        target = Target(
            name="測試",
            category="housing",  # 使用有效的 category
            priority=Priority.HIGH,
            amount=1000000,
            target_year=2030,
        )

        with pytest.raises(ValueError, match="monthly_payment 不能為負數"):
            TargetCalculation(
                target=target,
                years_to_goal=6,
                months_to_goal=72,
                base_amount=Decimal("1000000"),
                future_value=Decimal("1000000"),
                monthly_payment=Decimal("-100"),  # 負數
                mode=RatesMode.NOMINAL,
                investment_return=Decimal("0.05"),
            )


class TestEdgeCases:
    """邊緣情境測試"""

    def test_very_long_period(self):
        """極長期（50年）"""
        fv = Decimal("10000000")
        monthly_rate = Decimal("0.05") / Decimal("12")
        periods = 600  # 50 years

        pmt = calculate_pmt(fv, monthly_rate, periods)

        # 長期下 PMT 應該很低
        assert pmt < fv / Decimal(periods)

    def test_very_high_inflation(self):
        """高通膨（10%）"""
        pv = Decimal("1000000")
        rate = Decimal("0.10")
        periods = 30

        fv = calculate_fv(pv, rate, periods)

        # 30 年 10% 通膨，FV 應該非常大
        assert fv > pv * Decimal("10")

    def test_decimal_precision_maintained(self):
        """Decimal 精度維持"""
        # 使用精確的 Decimal 值
        pv = Decimal("1000000.123456789")
        rate = Decimal("0.02")
        periods = 10

        fv = calculate_fv(pv, rate, periods)
        pv_back = calculate_pv(fv, rate, periods)

        # 應該能完全還原
        assert pv_back == pv

    def test_small_amounts(self):
        """小金額"""
        fv = Decimal("100")  # 100 元
        monthly_rate = Decimal("0.05") / Decimal("12")
        periods = 12

        pmt = calculate_pmt(fv, monthly_rate, periods)

        # 應該正常計算
        assert pmt > Decimal("0")
        assert pmt < fv

    def test_large_amounts(self):
        """大金額"""
        fv = Decimal("1000000000000")  # 1 兆
        monthly_rate = Decimal("0.05") / Decimal("12")
        periods = 360  # 30 years

        pmt = calculate_pmt(fv, monthly_rate, periods)

        # 應該正常計算，無 overflow
        assert pmt > Decimal("0")
        assert pmt < fv
