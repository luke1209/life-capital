"""
Phase 4 CAPTURE 實體抽取器模組

從自然語言文字中抽取結構化實體：
- 金額（AmountSource）
- 日期（DateSource）
- 類別（CategorySource）
- 商家（Optional[str]）

V4.1.1 規格：使用 Source enums 標註信心度
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from life_capital.calculators.rounding import to_decimal
from life_capital.capture.date_adapter import DateAdapter
from life_capital.capture.models import AmountSource, CategorySource, DateSource
from life_capital.interfaces.canonical_reader import CanonicalReader


class EntityExtractor:
    """
    實體抽取器

    職責：
    - 從自然語言抽取金額、日期、類別、商家
    - 透過 CanonicalReader 取得有效類別清單
    - 使用 DateAdapter 處理日期解析
    - 標註抽取來源（exact/fuzzy/inferred/missing）
    """

    def __init__(self, reader: CanonicalReader):
        """
        初始化抽取器

        Args:
            reader: CanonicalReader 實例（取得有效類別清單）
        """
        self._reader = reader
        self._categories = set(reader.get_categories())
        self._date_adapter = DateAdapter()

        # 貨幣符號與關鍵字
        self._currency_symbols = ["元", "$", "NT$", "TWD", "ntd"]
        self._refund_keywords = ["退款", "退", "refund", "返還"]
        self._approximate_keywords = ["約", "大約", "左右", "around", "about"]

    def extract_amount(
        self, text: str
    ) -> Tuple[Optional[Decimal], AmountSource]:
        """
        抽取金額

        規則：
        1. 數字 + 可選貨幣符號: 320元, $1500, NT$200, 1000
        2. 分隔符正規化: 1,200 → 1200
        3. 全形數字正規化: １２３ → 123
        4. 範圍取值: 100-120 → 110 (標記 RANGE)
        5. 約略金額: 約 120 → 120 (標記 INFERRED)
        6. 負數/退款: -120, 退款 120 → -120 (標記 EXACT)
        7. 不支援: 中文數字、外幣

        Args:
            text: 輸入文字

        Returns:
            (amount, source) 或 (None, MISSING)
        """
        if not text or not text.strip():
            return (None, AmountSource.MISSING)

        # 正規化文字
        normalized = self._normalize_text_for_amount(text)

        # 檢查退款關鍵字
        is_refund = any(keyword in text for keyword in self._refund_keywords)

        # 檢查約略關鍵字
        is_approximate = any(keyword in text for keyword in self._approximate_keywords)

        # 先移除日期，避免將日期的 "-" 當作範圍符號
        text_without_dates = self._remove_date_patterns_for_amount(normalized)

        # 檢查範圍（100-120, 100~120）
        range_match = re.search(
            r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*[-~]\s*(\d+(?:,\d{3})*(?:\.\d+)?)',
            text_without_dates,
        )
        if range_match:
            start = self._parse_number(range_match.group(1))
            end = self._parse_number(range_match.group(2))
            if start and end:
                # 取平均值
                amount = (start + end) / Decimal("2")
                if is_refund:
                    amount = -amount
                return (amount, AmountSource.RANGE)

        # 抽取所有數字（含貨幣符號）
        amounts = self._extract_numbers(normalized)
        if not amounts:
            return (None, AmountSource.MISSING)

        # 取第一筆金額
        amount = amounts[0]

        # 處理退款
        if is_refund or amount < 0:
            amount = abs(amount) * Decimal("-1")
            return (amount, AmountSource.EXACT)

        # 處理約略金額
        if is_approximate:
            return (amount, AmountSource.INFERRED)

        # 精確金額
        return (amount, AmountSource.EXACT)

    def extract_date(
        self, text: str, reference_date: date
    ) -> Tuple[Optional[date], DateSource]:
        """
        抽取日期

        使用 DateAdapter 進行解析，並回傳來源標記

        Args:
            text: 輸入文字
            reference_date: 參考日期（通常為今天）

        Returns:
            (date, source) 或 (None, MISSING)
        """
        if not text or not text.strip():
            return (None, DateSource.MISSING)

        # 先嘗試從文字中提取日期候選詞
        date_candidates = self._extract_date_candidates(text)

        # 依序嘗試解析候選詞
        for candidate in date_candidates:
            result = self._date_adapter.parse(candidate, reference_date)
            if result:
                return result

            # 嘗試解析只有月份的情境
            month_result = self._date_adapter.parse_month_only(candidate, reference_date)
            if month_result:
                return month_result

        # 如果沒有明確的日期候選詞，嘗試完整文字
        result = self._date_adapter.parse(text, reference_date)
        if result:
            return result

        return (None, DateSource.MISSING)

    def _extract_date_candidates(self, text: str) -> list[str]:
        """
        提取可能的日期候選詞

        Returns:
            日期候選詞列表（按優先順序）
        """
        candidates = []

        # 1. 完整日期格式（YYYY-MM-DD, YYYY/MM/DD）
        for pattern in [r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', r'\d{1,2}[-/]\d{1,2}']:
            matches = re.findall(pattern, text)
            candidates.extend(matches)

        # 2. 相對日期關鍵字
        relative_keywords = ['昨天', '昨日', '今天', '今日', '前天', '前日', '大前天']
        for keyword in relative_keywords:
            if keyword in text:
                candidates.append(keyword)

        # 3. 週相關（上週五、本週一等）
        weekday_pattern = r'(上|本|這)(週|周|星期|禮拜)[一二三四五六日天]'
        weekday_matches = re.findall(weekday_pattern, text)
        if weekday_matches:
            # 重建完整的週幾表達
            for prefix, week_marker in weekday_matches:
                # 找到對應的週幾後綴
                full_pattern = f'{prefix}{week_marker}[一二三四五六日天]'
                match = re.search(full_pattern, text)
                if match:
                    candidates.append(match.group(0))

        # 4. 只有月份（如 "8月"）
        month_pattern = r'\d{1,2}月'
        month_matches = re.findall(month_pattern, text)
        candidates.extend(month_matches)

        return candidates

    def extract_category(
        self, text: str
    ) -> Tuple[Optional[str], CategorySource]:
        """
        抽取類別

        規則：
        1. 完全匹配 expense_policy → EXACT
        2. 模糊匹配（部分匹配）→ FUZZY
        3. 商家優先於類別（如 "星巴克" 不視為 "食物" 類別）

        Args:
            text: 輸入文字

        Returns:
            (category, source) 或 (None, MISSING)
        """
        if not text or not text.strip():
            return (None, CategorySource.MISSING)

        text_lower = text.lower().strip()

        # 1. 完全匹配（大小寫不敏感）
        for category in self._categories:
            if category.lower() in text_lower or text_lower in category.lower():
                # 檢查是否為完全匹配（避免部分匹配）
                # 例如: "food" 應該完全匹配 "food"，而非 "food_supplies"
                pattern = r'\b' + re.escape(category.lower()) + r'\b'
                if re.search(pattern, text_lower):
                    return (category, CategorySource.EXACT)

        # 2. 模糊匹配（部分匹配）
        for category in self._categories:
            if category.lower() in text_lower:
                return (category, CategorySource.FUZZY)

        return (None, CategorySource.MISSING)

    def extract_merchant(self, text: str) -> Optional[str]:
        """
        抽取商家名稱

        規則：
        - 上下文推斷（類別優先於商家）
        - 範例: 拉麵店, 捷運, 星巴克

        Args:
            text: 輸入文字

        Returns:
            商家名稱或 None
        """
        if not text or not text.strip():
            return None

        # 移除金額與日期後的文字作為候選
        text_without_amount = self._remove_amount_patterns(text)
        text_without_date = self._remove_date_patterns(text_without_amount)

        # 移除類別關鍵字
        for category in self._categories:
            text_without_date = text_without_date.replace(category, "")

        # 清理空白
        merchant = text_without_date.strip()

        # 移除特殊符號
        merchant = re.sub(r'[^\w\s\u4e00-\u9fff]', '', merchant)

        if merchant and len(merchant) > 0:
            return merchant

        return None

    def extract_all(
        self, text: str, reference_date: date
    ) -> dict:
        """
        一次抽取所有實體

        Args:
            text: 輸入文字
            reference_date: 參考日期

        Returns:
            {
                "amount": Optional[Decimal],
                "amount_source": AmountSource,
                "date": Optional[date],
                "date_source": DateSource,
                "category": Optional[str],
                "category_source": CategorySource,
                "merchant": Optional[str],
            }
        """
        amount, amount_source = self.extract_amount(text)
        parsed_date, date_source = self.extract_date(text, reference_date)
        category, category_source = self.extract_category(text)
        merchant = self.extract_merchant(text)

        return {
            "amount": amount,
            "amount_source": amount_source,
            "date": parsed_date,
            "date_source": date_source,
            "category": category,
            "category_source": category_source,
            "merchant": merchant,
        }

    # ===== 私有輔助方法 =====

    def _normalize_text_for_amount(self, text: str) -> str:
        """
        正規化文字用於金額抽取

        1. 全形數字 → 半形數字
        2. 移除空白
        """
        # 全形數字轉半形
        fullwidth_digits = "０１２３４５６７８９"
        halfwidth_digits = "0123456789"
        trans = str.maketrans(fullwidth_digits, halfwidth_digits)
        text = text.translate(trans)

        return text

    def _extract_numbers(self, text: str) -> list[Decimal]:
        """
        抽取所有數字（支援千分位分隔符）

        範例:
        - "320元" → [320]
        - "1,200" → [1200]
        - "$1500" → [1500]
        - "-120" → [-120]

        注意：排除日期格式（YYYY-MM-DD, MM/DD）
        """
        # 先移除日期模式，避免將日期當作金額
        text_without_dates = self._remove_date_patterns_for_amount(text)

        # 匹配模式：可選負號 + 數字（含千分位） + 可選小數
        # 支援: -120, 1,200, 1200.50, $1500
        pattern = r'-?\d+(?:,\d{3})*(?:\.\d+)?'
        matches = re.findall(pattern, text_without_dates)

        amounts = []
        for match in matches:
            # 移除千分位分隔符
            cleaned = match.replace(',', '')
            try:
                amount = to_decimal(cleaned)
                amounts.append(amount)
            except (InvalidOperation, ValueError):
                continue

        return amounts

    def _remove_date_patterns_for_amount(self, text: str) -> str:
        """移除日期模式（避免將日期當作金額）"""
        # 移除完整日期格式
        text = re.sub(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', '', text)
        # 移除不完整日期（需要更謹慎，避免誤刪金額）
        # 只移除明確的日期格式（如 12/25，但保留 1,200）
        text = re.sub(r'\b\d{1,2}[-/]\d{1,2}\b', '', text)
        return text

    def _parse_number(self, text: str) -> Optional[Decimal]:
        """解析單一數字字串"""
        cleaned = text.replace(',', '').strip()
        try:
            return to_decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None

    def _remove_amount_patterns(self, text: str) -> str:
        """移除金額模式"""
        # 移除數字與貨幣符號
        pattern = r'-?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:元|\$|NT\$|TWD|ntd))?'
        return re.sub(pattern, '', text)

    def _remove_date_patterns(self, text: str) -> str:
        """移除日期模式"""
        patterns = [
            r'\d{4}[-/]\d{1,2}[-/]\d{1,2}',  # YYYY-MM-DD
            r'\d{1,2}[-/]\d{1,2}',  # MM/DD
            r'昨天|昨日|今天|今日|前天|前日|大前天',  # 相對日期
            r'上週|本週|這週|上周|本周|這周',  # 週相關
        ]
        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        return text
