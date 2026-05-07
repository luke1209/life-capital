"""
Phase 4 CAPTURE 日期解析封裝模組

兩層日期解析策略：
1. 內建規則（穩定、快速）：今天、昨天、YYYY-MM-DD、MM/DD
2. dateparser fallback（處理複雜相對日期）

V4.1.1 規格：使用 DateSource enum 標註信心度
"""

import re
from datetime import date, timedelta
from typing import Optional, Tuple

try:
    import dateparser
    DATEPARSER_AVAILABLE = True
except ImportError:
    DATEPARSER_AVAILABLE = False

from life_capital.capture.models import DateSource


class DateAdapter:
    """
    日期解析適配器

    策略：內建規則優先（精確） → dateparser fallback（模糊）
    Locale：固定 zh-TW
    """

    LOCALE = "zh-TW"

    # 中文相對日期映射
    RELATIVE_DAYS_MAP = {
        "今天": 0,
        "今日": 0,
        "昨天": -1,
        "昨日": -1,
        "前天": -2,
        "前日": -2,
        "大前天": -3,
    }

    # 週幾映射（0=週一, 6=週日）
    WEEKDAY_MAP = {
        "週一": 0, "周一": 0, "星期一": 0, "禮拜一": 0,
        "週二": 1, "周二": 1, "星期二": 1, "禮拜二": 1,
        "週三": 2, "周三": 2, "星期三": 2, "禮拜三": 2,
        "週四": 3, "周四": 3, "星期四": 3, "禮拜四": 3,
        "週五": 4, "周五": 4, "星期五": 4, "禮拜五": 4,
        "週六": 5, "周六": 5, "星期六": 5, "禮拜六": 5,
        "週日": 6, "周日": 6, "星期日": 6, "禮拜日": 6,
        "週天": 6, "周天": 6, "星期天": 6, "禮拜天": 6,
    }

    def parse(self, text: str, reference_date: date) -> Optional[Tuple[date, DateSource]]:
        """
        解析日期文字

        Args:
            text: 日期文字（如 "昨天", "2024-12-25", "上週五"）
            reference_date: 參考日期（通常為今天）

        Returns:
            (parsed_date, source) 或 None（解析失敗）
        """
        if not text or not text.strip():
            return None

        text = text.strip()

        # 第一層：內建規則（穩定、精確）
        result = self._builtin_parse(text, reference_date)
        if result:
            return result

        # 第二層：dateparser fallback（模糊）
        if DATEPARSER_AVAILABLE:
            return self._dateparser_fallback(text, reference_date)

        return None

    def _builtin_parse(
        self, text: str, ref: date
    ) -> Optional[Tuple[date, DateSource]]:
        """
        內建規則解析（優先）

        規則：
        1. 相對日期（今天、昨天、前天）
        2. 完整日期（YYYY-MM-DD, YYYY/MM/DD）
        3. 不完整日期（MM/DD, MM-DD）
        4. 週幾（上週五、本週一）
        """
        # 1. 相對日期
        if text in self.RELATIVE_DAYS_MAP:
            delta = self.RELATIVE_DAYS_MAP[text]
            result_date = ref + timedelta(days=delta)
            return (result_date, DateSource.BUILTIN_EXACT)

        # 2. 完整日期（YYYY-MM-DD, YYYY/MM/DD）
        match = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', text)
        if match:
            try:
                year, month, day = map(int, match.groups())
                result_date = date(year, month, day)
                return (result_date, DateSource.BUILTIN_EXACT)
            except ValueError:
                pass

        # 3. 不完整日期（MM/DD, MM-DD）- 推斷年份
        match = re.match(r'^(\d{1,2})[-/](\d{1,2})$', text)
        if match:
            month, day = map(int, match.groups())
            inferred_date = self._infer_year(ref, month, day)
            if inferred_date:
                return (inferred_date, DateSource.BUILTIN_INFERRED)

        # 4. 週幾（上週五、本週一、這週二）
        weekday_result = self._parse_weekday(text, ref)
        if weekday_result:
            return weekday_result

        return None

    def _infer_year(self, ref: date, month: int, day: int) -> Optional[date]:
        """
        推斷年份（優先當年，若未來則取去年）

        範例：
        - ref = 2024-12-28, input = 8/1 → 2024-08-01（已過）
        - ref = 2024-01-05, input = 12/25 → 2023-12-25（去年）
        """
        try:
            # 嘗試當年
            candidate = date(ref.year, month, day)
            if candidate <= ref:
                return candidate

            # 未來日期 → 取去年
            return date(ref.year - 1, month, day)
        except ValueError:
            return None

    def _parse_weekday(
        self, text: str, ref: date
    ) -> Optional[Tuple[date, DateSource]]:
        """
        解析週幾（上週五、本週一、這週二）

        規則：
        - 上週X：ref 往前找最近的 X
        - 本週X / 這週X：本週的 X（未來則取下週）
        """
        # 匹配「上週五」、「本週一」、「這週二」、「上星期一」、「本禮拜二」等
        match = re.match(r'^(上|本|這)(週|周|星期|禮拜)(.+)$', text)
        if not match:
            return None

        prefix = match.group(1)
        week_marker = match.group(2)  # 週/周/星期/禮拜
        weekday_suffix = match.group(3)  # 一/二/.../日/天

        # 組合完整的週幾名稱（如「週五」、「星期一」）
        weekday_name = week_marker + weekday_suffix

        # 檢查是否在 WEEKDAY_MAP 中
        if weekday_name not in self.WEEKDAY_MAP:
            return None

        target_weekday = self.WEEKDAY_MAP[weekday_name]

        if prefix == "上":
            # 上週X：往前找最近的 X
            result_date = self._find_last_weekday(ref, target_weekday)
            return (result_date, DateSource.RELATIVE)

        # 本週/這週：計算本週該日
        result_date = self._find_current_week_day(ref, target_weekday)
        return (result_date, DateSource.RELATIVE)

    def _find_last_weekday(self, ref: date, target_weekday: int) -> date:
        """找最近的上週 X（往前找）"""
        current_weekday = ref.weekday()

        # 計算天數差異
        if current_weekday >= target_weekday:
            # 例如今天週五（4），找上週三（2） → -2 - 7 = -9 天
            delta = target_weekday - current_weekday - 7
        else:
            # 例如今天週一（0），找上週五（4） → -7 + 4 = -3 天
            delta = target_weekday - current_weekday - 7

        return ref + timedelta(days=delta)

    def _find_current_week_day(self, ref: date, target_weekday: int) -> date:
        """找本週的某一天（未來則取本週）"""
        current_weekday = ref.weekday()
        delta = target_weekday - current_weekday

        # 若目標日在未來，仍取本週（不跨週）
        return ref + timedelta(days=delta)

    def _dateparser_fallback(
        self, text: str, ref: date
    ) -> Optional[Tuple[date, DateSource]]:
        """
        dateparser fallback（處理複雜相對日期）

        設定：
        - locale = zh-TW
        - RELATIVE_BASE = reference_date
        """
        try:
            settings = {
                'RELATIVE_BASE': ref,
                'PREFER_DATES_FROM': 'past',  # 預設取過去日期
            }
            parsed = dateparser.parse(
                text,
                languages=[self.LOCALE.lower()],
                settings=settings
            )
            if parsed:
                # dateparser 回傳 datetime，轉為 date
                return (parsed.date(), DateSource.DATEPARSER)
        except Exception:
            # 靜默失敗
            pass

        return None

    def parse_month_only(self, text: str, ref: date) -> Optional[Tuple[date, DateSource]]:
        """
        處理只有月份的情境（如 "8月"）

        策略：預設該月 1 日，標記為低信心
        """
        match = re.match(r'^(\d{1,2})月$', text)
        if not match:
            return None

        month = int(match.group(1))
        try:
            # 嘗試當年該月 1 日
            result_date = date(ref.year, month, 1)
            if result_date <= ref:
                return (result_date, DateSource.BUILTIN_INFERRED)

            # 未來月份 → 取去年
            return (date(ref.year - 1, month, 1), DateSource.BUILTIN_INFERRED)
        except ValueError:
            return None
