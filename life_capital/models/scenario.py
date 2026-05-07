"""情境預測資料模型

定義 Phase 2 scenario 相關的所有資料結構：
- OneTimeExpense: 一次性支出項目
- MonthlyProjection: 單月預測結果
- ProjectionInput: 預測計算輸入
- ProjectionResult: 預測計算結果
- ScenarioType/ScenarioPreset: 情境類型 Enum
- ScenarioAssumption: 情境假設參數
- ScenarioResult: 單一情境計算結果
- ScenarioComparisonResult: 多情境比較結果
- DerivedProvenance: derived 輸出的來源追蹤

Note:
    部分類別使用 Pydantic BaseModel 以支援 JSON 序列化/反序列化。
    使用 ConfigDict(frozen=True) 保持不可變特性。
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict

from life_capital.models.assumptions import LifeAssumptions
from life_capital.models.expense import MonthlyExpenses
from life_capital.models.income import MonthlyIncome


class OneTimeExpense(BaseModel):
    """一次性支出項目（如旅遊、買房頭期、大型家電）

    Attributes:
        year: 支出發生年份
        month: 支出發生月份（1-12）
        amount: 支出金額（Decimal）
        description: 支出描述
        category: 支出類別（可選，用於統計分析）
    """

    model_config = ConfigDict(frozen=True)

    year: int
    month: int
    amount: Decimal
    description: str
    category: Optional[str] = None


class MonthlyProjection(BaseModel):
    """單月預測結果

    包含該月份的收支預測與累積狀態。

    Attributes:
        year: 年份
        month: 月份（1-12）
        income: 月收入
        regular_expenses: 常規月支出
        one_time_expenses: 一次性支出
        total_expenses: 總支出（regular + one_time）
        net_cashflow: 淨現金流（income - total_expenses）
        cumulative_savings: 累積儲蓄
        is_deficit: 是否為赤字月份（net_cashflow < 0）
    """

    model_config = ConfigDict(frozen=True)

    year: int
    month: int
    income: Decimal
    regular_expenses: Decimal
    one_time_expenses: Decimal
    total_expenses: Decimal
    net_cashflow: Decimal
    cumulative_savings: Decimal
    is_deficit: bool


@dataclass
class ProjectionInput:
    """預測計算輸入

    包含所有用於計算預測的輸入資料與參數。

    注意：以下二選一（或同時提供）：
    - income: 從 monthly_income.yaml 載入
    - income_override: 直接指定月收入金額

    注意：以下二選一（或同時提供）：
    - historical_expenses: 從 expenses_YYYY_MM.csv 載入
    - expense_override: 直接指定月支出金額

    Attributes:
        start_year: 預測起始年份
        start_month: 預測起始月份（1-12）
        initial_savings: 初始儲蓄金額（預設為 0）
        projection_months: 預測月數（預設為 24 個月）
        assumptions: 生活假設（從 life_assumptions.yaml）（可選）
        income: 月收入資料（從 monthly_income.yaml）（可選，若提供 income_override）
        historical_expenses: 歷史支出記錄（可選，若提供 expense_override）
        income_override: 收入覆寫值（用於情境分析）
        expense_override: 支出覆寫值（用於情境分析）
        one_time_expenses: 一次性支出清單（用於情境分析）
        expense_estimation_strategy: 支出估算策略（average/median/max/latest）
    """

    # 必填參數
    start_year: int
    start_month: int
    initial_savings: Decimal = Decimal("0")
    projection_months: int = 24

    # 可選資料來源（可用 override 替代）
    assumptions: Optional[LifeAssumptions] = None
    income: Optional[MonthlyIncome] = None
    historical_expenses: list[MonthlyExpenses] = field(default_factory=list)

    # Override 值（用於情境分析或簡化測試）
    income_override: Optional[Decimal] = None
    expense_override: Optional[Decimal] = None
    one_time_expenses: list[OneTimeExpense] = field(default_factory=list)

    expense_estimation_strategy: str = "average"  # average | median | max | latest


class ProjectionResult(BaseModel):
    """預測計算結果

    包含所有月份的預測結果與彙總統計。

    Attributes:
        monthly_projections: 每月預測結果清單
        total_income: 預測期間總收入
        total_expenses: 預測期間總支出
        final_cumulative_savings: 最終累積儲蓄
        average_monthly_cashflow: 平均月現金流
        deficit_months: 赤字月份清單 [(year, month), ...]
        first_deficit_month: 第一個赤字月份（若存在）
        asset_depletion_month: 資產耗盡月份（累積儲蓄 < 0）
        input_hash: 輸入資料 hash（用於快取驗證）
        calculation_timestamp: 計算時間戳記（ISO 8601 格式）
    """

    model_config = ConfigDict(frozen=True)

    monthly_projections: list[MonthlyProjection]

    total_income: Decimal
    total_expenses: Decimal
    final_cumulative_savings: Decimal
    average_monthly_cashflow: Decimal

    deficit_months: list[tuple[int, int]]  # [(year, month), ...]
    first_deficit_month: Optional[tuple[int, int]]
    asset_depletion_month: Optional[tuple[int, int]]

    input_hash: str
    calculation_timestamp: str  # ISO 8601 格式


class ScenarioType(str, Enum):
    """情境類型

    定義情境分析的類別：
    - INCOME_CHANGE: 收入變動情境（如失業、加薪）
    - LARGE_EXPENSE: 大額支出情境（如買房、旅遊）
    - COMBINED: 組合情境（收入變動 + 大額支出）
    """

    INCOME_CHANGE = "income_change"
    LARGE_EXPENSE = "large_expense"
    COMBINED = "combined"


class ScenarioPreset(str, Enum):
    """預設情境模板

    提供常用的情境參數組合：
    - CONSERVATIVE: 保守情境（收入 -10%, 支出 +5%）
    - BASELINE: 基準情境（無變動）
    - OPTIMISTIC: 樂觀情境（收入 +10%, 支出 -5%）
    """

    CONSERVATIVE = "conservative"  # 保守：收入-10%, 支出+5%
    BASELINE = "baseline"
    OPTIMISTIC = "optimistic"  # 樂觀：收入+10%, 支出-5%


class ScenarioAssumption(BaseModel):
    """情境假設參數

    定義單一情境的所有假設參數。

    Attributes:
        name: 情境名稱
        scenario_type: 情境類型
        income_change_percent: 收入變動百分比（0.1 代表 +10%）
        income_change_start_month: 收入變動起始月份（1-based）
        expense_change_percent: 支出變動百分比（0.05 代表 +5%）
        one_time_expenses: 一次性支出清單
        description: 情境描述
    """

    name: str
    scenario_type: ScenarioType

    income_change_percent: Decimal = Decimal("0")
    income_change_start_month: int = 1

    expense_change_percent: Decimal = Decimal("0")
    one_time_expenses: list[OneTimeExpense] = []

    description: str = ""


class ScenarioResult(BaseModel):
    """單一情境計算結果

    包含情境假設、預測結果，以及與基準線的比較。

    Attributes:
        scenario: 情境假設
        projection: 預測結果
        baseline_diff_savings: 與基準線的儲蓄差異（可選）
        baseline_diff_months_to_depletion: 與基準線的資產耗盡月數差異（可選）
    """

    model_config = ConfigDict(frozen=True)

    scenario: ScenarioAssumption
    projection: ProjectionResult

    baseline_diff_savings: Optional[Decimal] = None
    baseline_diff_months_to_depletion: Optional[int] = None


class ScenarioComparisonResult(BaseModel):
    """多情境比較結果

    包含所有情境的比較分析。

    Attributes:
        baseline_name: 基準線情境名稱
        scenarios: 所有情境結果清單
        comparison_table: 比較表格資料（用於輸出報表）
            格式: [{name, final_savings, deficit_months, depletion_month}, ...]
        input_hash: 輸入資料 hash（用於快取驗證）
    """

    model_config = ConfigDict(frozen=True)

    baseline_name: str
    scenarios: list[ScenarioResult]

    comparison_table: dict  # {"baseline": {...}, "scenarios": [...]}
    input_hash: str


@dataclass(frozen=True)
class DerivedProvenance:
    """derived 輸出的來源追蹤（輕量版）

    記錄 derived/ 目錄下檔案的生成來源與版本資訊。
    僅記錄必要的追溯資訊，不包含完整的 Operation log。

    Attributes:
        calc_version: 計算邏輯版本（如 "1.0.0"）
        input_hash: 輸入資料的 hash（用於驗證一致性）
        canonical_sources: canonical 來源檔案清單（相對路徑）
        generated_at: 生成時間戳記（ISO 8601 格式）
    """

    calc_version: str
    input_hash: str
    canonical_sources: list[str]
    generated_at: str  # ISO 8601 格式
