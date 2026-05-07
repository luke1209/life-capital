"""Redaction 資料結構定義

定義兩層 Redaction 輸出結構：
1. RedactedDecisionContext：給決策引擎使用，最小特徵集
2. RedactedPresentationView：給 CLI 輸出使用，含友善化描述

設計原則:
- frozen=True：確保不可變
- 欄位最小化：只包含決策必要特徵
- 泛化處理：數值改為區間/等級
"""

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional


@dataclass(frozen=True)
class RedactedDecisionContext:
    """給決策引擎使用的最小特徵集

    這是 Redaction Layer 1 的輸出，只包含決策比較所需的最小資訊。
    所有數值都已經過泛化處理，不包含可識別個人的資訊。

    設計約束:
    - 支出分佈：只有類別百分比，無具體金額
    - 流動性指標：只有整數月數，無具體金額
    - 風險信號：只有等級（low/medium/high），無具體數值

    Attributes:
        expense_distribution: 支出類別分佈（如 {"food": 0.3, "housing": 0.4}）
        deficit_month_count: 過去 N 個月中赤字的月數
        runway_months: 按當前消耗率，資產可支撐的月數（>120 則為 None）
        consecutive_deficit_months: 連續赤字月數
        income_volatility: 收入波動度（low/medium/high）
        savings_rate_band: 儲蓄率區間（如 "10-20%"）
        expense_trend: 支出趨勢（stable/increasing/decreasing）
        field_provenance: 每個欄位的資料來源追蹤
    """
    # 支出分佈（類別百分比）
    expense_distribution: Dict[str, float]

    # 流動性指標（泛化）
    deficit_month_count: int
    runway_months: Optional[int]  # >120 則為 None

    # 風險信號（等級化）
    consecutive_deficit_months: int
    income_volatility: Literal["low", "medium", "high"]

    # 財務健康指標（區間化）
    savings_rate_band: str  # "0-10%", "10-20%", "20-30%", "30%+"
    expense_trend: Literal["stable", "increasing", "decreasing"]

    # 來源追蹤
    field_provenance: Dict[str, str] = field(default_factory=dict)
    # 例如: {"deficit_month_count": "exact", "expense_distribution": "bucketed"}

    def has_high_risk_signals(self) -> bool:
        """檢查是否有高風險信號"""
        return (
            self.consecutive_deficit_months >= 3 or
            self.income_volatility == "high" or
            (self.runway_months is not None and self.runway_months < 6)
        )

    def get_risk_level(self) -> Literal["low", "medium", "high"]:
        """計算整體風險等級"""
        risk_score = 0

        # 連續赤字
        if self.consecutive_deficit_months >= 3:
            risk_score += 2
        elif self.consecutive_deficit_months >= 1:
            risk_score += 1

        # 收入波動
        if self.income_volatility == "high":
            risk_score += 2
        elif self.income_volatility == "medium":
            risk_score += 1

        # 跑道長度
        if self.runway_months is not None:
            if self.runway_months < 3:
                risk_score += 3
            elif self.runway_months < 6:
                risk_score += 2
            elif self.runway_months < 12:
                risk_score += 1

        # 儲蓄率
        if self.savings_rate_band == "0-10%":
            risk_score += 1

        # 支出趨勢
        if self.expense_trend == "increasing":
            risk_score += 1

        if risk_score >= 5:
            return "high"
        elif risk_score >= 2:
            return "medium"
        else:
            return "low"


@dataclass(frozen=True)
class RedactedPresentationView:
    """給 CLI 輸出使用的友善化視圖

    這是 Redaction Layer 2 的輸出，基於 Layer 1 的資料
    加上人類可讀的描述文字。

    設計約束:
    - 包含 Layer 1 的所有資料
    - 加上友善化的摘要文字
    - 所有文字都不包含可識別資訊

    Attributes:
        context: Layer 1 資料
        summary_text: 財務狀況摘要
        risk_explanation: 風險因素說明
        comparison_narrative: 比較說明
    """
    context: RedactedDecisionContext

    # 友善化描述
    summary_text: str  # "您的財務狀況：中等風險，建議關注..."
    risk_explanation: str  # "過去 6 個月有 2 個月赤字"
    comparison_narrative: str  # "方案 A 與方案 B 都適合您的情況"

    @classmethod
    def from_context(cls, context: RedactedDecisionContext) -> "RedactedPresentationView":
        """從 DecisionContext 建立 PresentationView

        自動生成友善化描述文字。
        """
        risk_level = context.get_risk_level()

        # 生成摘要
        summary_parts = []
        summary_parts.append(f"財務狀況：{_risk_level_cn(risk_level)}風險")

        if context.consecutive_deficit_months > 0:
            summary_parts.append(f"近期有連續 {context.consecutive_deficit_months} 個月赤字")

        if context.runway_months is not None and context.runway_months < 12:
            summary_parts.append(f"緊急備用金約可維持 {context.runway_months} 個月")

        summary_text = "，".join(summary_parts)

        # 生成風險說明
        risk_parts = []
        if context.income_volatility == "high":
            risk_parts.append("收入波動較大")
        if context.expense_trend == "increasing":
            risk_parts.append("支出呈上升趨勢")
        if context.savings_rate_band == "0-10%":
            risk_parts.append("儲蓄率偏低")

        risk_explanation = "；".join(risk_parts) if risk_parts else "財務狀況穩定"

        # 生成比較說明
        comparison_narrative = _generate_recommendation_context(context)

        return cls(
            context=context,
            summary_text=summary_text,
            risk_explanation=risk_explanation,
            comparison_narrative=comparison_narrative,
        )


def _risk_level_cn(level: str) -> str:
    """風險等級中文化"""
    mapping = {"low": "低", "medium": "中等", "high": "高"}
    return mapping.get(level, level)


def _generate_recommendation_context(context: RedactedDecisionContext) -> str:
    """生成建議上下文描述"""
    parts = []

    # 儲蓄率
    parts.append(f"儲蓄率區間為 {context.savings_rate_band}")

    # 支出趨勢
    trend_cn = {"stable": "穩定", "increasing": "上升", "decreasing": "下降"}
    parts.append(f"支出趨勢{trend_cn.get(context.expense_trend, context.expense_trend)}")

    # 主要支出類別
    if context.expense_distribution:
        top_categories = sorted(
            context.expense_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        cat_str = "、".join(f"{cat}({pct:.0%})" for cat, pct in top_categories)
        parts.append(f"主要支出為{cat_str}")

    return "，".join(parts) + "。"
