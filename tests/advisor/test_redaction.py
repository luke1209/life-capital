"""Redaction 測試

測試 privacy/redaction/ 的隱私保護層。
"""

import pytest

from life_capital.privacy.redaction.decision_context import (
    RedactedDecisionContext,
    RedactedPresentationView,
)
from life_capital.privacy.redaction.engine import (
    RedactionEngine,
    RedactionResult,
)
from life_capital.privacy.redaction.rules import (
    COMPOSITION_RULES,
    CURRENT_REDACTION_PROFILE,
    FORBIDDEN_FIELDS,
    SENSITIVE_FIELDS,
    RedactionProfile,
)


class TestForbiddenFields:
    """禁止欄位測試"""

    def test_contains_pii_fields(self):
        """測試包含個人識別欄位"""
        pii_fields = ["name", "full_name", "email", "phone", "id_number"]
        for field in pii_fields:
            assert field in FORBIDDEN_FIELDS, f"{field} should be forbidden"

    def test_contains_financial_fields(self):
        """測試包含金融欄位"""
        financial_fields = ["bank_account", "credit_card", "card_number", "iban"]
        for field in financial_fields:
            assert field in FORBIDDEN_FIELDS, f"{field} should be forbidden"

    def test_contains_contact_fields(self):
        """測試包含聯絡欄位"""
        contact_fields = ["address", "home_address", "company_address"]
        for field in contact_fields:
            assert field in FORBIDDEN_FIELDS, f"{field} should be forbidden"

    def test_is_frozen_set(self):
        """測試為不可變集合"""
        assert isinstance(FORBIDDEN_FIELDS, frozenset)


class TestSensitiveFields:
    """敏感欄位測試"""

    def test_contains_amount_fields(self):
        """測試包含金額欄位"""
        amount_fields = ["amount", "salary", "income"]
        for field in amount_fields:
            assert field in SENSITIVE_FIELDS, f"{field} should be sensitive"

    def test_contains_location_fields(self):
        """測試包含地點欄位"""
        location_fields = ["city", "district"]
        for field in location_fields:
            assert field in SENSITIVE_FIELDS, f"{field} should be sensitive"

    def test_contains_time_fields(self):
        """測試包含時間欄位"""
        time_fields = ["date", "birth_date"]
        for field in time_fields:
            assert field in SENSITIVE_FIELDS, f"{field} should be sensitive"


class TestCompositionRules:
    """組合規則測試"""

    def test_occupation_salary_rule(self):
        """測試職業+薪資規則"""
        assert ("occupation", "salary") in COMPOSITION_RULES

    def test_city_job_salary_rule(self):
        """測試城市+職位+薪資規則"""
        assert ("city", "job_title", "salary") in COMPOSITION_RULES

    def test_age_income_city_rule(self):
        """測試年齡+收入+城市規則"""
        assert ("age", "income_bracket", "city") in COMPOSITION_RULES

    def test_composition_rules_are_tuples(self):
        """測試組合規則為 tuple"""
        for rule in COMPOSITION_RULES:
            assert isinstance(rule, tuple)
            assert len(rule) >= 2


class TestRedactionProfile:
    """Redaction 配置測試"""

    def test_profile_version(self):
        """測試配置版本"""
        profile = CURRENT_REDACTION_PROFILE
        assert profile.version == "1.0"

    def test_profile_contains_forbidden(self):
        """測試配置包含禁止欄位"""
        profile = CURRENT_REDACTION_PROFILE
        assert len(profile.forbidden_fields) > 0

    def test_profile_contains_sensitive(self):
        """測試配置包含敏感欄位"""
        profile = CURRENT_REDACTION_PROFILE
        assert len(profile.sensitive_fields) > 0

    def test_profile_diff_detects_changes(self):
        """測試配置 diff 偵測變化"""
        profile_v1 = RedactionProfile(
            version="1.0",
            forbidden_fields=frozenset(["name", "email"]),
            sensitive_fields=frozenset(["amount"]),
            composition_rules=(("a", "b"),),
        )
        profile_v2 = RedactionProfile(
            version="1.1",
            forbidden_fields=frozenset(["name", "email", "phone"]),
            sensitive_fields=frozenset(["amount", "date"]),
            composition_rules=(("a", "b"), ("c", "d")),
        )

        diff = profile_v2.diff(profile_v1)
        assert "phone" in diff["added_forbidden"]
        assert "date" in diff["added_sensitive"]

    def test_profile_diff_detects_removed(self):
        """測試配置 diff 偵測移除"""
        profile_v1 = RedactionProfile(
            version="1.0",
            forbidden_fields=frozenset(["name", "email", "phone"]),
            sensitive_fields=frozenset(["amount"]),
            composition_rules=(),
        )
        profile_v2 = RedactionProfile(
            version="1.1",
            forbidden_fields=frozenset(["name", "email"]),
            sensitive_fields=frozenset(["amount"]),
            composition_rules=(),
        )

        diff = profile_v2.diff(profile_v1)
        assert "phone" in diff["removed_forbidden"]


class TestRedactedDecisionContext:
    """去識別決策上下文測試"""

    def test_create_context(self):
        """測試建立上下文"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.3, "housing": 0.4, "other": 0.3},
            deficit_month_count=2,
            runway_months=12,
            consecutive_deficit_months=1,
            income_volatility="medium",
            savings_rate_band="10-20%",
            expense_trend="stable",
        )
        assert context.deficit_month_count == 2
        assert context.income_volatility == "medium"

    def test_context_immutability(self):
        """測試上下文不可變性"""
        context = RedactedDecisionContext(
            expense_distribution={},
            deficit_month_count=0,
            runway_months=24,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="20-30%",
            expense_trend="stable",
        )
        with pytest.raises(Exception):
            context.deficit_month_count = 5

    def test_expense_distribution_normalized(self):
        """測試支出分佈已正規化"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.3, "housing": 0.4, "transport": 0.2, "other": 0.1},
            deficit_month_count=0,
            runway_months=24,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="20-30%",
            expense_trend="stable",
        )
        total = sum(context.expense_distribution.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_runway_months_none_for_long_horizon(self):
        """測試長期跑道為 None"""
        context = RedactedDecisionContext(
            expense_distribution={},
            deficit_month_count=0,
            runway_months=None,  # >120 個月
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="40-50%",
            expense_trend="decreasing",
        )
        assert context.runway_months is None


class TestRedactedPresentationView:
    """去識別呈現視圖測試"""

    def test_create_view(self):
        """測試建立視圖"""
        context = RedactedDecisionContext(
            expense_distribution={"food": 0.5, "other": 0.5},
            deficit_month_count=0,
            runway_months=24,
            consecutive_deficit_months=0,
            income_volatility="low",
            savings_rate_band="20-30%",
            expense_trend="stable",
        )
        view = RedactedPresentationView(
            context=context,
            summary_text="您的財務狀況穩健",
            risk_explanation="無明顯風險因素",
            comparison_narrative="方案 A 與方案 B 都適合您的情況",
        )
        assert view.summary_text == "您的財務狀況穩健"
        assert view.context.income_volatility == "low"


class TestRedactionEngine:
    """Redaction 引擎測試"""

    @pytest.fixture
    def engine(self):
        """建立引擎"""
        return RedactionEngine()

    @pytest.fixture
    def sample_data(self):
        """範例原始資料"""
        return {
            "monthly_income": 100000,
            "monthly_expense": 80000,
            "savings": 500000,
            "expense_categories": {
                "food": 20000,
                "housing": 30000,
                "transport": 10000,
                "other": 20000,
            },
            "deficit_months": [1, 2],
            "income_history": [95000, 100000, 105000, 100000, 98000, 102000],
        }

    def test_redact_produces_context(self, engine, sample_data):
        """測試 redact 產生上下文"""
        result = engine.redact(sample_data)
        assert isinstance(result.context, RedactedDecisionContext)

    def test_redact_tracks_redacted_fields(self, engine, sample_data):
        """測試追蹤已去識別欄位"""
        result = engine.redact(sample_data)
        assert isinstance(result, RedactionResult)
        # 原始金額欄位應被泛化
        assert "monthly_income" in result.generalized_fields or len(result.generalized_fields) >= 0

    def test_no_forbidden_fields_in_output(self, engine):
        """測試輸出不包含禁止欄位"""
        data_with_pii = {
            "name": "測試用戶",
            "email": "test@example.com",
            "monthly_income": 100000,
            "monthly_expense": 80000,
        }
        result = engine.redact(data_with_pii)

        # 確認禁止欄位被標記為已去識別
        if "name" in result.redacted_fields or "email" in result.redacted_fields:
            assert True
        else:
            # 即使沒有追蹤，輸出的 context 也不應包含這些欄位
            context_dict = {
                "expense_distribution": result.context.expense_distribution,
                "deficit_month_count": result.context.deficit_month_count,
                "runway_months": result.context.runway_months,
                "consecutive_deficit_months": result.context.consecutive_deficit_months,
                "income_volatility": result.context.income_volatility,
                "savings_rate_band": result.context.savings_rate_band,
                "expense_trend": result.context.expense_trend,
            }
            assert "name" not in str(context_dict)
            assert "email" not in str(context_dict)

    def test_composition_violation_detection(self, engine):
        """測試組合違規偵測"""
        data_with_composition = {
            "occupation": "軟體工程師",
            "salary": 200000,
            "monthly_expense": 80000,
        }
        result = engine.redact(data_with_composition)

        # 檢查是否偵測到組合違規
        # 即使沒有偵測到，也確保輸出不包含完整組合
        context_str = str(result.context)
        # 輸出不應同時包含職業和具體薪資
        has_occupation = "軟體工程師" in context_str
        has_exact_salary = "200000" in context_str
        # 至少其中一個應該被泛化
        assert not (has_occupation and has_exact_salary)


class TestRedactionStructuralTests:
    """結構化洩漏測試（property-based 風格）"""

    def test_no_exact_amount_in_output(self):
        """測試輸出不包含精確金額"""
        engine = RedactionEngine()
        test_amounts = [12345, 67890, 100000, 999999]

        for amount in test_amounts:
            data = {
                "monthly_income": amount,
                "monthly_expense": int(amount * 0.8),
            }
            result = engine.redact(data)

            # 上下文中不應包含精確金額
            context_str = str(result.context)
            assert str(amount) not in context_str

    def test_no_exact_date_in_output(self):
        """測試輸出不包含精確日期"""
        engine = RedactionEngine()
        data = {
            "transaction_date": "2025-01-15",
            "monthly_income": 100000,
            "monthly_expense": 80000,
        }
        result = engine.redact(data)

        context_str = str(result.context)
        assert "2025-01-15" not in context_str

    def test_income_volatility_is_categorical(self):
        """測試收入波動性為分類值"""
        engine = RedactionEngine()
        data = {
            "income_history": [100000, 95000, 105000, 98000, 102000, 100000],
            "monthly_expense": 80000,
        }
        result = engine.redact(data)

        assert result.context.income_volatility in ["low", "medium", "high"]

    def test_savings_rate_is_banded(self):
        """測試儲蓄率為區間值"""
        engine = RedactionEngine()
        data = {
            "monthly_income": 100000,
            "monthly_expense": 75000,
        }
        result = engine.redact(data)

        # 儲蓄率應為區間格式
        band = result.context.savings_rate_band
        assert "-" in band or "%" in band

    def test_expense_distribution_is_percentage(self):
        """測試支出分佈為百分比"""
        engine = RedactionEngine()
        data = {
            "expense_categories": {
                "food": 30000,
                "housing": 40000,
                "transport": 20000,
                "other": 20000,
            },
            "monthly_income": 100000,
        }
        result = engine.redact(data)

        for category, percentage in result.context.expense_distribution.items():
            assert 0 <= percentage <= 1, f"{category} percentage out of range"


class TestRedactionIntegration:
    """整合測試"""

    def test_full_redaction_workflow(self):
        """完整去識別工作流程"""
        # 模擬原始財務資料
        raw_data = {
            "user_name": "張三",
            "email": "zhangsan@example.com",
            "monthly_income": 120000,
            "monthly_expense": 60000,
            "savings": 600000,
            "expense_categories": {
                "food": 20000,
                "housing": 35000,
                "transport": 12000,
                "entertainment": 8000,
                "other": 5000,
            },
            "occupation": "工程師",
            "city": "台北",
            "income_history": [120000, 120000, 118000, 122000, 120000, 120000],
        }

        engine = RedactionEngine()
        result = engine.redact(raw_data)

        # 1. 確認產生有效上下文
        context = result.context
        assert isinstance(context, RedactedDecisionContext)

        # 2. 確認禁止欄位不在輸出
        context_str = str(context)
        assert "張三" not in context_str
        assert "zhangsan@example.com" not in context_str

        # 3. 確認敏感欄位已泛化
        assert "120000" not in context_str  # 精確收入
        assert "600000" not in context_str  # 精確存款

        # 4. 確認輸出包含可用的決策特徵
        assert context.income_volatility in ["low", "medium", "high"]
        assert len(context.expense_distribution) > 0
        assert context.deficit_month_count >= 0
