"""Redaction 引擎

核心去識別化邏輯，將原始財務資料轉換為 RedactedDecisionContext。

設計原則:
- 安全優先：寧可丟失資訊，不可洩漏隱私
- 可追蹤：記錄每個欄位的處理方式
- 可測試：所有轉換邏輯都有對應測試

使用方式:
    engine = RedactionEngine()
    context = engine.redact(financial_data)
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from life_capital.privacy.redaction.decision_context import (
    RedactedDecisionContext,
    RedactedPresentationView,
)
from life_capital.privacy.redaction.rules import (
    CURRENT_REDACTION_PROFILE,
    RedactionProfile,
)


@dataclass
class RedactionResult:
    """Redaction 處理結果

    包含去識別化後的資料以及處理過程的元資料。

    Attributes:
        context: 去識別化後的決策上下文
        redacted_fields: 被過濾的欄位清單
        generalized_fields: 被泛化的欄位清單
        composition_violations: 違反組合規則的欄位組合
        profile_version: 使用的 Profile 版本
    """
    context: RedactedDecisionContext
    redacted_fields: List[str]
    generalized_fields: List[str]
    composition_violations: List[Tuple[str, ...]]
    profile_version: str


class RedactionEngine:
    """Redaction 引擎

    執行資料去識別化的核心邏輯。

    使用方式:
        engine = RedactionEngine()
        result = engine.redact(financial_data)

        # 取得去識別化後的上下文
        context = result.context

        # 取得友善化視圖（給 CLI）
        view = engine.create_presentation_view(context)
    """

    def __init__(self, profile: Optional[RedactionProfile] = None):
        """初始化引擎

        Args:
            profile: 使用的 Redaction Profile，預設為 V1.0
        """
        self.profile = profile or CURRENT_REDACTION_PROFILE

    def redact(self, financial_data: Dict[str, Any]) -> RedactionResult:
        """執行去識別化

        Args:
            financial_data: 原始財務資料字典

        Returns:
            RedactionResult 包含去識別化結果與元資料
        """
        redacted_fields: List[str] = []
        generalized_fields: List[str] = []

        # Step 1: 過濾禁止欄位
        filtered_data = {}
        for key, value in financial_data.items():
            if self.profile.is_forbidden(key):
                redacted_fields.append(key)
            else:
                filtered_data[key] = value

        # Step 2: 檢查組合違規
        composition_violations = self.profile.violates_composition(
            set(filtered_data.keys())
        )

        # 移除違規組合中的敏感欄位
        for violation in composition_violations:
            for field in violation:
                if field in filtered_data and self.profile.is_sensitive(field):
                    del filtered_data[field]
                    redacted_fields.append(f"{field} (composition)")

        # Step 3: 泛化敏感欄位
        expense_distribution = self._extract_expense_distribution(filtered_data)
        deficit_month_count = self._extract_deficit_count(filtered_data)
        runway_months = self._extract_runway_months(filtered_data)
        consecutive_deficit_months = self._extract_consecutive_deficit(filtered_data)
        income_volatility = self._extract_income_volatility(filtered_data)
        savings_rate_band = self._extract_savings_rate_band(filtered_data)
        expense_trend = self._extract_expense_trend(filtered_data)

        # 記錄泛化的欄位
        for field in filtered_data:
            if self.profile.is_sensitive(field):
                generalized_fields.append(field)

        # Step 4: 建立來源追蹤
        field_provenance = {
            "expense_distribution": "bucketed",
            "deficit_month_count": "exact",
            "runway_months": "capped_120" if runway_months is None else "exact",
            "consecutive_deficit_months": "exact",
            "income_volatility": "categorized",
            "savings_rate_band": "bucketed",
            "expense_trend": "categorized",
        }

        context = RedactedDecisionContext(
            expense_distribution=expense_distribution,
            deficit_month_count=deficit_month_count,
            runway_months=runway_months,
            consecutive_deficit_months=consecutive_deficit_months,
            income_volatility=income_volatility,
            savings_rate_band=savings_rate_band,
            expense_trend=expense_trend,
            field_provenance=field_provenance,
        )

        return RedactionResult(
            context=context,
            redacted_fields=redacted_fields,
            generalized_fields=generalized_fields,
            composition_violations=composition_violations,
            profile_version=self.profile.version,
        )

    def create_presentation_view(
        self,
        context: RedactedDecisionContext
    ) -> RedactedPresentationView:
        """建立友善化視圖（給 CLI 輸出）

        Args:
            context: 去識別化後的決策上下文

        Returns:
            包含友善化描述的視圖
        """
        return RedactedPresentationView.from_context(context)

    # === 私有方法：欄位抽取與泛化 ===

    def _extract_expense_distribution(
        self,
        data: Dict[str, Any]
    ) -> Dict[str, float]:
        """抽取支出類別分佈

        將具體金額轉換為百分比分佈。
        支援 expense_categories 或 expense_by_category 欄位名稱。
        """
        expenses = None
        if "expense_categories" in data:
            expenses = data["expense_categories"]
        elif "expense_by_category" in data:
            expenses = data["expense_by_category"]

        if expenses is not None and isinstance(expenses, dict):
            total = sum(
                float(v) if isinstance(v, (int, float, Decimal)) else 0
                for v in expenses.values()
            )
            if total > 0:
                return {
                    k: float(v) / total
                    for k, v in expenses.items()
                    if isinstance(v, (int, float, Decimal))
                }

        # 預設空分佈
        return {}

    def _extract_deficit_count(self, data: Dict[str, Any]) -> int:
        """抽取赤字月數"""
        if "deficit_months" in data:
            deficit_data = data["deficit_months"]
            # 支援 list（月份索引）或 int（直接數量）
            if isinstance(deficit_data, list):
                return len(deficit_data)
            return int(deficit_data)
        if "monthly_balances" in data:
            balances = data["monthly_balances"]
            if isinstance(balances, list):
                return sum(1 for b in balances if float(b) < 0)
        return 0

    def _extract_runway_months(self, data: Dict[str, Any]) -> Optional[int]:
        """抽取跑道月數

        超過 120 個月回傳 None（隱私保護）
        """
        if "runway_months" in data:
            months = int(data["runway_months"])
            return None if months > 120 else months
        if "current_savings" in data and "monthly_expense" in data:
            savings = float(data["current_savings"])
            expense = float(data["monthly_expense"])
            if expense > 0:
                months = int(savings / expense)
                return None if months > 120 else months
        return None

    def _extract_consecutive_deficit(self, data: Dict[str, Any]) -> int:
        """抽取連續赤字月數"""
        if "consecutive_deficit_months" in data:
            return int(data["consecutive_deficit_months"])
        if "monthly_balances" in data:
            balances = data["monthly_balances"]
            if isinstance(balances, list):
                # 計算最近的連續赤字
                consecutive = 0
                for b in reversed(balances):
                    if float(b) < 0:
                        consecutive += 1
                    else:
                        break
                return consecutive
        return 0

    def _extract_income_volatility(
        self,
        data: Dict[str, Any]
    ) -> str:
        """抽取收入波動度

        將標準差/變異係數轉換為等級
        """
        if "income_volatility" in data:
            vol = data["income_volatility"]
            if isinstance(vol, str) and vol in ("low", "medium", "high"):
                return vol

        if "income_cv" in data:  # 變異係數
            cv = float(data["income_cv"])
            if cv < 0.1:
                return "low"
            elif cv < 0.25:
                return "medium"
            else:
                return "high"

        # 從收入歷史計算變異係數
        if "income_history" in data:
            history = data["income_history"]
            if isinstance(history, list) and len(history) >= 2:
                import statistics
                mean = statistics.mean(history)
                if mean > 0:
                    stdev = statistics.stdev(history)
                    cv = stdev / mean
                    if cv < 0.1:
                        return "low"
                    elif cv < 0.25:
                        return "medium"
                    else:
                        return "high"

        return "low"  # 預設低波動

    def _extract_savings_rate_band(self, data: Dict[str, Any]) -> str:
        """抽取儲蓄率區間

        將具體百分比轉換為區間
        """
        rate = None

        if "savings_rate" in data:
            rate = float(data["savings_rate"])
        elif "monthly_income" in data and "monthly_expense" in data:
            income = float(data["monthly_income"])
            expense = float(data["monthly_expense"])
            if income > 0:
                rate = (income - expense) / income

        if rate is not None:
            if rate < 0.1:
                return "0-10%"
            elif rate < 0.2:
                return "10-20%"
            elif rate < 0.3:
                return "20-30%"
            else:
                return "30%+"

        return "10-20%"  # 預設中等

    def _extract_expense_trend(
        self,
        data: Dict[str, Any]
    ) -> str:
        """抽取支出趨勢

        將數值變化轉換為趨勢類別
        """
        if "expense_trend" in data:
            trend = data["expense_trend"]
            if isinstance(trend, str) and trend in ("stable", "increasing", "decreasing"):
                return trend

        if "expense_growth_rate" in data:
            rate = float(data["expense_growth_rate"])
            if rate > 0.05:
                return "increasing"
            elif rate < -0.05:
                return "decreasing"
            else:
                return "stable"

        return "stable"  # 預設穩定

    # === 便捷方法 ===

    def redact_and_present(
        self,
        financial_data: Dict[str, Any]
    ) -> RedactedPresentationView:
        """一步完成去識別化並建立友善化視圖

        Args:
            financial_data: 原始財務資料

        Returns:
            友善化視圖（包含 context）
        """
        result = self.redact(financial_data)
        return self.create_presentation_view(result.context)
