"""Templates 測試

測試 advisor/templates/ 的模板 DSL 與註冊機制。
"""

import pytest

from life_capital.advisor.templates import (
    DecisionTemplate,
    TemplateRegistry,
    get_all_templates,
    load_template,
)
from life_capital.advisor.templates.schema import (
    TEMPLATE_BUYING_HOUSE,
    TEMPLATE_CAR_PURCHASE,
    TEMPLATE_DEFAULT,
    TEMPLATE_INVESTMENT,
    TEMPLATE_SAVINGS_TARGET,
    TEMPLATE_TRAVEL,
    ComparabilityConfig,
    OptionLabels,
    RecommendationTexts,
    RiskRule,
    TimeSegmentConfig,
)


class TestTimeSegmentConfig:
    """時間分段配置測試"""

    def test_create_time_segment(self):
        """測試建立時間分段"""
        segment = TimeSegmentConfig(
            name="首付階段",
            duration="0-6個月",
            weight=0.3,
            threshold=0.7,
            metrics=("可用現金", "緊急備金"),
        )
        assert segment.name == "首付階段"
        assert segment.weight == 0.3
        assert segment.threshold == 0.7
        assert len(segment.metrics) == 2

    def test_immutability(self):
        """測試不可變性"""
        segment = TimeSegmentConfig(
            name="測試",
            duration="0-12個月",
            weight=0.5,
        )
        with pytest.raises(Exception):
            segment.name = "新名稱"


class TestRiskRule:
    """風險規則測試"""

    def test_create_risk_rule(self):
        """測試建立風險規則"""
        rule = RiskRule(
            tag="insufficient_downpayment",
            condition="runway_months < 12",
            severity="high",
            message="首付準備期間備用金不足",
        )
        assert rule.tag == "insufficient_downpayment"
        assert rule.severity == "high"

    def test_severity_values(self):
        """測試嚴重程度值"""
        for severity in ["high", "medium", "low"]:
            rule = RiskRule(
                tag="test",
                condition="true",
                severity=severity,
                message="test",
            )
            assert rule.severity == severity


class TestOptionLabels:
    """選項標籤測試"""

    def test_create_labels(self):
        """測試建立標籤"""
        labels = OptionLabels(
            conservative="方案 A：穩健選擇",
            aggressive="方案 B：積極選擇",
        )
        assert "穩健" in labels.conservative
        assert "積極" in labels.aggressive


class TestRecommendationTexts:
    """建議文字測試"""

    def test_create_recommendations(self):
        """測試建立建議文字"""
        recs = RecommendationTexts(
            conservative_high_risk="建議優先穩固財務基礎",
            conservative_medium_risk="建議謹慎評估",
            conservative_low_risk="財務狀況良好",
            aggressive_high_risk="目前不適合激進方案",
            aggressive_medium_risk="可謹慎考慮進取方案",
            aggressive_low_risk="財務狀況支持進取方案",
        )
        assert "財務基礎" in recs.conservative_high_risk
        assert "不適合" in recs.aggressive_high_risk


class TestComparabilityConfig:
    """可比較性配置測試"""

    def test_default_config(self):
        """測試預設配置"""
        config = ComparabilityConfig()
        assert config.threshold == 0.6
        assert len(config.time_segments) == 0

    def test_custom_config(self):
        """測試自訂配置"""
        config = ComparabilityConfig(
            threshold=0.7,
            time_segments=(
                TimeSegmentConfig(
                    name="初期",
                    duration="0-6個月",
                    weight=0.4,
                ),
                TimeSegmentConfig(
                    name="後期",
                    duration="6-12個月",
                    weight=0.6,
                ),
            ),
        )
        assert config.threshold == 0.7
        assert len(config.time_segments) == 2
        # 權重總和應為 1
        total_weight = sum(s.weight for s in config.time_segments)
        assert total_weight == pytest.approx(1.0, abs=0.01)


class TestDecisionTemplate:
    """決策模板測試"""

    def test_template_structure(self):
        """測試模板結構"""
        template = TEMPLATE_DEFAULT
        assert template.id == "default"
        assert template.name == "通用決策"
        assert template.category == "general"
        assert template.version == "1.0"

    def test_buying_house_template(self):
        """測試買房模板"""
        template = TEMPLATE_BUYING_HOUSE
        assert template.id == "buying_house"
        assert template.category == "major_purchase"
        assert len(template.comparability.time_segments) == 3
        assert len(template.risk_rules) >= 1

    def test_investment_template(self):
        """測試投資模板"""
        template = TEMPLATE_INVESTMENT
        assert template.id == "investment"
        assert template.category == "investment"
        assert len(template.required_fields) >= 1

    def test_template_immutability(self):
        """測試模板不可變性"""
        template = TEMPLATE_DEFAULT
        with pytest.raises(Exception):
            template.id = "new_id"


class TestTemplateRegistry:
    """模板註冊表測試"""

    def test_create_registry(self):
        """測試建立註冊表"""
        registry = TemplateRegistry()
        assert registry is not None

    def test_get_template(self):
        """測試取得模板"""
        registry = TemplateRegistry()
        template = registry.get("buying_house")
        assert template is not None
        assert template.id == "buying_house"

    def test_get_nonexistent_template(self):
        """測試取得不存在的模板"""
        registry = TemplateRegistry()
        template = registry.get("nonexistent")
        assert template is None

    def test_get_or_default(self):
        """測試取得模板或預設"""
        registry = TemplateRegistry()

        # 存在的模板
        template = registry.get_or_default("buying_house")
        assert template.id == "buying_house"

        # 不存在的模板應回傳 default
        template = registry.get_or_default("nonexistent")
        assert template.id == "default"

    def test_get_all(self):
        """測試取得所有模板"""
        registry = TemplateRegistry()
        templates = registry.get_all()
        assert len(templates) >= 6
        ids = [t.id for t in templates]
        assert "default" in ids
        assert "buying_house" in ids
        assert "investment" in ids

    def test_get_by_category(self):
        """測試根據分類取得模板"""
        registry = TemplateRegistry()

        major_purchases = registry.get_by_category("major_purchase")
        assert len(major_purchases) >= 2
        for t in major_purchases:
            assert t.category == "major_purchase"

    def test_list_ids(self):
        """測試列出所有 ID"""
        registry = TemplateRegistry()
        ids = registry.list_ids()
        assert "default" in ids
        assert "buying_house" in ids
        assert len(ids) >= 6

    def test_register_custom_template(self):
        """測試註冊自訂模板"""
        registry = TemplateRegistry()
        custom = DecisionTemplate(
            id="custom_test",
            name="測試模板",
            description="用於測試的自訂模板",
            category="test",
            labels=OptionLabels(
                conservative="A",
                aggressive="B",
            ),
            recommendations=RecommendationTexts(
                conservative_high_risk="A",
                conservative_medium_risk="B",
                conservative_low_risk="C",
                aggressive_high_risk="D",
                aggressive_medium_risk="E",
                aggressive_low_risk="F",
            ),
        )
        registry.register(custom)

        retrieved = registry.get("custom_test")
        assert retrieved is not None
        assert retrieved.id == "custom_test"


class TestConvenienceFunctions:
    """便捷函式測試"""

    def test_load_template(self):
        """測試載入模板"""
        template = load_template("buying_house")
        assert template.id == "buying_house"

    def test_load_template_fallback(self):
        """測試載入模板 fallback"""
        template = load_template("nonexistent")
        assert template.id == "default"

    def test_get_all_templates(self):
        """測試取得所有模板"""
        templates = get_all_templates()
        assert len(templates) >= 6


class TestTemplateContentValidation:
    """模板內容驗證測試"""

    @pytest.mark.parametrize("template", [
        TEMPLATE_DEFAULT,
        TEMPLATE_BUYING_HOUSE,
        TEMPLATE_INVESTMENT,
        TEMPLATE_CAR_PURCHASE,
        TEMPLATE_TRAVEL,
        TEMPLATE_SAVINGS_TARGET,
    ])
    def test_template_has_required_fields(self, template):
        """測試模板有必要欄位"""
        assert template.id
        assert template.name
        assert template.description
        assert template.category
        assert template.labels
        assert template.recommendations

    @pytest.mark.parametrize("template", [
        TEMPLATE_DEFAULT,
        TEMPLATE_BUYING_HOUSE,
        TEMPLATE_INVESTMENT,
        TEMPLATE_CAR_PURCHASE,
        TEMPLATE_TRAVEL,
        TEMPLATE_SAVINGS_TARGET,
    ])
    def test_template_labels_not_empty(self, template):
        """測試標籤非空"""
        assert len(template.labels.conservative) > 0
        assert len(template.labels.aggressive) > 0

    @pytest.mark.parametrize("template", [
        TEMPLATE_DEFAULT,
        TEMPLATE_BUYING_HOUSE,
        TEMPLATE_INVESTMENT,
        TEMPLATE_CAR_PURCHASE,
        TEMPLATE_TRAVEL,
        TEMPLATE_SAVINGS_TARGET,
    ])
    def test_template_recommendations_not_empty(self, template):
        """測試建議文字非空"""
        recs = template.recommendations
        assert len(recs.conservative_high_risk) > 0
        assert len(recs.conservative_medium_risk) > 0
        assert len(recs.conservative_low_risk) > 0
        assert len(recs.aggressive_high_risk) > 0
        assert len(recs.aggressive_medium_risk) > 0
        assert len(recs.aggressive_low_risk) > 0

    def test_buying_house_time_segments_weights(self):
        """測試買房模板時間分段權重"""
        template = TEMPLATE_BUYING_HOUSE
        segments = template.comparability.time_segments
        total_weight = sum(s.weight for s in segments)
        assert total_weight == pytest.approx(1.0, abs=0.01)

    def test_investment_time_segments_weights(self):
        """測試投資模板時間分段權重"""
        template = TEMPLATE_INVESTMENT
        segments = template.comparability.time_segments
        if segments:
            total_weight = sum(s.weight for s in segments)
            assert total_weight == pytest.approx(1.0, abs=0.01)
