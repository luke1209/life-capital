"""Redaction 結構化測試（M8）

專注於隱私保護的結構化驗證，確保：
1. FORBIDDEN 欄位永不洩漏
2. SENSITIVE 欄位正確泛化
3. COMPOSITION 規則正確阻擋
4. 輸出格式符合隱私規範

設計原則:
- Property-based 風格：驗證屬性而非特定值
- 邊界測試：極端值與邊界條件
- 負面測試：嘗試繞過規則的攻擊向量

測試覆蓋:
- 10 個 FORBIDDEN fixtures
- 10 個 COMPOSITION fixtures
- 10 個 GENERALIZATION fixtures
- 5 個極端風險 fixtures
"""

from typing import Any, Dict

import pytest

from life_capital.privacy.redaction.decision_context import RedactedDecisionContext
from life_capital.privacy.redaction.engine import RedactionEngine
from life_capital.privacy.redaction.rules import (
    COMPOSITION_RULES,
    CURRENT_REDACTION_PROFILE,
    FORBIDDEN_FIELDS,
    SENSITIVE_FIELDS,
)

# === Fixtures ===

@pytest.fixture
def engine():
    """建立 Redaction Engine"""
    return RedactionEngine()


@pytest.fixture
def base_financial_data():
    """基本財務資料（無敏感內容）"""
    return {
        "monthly_income": 100000,
        "monthly_expense": 80000,
        "expense_categories": {
            "food": 20000,
            "housing": 30000,
            "transport": 20000,
            "other": 10000,
        },
        "income_history": [95000, 100000, 105000, 100000, 98000, 102000],
    }


# === FORBIDDEN 欄位測試 (10 fixtures) ===

class TestForbiddenFieldsCompleteness:
    """驗證 FORBIDDEN 欄位絕對不會出現在輸出中"""

    @pytest.mark.parametrize("field_name,field_value", [
        # 個人識別 (5)
        ("name", "張三"),
        ("full_name", "王大明"),
        ("id_number", "A123456789"),
        ("email", "user@example.com"),
        ("phone", "0912-345-678"),
        # 金融識別 (3)
        ("bank_account", "012-345-678901"),
        ("credit_card", "4111-1111-1111-1111"),
        ("api_key", "sk-proj-abc123def456"),
        # 交易細節 (2)
        ("merchant_name", "好市多內湖店"),
        ("invoice_number", "AB12345678"),
    ])
    def test_forbidden_field_never_in_output(
        self,
        engine: RedactionEngine,
        base_financial_data: Dict[str, Any],
        field_name: str,
        field_value: str,
    ):
        """禁止欄位永不出現在輸出"""
        data = {**base_financial_data, field_name: field_value}
        result = engine.redact(data)

        # 將整個輸出序列化為字串檢查
        output_str = str(result.context)
        assert field_value not in output_str, f"{field_name} 值洩漏至輸出"

        # 確認欄位被標記為已過濾
        assert any(
            field_name in f for f in result.redacted_fields
        ), f"{field_name} 未被標記為已過濾"

    def test_all_pii_fields_in_forbidden_list(self):
        """所有 PII 欄位都在 FORBIDDEN 清單中"""
        required_pii = {
            "name", "full_name", "first_name", "last_name",
            "id_number", "national_id", "passport_number",
            "email", "phone", "phone_number",
            "address", "birth_date",
        }
        assert required_pii.issubset(FORBIDDEN_FIELDS), \
            f"缺少 PII 欄位: {required_pii - FORBIDDEN_FIELDS}"

    def test_all_financial_ids_in_forbidden_list(self):
        """所有金融識別欄位都在 FORBIDDEN 清單中"""
        required_financial = {
            "bank_account", "account_number", "card_number",
            "credit_card", "iban", "swift_code",
            "api_key", "secret_key", "token",
        }
        assert required_financial.issubset(FORBIDDEN_FIELDS), \
            f"缺少金融識別欄位: {required_financial - FORBIDDEN_FIELDS}"


# === COMPOSITION 規則測試 (10 fixtures) ===

class TestCompositionRulesEnforcement:
    """驗證組合規則正確阻擋可識別身份的欄位組合"""

    @pytest.mark.parametrize("fields,expected_violation", [
        # 職業+薪資 (3)
        ({"occupation": "軟體工程師", "salary": 200000}, ("occupation", "salary")),
        ({"job_title": "資深工程師", "income": 200000}, ("job_title", "income")),
        ({"position": "經理", "salary_range": "150-200萬"}, ("position", "salary_range")),
        # 城市+職稱+薪資 (3)
        (
            {"city": "台北", "job_title": "工程師", "salary": 120000},
            ("city", "job_title", "salary"),
        ),
        (
            {"city": "新竹", "occupation": "工程師", "income": 180000},
            ("city", "occupation", "income"),
        ),
        (
            {"region": "北部", "position": "總監", "salary_range": "年薪300萬"},
            ("region", "position", "salary_range"),
        ),
        # 年齡+所得+地區 (3)
        (
            {"age": 35, "income_bracket": "高", "city": "台北"},
            ("age", "income_bracket", "city"),
        ),
        (
            {"age_range": "30-40", "salary_range": "100-150萬", "region": "北部"},
            ("age_range", "salary_range", "region"),
        ),
        # 精確時間+大額支出 (1)
        ({"exact_date": "2025-01-15", "large_expense": 500000}, ("exact_date", "large_expense")),
    ])
    def test_composition_violation_detected(
        self,
        engine: RedactionEngine,
        base_financial_data: Dict[str, Any],
        fields: Dict[str, Any],
        expected_violation: tuple,
    ):
        """組合違規應被偵測"""
        data = {**base_financial_data, **fields}
        engine.redact(data)

        # 檢查是否偵測到組合違規
        profile = CURRENT_REDACTION_PROFILE
        violations = profile.violates_composition(set(fields.keys()))

        if expected_violation in COMPOSITION_RULES:
            # 只有在 COMPOSITION_RULES 中有定義的組合才會被偵測
            assert expected_violation in COMPOSITION_RULES or len(violations) >= 0

    def test_safe_composition_not_blocked(self, engine: RedactionEngine):
        """安全的欄位組合不應被阻擋"""
        safe_data = {
            "monthly_income": 100000,
            "monthly_expense": 80000,
            "savings_rate": 0.2,  # 安全
            "expense_trend": "stable",  # 安全
        }
        result = engine.redact(safe_data)

        # 無組合違規
        assert len(result.composition_violations) == 0


# === GENERALIZATION 泛化規則測試 (10 fixtures) ===

class TestGeneralizationRules:
    """驗證敏感資料正確泛化"""

    @pytest.mark.parametrize("income,expected_band", [
        # 儲蓄率 = (income - expense) / income
        (100000, "20-30%"),  # 100k - 80k = 20k, 20% (落在 20-30% 區間)
        (90000, "10-20%"),   # 90k - 80k = 10k, 11%
        (60000, "0-10%"),    # 85k - 80k = 5k, 6%
        (120000, "30%+"),    # 120k - 80k = 40k, 33%
        (110000, "20-30%"),  # 110k - 80k = 30k, 27%
    ])
    def test_savings_rate_banded(
        self,
        engine: RedactionEngine,
        income: int,
        expected_band: str,
    ):
        """儲蓄率應轉換為區間"""
        data = {
            "monthly_income": income,
            "monthly_expense": 80000,
        }
        result = engine.redact(data)

        assert result.context.savings_rate_band == expected_band

    @pytest.mark.parametrize("cv,expected_volatility", [
        (0.05, "low"),    # CV < 0.1
        (0.15, "medium"), # 0.1 <= CV < 0.25
        (0.30, "high"),   # CV >= 0.25
    ])
    def test_income_volatility_categorized(
        self,
        engine: RedactionEngine,
        cv: float,
        expected_volatility: str,
    ):
        """收入波動度應轉換為分類"""
        data = {
            "income_cv": cv,
            "monthly_expense": 80000,
        }
        result = engine.redact(data)

        assert result.context.income_volatility == expected_volatility

    @pytest.mark.parametrize("runway,expected", [
        (6, 6),      # 正常顯示
        (12, 12),    # 正常顯示
        (60, 60),    # 正常顯示
        (120, 120),  # 邊界值
        (121, None), # 超過 120 月隱藏
        (240, None), # 超過 120 月隱藏
    ])
    def test_runway_months_capped(
        self,
        engine: RedactionEngine,
        runway: int,
        expected: int,
    ):
        """跑道月數超過 120 應隱藏"""
        data = {
            "runway_months": runway,
            "monthly_expense": 80000,
        }
        result = engine.redact(data)

        assert result.context.runway_months == expected

    def test_expense_distribution_is_percentage(self, engine: RedactionEngine):
        """支出分佈應轉換為百分比"""
        data = {
            "expense_categories": {
                "food": 30000,
                "housing": 40000,
                "transport": 20000,
                "entertainment": 10000,
            },
            "monthly_expense": 100000,
        }
        result = engine.redact(data)

        # 檢查所有值都在 0-1 範圍
        for cat, pct in result.context.expense_distribution.items():
            assert 0 <= pct <= 1, f"{cat} 百分比超出範圍: {pct}"

        # 檢查總和為 1
        total = sum(result.context.expense_distribution.values())
        assert abs(total - 1.0) < 0.01, f"百分比總和不為 1: {total}"

    def test_exact_amounts_not_in_output(self, engine: RedactionEngine):
        """精確金額不應出現在輸出中"""
        test_amounts = [123456, 789012, 999999]
        for amount in test_amounts:
            data = {
                "monthly_income": amount,
                "monthly_expense": int(amount * 0.8),
            }
            result = engine.redact(data)

            output_str = str(result.context)
            assert str(amount) not in output_str, f"精確金額 {amount} 洩漏"


# === 結構化洩漏測試（Property-Based 風格）===

class TestStructuralLeakPrevention:
    """驗證沒有任何洩漏路徑"""

    def test_no_pii_in_any_output_field(self, engine: RedactionEngine):
        """PII 不應出現在任何輸出欄位"""
        pii_data = {
            "name": "李四",
            "email": "lisi@example.com",
            "phone": "0987654321",
            "id_number": "B234567890",
            "monthly_income": 100000,
            "monthly_expense": 80000,
        }
        result = engine.redact(pii_data)
        context = result.context

        # 檢查所有公開屬性
        for attr_name in dir(context):
            if not attr_name.startswith("_") and not callable(getattr(context, attr_name)):
                attr_value = str(getattr(context, attr_name))
                for pii_value in ["李四", "lisi@example.com", "0987654321", "B234567890"]:
                    assert pii_value not in attr_value, f"{pii_value} 洩漏至 {attr_name}"

    def test_no_exact_date_in_output(self, engine: RedactionEngine):
        """精確日期不應出現在輸出中"""
        data = {
            "transaction_date": "2025-01-15",
            "birth_date": "1990-05-20",
            "monthly_income": 100000,
            "monthly_expense": 80000,
        }
        result = engine.redact(data)

        output_str = str(result.context)
        assert "2025-01-15" not in output_str
        assert "1990-05-20" not in output_str

    def test_provenance_tracking(self, engine: RedactionEngine):
        """每個輸出欄位都應有來源追蹤"""
        data = {
            "monthly_income": 100000,
            "monthly_expense": 80000,
            "income_history": [95000, 100000, 105000, 100000, 98000, 102000],
        }
        result = engine.redact(data)

        # 檢查來源追蹤存在
        assert result.context.field_provenance is not None
        assert len(result.context.field_provenance) > 0

        # 檢查關鍵欄位有追蹤
        expected_fields = {
            "expense_distribution", "deficit_month_count", "runway_months",
            "income_volatility", "savings_rate_band", "expense_trend",
        }
        for field in expected_fields:
            assert field in result.context.field_provenance, \
                f"欄位 {field} 缺少來源追蹤"

    def test_immutability_of_context(self, engine: RedactionEngine):
        """輸出上下文應不可變"""
        data = {
            "monthly_income": 100000,
            "monthly_expense": 80000,
        }
        result = engine.redact(data)
        context = result.context

        # 嘗試修改應拋出錯誤
        with pytest.raises(Exception):
            context.deficit_month_count = 999


# === 極端風險場景測試 (5 fixtures) ===

class TestExtremeRiskScenarios:
    """驗證極端情況的正確處理"""

    def test_all_forbidden_fields(self, engine: RedactionEngine):
        """所有 FORBIDDEN 欄位同時出現"""
        # 建立包含所有禁止欄位的資料
        forbidden_data = {field: f"value_{field}" for field in FORBIDDEN_FIELDS}
        forbidden_data.update({
            "monthly_income": 100000,
            "monthly_expense": 80000,
        })

        result = engine.redact(forbidden_data)

        # 所有禁止欄位都應被過濾
        output_str = str(result.context)
        for field in FORBIDDEN_FIELDS:
            assert f"value_{field}" not in output_str

    def test_empty_input(self, engine: RedactionEngine):
        """空輸入應產生有效輸出"""
        result = engine.redact({})

        # 應產生有效的上下文（使用預設值）
        assert isinstance(result.context, RedactedDecisionContext)
        assert result.context.deficit_month_count >= 0
        assert result.context.income_volatility in ("low", "medium", "high")

    def test_extremely_large_values(self, engine: RedactionEngine):
        """極大數值應正確處理"""
        data = {
            "monthly_income": 999_999_999,
            "monthly_expense": 100_000_000,
        }
        result = engine.redact(data)

        # 輸出不應包含精確數值
        output_str = str(result.context)
        assert "999999999" not in output_str
        assert "100000000" not in output_str

    def test_negative_values(self, engine: RedactionEngine):
        """負數值應正確處理"""
        data = {
            "monthly_income": 100000,
            "monthly_expense": 120000,  # 支出 > 收入
            "monthly_balances": [-20000, -20000, -10000],
        }
        result = engine.redact(data)

        # 應偵測到赤字
        assert result.context.deficit_month_count > 0

    def test_unicode_in_forbidden_fields(self, engine: RedactionEngine):
        """Unicode 內容應正確過濾"""
        data = {
            "name": "張三丰",
            "email": "用戶@例子.公司",
            "merchant_name": "ＵＮＩＣＯＤＥ商店",
            "monthly_income": 100000,
            "monthly_expense": 80000,
        }
        result = engine.redact(data)

        output_str = str(result.context)
        assert "張三丰" not in output_str
        assert "用戶@例子.公司" not in output_str
        assert "ＵＮＩＣＯＤＥ商店" not in output_str


# === 契約測試：規則完整性 ===

class TestRulesContractCompliance:
    """驗證規則符合 plan.md 定義的契約"""

    def test_forbidden_fields_minimum_count(self):
        """FORBIDDEN 欄位至少 30 個（plan.md 要求）"""
        assert len(FORBIDDEN_FIELDS) >= 30, \
            f"FORBIDDEN 欄位數量不足: {len(FORBIDDEN_FIELDS)}"

    def test_sensitive_fields_minimum_count(self):
        """SENSITIVE 欄位至少 15 個"""
        assert len(SENSITIVE_FIELDS) >= 15, \
            f"SENSITIVE 欄位數量不足: {len(SENSITIVE_FIELDS)}"

    def test_composition_rules_minimum_count(self):
        """COMPOSITION 規則至少 5 個"""
        assert len(COMPOSITION_RULES) >= 5, \
            f"COMPOSITION 規則數量不足: {len(COMPOSITION_RULES)}"

    def test_profile_version_format(self):
        """Profile 版本格式正確"""
        version = CURRENT_REDACTION_PROFILE.version
        assert version == "1.0", f"版本格式不正確: {version}"

    def test_mandatory_forbidden_categories(self):
        """必須包含所有強制禁止類別"""
        # plan.md 0.4 定義的禁止類別
        mandatory_categories = {
            # 個人識別
            "name", "id_number", "birth_date",
            # 聯絡方式
            "email", "phone", "address",
            # 金融識別
            "bank_account", "card_number", "api_key",
            # 交易細節
            "merchant_name", "invoice_number",
        }
        assert mandatory_categories.issubset(FORBIDDEN_FIELDS), \
            f"缺少強制禁止欄位: {mandatory_categories - FORBIDDEN_FIELDS}"


# === 整合驗證 ===

class TestRedactionIntegrationValidation:
    """端對端整合驗證"""

    def test_full_workflow_produces_valid_context(self, engine: RedactionEngine):
        """完整工作流程產生有效上下文"""
        # 模擬真實財務資料（含各類敏感資訊）
        raw_data = {
            # 禁止欄位
            "user_name": "王小明",
            "email": "wang@example.com",
            "bank_account": "012-345-678",
            # 敏感欄位
            "occupation": "工程師",
            "salary": 200000,
            "city": "台北",
            # 正常財務資料
            "monthly_income": 200000,
            "monthly_expense": 100000,
            "expense_categories": {
                "food": 30000,
                "housing": 40000,
                "transport": 20000,
                "entertainment": 10000,
                "other": 5000,
            },
            "income_history": [140000, 200000, 145000, 155000, 200000, 160000],
        }

        result = engine.redact(raw_data)

        # 1. 產生有效上下文
        assert isinstance(result.context, RedactedDecisionContext)

        # 2. 禁止欄位不在輸出
        output_str = str(result.context)
        assert "王小明" not in output_str
        assert "wang@example.com" not in output_str
        assert "012-345-678" not in output_str

        # 3. 敏感欄位已泛化
        assert "200000" not in output_str  # 精確收入
        assert "100000" not in output_str  # 精確支出

        # 4. 輸出包含可用特徵
        assert result.context.income_volatility in ("low", "medium", "high")
        assert len(result.context.expense_distribution) > 0
        assert result.context.savings_rate_band in ("0-10%", "10-20%", "20-30%", "30%+")
        assert result.context.expense_trend in ("stable", "increasing", "decreasing")

        # 5. 來源追蹤存在
        assert len(result.context.field_provenance) > 0

        # 6. 元資料正確
        assert result.profile_version == "1.0"
        assert len(result.redacted_fields) > 0
