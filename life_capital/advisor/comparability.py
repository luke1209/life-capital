"""可比較性判定模組

實現四維特徵向量的可比較性評分，決定兩個決策選項是否可以進行比較。

四維特徵:
1. time_horizon: 期限匹配度
2. risk_tolerance: 風險容忍度
3. liquidity: 流動性需求
4. capital_need: 資金需求

評分公式:
    score = time_horizon * 0.3 + risk_tolerance * 0.2 + liquidity * 0.3 + capital_need * 0.2

閾值:
    >= 0.6 為可比較
    < 0.6 為不可比較
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from life_capital.io.registry import COMPARABILITY_THRESHOLD
from life_capital.privacy.redaction.decision_context import RedactedDecisionContext


@dataclass
class ComparabilityFeatures:
    """可比較性四維特徵向量

    每個維度的分數範圍為 0.0 - 1.0。

    Attributes:
        time_horizon: 期限匹配度（短期 vs 長期）
        risk_tolerance: 風險容忍度匹配度
        liquidity: 流動性需求匹配度
        capital_need: 資金需求匹配度
    """
    time_horizon: float
    risk_tolerance: float
    liquidity: float
    capital_need: float

    def __post_init__(self):
        """驗證分數範圍"""
        for field in ["time_horizon", "risk_tolerance", "liquidity", "capital_need"]:
            value = getattr(self, field)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field} 必須在 0.0-1.0 範圍內，目前值：{value}")

    def score(self) -> float:
        """計算加權平均分數

        權重分配:
        - time_horizon: 30%（期限是最關鍵的比較因素）
        - risk_tolerance: 20%（風險容忍度需要匹配）
        - liquidity: 30%（流動性需求影響決策可行性）
        - capital_need: 20%（資金需求影響選項可及性）

        Returns:
            0.0-1.0 的可比較性分數
        """
        return (
            self.time_horizon * 0.3 +
            self.risk_tolerance * 0.2 +
            self.liquidity * 0.3 +
            self.capital_need * 0.2
        )

    def is_comparable(self, threshold: float = COMPARABILITY_THRESHOLD) -> bool:
        """判斷是否可比較

        Args:
            threshold: 可比較性閾值，預設為 0.6

        Returns:
            True 如果分數 >= 閾值
        """
        return self.score() >= threshold

    def get_weak_dimensions(self, threshold: float = 0.5) -> List[str]:
        """取得低於閾值的弱維度

        用於生成補件指引。

        Args:
            threshold: 弱維度閾值

        Returns:
            弱維度名稱列表
        """
        weak = []
        if self.time_horizon < threshold:
            weak.append("time_horizon")
        if self.risk_tolerance < threshold:
            weak.append("risk_tolerance")
        if self.liquidity < threshold:
            weak.append("liquidity")
        if self.capital_need < threshold:
            weak.append("capital_need")
        return weak

    # 別名方法，保持向後相容
    def weak_dimensions(self, threshold: float = 0.5) -> List[str]:
        """取得低於閾值的弱維度（別名）"""
        return self.get_weak_dimensions(threshold)


@dataclass
class TimeSegment:
    """時間分段評分

    用於多時段評分框架（如買房場景）。

    Attributes:
        name: 分段名稱（如 "首付階段"）
        duration: 持續時間描述（如 "0-6個月"）
        weight: 權重（如 0.3）
        score: 該分段的可比較性分數（可選，evaluate 時設定）
        threshold: 該分段的最低閾值
        metrics: 評估的指標列表
    """
    name: str
    duration: str
    weight: float
    threshold: float = 0.6
    metrics: Tuple[str, ...] = ()
    score: Optional[float] = None

    def passes_threshold(self) -> bool:
        """檢查是否通過閾值"""
        if self.score is None:
            return False
        return self.score >= self.threshold

    def evaluate(self, score: float) -> dict:
        """評估給定分數

        Args:
            score: 要評估的分數 (0-1)

        Returns:
            評估結果字典，包含 passed, score, weighted_score
        """
        return {
            "passed": score >= self.threshold,
            "score": score,
            "weighted_score": score * self.weight,
        }


@dataclass
class ComparabilityResult:
    """可比較性評估結果

    包含完整的評估資訊，用於決策比較器。

    Attributes:
        features: 四維特徵向量
        total_score: 總分（別名：score）
        is_comparable: 是否可比較
        weak_dimensions: 弱維度列表
        time_segments: 時間分段評分（可選）
        blocking_reasons: 阻擋原因
    """
    is_comparable: bool
    features: ComparabilityFeatures
    weak_dimensions: List[str]
    blocking_reasons: List[str]
    total_score: Optional[float] = None
    score: Optional[float] = None  # 別名，向後相容
    time_segments: Optional[List[TimeSegment]] = None

    def __post_init__(self):
        """確保 score 和 total_score 同步"""
        if self.score is not None and self.total_score is None:
            object.__setattr__(self, 'total_score', self.score)
        elif self.total_score is not None and self.score is None:
            object.__setattr__(self, 'score', self.total_score)


class ComparabilityCalculator:
    """可比較性計算器

    從 RedactedDecisionContext 計算可比較性分數。

    使用方式:
        calculator = ComparabilityCalculator()
        result = calculator.calculate(context, template_id="buying_house")
    """

    def __init__(self, threshold: float = COMPARABILITY_THRESHOLD):
        """初始化計算器

        Args:
            threshold: 可比較性閾值
        """
        self.threshold = threshold

    def calculate(
        self,
        context: RedactedDecisionContext,
        template_id: str = "default"
    ) -> ComparabilityResult:
        """計算可比較性

        Args:
            context: 去識別化的決策上下文
            template_id: 決策模板 ID，影響評分邏輯

        Returns:
            可比較性評估結果
        """
        # 計算四維特徵
        features = self._extract_features(context, template_id)

        # 計算總分與判斷
        total_score = features.score()
        is_comparable = features.is_comparable(self.threshold)
        weak_dimensions = features.get_weak_dimensions()

        # 時間分段評分（特定模板）
        time_segments = None
        if template_id in ("buying_house", "investment"):
            time_segments = self._calculate_time_segments(context, template_id)

        # 阻擋原因
        blocking_reasons = self._get_blocking_reasons(
            features, weak_dimensions, time_segments
        )

        return ComparabilityResult(
            is_comparable=is_comparable,
            features=features,
            weak_dimensions=weak_dimensions,
            blocking_reasons=blocking_reasons if not is_comparable else [],
            total_score=total_score,
            score=total_score,
            time_segments=time_segments,
        )

    def _extract_features(
        self,
        context: RedactedDecisionContext,
        template_id: str
    ) -> ComparabilityFeatures:
        """從上下文抽取四維特徵

        Args:
            context: 去識別化的決策上下文
            template_id: 決策模板 ID

        Returns:
            四維特徵向量
        """
        # 期限匹配度：基於跑道長度與赤字情況
        time_horizon = self._calc_time_horizon_score(context)

        # 風險容忍度：基於收入波動與連續赤字
        risk_tolerance = self._calc_risk_tolerance_score(context)

        # 流動性需求：基於儲蓄率與支出趨勢
        liquidity = self._calc_liquidity_score(context)

        # 資金需求：基於模板類型與財務狀況
        capital_need = self._calc_capital_need_score(context, template_id)

        return ComparabilityFeatures(
            time_horizon=time_horizon,
            risk_tolerance=risk_tolerance,
            liquidity=liquidity,
            capital_need=capital_need,
        )

    def _calc_time_horizon_score(self, context: RedactedDecisionContext) -> float:
        """計算期限匹配度分數"""
        score = 1.0

        # 跑道不足扣分
        if context.runway_months is not None:
            if context.runway_months < 3:
                score -= 0.5
            elif context.runway_months < 6:
                score -= 0.3
            elif context.runway_months < 12:
                score -= 0.1

        # 赤字月數扣分
        if context.deficit_month_count >= 3:
            score -= 0.3
        elif context.deficit_month_count >= 1:
            score -= 0.1

        return max(0.0, min(1.0, score))

    def _calc_risk_tolerance_score(self, context: RedactedDecisionContext) -> float:
        """計算風險容忍度分數"""
        score = 1.0

        # 收入波動扣分
        if context.income_volatility == "high":
            score -= 0.4
        elif context.income_volatility == "medium":
            score -= 0.2

        # 連續赤字扣分
        if context.consecutive_deficit_months >= 3:
            score -= 0.4
        elif context.consecutive_deficit_months >= 1:
            score -= 0.2

        return max(0.0, min(1.0, score))

    def _calc_liquidity_score(self, context: RedactedDecisionContext) -> float:
        """計算流動性需求分數"""
        score = 1.0

        # 儲蓄率區間
        if context.savings_rate_band == "0-10%":
            score -= 0.4
        elif context.savings_rate_band == "10-20%":
            score -= 0.2

        # 支出趨勢
        if context.expense_trend == "increasing":
            score -= 0.2

        # 跑道長度
        if context.runway_months is not None and context.runway_months < 6:
            score -= 0.3

        return max(0.0, min(1.0, score))

    def _calc_capital_need_score(
        self,
        context: RedactedDecisionContext,
        template_id: str
    ) -> float:
        """計算資金需求分數

        根據模板類型調整邏輯。
        """
        score = 1.0

        # 買房模板：需要較高資本
        if template_id == "buying_house":
            if context.savings_rate_band in ("0-10%", "10-20%"):
                score -= 0.3
            if context.runway_months is not None and context.runway_months < 12:
                score -= 0.2

        # 投資模板：需要穩定收入
        elif template_id == "investment":
            if context.income_volatility == "high":
                score -= 0.3
            if context.consecutive_deficit_months >= 2:
                score -= 0.2

        # 其他模板：一般評估
        else:
            if context.savings_rate_band == "0-10%":
                score -= 0.2

        return max(0.0, min(1.0, score))

    def _calculate_time_segments(
        self,
        context: RedactedDecisionContext,
        template_id: str
    ) -> List[TimeSegment]:
        """計算時間分段評分

        針對特定模板（如買房）進行多時段評估。
        """
        if template_id == "buying_house":
            return [
                TimeSegment(
                    name="首付階段",
                    duration="0-6個月",
                    weight=0.3,
                    score=self._calc_downpayment_score(context),
                    threshold=0.7,
                    metrics=("可用現金", "緊急備金"),
                ),
                TimeSegment(
                    name="貸款期",
                    duration="6個月-30年",
                    weight=0.5,
                    score=self._calc_mortgage_score(context),
                    threshold=0.6,
                    metrics=("月現金流", "利率風險"),
                ),
                TimeSegment(
                    name="退休累積",
                    duration="30年-60年",
                    weight=0.2,
                    score=self._calc_retirement_score(context),
                    threshold=0.5,
                    metrics=("資產淨值", "終身購買力"),
                ),
            ]

        elif template_id == "investment":
            return [
                TimeSegment(
                    name="初期投入",
                    duration="0-1年",
                    weight=0.4,
                    score=self._calc_initial_investment_score(context),
                    threshold=0.6,
                    metrics=("可投資金額", "風險承受"),
                ),
                TimeSegment(
                    name="增長期",
                    duration="1-10年",
                    weight=0.6,
                    score=self._calc_growth_period_score(context),
                    threshold=0.5,
                    metrics=("持續投入能力", "市場風險"),
                ),
            ]

        return []

    def _calc_downpayment_score(self, context: RedactedDecisionContext) -> float:
        """計算首付階段分數"""
        score = 0.8
        if context.runway_months is not None and context.runway_months >= 12:
            score += 0.2
        if context.savings_rate_band == "30%+":
            score += 0.1
        return min(1.0, score)

    def _calc_mortgage_score(self, context: RedactedDecisionContext) -> float:
        """計算貸款期分數"""
        score = 0.7
        if context.income_volatility == "low":
            score += 0.2
        if context.consecutive_deficit_months == 0:
            score += 0.1
        return min(1.0, score)

    def _calc_retirement_score(self, context: RedactedDecisionContext) -> float:
        """計算退休累積分數"""
        score = 0.6
        if context.savings_rate_band in ("20-30%", "30%+"):
            score += 0.2
        if context.expense_trend == "decreasing":
            score += 0.1
        return min(1.0, score)

    def _calc_initial_investment_score(self, context: RedactedDecisionContext) -> float:
        """計算初期投入分數"""
        score = 0.7
        if context.runway_months is not None and context.runway_months >= 6:
            score += 0.2
        if context.savings_rate_band in ("20-30%", "30%+"):
            score += 0.1
        return min(1.0, score)

    def _calc_growth_period_score(self, context: RedactedDecisionContext) -> float:
        """計算增長期分數"""
        score = 0.6
        if context.income_volatility == "low":
            score += 0.2
        if context.consecutive_deficit_months == 0:
            score += 0.2
        return min(1.0, score)

    def _get_blocking_reasons(
        self,
        features: ComparabilityFeatures,
        weak_dimensions: List[str],
        time_segments: Optional[List[TimeSegment]]
    ) -> List[str]:
        """生成阻擋原因

        Args:
            features: 四維特徵
            weak_dimensions: 弱維度
            time_segments: 時間分段

        Returns:
            阻擋原因代碼列表
        """
        reasons = []

        # 弱維度原因
        dimension_reasons = {
            "time_horizon": "TIME_HORIZON_INSUFFICIENT",
            "risk_tolerance": "RISK_TOLERANCE_LOW",
            "liquidity": "LIQUIDITY_INSUFFICIENT",
            "capital_need": "CAPITAL_NEED_HIGH",
        }

        for dim in weak_dimensions:
            if dim in dimension_reasons:
                reasons.append(dimension_reasons[dim])

        # 時間分段原因
        if time_segments:
            for segment in time_segments:
                if not segment.passes_threshold():
                    reasons.append(f"SEGMENT_{segment.name.upper()}_INSUFFICIENT")

        return reasons
