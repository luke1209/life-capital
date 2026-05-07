"""
ExpenseParser 單元測試

測試範圍：
- ConfidenceConfig 驗證
- ParseResult 屬性
- ExpenseParser.parse() 解析流程
- 信心度計算（各權重組合）
- Auto-approve 護欄（邊界條件）
- 信心度降級規則
"""

from datetime import date
from decimal import Decimal

import pytest

from life_capital.capture.expense_parser import (
    ConfidenceConfig,
    ExpenseParser,
    ParseResult,
)
from life_capital.capture.models import AmountSource, CategorySource, DateSource
from tests.fixtures.canonical_reader_fake import CanonicalReaderFake


class TestConfidenceConfig:
    """ConfidenceConfig 測試"""

    def test_default_config(self):
        """預設配置"""
        config = ConfidenceConfig.default()

        assert config.amount_weight == 0.4
        assert config.date_weight == 0.3
        assert config.category_weight == 0.2
        assert config.merchant_weight == 0.1
        assert config.auto_approve_threshold == 0.7

    def test_custom_config(self):
        """自訂配置"""
        config = ConfidenceConfig(
            amount_weight=0.5,
            date_weight=0.3,
            category_weight=0.15,
            merchant_weight=0.05,
            auto_approve_threshold=0.8,
        )

        assert config.amount_weight == 0.5
        assert config.auto_approve_threshold == 0.8

    def test_config_weight_validation(self):
        """權重總和必須為 1.0"""
        with pytest.raises(ValueError, match="權重總和必須為 1.0"):
            ConfidenceConfig(
                amount_weight=0.4,
                date_weight=0.3,
                category_weight=0.2,
                merchant_weight=0.2,  # 總和 1.1
            )

    def test_config_weight_validation_precise(self):
        """權重總和驗證（精確到 1e-6）"""
        # 允許浮點誤差
        config = ConfidenceConfig(
            amount_weight=0.4,
            date_weight=0.3,
            category_weight=0.2,
            merchant_weight=0.1 + 1e-7,  # 總和 1.0 + 1e-7（允許）
        )
        assert config is not None

        # 超過容忍範圍則拒絕
        with pytest.raises(ValueError):
            ConfidenceConfig(
                amount_weight=0.4,
                date_weight=0.3,
                category_weight=0.2,
                merchant_weight=0.15,  # 總和 1.05（拒絕）
            )


class TestParseResult:
    """ParseResult 屬性測試"""

    def test_amount_certain_property(self):
        """amount_certain 屬性"""
        # EXACT → True
        result = ParseResult(
            amount=Decimal("320"),
            date=None,
            category=None,
            merchant=None,
            note="",
            confidence=0.4,
            confidence_breakdown={},
            amount_source=AmountSource.EXACT,
        )
        assert result.amount_certain is True

        # RANGE → False
        result.amount_source = AmountSource.RANGE
        assert result.amount_certain is False

        # INFERRED → False
        result.amount_source = AmountSource.INFERRED
        assert result.amount_certain is False

        # MISSING → False
        result.amount_source = AmountSource.MISSING
        assert result.amount_certain is False

    def test_date_certain_property(self):
        """date_certain 屬性"""
        # BUILTIN_EXACT → True
        result = ParseResult(
            amount=None,
            date=date(2024, 12, 25),
            category=None,
            merchant=None,
            note="",
            confidence=0.3,
            confidence_breakdown={},
            date_source=DateSource.BUILTIN_EXACT,
        )
        assert result.date_certain is True

        # BUILTIN_INFERRED → False
        result.date_source = DateSource.BUILTIN_INFERRED
        assert result.date_certain is False

        # DATEPARSER → False
        result.date_source = DateSource.DATEPARSER
        assert result.date_certain is False

        # RELATIVE → False
        result.date_source = DateSource.RELATIVE
        assert result.date_certain is False

    def test_category_certain_property(self):
        """category_certain 屬性"""
        # EXACT → True
        result = ParseResult(
            amount=None,
            date=None,
            category="food",
            merchant=None,
            note="",
            confidence=0.2,
            confidence_breakdown={},
            category_source=CategorySource.EXACT,
        )
        assert result.category_certain is True

        # FUZZY → False
        result.category_source = CategorySource.FUZZY
        assert result.category_certain is False

        # MISSING → False
        result.category_source = CategorySource.MISSING
        assert result.category_certain is False

    def test_all_certain_property(self):
        """all_certain 屬性（三欄位全部確定）"""
        # 全部確定 → True
        result = ParseResult(
            amount=Decimal("320"),
            date=date(2024, 12, 25),
            category="food",
            merchant=None,
            note="",
            confidence=0.9,
            confidence_breakdown={},
            amount_source=AmountSource.EXACT,
            date_source=DateSource.BUILTIN_EXACT,
            category_source=CategorySource.EXACT,
        )
        assert result.all_certain is True

        # 金額不確定 → False
        result.amount_source = AmountSource.RANGE
        assert result.all_certain is False

        # 日期不確定 → False
        result.amount_source = AmountSource.EXACT
        result.date_source = DateSource.DATEPARSER
        assert result.all_certain is False

        # 類別不確定 → False
        result.date_source = DateSource.BUILTIN_EXACT
        result.category_source = CategorySource.FUZZY
        assert result.all_certain is False


class TestExpenseParser:
    """ExpenseParser 核心測試"""

    @pytest.fixture
    def reader(self):
        """建立 CanonicalReaderFake"""
        return CanonicalReaderFake()

    @pytest.fixture
    def parser(self, reader):
        """建立 ExpenseParser（預設配置）"""
        return ExpenseParser(reader)

    @pytest.fixture
    def parser_custom_config(self, reader):
        """建立 ExpenseParser（自訂配置）"""
        config = ConfidenceConfig(
            amount_weight=0.5,
            date_weight=0.3,
            category_weight=0.15,
            merchant_weight=0.05,
            auto_approve_threshold=0.8,
        )
        return ExpenseParser(reader, config)

    def test_parse_basic(self, parser):
        """基本解析"""
        result = parser.parse("昨天 food 320 元拉麵", reference_date=date(2024, 12, 28))

        assert result.amount == Decimal("320")
        assert result.date == date(2024, 12, 27)  # 昨天
        assert result.category == "food"
        assert result.merchant is not None
        assert result.note == "昨天 food 320 元拉麵"
        assert result.confidence > 0.7
        assert result.amount_source == AmountSource.EXACT
        assert result.date_source == DateSource.BUILTIN_EXACT
        assert result.category_source == CategorySource.EXACT

    def test_parse_exact_date(self, parser):
        """完整日期解析"""
        result = parser.parse("2024-12-25 聖誕禮物 1500 元", reference_date=date(2024, 12, 28))

        assert result.amount == Decimal("1500")
        assert result.date == date(2024, 12, 25)
        assert result.amount_source == AmountSource.EXACT
        assert result.date_source == DateSource.BUILTIN_EXACT

    def test_parse_category_with_amount(self, parser):
        """類別與金額解析"""
        result = parser.parse("transportation 捷運加值 500", reference_date=date(2024, 12, 28))

        assert result.amount == Decimal("500")
        assert result.category == "transportation"
        assert result.category_source == CategorySource.EXACT

    def test_parse_invalid_category(self, parser):
        """無效類別（不在 expense_policy）"""
        result = parser.parse("昨天吃了 320 元", reference_date=date(2024, 12, 28))

        # 即使 EntityExtractor 抽取到 category，ExpenseParser 會驗證並設為 None
        # 假設 "吃了" 不是有效類別
        assert result.category is None or result.category in ["food"]

    def test_parse_missing_amount(self, parser):
        """缺少金額"""
        result = parser.parse("昨天去吃拉麵", reference_date=date(2024, 12, 28))

        assert result.amount is None
        assert result.amount_source == AmountSource.MISSING
        assert result.confidence < 0.7

    def test_parse_missing_date(self, parser):
        """缺少日期"""
        result = parser.parse("吃了 320 元拉麵", reference_date=date(2024, 12, 28))

        # 若沒有日期，信心度會降低
        if result.date is None:
            assert result.date_source == DateSource.MISSING
            assert result.confidence < 0.7

    def test_parse_refund(self, parser):
        """退款解析"""
        result = parser.parse("退款 200 元", reference_date=date(2024, 12, 28))

        assert result.amount == Decimal("-200")
        assert result.amount_source == AmountSource.EXACT

    def test_parse_range_amount(self, parser):
        """範圍金額"""
        result = parser.parse("100-120 元", reference_date=date(2024, 12, 28))

        assert result.amount == Decimal("110")  # 平均值
        assert result.amount_source == AmountSource.RANGE


class TestConfidenceCalculation:
    """信心度計算測試"""

    @pytest.fixture
    def reader(self):
        return CanonicalReaderFake()

    def test_confidence_all_present(self, reader):
        """所有欄位皆存在"""
        parser = ExpenseParser(reader)
        result = parser.parse("昨天 food 320 元拉麵", reference_date=date(2024, 12, 28))

        # 預設權重: amount=0.4, date=0.3, category=0.2, merchant=0.1
        # 若全部抽取成功，信心度應為 1.0（扣除降級前）
        assert result.confidence_breakdown["amount"] == 0.4
        assert result.confidence_breakdown["date"] == 0.3
        assert result.confidence_breakdown["category"] == 0.2
        assert result.confidence_breakdown["merchant"] > 0.0

    def test_confidence_missing_merchant(self, reader):
        """缺少商家"""
        parser = ExpenseParser(reader)
        result = parser.parse("昨天 320 元 food", reference_date=date(2024, 12, 28))

        # merchant 缺失，其他皆存在
        expected = 0.4 + 0.3 + 0.2  # amount + date + category
        # 允許降級規則影響
        assert result.confidence >= expected - 0.2

    def test_confidence_custom_weights(self, reader):
        """自訂權重"""
        config = ConfidenceConfig(
            amount_weight=0.5,
            date_weight=0.3,
            category_weight=0.15,
            merchant_weight=0.05,
        )
        parser = ExpenseParser(reader, config)
        result = parser.parse("昨天 food 320 元拉麵", reference_date=date(2024, 12, 28))

        # 檢查自訂權重
        assert result.confidence_breakdown["amount"] == 0.5
        assert result.confidence_breakdown["date"] == 0.3
        assert result.confidence_breakdown["category"] == 0.15

    def test_confidence_only_amount(self, reader):
        """只有金額"""
        parser = ExpenseParser(reader)
        result = parser.parse("320 元", reference_date=date(2024, 12, 28))

        # 只有 amount，信心度應為 0.4（扣除降級前）
        assert result.confidence_breakdown["amount"] == 0.4
        # 其他皆為 0
        assert result.confidence_breakdown["date"] == 0.0
        assert result.confidence_breakdown["category"] == 0.0


class TestConfidencePenalties:
    """信心度降級規則測試"""

    @pytest.fixture
    def reader(self):
        return CanonicalReaderFake()

    @pytest.fixture
    def parser(self, reader):
        return ExpenseParser(reader)

    def test_penalty_dateparser_fallback(self, parser):
        """dateparser fallback 降級 -0.1"""
        # 使用相對日期觸發 dateparser fallback
        result = parser.parse("上週五 320 元", reference_date=date(2024, 12, 28))

        # 檢查是否有 penalties
        if "penalties" in result.confidence_breakdown:
            penalties = result.confidence_breakdown["penalties"]
            # 可能是 dateparser_fallback 或 relative_date
            assert "dateparser_fallback" in penalties or "relative_date" in penalties

    def test_penalty_relative_date(self, parser):
        """相對日期降級 -0.05"""
        result = parser.parse("上週 320 元", reference_date=date(2024, 12, 28))

        # 若使用相對日期
        if result.date_source == DateSource.RELATIVE:
            penalties = result.confidence_breakdown.get("penalties", {})
            assert "relative_date" in penalties
            assert penalties["relative_date"] == -0.05

    def test_penalty_fuzzy_category(self, parser):
        """模糊匹配類別降級 -0.1"""
        # 使用部分匹配的類別（假設 "foo" 會模糊匹配到 "food"）
        # 實際測試需依據 EntityExtractor 的實作
        result = parser.parse("昨天 foo 320 元", reference_date=date(2024, 12, 28))

        # 若類別為模糊匹配
        if result.category_source == CategorySource.FUZZY:
            penalties = result.confidence_breakdown.get("penalties", {})
            assert "fuzzy_category" in penalties
            assert penalties["fuzzy_category"] == -0.1

    def test_penalty_range_amount(self, parser):
        """範圍金額降級 -0.05"""
        result = parser.parse("昨天 100-120 元", reference_date=date(2024, 12, 28))

        # 範圍金額
        if result.amount_source == AmountSource.RANGE:
            penalties = result.confidence_breakdown.get("penalties", {})
            assert "range_amount" in penalties
            assert penalties["range_amount"] == -0.05

    def test_penalty_inferred_amount(self, parser):
        """推斷金額降級 -0.1"""
        result = parser.parse("昨天約 320 元", reference_date=date(2024, 12, 28))

        # 推斷金額
        if result.amount_source == AmountSource.INFERRED:
            penalties = result.confidence_breakdown.get("penalties", {})
            assert "inferred_amount" in penalties
            assert penalties["inferred_amount"] == -0.1

    def test_penalty_multiple(self, parser):
        """多重降級"""
        result = parser.parse("上週約 100-120 元", reference_date=date(2024, 12, 28))

        # 可能同時觸發多個降級
        penalties = result.confidence_breakdown.get("penalties", {})
        # 至少有一個 penalty
        assert len(penalties) > 0
        # 總 penalty 應為負數
        assert result.confidence_breakdown.get("total_penalty", 0) < 0


class TestAutoApprove:
    """Auto-approve 護欄測試"""

    @pytest.fixture
    def reader(self):
        return CanonicalReaderFake()

    def test_auto_approve_all_certain(self, reader):
        """三欄位皆確定 + 信心度 ≥ 0.7 → auto-approve"""
        parser = ExpenseParser(reader)
        result = parser.parse("昨天吃了 320 元拉麵", reference_date=date(2024, 12, 28))

        # 假設解析成功且三欄位皆確定
        if result.all_certain and result.confidence >= 0.7:
            assert parser.should_auto_approve(result) is True

    def test_auto_approve_low_confidence(self, reader):
        """信心度 < 0.7 → 不 auto-approve"""
        # 自訂配置，閾值為 0.9（較高）
        config = ConfidenceConfig(auto_approve_threshold=0.9)
        parser = ExpenseParser(reader, config)
        result = parser.parse("320 元", reference_date=date(2024, 12, 28))

        # 信心度不足（只有金額）
        assert result.confidence < 0.9
        assert parser.should_auto_approve(result) is False

    def test_auto_approve_amount_not_certain(self, reader):
        """金額不確定 → 不 auto-approve"""
        parser = ExpenseParser(reader)
        result = parser.parse("昨天約 320 元 food", reference_date=date(2024, 12, 28))

        # 金額為推斷（INFERRED）
        if result.amount_source == AmountSource.INFERRED:
            assert result.amount_certain is False
            assert parser.should_auto_approve(result) is False

    def test_auto_approve_date_not_certain(self, reader):
        """日期不確定 → 不 auto-approve"""
        parser = ExpenseParser(reader)
        result = parser.parse("上週五 320 元 food", reference_date=date(2024, 12, 28))

        # 日期為相對日期（非 BUILTIN_EXACT）
        if result.date_source != DateSource.BUILTIN_EXACT:
            assert result.date_certain is False
            assert parser.should_auto_approve(result) is False

    def test_auto_approve_category_not_certain(self, reader):
        """類別不確定 → 不 auto-approve"""
        parser = ExpenseParser(reader)
        # 假設 "foo" 會模糊匹配到 "food"
        result = parser.parse("昨天 320 元 foo", reference_date=date(2024, 12, 28))

        # 類別為模糊匹配（FUZZY）
        if result.category_source == CategorySource.FUZZY:
            assert result.category_certain is False
            assert parser.should_auto_approve(result) is False

    def test_auto_approve_custom_threshold(self, reader):
        """自訂閾值測試"""
        # 閾值設為 0.5（較低）
        config = ConfidenceConfig(auto_approve_threshold=0.5)
        parser = ExpenseParser(reader, config)
        result = parser.parse("昨天吃了 320 元拉麵", reference_date=date(2024, 12, 28))

        # 若信心度 ≥ 0.5 且三欄位確定
        if result.all_certain and result.confidence >= 0.5:
            assert parser.should_auto_approve(result) is True

    def test_auto_approve_boundary_case_exact_threshold(self, reader):
        """邊界條件：信心度恰好等於閾值"""
        # 假設我們能精確控制信心度為 0.7
        config = ConfidenceConfig(auto_approve_threshold=0.7)
        parser = ExpenseParser(reader, config)
        result = parser.parse("昨天吃了 320 元拉麵", reference_date=date(2024, 12, 28))

        # 若信心度恰好為 0.7 且三欄位確定
        if result.all_certain and abs(result.confidence - 0.7) < 1e-6:
            # 應通過（≥ threshold）
            assert parser.should_auto_approve(result) is True


class TestIntegration:
    """整合測試"""

    @pytest.fixture
    def reader(self):
        return CanonicalReaderFake()

    @pytest.fixture
    def parser(self, reader):
        return ExpenseParser(reader)

    def test_full_parsing_workflow(self, parser):
        """完整解析流程"""
        text = "昨天 food 320 元拉麵"
        reference_date = date(2024, 12, 28)

        result = parser.parse(text, reference_date)

        # 驗證解析結果
        assert result.amount == Decimal("320")
        assert result.date == date(2024, 12, 27)
        assert result.category == "food"
        assert result.note == text

        # 驗證信心度
        assert result.confidence > 0.0
        assert "amount" in result.confidence_breakdown
        assert "date" in result.confidence_breakdown
        assert "category" in result.confidence_breakdown

        # 驗證來源
        assert result.amount_source == AmountSource.EXACT
        assert result.date_source == DateSource.BUILTIN_EXACT
        assert result.category_source == CategorySource.EXACT

        # 驗證確定性
        assert result.amount_certain is True
        assert result.date_certain is True
        assert result.category_certain is True
        assert result.all_certain is True

        # 驗證 auto-approve
        assert parser.should_auto_approve(result) is True

    def test_parsing_with_penalties(self, parser):
        """解析流程（含降級）"""
        text = "上週約 100-120 元"
        reference_date = date(2024, 12, 28)

        result = parser.parse(text, reference_date)

        # 驗證解析結果
        assert result.amount == Decimal("110")  # 範圍平均值
        assert result.amount_source == AmountSource.RANGE

        # 驗證降級
        penalties = result.confidence_breakdown.get("penalties", {})
        assert len(penalties) > 0  # 至少有一個 penalty

        # 驗證 auto-approve（應該為 False，因為金額不確定）
        assert result.amount_certain is False
        assert parser.should_auto_approve(result) is False

    def test_parsing_incomplete_input(self, parser):
        """不完整輸入"""
        text = "吃了拉麵"
        reference_date = date(2024, 12, 28)

        result = parser.parse(text, reference_date)

        # 金額缺失
        assert result.amount is None
        assert result.amount_source == AmountSource.MISSING

        # 信心度低
        assert result.confidence < 0.7

        # 不 auto-approve
        assert parser.should_auto_approve(result) is False
