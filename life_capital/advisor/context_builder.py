"""上下文建構器

從 canonical 資料建構決策上下文，並透過 Redaction 引擎去識別化。

設計原則:
- 隔離層：只透過 CanonicalReader Protocol 讀取資料
- 單向流：raw data → financial context → redacted context
- 可追蹤：記錄資料來源與處理步驟

使用方式:
    builder = ContextBuilder(reader=canonical_reader)
    redacted_context = builder.build()
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from life_capital.interfaces.canonical_reader import CanonicalReader
from life_capital.interfaces.canonical_reader_impl import CanonicalReaderImpl
from life_capital.privacy.redaction.decision_context import (
    RedactedDecisionContext,
    RedactedPresentationView,
)
from life_capital.privacy.redaction.engine import RedactionEngine, RedactionResult


@dataclass
class FinancialContext:
    """財務上下文（原始資料）

    從 canonical 讀取的原始財務資料，尚未去識別化。

    Attributes:
        monthly_incomes: 月度收入列表（最近 N 個月）
        monthly_expenses: 月度支出列表（最近 N 個月）
        expense_by_category: 各類別支出（最近月份）
        current_savings: 當前儲蓄
        monthly_expense_avg: 平均月支出
        months_analyzed: 分析的月數
    """
    monthly_incomes: List[Decimal]
    monthly_expenses: List[Decimal]
    expense_by_category: Dict[str, Decimal]
    current_savings: Optional[Decimal]
    monthly_expense_avg: Decimal
    months_analyzed: int


class ContextBuilder:
    """上下文建構器

    從 canonical 資料建構決策上下文。

    使用方式:
        # 方式 1：使用檔案路徑
        builder = ContextBuilder.from_path(Path("~/.life-capital"))
        redacted_context = builder.build()

        # 方式 2：使用 CanonicalReader
        builder = ContextBuilder(reader=reader)
        redacted_context = builder.build()

        # 方式 3：取得完整結果（含 Presentation View）
        result = builder.build_with_view()
    """

    def __init__(
        self,
        reader: CanonicalReader,
        redaction_engine: Optional[RedactionEngine] = None,
        lookback_months: int = 6,
    ):
        """初始化建構器

        Args:
            reader: Canonical 資料讀取器
            redaction_engine: Redaction 引擎（可選，預設使用標準引擎）
            lookback_months: 回溯月數（預設 6 個月）
        """
        self.reader = reader
        self.redaction_engine = redaction_engine or RedactionEngine()
        self.lookback_months = lookback_months

    @classmethod
    def from_path(
        cls,
        data_path: Path,
        lookback_months: int = 6,
    ) -> "ContextBuilder":
        """從路徑建立建構器

        Args:
            data_path: 資料目錄路徑
            lookback_months: 回溯月數

        Returns:
            ContextBuilder 實例
        """
        reader = CanonicalReaderImpl(data_path)
        return cls(reader=reader, lookback_months=lookback_months)

    def build(self) -> RedactedDecisionContext:
        """建構去識別化的決策上下文

        Returns:
            RedactedDecisionContext 實例
        """
        result = self._build_internal()
        return result.context

    def build_with_view(self) -> RedactedPresentationView:
        """建構包含 Presentation View 的完整結果

        Returns:
            RedactedPresentationView 實例
        """
        result = self._build_internal()
        return self.redaction_engine.create_presentation_view(result.context)

    def build_with_metadata(self) -> RedactionResult:
        """建構包含元資料的完整結果

        Returns:
            RedactionResult 實例（含 redacted_fields 等元資料）
        """
        return self._build_internal()

    def _build_internal(self) -> RedactionResult:
        """內部建構方法

        Returns:
            RedactionResult 實例
        """
        # Step 1: 從 canonical 讀取財務資料
        financial_data = self._collect_financial_data()

        # Step 2: 透過 Redaction Engine 處理
        result = self.redaction_engine.redact(financial_data)

        return result

    def _collect_financial_data(self) -> Dict[str, Any]:
        """從 canonical 收集財務資料

        Returns:
            財務資料字典（原始格式）
        """
        # 計算查詢範圍
        today = date.today()
        months_to_query = []
        for i in range(self.lookback_months):
            target_date = today - timedelta(days=30 * i)
            months_to_query.append(target_date.strftime("%Y-%m"))

        # 收集月度資料
        monthly_incomes = []
        monthly_expenses = []
        monthly_balances = []
        expense_by_category: Dict[str, float] = {}

        for month in months_to_query:
            try:
                expenses = self.reader.read_expenses(month)

                # 計算月支出
                month_total = sum(
                    float(e.amount) for e in expenses
                    if hasattr(e, 'amount')
                )
                monthly_expenses.append(month_total)

                # 收集類別分佈（以最近月份為準）
                if month == months_to_query[0]:
                    for expense in expenses:
                        if hasattr(expense, 'category') and hasattr(expense, 'amount'):
                            cat = expense.category
                            amt = float(expense.amount)
                            expense_by_category[cat] = expense_by_category.get(cat, 0) + amt

            except (FileNotFoundError, Exception):
                # 沒有該月資料，跳過
                continue

        # 嘗試讀取收入資料（如果存在）
        try:
            # 假設有 income 讀取方法
            if hasattr(self.reader, 'read_incomes'):
                for month in months_to_query:
                    try:
                        incomes = self.reader.read_incomes(month)
                        month_income = sum(float(i.amount) for i in incomes if hasattr(i, 'amount'))
                        monthly_incomes.append(month_income)
                    except Exception:
                        continue
        except Exception:
            pass

        # 計算餘額（收入 - 支出）
        for i in range(min(len(monthly_incomes), len(monthly_expenses))):
            balance = monthly_incomes[i] - monthly_expenses[i]
            monthly_balances.append(balance)

        # 計算赤字月份
        deficit_months = []
        for i, bal in enumerate(monthly_balances):
            if bal < 0:
                deficit_months.append(i)

        # 計算連續赤字
        consecutive_deficit = 0
        for bal in reversed(monthly_balances):
            if bal < 0:
                consecutive_deficit += 1
            else:
                break

        # 組裝資料
        data: Dict[str, Any] = {}

        if expense_by_category:
            data["expense_categories"] = expense_by_category

        if monthly_balances:
            data["monthly_balances"] = monthly_balances

        if deficit_months:
            data["deficit_months"] = deficit_months

        data["consecutive_deficit_months"] = consecutive_deficit

        # 計算收入波動度
        if len(monthly_incomes) >= 2:
            data["income_history"] = monthly_incomes

        # 計算儲蓄率（如果有收支資料）
        if monthly_incomes and monthly_expenses:
            avg_income = sum(monthly_incomes) / len(monthly_incomes)
            avg_expense = sum(monthly_expenses) / len(monthly_expenses)
            if avg_income > 0:
                data["monthly_income"] = avg_income
                data["monthly_expense"] = avg_expense

        # 計算跑道月數（簡化版：假設當前儲蓄 = 6 個月收入）
        # 實際實作應從 assets 讀取
        if monthly_incomes and monthly_expenses:
            avg_expense = sum(monthly_expenses) / len(monthly_expenses) if monthly_expenses else 1
            # 假設儲蓄為 6 個月平均支出（簡化）
            estimated_savings = avg_expense * 6
            data["current_savings"] = estimated_savings
            data["monthly_expense"] = avg_expense
            if avg_expense > 0:
                data["runway_months"] = int(estimated_savings / avg_expense)

        # 計算支出趨勢
        if len(monthly_expenses) >= 2:
            first_half = monthly_expenses[:len(monthly_expenses)//2]
            second_half = monthly_expenses[len(monthly_expenses)//2:]
            avg_first = sum(first_half) / len(first_half) if first_half else 0
            avg_second = sum(second_half) / len(second_half) if second_half else 0

            if avg_first > 0:
                change_rate = (avg_second - avg_first) / avg_first
                if change_rate > 0.05:
                    data["expense_trend"] = "increasing"
                elif change_rate < -0.05:
                    data["expense_trend"] = "decreasing"
                else:
                    data["expense_trend"] = "stable"

        return data


def build_context_from_path(
    data_path: Path,
    lookback_months: int = 6,
) -> RedactedDecisionContext:
    """便捷函式：從路徑建構上下文

    Args:
        data_path: 資料目錄路徑
        lookback_months: 回溯月數

    Returns:
        RedactedDecisionContext 實例
    """
    builder = ContextBuilder.from_path(data_path, lookback_months)
    return builder.build()


def build_view_from_path(
    data_path: Path,
    lookback_months: int = 6,
) -> RedactedPresentationView:
    """便捷函式：從路徑建構 Presentation View

    Args:
        data_path: 資料目錄路徑
        lookback_months: 回溯月數

    Returns:
        RedactedPresentationView 實例
    """
    builder = ContextBuilder.from_path(data_path, lookback_months)
    return builder.build_with_view()
