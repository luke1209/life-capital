"""Rounding 模組測試

測試範圍:
- to_decimal 轉換
- RoundingConfig 量化
- 各種 rounding method 與 scale 組合
"""

from decimal import Decimal

import pytest

from life_capital.calculators.rounding import (
    DEFAULT_SCALE,
    RoundingConfig,
    ensure_decimal,
    quantize_amount,
    to_decimal,
)
from life_capital.models.assumptions import (
    Calculation,
    RoundingMethod,
    RoundingStage,
)


class TestToDecimal:
    """to_decimal 轉換測試"""

    def test_from_int(self):
        """整數轉換"""
        assert to_decimal(100) == Decimal("100")
        assert to_decimal(0) == Decimal("0")
        assert to_decimal(-50) == Decimal("-50")

    def test_from_float(self):
        """浮點數轉換（透過 str 避免精度問題）"""
        result = to_decimal(0.1)
        assert result == Decimal("0.1")
        # 確保不是 0.1000000000000000055511151231257827021181583404541015625
        assert str(result) == "0.1"

    def test_from_str(self):
        """字串轉換"""
        assert to_decimal("123.45") == Decimal("123.45")
        assert to_decimal("-999.99") == Decimal("-999.99")
        assert to_decimal("0") == Decimal("0")

    def test_from_decimal(self):
        """Decimal 直接返回"""
        d = Decimal("123.456")
        assert to_decimal(d) is d  # 應該是同一個物件

    def test_invalid_value(self):
        """無效值應拋出 ValueError"""
        with pytest.raises(ValueError, match="無法轉換為 Decimal"):
            to_decimal("invalid")

        with pytest.raises(ValueError, match="無法轉換為 Decimal"):
            to_decimal("abc123")

    def test_ensure_decimal_alias(self):
        """ensure_decimal 是 to_decimal 的別名"""
        assert ensure_decimal(100) == to_decimal(100)
        assert ensure_decimal("123.45") == to_decimal("123.45")


class TestRoundingConfig:
    """RoundingConfig 測試"""

    def test_default_config(self):
        """預設設定"""
        config = RoundingConfig.default()
        assert config.scale == DEFAULT_SCALE
        assert config.rounding_method == RoundingMethod.ROUND_HALF_UP
        assert config.stage == RoundingStage.FINAL

    def test_from_calculation(self):
        """從 Calculation model 建立"""
        calc = Calculation(
            scale=2,
            rounding=RoundingMethod.ROUND_HALF_EVEN,
            rounding_stage=RoundingStage.PER_YEAR,
        )
        config = RoundingConfig.from_calculation(calc)
        assert config.scale == 2
        assert config.rounding_method == RoundingMethod.ROUND_HALF_EVEN
        assert config.stage == RoundingStage.PER_YEAR

    def test_scale_0_quantize(self):
        """scale=0 量化至整數"""
        config = RoundingConfig(scale=0)
        assert config.quantize(Decimal("123.45")) == Decimal("123")
        assert config.quantize(Decimal("123.50")) == Decimal("124")  # ROUND_HALF_UP
        assert config.quantize(Decimal("123.49")) == Decimal("123")

    def test_scale_2_quantize(self):
        """scale=2 量化至角分"""
        config = RoundingConfig(scale=2)
        assert config.quantize(Decimal("123.456")) == Decimal("123.46")
        assert config.quantize(Decimal("123.454")) == Decimal("123.45")
        assert config.quantize(Decimal("123.455")) == Decimal("123.46")  # ROUND_HALF_UP

    def test_round_half_up(self):
        """四捨五入（ROUND_HALF_UP）"""
        config = RoundingConfig(scale=0, rounding=RoundingMethod.ROUND_HALF_UP)
        assert config.quantize(Decimal("2.5")) == Decimal("3")
        assert config.quantize(Decimal("3.5")) == Decimal("4")
        assert config.quantize(Decimal("-2.5")) == Decimal("-3")

    def test_round_half_even(self):
        """銀行家捨入（ROUND_HALF_EVEN）"""
        config = RoundingConfig(scale=0, rounding=RoundingMethod.ROUND_HALF_EVEN)
        assert config.quantize(Decimal("2.5")) == Decimal("2")  # 捨入至偶數
        assert config.quantize(Decimal("3.5")) == Decimal("4")  # 捨入至偶數
        assert config.quantize(Decimal("4.5")) == Decimal("4")  # 捨入至偶數

    def test_quantize_from_various_types(self):
        """quantize 接受多種類型"""
        config = RoundingConfig(scale=0)
        assert config.quantize(100) == Decimal("100")
        assert config.quantize(100.5) == Decimal("101")
        assert config.quantize("100.5") == Decimal("101")

    def test_should_round_at_final(self):
        """rounding_stage=final 只在最後 round"""
        config = RoundingConfig(stage=RoundingStage.FINAL)
        assert config.should_round_at(RoundingStage.FINAL) is True
        assert config.should_round_at(RoundingStage.PER_YEAR) is False
        assert config.should_round_at(RoundingStage.PER_PERIOD) is False

    def test_should_round_at_per_year(self):
        """rounding_stage=per_year 在每年與最後 round"""
        config = RoundingConfig(stage=RoundingStage.PER_YEAR)
        assert config.should_round_at(RoundingStage.FINAL) is True
        assert config.should_round_at(RoundingStage.PER_YEAR) is True
        assert config.should_round_at(RoundingStage.PER_PERIOD) is False

    def test_should_round_at_per_period(self):
        """rounding_stage=per_period 在所有階段 round"""
        config = RoundingConfig(stage=RoundingStage.PER_PERIOD)
        assert config.should_round_at(RoundingStage.FINAL) is True
        assert config.should_round_at(RoundingStage.PER_YEAR) is True
        assert config.should_round_at(RoundingStage.PER_PERIOD) is True

    def test_repr(self):
        """__repr__ 輸出"""
        config = RoundingConfig(scale=2, rounding=RoundingMethod.ROUND_HALF_EVEN)
        repr_str = repr(config)
        assert "scale=2" in repr_str
        assert "ROUND_HALF_EVEN" in repr_str


class TestQuantizeAmount:
    """quantize_amount 便捷函式測試"""

    def test_basic_usage(self):
        """基本使用"""
        config = RoundingConfig(scale=0)
        assert quantize_amount(Decimal("123.45"), config) == Decimal("123")

    def test_with_various_types(self):
        """各種輸入類型"""
        config = RoundingConfig(scale=2)
        assert quantize_amount(100, config) == Decimal("100.00")
        assert quantize_amount(100.456, config) == Decimal("100.46")
        assert quantize_amount("100.456", config) == Decimal("100.46")


class TestEdgeCases:
    """邊緣情境測試"""

    def test_very_large_number(self):
        """極大數字"""
        config = RoundingConfig(scale=0)
        large = Decimal("999999999999999999.5")
        result = config.quantize(large)
        assert result == Decimal("1000000000000000000")

    def test_very_small_number(self):
        """極小數字"""
        config = RoundingConfig(scale=10)
        small = Decimal("0.00000000005")
        result = config.quantize(small)
        assert result == Decimal("0.0000000001")

    def test_negative_numbers(self):
        """負數"""
        config = RoundingConfig(scale=0)
        assert config.quantize(Decimal("-123.5")) == Decimal("-124")  # ROUND_HALF_UP
        assert config.quantize(Decimal("-123.4")) == Decimal("-123")

    def test_zero(self):
        """零值"""
        config = RoundingConfig(scale=2)
        assert config.quantize(Decimal("0")) == Decimal("0.00")
        assert config.quantize(0) == Decimal("0.00")
        assert config.quantize(0.0) == Decimal("0.00")

    def test_precision_preservation(self):
        """精度保持（避免浮點數問題）"""
        config = RoundingConfig(scale=10)
        # 0.1 + 0.2 在浮點數會有精度問題
        result = config.quantize(Decimal("0.1") + Decimal("0.2"))
        assert result == Decimal("0.3000000000")
