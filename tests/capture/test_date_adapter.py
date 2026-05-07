"""
Phase 4 CAPTURE 日期解析適配器測試

測試涵蓋：
1. 內建規則（相對日期、完整日期、不完整日期、週幾）
2. 邊緣情境（節慶、週期性、不完整日期）
3. Reference date 正確處理
4. DateSource 標註正確性
"""

from datetime import date

import pytest

from life_capital.capture.date_adapter import DateAdapter
from life_capital.capture.models import DateSource


@pytest.fixture
def adapter():
    """建立 DateAdapter 實例"""
    return DateAdapter()


@pytest.fixture
def ref_date():
    """固定參考日期：2024-12-28（週六）"""
    return date(2024, 12, 28)


# ===== 內建規則測試：相對日期 =====


def test_today(adapter, ref_date):
    """測試「今天」"""
    result = adapter.parse("今天", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 12, 28)
    assert source == DateSource.BUILTIN_EXACT


def test_yesterday(adapter, ref_date):
    """測試「昨天」"""
    result = adapter.parse("昨天", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 12, 27)
    assert source == DateSource.BUILTIN_EXACT


def test_day_before_yesterday(adapter, ref_date):
    """測試「前天」"""
    result = adapter.parse("前天", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 12, 26)
    assert source == DateSource.BUILTIN_EXACT


def test_three_days_ago(adapter, ref_date):
    """測試「大前天」"""
    result = adapter.parse("大前天", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 12, 25)
    assert source == DateSource.BUILTIN_EXACT


def test_today_variants(adapter, ref_date):
    """測試「今日」變體"""
    result = adapter.parse("今日", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 12, 28)
    assert source == DateSource.BUILTIN_EXACT


def test_yesterday_variants(adapter, ref_date):
    """測試「昨日」變體"""
    result = adapter.parse("昨日", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 12, 27)
    assert source == DateSource.BUILTIN_EXACT


# ===== 內建規則測試：完整日期 =====


def test_iso_format(adapter, ref_date):
    """測試 YYYY-MM-DD 格式"""
    result = adapter.parse("2024-12-25", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 12, 25)
    assert source == DateSource.BUILTIN_EXACT


def test_slash_format(adapter, ref_date):
    """測試 YYYY/MM/DD 格式"""
    result = adapter.parse("2024/12/25", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 12, 25)
    assert source == DateSource.BUILTIN_EXACT


def test_single_digit_month_day(adapter, ref_date):
    """測試單位數月份與日期（YYYY-M-D）"""
    result = adapter.parse("2024-8-1", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 8, 1)
    assert source == DateSource.BUILTIN_EXACT


def test_invalid_date(adapter, ref_date):
    """測試無效日期（2024-02-30）"""
    result = adapter.parse("2024-02-30", ref_date)
    # 內建規則失敗，fallback 到 dateparser（若可用）或返回 None
    # 此處預期返回 None（無效日期）
    assert result is None


# ===== 內建規則測試：不完整日期（年份推斷）=====


def test_incomplete_date_current_year(adapter, ref_date):
    """測試不完整日期（當年）：8/1 → 2024-08-01（已過）"""
    result = adapter.parse("8/1", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 8, 1)
    assert source == DateSource.BUILTIN_INFERRED


def test_incomplete_date_last_year(adapter):
    """測試不完整日期（去年）：12/25 → 2023-12-25（參考日期 2024-01-05）"""
    ref = date(2024, 1, 5)
    result = adapter.parse("12/25", ref)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2023, 12, 25)
    assert source == DateSource.BUILTIN_INFERRED


def test_incomplete_date_hyphen(adapter, ref_date):
    """測試不完整日期（連字號）：8-1"""
    result = adapter.parse("8-1", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 8, 1)
    assert source == DateSource.BUILTIN_INFERRED


def test_incomplete_date_invalid(adapter, ref_date):
    """測試無效不完整日期：2/30"""
    result = adapter.parse("2/30", ref_date)
    assert result is None


# ===== 內建規則測試：週幾（相對日期）=====


def test_last_friday(adapter, ref_date):
    """測試「上週五」（ref = 2024-12-28 週六）"""
    result = adapter.parse("上週五", ref_date)
    assert result is not None
    parsed_date, source = result
    # 上週五 = 2024-12-20
    assert parsed_date == date(2024, 12, 20)
    assert source == DateSource.RELATIVE


def test_this_monday(adapter, ref_date):
    """測試「本週一」（ref = 2024-12-28 週六）"""
    result = adapter.parse("本週一", ref_date)
    assert result is not None
    parsed_date, source = result
    # 本週一 = 2024-12-23（週一）
    assert parsed_date == date(2024, 12, 23)
    assert source == DateSource.RELATIVE


def test_this_tuesday_variant(adapter, ref_date):
    """測試「這週二」變體"""
    result = adapter.parse("這週二", ref_date)
    assert result is not None
    parsed_date, source = result
    # 本週二 = 2024-12-24
    assert parsed_date == date(2024, 12, 24)
    assert source == DateSource.RELATIVE


def test_weekday_variants(adapter, ref_date):
    """測試週幾變體（周、星期、禮拜）"""
    # 周一
    result = adapter.parse("上周一", ref_date)
    assert result is not None
    assert result[0] == date(2024, 12, 16)

    # 星期三
    result = adapter.parse("本星期三", ref_date)
    assert result is not None
    assert result[0] == date(2024, 12, 25)

    # 禮拜五
    result = adapter.parse("上禮拜五", ref_date)
    assert result is not None
    assert result[0] == date(2024, 12, 20)


def test_weekday_sunday_variants(adapter, ref_date):
    """測試週日變體（週日、周日、星期日、星期天、禮拜天）"""
    result = adapter.parse("本週日", ref_date)
    assert result is not None
    assert result[0] == date(2024, 12, 29)  # 本週日（週六 +1）

    result = adapter.parse("本星期天", ref_date)
    assert result is not None
    assert result[0] == date(2024, 12, 29)


# ===== 邊緣情境測試：節慶、週期性、不完整日期 =====


def test_festival_not_supported(adapter, ref_date):
    """測試節慶（中秋）→ 不支援，返回 None"""
    result = adapter.parse("中秋", ref_date)
    # 內建不支援，dateparser 可能可以（但不可靠）
    # 此處預期 None 或 dateparser fallback
    # 根據規劃：節慶不支援 → error
    # 若無 dateparser，應返回 None
    if result is None:
        pass  # 預期
    else:
        # 若 dateparser 可用，可能回傳某個日期（但不可靠）
        assert result[1] == DateSource.DATEPARSER


def test_periodic_not_supported(adapter, ref_date):
    """測試週期性（每週五）→ 不支援，返回 None"""
    result = adapter.parse("每週五", ref_date)
    # 週期性不支援
    assert result is None


def test_month_only(adapter, ref_date):
    """測試只有月份（8月）→ 預設 1 日 + 低信心"""
    result = adapter.parse_month_only("8月", ref_date)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2024, 8, 1)
    assert source == DateSource.BUILTIN_INFERRED


def test_month_only_last_year(adapter):
    """測試只有月份（未來月份）→ 取去年"""
    ref = date(2024, 3, 15)  # 3 月
    result = adapter.parse_month_only("12月", ref)
    assert result is not None
    parsed_date, source = result
    assert parsed_date == date(2023, 12, 1)  # 去年 12 月
    assert source == DateSource.BUILTIN_INFERRED


def test_month_only_invalid(adapter, ref_date):
    """測試無效月份（13月）"""
    result = adapter.parse_month_only("13月", ref_date)
    assert result is None


# ===== Reference Date 測試 =====


def test_reference_date_affects_relative(adapter):
    """測試 reference date 影響相對日期"""
    ref1 = date(2024, 1, 1)
    ref2 = date(2024, 12, 31)

    # 「昨天」依賴 reference date
    result1 = adapter.parse("昨天", ref1)
    assert result1[0] == date(2023, 12, 31)

    result2 = adapter.parse("昨天", ref2)
    assert result2[0] == date(2024, 12, 30)


def test_reference_date_affects_weekday(adapter):
    """測試 reference date 影響週幾計算"""
    # ref = 2024-12-28（週六）
    ref1 = date(2024, 12, 28)
    result1 = adapter.parse("上週五", ref1)
    assert result1[0] == date(2024, 12, 20)

    # ref = 2024-12-23（週一）
    ref2 = date(2024, 12, 23)
    result2 = adapter.parse("上週五", ref2)
    # 上週五 = 2024-12-20（上一週的週五）
    assert result2[0] == date(2024, 12, 20)


# ===== 空輸入與特殊情境測試 =====


def test_empty_string(adapter, ref_date):
    """測試空字串"""
    result = adapter.parse("", ref_date)
    assert result is None


def test_whitespace_only(adapter, ref_date):
    """測試只有空白"""
    result = adapter.parse("   ", ref_date)
    assert result is None


def test_none_input(adapter, ref_date):
    """測試 None 輸入"""
    result = adapter.parse(None, ref_date)
    assert result is None


def test_unrecognized_text(adapter, ref_date):
    """測試無法識別的文字"""
    result = adapter.parse("這不是日期", ref_date)
    # 內建規則無法解析，dateparser 可能也無法
    # 預期 None 或 dateparser fallback（但不可靠）
    if result is None:
        pass  # 預期
    else:
        # 若 dateparser 回傳某個值，也接受（但標記為 DATEPARSER）
        assert result[1] == DateSource.DATEPARSER


# ===== DateSource 標註測試 =====


def test_date_source_exact(adapter, ref_date):
    """測試 BUILTIN_EXACT 標註"""
    # 相對日期（今天、昨天）
    assert adapter.parse("今天", ref_date)[1] == DateSource.BUILTIN_EXACT
    assert adapter.parse("昨天", ref_date)[1] == DateSource.BUILTIN_EXACT

    # 完整日期
    assert adapter.parse("2024-12-25", ref_date)[1] == DateSource.BUILTIN_EXACT
    assert adapter.parse("2024/12/25", ref_date)[1] == DateSource.BUILTIN_EXACT


def test_date_source_inferred(adapter, ref_date):
    """測試 BUILTIN_INFERRED 標註"""
    # 不完整日期
    result = adapter.parse("8/1", ref_date)
    assert result[1] == DateSource.BUILTIN_INFERRED

    # 只有月份
    result = adapter.parse_month_only("8月", ref_date)
    assert result[1] == DateSource.BUILTIN_INFERRED


def test_date_source_relative(adapter, ref_date):
    """測試 RELATIVE 標註"""
    # 週幾（上週五、本週一）
    assert adapter.parse("上週五", ref_date)[1] == DateSource.RELATIVE
    assert adapter.parse("本週一", ref_date)[1] == DateSource.RELATIVE


# ===== 複雜情境測試 =====


def test_weekday_cross_year(adapter):
    """測試跨年週幾計算"""
    ref = date(2024, 1, 2)  # 2024-01-02（週二）
    result = adapter.parse("上週五", ref)
    assert result is not None
    # 上週五 = 2023-12-29
    assert result[0] == date(2023, 12, 29)


def test_incomplete_date_february_leap_year(adapter):
    """測試閏年 2 月（2/29）"""
    ref = date(2024, 3, 1)  # 2024 閏年
    result = adapter.parse("2/29", ref)
    assert result is not None
    assert result[0] == date(2024, 2, 29)  # 合法


def test_incomplete_date_february_non_leap_year(adapter):
    """測試非閏年 2 月（2/29）"""
    ref = date(2023, 3, 1)  # 2023 非閏年
    result = adapter.parse("2/29", ref)
    # 2023-02-29 不存在
    assert result is None


# ===== 整合測試：混合場景 =====


def test_parse_multiple_formats(adapter, ref_date):
    """測試解析多種格式（回歸測試）"""
    test_cases = [
        ("今天", date(2024, 12, 28), DateSource.BUILTIN_EXACT),
        ("昨天", date(2024, 12, 27), DateSource.BUILTIN_EXACT),
        ("2024-12-25", date(2024, 12, 25), DateSource.BUILTIN_EXACT),
        ("12/25", date(2024, 12, 25), DateSource.BUILTIN_INFERRED),
        ("上週五", date(2024, 12, 20), DateSource.RELATIVE),
        ("本週一", date(2024, 12, 23), DateSource.RELATIVE),
    ]

    for text, expected_date, expected_source in test_cases:
        result = adapter.parse(text, ref_date)
        assert result is not None, f"Failed to parse: {text}"
        parsed_date, source = result
        assert parsed_date == expected_date, f"Date mismatch for: {text}"
        assert source == expected_source, f"Source mismatch for: {text}"
