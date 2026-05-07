"""Rounding Policy 模組

從 assumptions 讀取設定，提供統一的金額量化入口。
確保所有金額計算使用一致的捨入策略。
"""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from typing import Union

from life_capital.models.assumptions import (
    Calculation,
    RoundingMethod,
    RoundingStage,
)

# 預設設定（當無法取得 assumptions 時使用）
DEFAULT_SCALE = 0
DEFAULT_ROUNDING = ROUND_HALF_UP
DEFAULT_STAGE = RoundingStage.FINAL


class RoundingConfig:
    """Rounding 設定封裝

    從 Calculation model 建立，提供量化方法。
    """

    def __init__(
        self,
        scale: int = DEFAULT_SCALE,
        rounding: RoundingMethod = RoundingMethod.ROUND_HALF_UP,
        stage: RoundingStage = RoundingStage.FINAL,
    ):
        self.scale = scale
        self.rounding_method = rounding
        self.stage = stage

        # 建立 quantize 用的 Decimal pattern
        if scale == 0:
            self._quantize_exp = Decimal("1")
        else:
            self._quantize_exp = Decimal(10) ** -scale

        # 轉換 rounding method
        self._rounding = (
            ROUND_HALF_UP
            if rounding == RoundingMethod.ROUND_HALF_UP
            else ROUND_HALF_EVEN
        )

    @classmethod
    def from_calculation(cls, calc: Calculation) -> "RoundingConfig":
        """從 Calculation model 建立"""
        return cls(
            scale=calc.scale,
            rounding=calc.rounding,
            stage=calc.rounding_stage,
        )

    @classmethod
    def default(cls) -> "RoundingConfig":
        """建立預設設定"""
        return cls()

    def quantize(self, value: Union[Decimal, float, int, str]) -> Decimal:
        """量化金額

        Args:
            value: 金額數值（建議傳入 Decimal）

        Returns:
            量化後的 Decimal
        """
        if not isinstance(value, Decimal):
            value = Decimal(str(value))

        return value.quantize(self._quantize_exp, rounding=self._rounding)

    def should_round_at(self, stage: RoundingStage) -> bool:
        """判斷是否應該在指定階段執行 rounding

        Args:
            stage: 目前的計算階段

        Returns:
            是否應該執行 rounding
        """
        if self.stage == RoundingStage.FINAL:
            return stage == RoundingStage.FINAL
        elif self.stage == RoundingStage.PER_YEAR:
            return stage in (RoundingStage.PER_YEAR, RoundingStage.FINAL)
        else:  # PER_PERIOD
            return True

    def __repr__(self) -> str:
        return (
            f"RoundingConfig(scale={self.scale}, "
            f"rounding={self.rounding_method.value}, "
            f"stage={self.stage.value})"
        )


def quantize_amount(
    value: Union[Decimal, float, int, str],
    config: RoundingConfig,
) -> Decimal:
    """量化金額的便捷函式

    Args:
        value: 金額數值
        config: Rounding 設定

    Returns:
        量化後的 Decimal
    """
    return config.quantize(value)


def to_decimal(value: Union[Decimal, float, int, str]) -> Decimal:
    """轉換為 Decimal

    這是進入 calculators 層的標準入口。
    所有外部數值都應該先經過此函式轉換。

    Args:
        value: 任意數值

    Returns:
        Decimal 表示

    Raises:
        ValueError: 無法轉換的數值
    """
    if isinstance(value, Decimal):
        return value

    try:
        # 使用 str 中介轉換，避免 float 精度問題
        return Decimal(str(value))
    except Exception as e:
        raise ValueError(f"無法轉換為 Decimal: {value}") from e


def ensure_decimal(value: Union[Decimal, float, int, str]) -> Decimal:
    """確保數值為 Decimal（to_decimal 的別名）

    提供語意更清晰的函式名稱。
    """
    return to_decimal(value)
