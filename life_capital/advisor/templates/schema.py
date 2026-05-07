"""決策模板 DSL Schema

定義決策模板的結構化格式，支援規則配置化。

設計原則:
- 配置化：模板規則以資料結構定義，非硬編碼
- 可擴展：新增模板無需修改核心邏輯
- 可驗證：每個模板都有 schema 驗證

使用方式:
    template = load_template("buying_house")
    registry = TemplateRegistry()
    all_templates = registry.get_all()
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass(frozen=True)
class TimeSegmentConfig:
    """時間分段配置

    定義特定時段的評分參數。

    Attributes:
        name: 分段名稱
        duration: 持續時間描述
        weight: 權重（0-1）
        threshold: 最低閾值
        metrics: 評估的指標列表
    """

    name: str
    duration: str
    weight: float
    threshold: float = 0.6
    metrics: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskRule:
    """風險規則

    定義觸發風險標籤的條件。

    Attributes:
        tag: 風險標籤
        condition: 觸發條件描述
        severity: 嚴重程度
        message: 風險訊息
    """

    tag: str
    condition: str
    severity: Literal["high", "medium", "low"]
    message: str


@dataclass(frozen=True)
class OptionLabels:
    """選項標籤配置

    Attributes:
        conservative: 保守方案標籤
        aggressive: 進取方案標籤
    """

    conservative: str
    aggressive: str


@dataclass(frozen=True)
class RecommendationTexts:
    """建議文字配置

    根據風險等級提供不同的建議文字。

    Attributes:
        conservative_high_risk: 高風險時的保守建議
        conservative_medium_risk: 中風險時的保守建議
        conservative_low_risk: 低風險時的保守建議
        aggressive_high_risk: 高風險時的進取建議
        aggressive_medium_risk: 中風險時的進取建議
        aggressive_low_risk: 低風險時的進取建議
    """

    conservative_high_risk: str
    conservative_medium_risk: str
    conservative_low_risk: str
    aggressive_high_risk: str
    aggressive_medium_risk: str
    aggressive_low_risk: str


@dataclass(frozen=True)
class ComparabilityConfig:
    """可比較性配置

    定義模板的可比較性評分參數。

    Attributes:
        threshold: 可比較性閾值
        time_segments: 時間分段配置列表
        dimension_weights: 維度權重覆寫
    """

    threshold: float = 0.6
    time_segments: tuple[TimeSegmentConfig, ...] = ()
    dimension_weights: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionTemplate:
    """決策模板

    定義決策場景的完整配置。

    Attributes:
        id: 模板 ID
        name: 模板名稱
        description: 模板描述
        category: 模板分類
        labels: 選項標籤
        recommendations: 建議文字
        comparability: 可比較性配置
        risk_rules: 風險規則列表
        required_fields: 必要欄位
        version: 模板版本
    """

    id: str
    name: str
    description: str
    category: str
    labels: OptionLabels
    recommendations: RecommendationTexts
    comparability: ComparabilityConfig = field(default_factory=ComparabilityConfig)
    risk_rules: tuple[RiskRule, ...] = ()
    required_fields: tuple[str, ...] = ()
    version: str = "1.0"


# === 預設模板定義 ===

TEMPLATE_DEFAULT = DecisionTemplate(
    id="default",
    name="通用決策",
    description="適用於一般財務決策的通用模板",
    category="general",
    labels=OptionLabels(
        conservative="方案 A：穩健選擇",
        aggressive="方案 B：積極選擇",
    ),
    recommendations=RecommendationTexts(
        conservative_high_risk="建議優先穩固財務基礎，延後重大決策。",
        conservative_medium_risk="建議謹慎評估，可考慮較保守的方案。",
        conservative_low_risk="財務狀況良好，保守方案可作為備選。",
        aggressive_high_risk="目前財務狀況不適合激進方案，建議先改善財務。",
        aggressive_medium_risk="可謹慎考慮進取方案，但需準備應急預案。",
        aggressive_low_risk="財務狀況支持進取方案，可積極把握機會。",
    ),
)

TEMPLATE_BUYING_HOUSE = DecisionTemplate(
    id="buying_house",
    name="買房決策",
    description="評估是否現在購房或延後購房",
    category="major_purchase",
    labels=OptionLabels(
        conservative="方案 A：延後購房",
        aggressive="方案 B：現在購房",
    ),
    recommendations=RecommendationTexts(
        conservative_high_risk="建議延後購房 6-12 個月，先累積更多首付並建立緊急備用金。",
        conservative_medium_risk="可考慮延後購房，或選擇較低總價的物件以降低風險。",
        conservative_low_risk="財務狀況良好，延後購房可進一步累積資本。",
        aggressive_high_risk="目前財務狀況不適合購房，貸款壓力可能過大。",
        aggressive_medium_risk="現在購房需謹慎評估貸款負擔，建議準備充足備用金。",
        aggressive_low_risk="財務狀況支持購房，可積極尋找合適物件。",
    ),
    comparability=ComparabilityConfig(
        threshold=0.6,
        time_segments=(
            TimeSegmentConfig(
                name="首付階段",
                duration="0-6個月",
                weight=0.3,
                threshold=0.7,
                metrics=("可用現金", "緊急備金"),
            ),
            TimeSegmentConfig(
                name="貸款期",
                duration="6個月-30年",
                weight=0.5,
                threshold=0.6,
                metrics=("月現金流", "利率風險"),
            ),
            TimeSegmentConfig(
                name="退休累積",
                duration="30年-60年",
                weight=0.2,
                threshold=0.5,
                metrics=("資產淨值", "終身購買力"),
            ),
        ),
    ),
    risk_rules=(
        RiskRule(
            tag="insufficient_downpayment",
            condition="runway_months < 12",
            severity="high",
            message="首付準備期間備用金不足",
        ),
        RiskRule(
            tag="high_debt_ratio",
            condition="savings_rate_band == '0-10%'",
            severity="medium",
            message="儲蓄率偏低，貸款負擔可能過重",
        ),
    ),
    required_fields=("runway_months", "savings_rate_band", "income_volatility"),
)

TEMPLATE_INVESTMENT = DecisionTemplate(
    id="investment",
    name="投資決策",
    description="評估是否增加投資配置",
    category="investment",
    labels=OptionLabels(
        conservative="方案 A：維持現狀",
        aggressive="方案 B：增加投資",
    ),
    recommendations=RecommendationTexts(
        conservative_high_risk="建議暫不增加投資，優先建立穩定的現金流。",
        conservative_medium_risk="可維持現有投資配置，待財務更穩定後再調整。",
        conservative_low_risk="財務穩健，維持現狀可保持彈性。",
        aggressive_high_risk="目前不建議增加投資，需先改善財務狀況。",
        aggressive_medium_risk="可小幅增加投資，但需保留足夠流動資金。",
        aggressive_low_risk="財務狀況良好，可考慮增加投資配置。",
    ),
    comparability=ComparabilityConfig(
        threshold=0.6,
        time_segments=(
            TimeSegmentConfig(
                name="初期投入",
                duration="0-1年",
                weight=0.4,
                threshold=0.6,
                metrics=("可投資金額", "風險承受"),
            ),
            TimeSegmentConfig(
                name="增長期",
                duration="1-10年",
                weight=0.6,
                threshold=0.5,
                metrics=("持續投入能力", "市場風險"),
            ),
        ),
    ),
    risk_rules=(
        RiskRule(
            tag="high_volatility",
            condition="income_volatility == 'high'",
            severity="high",
            message="收入波動大，投資風險承受能力有限",
        ),
    ),
    required_fields=("income_volatility", "consecutive_deficit_months"),
)

TEMPLATE_CAR_PURCHASE = DecisionTemplate(
    id="car_purchase",
    name="購車決策",
    description="評估是否現在購車或延後購車",
    category="major_purchase",
    labels=OptionLabels(
        conservative="方案 A：延後購車",
        aggressive="方案 B：現在購車",
    ),
    recommendations=RecommendationTexts(
        conservative_high_risk="建議延後購車，優先處理財務赤字問題。",
        conservative_medium_risk="可考慮延後購車或選擇較經濟的車款。",
        conservative_low_risk="財務狀況良好，延後購車可累積更多資金。",
        aggressive_high_risk="目前財務狀況不適合購車，會加重現金流壓力。",
        aggressive_medium_risk="購車需謹慎評估每月開支增加的影響。",
        aggressive_low_risk="財務狀況支持購車，可選擇合適價位的車款。",
    ),
)

TEMPLATE_TRAVEL = DecisionTemplate(
    id="travel",
    name="旅行決策",
    description="評估旅行預算等級",
    category="leisure",
    labels=OptionLabels(
        conservative="方案 A：簡約旅行",
        aggressive="方案 B：豪華旅行",
    ),
    recommendations=RecommendationTexts(
        conservative_high_risk="建議選擇簡約旅行或暫時延後，優先穩定財務。",
        conservative_medium_risk="可選擇較經濟的旅行方案。",
        conservative_low_risk="財務狀況良好，簡約旅行可保留更多彈性。",
        aggressive_high_risk="目前不建議大額旅行支出。",
        aggressive_medium_risk="可在預算範圍內安排旅行，但需控制開支。",
        aggressive_low_risk="財務狀況支持較高預算的旅行。",
    ),
)

TEMPLATE_SAVINGS_TARGET = DecisionTemplate(
    id="savings_target",
    name="儲蓄目標",
    description="評估儲蓄目標等級",
    category="savings",
    labels=OptionLabels(
        conservative="方案 A：穩健目標",
        aggressive="方案 B：積極目標",
    ),
    recommendations=RecommendationTexts(
        conservative_high_risk="建議設定較保守的儲蓄目標，優先穩定收支。",
        conservative_medium_risk="可設定中等儲蓄目標，逐步提升。",
        conservative_low_risk="財務穩健，穩健目標可確保達成。",
        aggressive_high_risk="目前不適合設定高儲蓄目標，需先改善財務。",
        aggressive_medium_risk="積極目標需謹慎評估可行性。",
        aggressive_low_risk="財務狀況支持較高的儲蓄目標。",
    ),
)


class TemplateRegistry:
    """模板註冊表

    管理所有決策模板的註冊與查詢。

    使用方式:
        registry = TemplateRegistry()
        template = registry.get("buying_house")
        all_templates = registry.get_all()
    """

    def __init__(self):
        """初始化註冊表"""
        self._templates: dict[str, DecisionTemplate] = {}
        self._register_defaults()

    def _register_defaults(self):
        """註冊預設模板"""
        defaults = [
            TEMPLATE_DEFAULT,
            TEMPLATE_BUYING_HOUSE,
            TEMPLATE_INVESTMENT,
            TEMPLATE_CAR_PURCHASE,
            TEMPLATE_TRAVEL,
            TEMPLATE_SAVINGS_TARGET,
        ]
        for template in defaults:
            self.register(template)

    def register(self, template: DecisionTemplate) -> None:
        """註冊模板

        Args:
            template: 要註冊的模板
        """
        self._templates[template.id] = template

    def get(self, template_id: str) -> Optional[DecisionTemplate]:
        """取得模板

        Args:
            template_id: 模板 ID

        Returns:
            模板實例，若不存在則回傳 None
        """
        return self._templates.get(template_id)

    def get_or_default(self, template_id: str) -> DecisionTemplate:
        """取得模板或預設模板

        Args:
            template_id: 模板 ID

        Returns:
            模板實例，若不存在則回傳預設模板
        """
        return self._templates.get(template_id, TEMPLATE_DEFAULT)

    def get_all(self) -> list[DecisionTemplate]:
        """取得所有模板

        Returns:
            所有已註冊的模板列表
        """
        return list(self._templates.values())

    def get_by_category(self, category: str) -> list[DecisionTemplate]:
        """根據分類取得模板

        Args:
            category: 模板分類

        Returns:
            該分類的所有模板
        """
        return [t for t in self._templates.values() if t.category == category]

    def list_ids(self) -> list[str]:
        """列出所有模板 ID

        Returns:
            模板 ID 列表
        """
        return list(self._templates.keys())


# === 便捷函式 ===

_default_registry: Optional[TemplateRegistry] = None


def _get_registry() -> TemplateRegistry:
    """取得預設註冊表（單例）"""
    global _default_registry
    if _default_registry is None:
        _default_registry = TemplateRegistry()
    return _default_registry


def load_template(template_id: str) -> DecisionTemplate:
    """載入模板

    Args:
        template_id: 模板 ID

    Returns:
        模板實例，若不存在則回傳預設模板
    """
    return _get_registry().get_or_default(template_id)


def get_all_templates() -> list[DecisionTemplate]:
    """取得所有模板

    Returns:
        所有已註冊的模板列表
    """
    return _get_registry().get_all()
