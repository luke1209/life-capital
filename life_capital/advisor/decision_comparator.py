"""決策比較器規則引擎

純規則引擎，無 I/O 操作，從 RedactedDecisionContext 生成比較結果。

設計原則:
- 純函式：無副作用，相同輸入產生相同輸出
- 規則驅動：決定論邏輯，完全可追蹤
- 隱私優先：只接受已去識別化的資料

使用方式:
    comparator = DecisionComparator()
    result = comparator.compare(context, template_id="buying_house")
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

from life_capital.advisor.comparability import (
    ComparabilityCalculator,
    ComparabilityResult,
)
from life_capital.advisor.schemas import (
    BlockingReasonDetail,
    DecisionOptionSchema,
)
from life_capital.privacy.redaction.decision_context import RedactedDecisionContext


@dataclass(frozen=True)
class ComparisonOption:
    """比較選項

    決策比較器輸出的單一選項。

    Attributes:
        direction: 方向（保守/進取）
        label: 選項標籤
        recommendation: 建議內容（可比較時）
        score: 選項分數（可比較時）
        status: 選項狀態
        to_comparable_guidance: 變成可比較的指引（不可比較時）
    """

    direction: Literal["conservative", "aggressive"]
    label: str
    recommendation: Optional[str] = None
    score: Optional[float] = None
    status: Literal["comparable", "not_comparable", "partial"] = "comparable"
    to_comparable_guidance: Optional[str] = None

    def to_schema(self) -> DecisionOptionSchema:
        """轉換為 Schema 格式"""
        return DecisionOptionSchema(
            direction=self.direction,
            label=self.label,
            recommendation=self.recommendation,
            score=self.score,
            status=self.status,
            to_comparable_guidance=self.to_comparable_guidance,
        )


@dataclass
class ComparisonResult:
    """比較結果

    決策比較器的完整輸出，永遠包含兩個選項。

    Attributes:
        comparability_score: 可比較性分數（0-1）
        is_comparable: 是否可比較（分數 >= 0.6）
        option_a: 保守方案
        option_b: 進取方案
        blocking_details: 結構化阻擋說明
        risk_tags: 風險標籤
        risk_explanation: 風險說明
        template_id: 使用的模板 ID
        weak_dimensions: 弱維度列表
    """

    comparability_score: float
    is_comparable: bool
    option_a: ComparisonOption
    option_b: ComparisonOption
    blocking_details: list[BlockingReasonDetail] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    risk_explanation: str = ""
    template_id: str = "default"
    weak_dimensions: list[str] = field(default_factory=list)

    @property
    def blocking_reasons(self) -> list[str]:
        """向後相容：回傳阻擋原因代碼列表"""
        return [d.code for d in self.blocking_details]


class DecisionComparator:
    """決策比較器

    純規則引擎，從去識別化的決策上下文生成比較結果。

    使用方式:
        comparator = DecisionComparator()
        result = comparator.compare(context, template_id="buying_house")
    """

    def __init__(self):
        """初始化比較器"""
        self.comparability_calculator = ComparabilityCalculator()
        self._template_rules = self._load_template_rules()

    def compare(
        self,
        context: RedactedDecisionContext,
        template_id: str = "default"
    ) -> ComparisonResult:
        """執行決策比較

        Args:
            context: 去識別化的決策上下文
            template_id: 決策模板 ID

        Returns:
            比較結果（永遠包含兩個選項）
        """
        # Step 1: 計算可比較性
        comparability = self.comparability_calculator.calculate(
            context, template_id
        )

        # Step 2: 評估風險
        risk_tags, risk_explanation = self._assess_risks(context, template_id)

        # Step 3: 生成選項（無論是否可比較都生成兩個）
        if comparability.is_comparable:
            option_a, option_b = self._generate_comparable_options(
                context, template_id, comparability
            )
        else:
            option_a, option_b = self._generate_not_comparable_options(
                context, template_id, comparability
            )

        # Step 4: 生成阻擋詳情
        blocking_details = self._generate_blocking_details(
            comparability, template_id
        )

        return ComparisonResult(
            comparability_score=comparability.total_score,
            is_comparable=comparability.is_comparable,
            option_a=option_a,
            option_b=option_b,
            blocking_details=blocking_details,
            risk_tags=risk_tags,
            risk_explanation=risk_explanation,
            template_id=template_id,
            weak_dimensions=comparability.weak_dimensions,
        )

    def _assess_risks(
        self,
        context: RedactedDecisionContext,
        template_id: str
    ) -> tuple[list[str], str]:
        """評估風險

        Args:
            context: 決策上下文
            template_id: 模板 ID

        Returns:
            (風險標籤列表, 風險說明)
        """
        risk_tags = []
        explanations = []

        # 連續赤字風險
        if context.consecutive_deficit_months >= 3:
            risk_tags.append("high_deficit_streak")
            explanations.append(
                f"連續 {context.consecutive_deficit_months} 個月赤字"
            )
        elif context.consecutive_deficit_months >= 1:
            risk_tags.append("recent_deficit")
            explanations.append(
                f"近期有 {context.consecutive_deficit_months} 個月赤字"
            )

        # 收入波動風險
        if context.income_volatility == "high":
            risk_tags.append("high_income_volatility")
            explanations.append("收入波動較大")

        # 跑道不足風險
        if context.runway_months is not None:
            if context.runway_months < 3:
                risk_tags.append("critical_runway")
                explanations.append(f"緊急備用金僅剩 {context.runway_months} 個月")
            elif context.runway_months < 6:
                risk_tags.append("short_runway")
                explanations.append(f"緊急備用金約 {context.runway_months} 個月")

        # 儲蓄率風險
        if context.savings_rate_band == "0-10%":
            risk_tags.append("low_savings_rate")
            explanations.append("儲蓄率偏低（<10%）")

        # 支出趨勢風險
        if context.expense_trend == "increasing":
            risk_tags.append("increasing_expenses")
            explanations.append("支出呈上升趨勢")

        # 模板特定風險
        if template_id == "buying_house":
            if context.runway_months is not None and context.runway_months < 12:
                if "short_runway" not in risk_tags:
                    risk_tags.append("insufficient_downpayment_buffer")
                    explanations.append("首付準備期間備用金不足")

        risk_explanation = "；".join(explanations) if explanations else "財務狀況穩定"

        return risk_tags, risk_explanation

    def _generate_comparable_options(
        self,
        context: RedactedDecisionContext,
        template_id: str,
        comparability: ComparabilityResult
    ) -> tuple[ComparisonOption, ComparisonOption]:
        """生成可比較的選項

        Args:
            context: 決策上下文
            template_id: 模板 ID
            comparability: 可比較性結果

        Returns:
            (保守方案, 進取方案)
        """
        rules = self._template_rules.get(template_id, self._template_rules["default"])

        # 計算選項分數
        conservative_score = self._calculate_option_score(
            context, "conservative", template_id
        )
        aggressive_score = self._calculate_option_score(
            context, "aggressive", template_id
        )

        option_a = ComparisonOption(
            direction="conservative",
            label=rules["conservative_label"],
            recommendation=self._generate_recommendation(
                context, "conservative", template_id
            ),
            score=conservative_score,
            status="comparable",
        )

        option_b = ComparisonOption(
            direction="aggressive",
            label=rules["aggressive_label"],
            recommendation=self._generate_recommendation(
                context, "aggressive", template_id
            ),
            score=aggressive_score,
            status="comparable",
        )

        return option_a, option_b

    def _generate_not_comparable_options(
        self,
        context: RedactedDecisionContext,
        template_id: str,
        comparability: ComparabilityResult
    ) -> tuple[ComparisonOption, ComparisonOption]:
        """生成不可比較的選項（仍輸出兩個選項）

        Args:
            context: 決策上下文
            template_id: 模板 ID
            comparability: 可比較性結果

        Returns:
            (保守方案, 進取方案)
        """
        rules = self._template_rules.get(template_id, self._template_rules["default"])

        # 生成補件指引
        guidance = self._generate_comparable_guidance(
            comparability.weak_dimensions, template_id
        )

        option_a = ComparisonOption(
            direction="conservative",
            label=rules["conservative_label"],
            recommendation=None,
            score=None,
            status="not_comparable",
            to_comparable_guidance=guidance,
        )

        option_b = ComparisonOption(
            direction="aggressive",
            label=rules["aggressive_label"],
            recommendation=None,
            score=None,
            status="not_comparable",
            to_comparable_guidance=guidance,
        )

        return option_a, option_b

    def _calculate_option_score(
        self,
        context: RedactedDecisionContext,
        direction: Literal["conservative", "aggressive"],
        template_id: str
    ) -> float:
        """計算選項分數

        Args:
            context: 決策上下文
            direction: 選項方向
            template_id: 模板 ID

        Returns:
            選項分數（0-1）
        """
        base_score = 0.5

        # 根據財務狀況調整
        risk_level = context.get_risk_level()

        if direction == "conservative":
            # 保守方案在高風險時更有利
            if risk_level == "high":
                base_score += 0.3
            elif risk_level == "medium":
                base_score += 0.15
            # 儲蓄率低時保守更好
            if context.savings_rate_band == "0-10%":
                base_score += 0.1
        else:  # aggressive
            # 進取方案在低風險時更有利
            if risk_level == "low":
                base_score += 0.25
            # 儲蓄率高時進取更好
            if context.savings_rate_band == "30%+":
                base_score += 0.15
            # 收入穩定時進取更好
            if context.income_volatility == "low":
                base_score += 0.1

        return max(0.0, min(1.0, base_score))

    def _generate_recommendation(
        self,
        context: RedactedDecisionContext,
        direction: Literal["conservative", "aggressive"],
        template_id: str
    ) -> str:
        """生成建議文字

        Args:
            context: 決策上下文
            direction: 選項方向
            template_id: 模板 ID

        Returns:
            建議文字
        """
        rules = self._template_rules.get(template_id, self._template_rules["default"])
        risk_level = context.get_risk_level()

        if direction == "conservative":
            if risk_level == "high":
                return rules.get(
                    "conservative_high_risk",
                    "建議優先穩固財務基礎，延後重大決策。"
                )
            elif risk_level == "medium":
                return rules.get(
                    "conservative_medium_risk",
                    "建議謹慎評估，可考慮較保守的方案。"
                )
            else:
                return rules.get(
                    "conservative_low_risk",
                    "財務狀況良好，保守方案可作為備選。"
                )
        else:  # aggressive
            if risk_level == "high":
                return rules.get(
                    "aggressive_high_risk",
                    "目前財務狀況不適合激進方案，建議先改善財務。"
                )
            elif risk_level == "medium":
                return rules.get(
                    "aggressive_medium_risk",
                    "可謹慎考慮進取方案，但需準備應急預案。"
                )
            else:
                return rules.get(
                    "aggressive_low_risk",
                    "財務狀況支持進取方案，可積極把握機會。"
                )

    def _generate_comparable_guidance(
        self,
        weak_dimensions: list[str],
        template_id: str
    ) -> str:
        """生成補件指引

        Args:
            weak_dimensions: 弱維度列表
            template_id: 模板 ID

        Returns:
            補件指引文字
        """
        guidance_parts = ["需補充以下資訊以進行比較："]

        dimension_guidance = {
            "time_horizon": "確認決策時間範圍與財務跑道",
            "risk_tolerance": "評估收入穩定度與風險承受能力",
            "liquidity": "確認流動性需求與緊急備用金狀況",
            "capital_need": "確認資金需求與儲蓄能力",
        }

        for dim in weak_dimensions:
            if dim in dimension_guidance:
                guidance_parts.append(f"• {dimension_guidance[dim]}")

        return "\n".join(guidance_parts)

    def _generate_blocking_details(
        self,
        comparability: ComparabilityResult,
        template_id: str
    ) -> list[BlockingReasonDetail]:
        """生成阻擋詳情

        Args:
            comparability: 可比較性結果
            template_id: 模板 ID

        Returns:
            阻擋詳情列表
        """
        details = []

        if comparability.blocking_reasons:
            for reason in comparability.blocking_reasons:
                severity: Literal["blocking", "warning"] = "blocking"
                message = self._get_blocking_message(reason)

                # 判斷是否為警告級別
                if reason.startswith("SEGMENT_"):
                    severity = "warning"

                details.append(BlockingReasonDetail(
                    code=reason,
                    message=message,
                    severity=severity,
                    affected_segments=self._get_affected_segments(reason),
                ))

        return details

    def _get_blocking_message(self, reason: str) -> str:
        """取得阻擋原因訊息

        Args:
            reason: 阻擋原因代碼

        Returns:
            人類可讀的訊息
        """
        messages = {
            "TIME_HORIZON_INSUFFICIENT": "財務跑道不足以支撐決策時間範圍",
            "RISK_TOLERANCE_LOW": "收入波動度過高，風險承受能力不足",
            "LIQUIDITY_INSUFFICIENT": "流動性不足，緊急備用金過低",
            "CAPITAL_NEED_HIGH": "資金需求與當前財務狀況不匹配",
            "SEGMENT_首付階段_INSUFFICIENT": "首付階段資金準備不足",
            "SEGMENT_貸款期_INSUFFICIENT": "貸款期現金流評估未達標準",
            "SEGMENT_退休累積_INSUFFICIENT": "退休累積規劃需要調整",
            "SEGMENT_初期投入_INSUFFICIENT": "初期投入資金評估未達標準",
            "SEGMENT_增長期_INSUFFICIENT": "增長期持續投入能力不足",
        }
        return messages.get(reason, reason)

    def _get_affected_segments(self, reason: str) -> list[str]:
        """取得受影響的時段

        Args:
            reason: 阻擋原因代碼

        Returns:
            受影響的時段列表
        """
        if reason.startswith("SEGMENT_"):
            # 從 SEGMENT_<名稱>_INSUFFICIENT 抽取時段名稱
            parts = reason.split("_")
            if len(parts) >= 2:
                return [parts[1]]
        return []

    def _load_template_rules(self) -> dict:
        """載入模板規則

        Returns:
            模板規則字典
        """
        return {
            "default": {
                "conservative_label": "方案 A：穩健選擇",
                "aggressive_label": "方案 B：積極選擇",
                "conservative_high_risk": "建議優先穩固財務基礎，延後重大決策。",
                "conservative_medium_risk": "建議謹慎評估，可考慮較保守的方案。",
                "conservative_low_risk": "財務狀況良好，保守方案可作為備選。",
                "aggressive_high_risk": "目前財務狀況不適合激進方案，建議先改善財務。",
                "aggressive_medium_risk": "可謹慎考慮進取方案，但需準備應急預案。",
                "aggressive_low_risk": "財務狀況支持進取方案，可積極把握機會。",
            },
            "buying_house": {
                "conservative_label": "方案 A：延後購房",
                "aggressive_label": "方案 B：現在購房",
                "conservative_high_risk": (
                    "建議延後購房 6-12 個月，先累積更多首付並建立緊急備用金。"
                ),
                "conservative_medium_risk": "可考慮延後購房，或選擇較低總價的物件以降低風險。",
                "conservative_low_risk": "財務狀況良好，延後購房可進一步累積資本。",
                "aggressive_high_risk": "目前財務狀況不適合購房，貸款壓力可能過大。",
                "aggressive_medium_risk": "現在購房需謹慎評估貸款負擔，建議準備充足備用金。",
                "aggressive_low_risk": "財務狀況支持購房，可積極尋找合適物件。",
            },
            "investment": {
                "conservative_label": "方案 A：維持現狀",
                "aggressive_label": "方案 B：增加投資",
                "conservative_high_risk": "建議暫不增加投資，優先建立穩定的現金流。",
                "conservative_medium_risk": "可維持現有投資配置，待財務更穩定後再調整。",
                "conservative_low_risk": "財務穩健，維持現狀可保持彈性。",
                "aggressive_high_risk": "目前不建議增加投資，需先改善財務狀況。",
                "aggressive_medium_risk": "可小幅增加投資，但需保留足夠流動資金。",
                "aggressive_low_risk": "財務狀況良好，可考慮增加投資配置。",
            },
            "car_purchase": {
                "conservative_label": "方案 A：延後購車",
                "aggressive_label": "方案 B：現在購車",
                "conservative_high_risk": "建議延後購車，優先處理財務赤字問題。",
                "conservative_medium_risk": "可考慮延後購車或選擇較經濟的車款。",
                "conservative_low_risk": "財務狀況良好，延後購車可累積更多資金。",
                "aggressive_high_risk": "目前財務狀況不適合購車，會加重現金流壓力。",
                "aggressive_medium_risk": "購車需謹慎評估每月開支增加的影響。",
                "aggressive_low_risk": "財務狀況支持購車，可選擇合適價位的車款。",
            },
            "travel": {
                "conservative_label": "方案 A：簡約旅行",
                "aggressive_label": "方案 B：豪華旅行",
                "conservative_high_risk": "建議選擇簡約旅行或暫時延後，優先穩定財務。",
                "conservative_medium_risk": "可選擇較經濟的旅行方案。",
                "conservative_low_risk": "財務狀況良好，簡約旅行可保留更多彈性。",
                "aggressive_high_risk": "目前不建議大額旅行支出。",
                "aggressive_medium_risk": "可在預算範圍內安排旅行，但需控制開支。",
                "aggressive_low_risk": "財務狀況支持較高預算的旅行。",
            },
            "savings_target": {
                "conservative_label": "方案 A：穩健目標",
                "aggressive_label": "方案 B：積極目標",
                "conservative_high_risk": "建議設定較保守的儲蓄目標，優先穩定收支。",
                "conservative_medium_risk": "可設定中等儲蓄目標，逐步提升。",
                "conservative_low_risk": "財務穩健，穩健目標可確保達成。",
                "aggressive_high_risk": "目前不適合設定高儲蓄目標，需先改善財務。",
                "aggressive_medium_risk": "積極目標需謹慎評估可行性。",
                "aggressive_low_risk": "財務狀況支持較高的儲蓄目標。",
            },
        }
