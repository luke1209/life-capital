"""
Phase 4 CAPTURE 解析器核心模組

組合實體抽取結果、計算信心度、實作 auto-approve 護欄

V4.1.1 規格：
- 使用 Source enum 標註確定性
- 三欄位確定性檢查（amount_certain, date_certain, category_certain）
- 可配置信心度權重（ConfidenceConfig）
- Auto-approve 護欄（僅當三欄位皆確定才批准）
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from life_capital.capture.entity_extractor import EntityExtractor
from life_capital.capture.models import AmountSource, CategorySource, DateSource
from life_capital.interfaces.canonical_reader import CanonicalReader


@dataclass
class ConfidenceConfig:
    """
    信心度計算配置

    可配置各欄位的權重，以及 auto-approve 閾值
    V2 新增：支援可配置信心度計算
    """

    amount_weight: float = 0.4  # 金額權重
    date_weight: float = 0.3  # 日期權重
    category_weight: float = 0.2  # 類別權重
    merchant_weight: float = 0.1  # 商家權重
    auto_approve_threshold: float = 0.7  # 自動批准閾值

    @classmethod
    def default(cls) -> "ConfidenceConfig":
        """回傳預設配置"""
        return cls()

    def __post_init__(self):
        """驗證權重總和 = 1.0"""
        total = (
            self.amount_weight
            + self.date_weight
            + self.category_weight
            + self.merchant_weight
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"權重總和必須為 1.0，當前為 {total:.6f}"
            )


@dataclass
class ParseResult:
    """
    解析結果

    V4.1.1 規格：
    - 使用 Source enum 標註抽取來源
    - Derived properties 計算確定性（*_certain）
    - 包含信心度與信心度拆解
    """

    # === 抽取結果 ===
    amount: Optional[Decimal]
    date: Optional[date]
    category: Optional[str]
    merchant: Optional[str]
    note: Optional[str]

    # === 信心度 ===
    confidence: float
    confidence_breakdown: dict[str, float]

    # === V4.1.1: 來源枚舉 ===
    amount_source: AmountSource = AmountSource.MISSING
    date_source: DateSource = DateSource.MISSING
    category_source: CategorySource = CategorySource.MISSING

    # === V4.1.1: 確定性 derived properties ===
    @property
    def amount_certain(self) -> bool:
        """金額是否確定（非推斷、非範圍）"""
        return self.amount_source == AmountSource.EXACT

    @property
    def date_certain(self) -> bool:
        """日期是否確定（非 fallback、非相對日期）"""
        return self.date_source == DateSource.BUILTIN_EXACT

    @property
    def category_certain(self) -> bool:
        """類別是否確定（非模糊匹配）"""
        return self.category_source == CategorySource.EXACT

    @property
    def all_certain(self) -> bool:
        """三欄位是否全部確定（auto-approve 護欄條件之一）"""
        return self.amount_certain and self.date_certain and self.category_certain


class ExpenseParser:
    """
    支出解析器

    職責：
    - 使用 EntityExtractor 抽取實體
    - 驗證類別是否存在於 expense_policy
    - 計算信心度（使用可配置權重）
    - 檢查 auto-approve 護欄（V4.1）
    """

    def __init__(
        self,
        reader: CanonicalReader,
        config: Optional[ConfidenceConfig] = None,
    ):
        """
        初始化解析器

        Args:
            reader: CanonicalReader 實例（取得類別清單）
            config: 信心度配置（可選，預設使用 ConfidenceConfig.default()）
        """
        self._reader = reader
        self._categories = set(reader.get_categories())
        self._config = config or ConfidenceConfig.default()
        self._extractor = EntityExtractor(reader)

    def parse(self, text: str, reference_date: Optional[date] = None) -> ParseResult:
        """
        解析自然語言支出描述

        Args:
            text: 輸入文字
            reference_date: 參考日期（通常為今天，若不提供則使用當前日期）

        Returns:
            ParseResult: 解析結果（包含抽取實體、信心度、來源枚舉）
        """
        if reference_date is None:
            from datetime import date as date_module

            reference_date = date_module.today()

        # 1. 使用 EntityExtractor 抽取實體
        extracted = self._extractor.extract_all(text, reference_date)

        # 2. 驗證類別是否存在於 expense_policy
        category = extracted["category"]
        if category and category not in self._categories:
            # 類別不存在，標記為 MISSING
            category = None
            extracted["category_source"] = CategorySource.MISSING

        # 3. 計算信心度
        confidence, breakdown = self._calculate_confidence(extracted)

        # 4. 套用信心度降級規則（V2）
        confidence, breakdown = self._apply_confidence_penalties(
            confidence, breakdown, extracted
        )

        # 5. 回傳 ParseResult
        return ParseResult(
            amount=extracted["amount"],
            date=extracted["date"],
            category=category,
            merchant=extracted["merchant"],
            note=text,  # 將原始文字作為 note
            confidence=confidence,
            confidence_breakdown=breakdown,
            amount_source=extracted["amount_source"],
            date_source=extracted["date_source"],
            category_source=extracted["category_source"],
        )

    def _calculate_confidence(
        self, extracted: dict
    ) -> tuple[float, dict[str, float]]:
        """
        計算信心度（使用 config 權重）

        公式：
        confidence = (
            amount_weight × (1.0 if amount else 0.0) +
            date_weight × (1.0 if date else 0.0) +
            category_weight × (1.0 if category else 0.0) +
            merchant_weight × (1.0 if merchant else 0.0)
        )

        Args:
            extracted: EntityExtractor.extract_all() 回傳的字典

        Returns:
            (total_confidence, breakdown): 總信心度與各項分數
        """
        # 計算各項得分
        amount_score = self._config.amount_weight if extracted["amount"] else 0.0
        date_score = self._config.date_weight if extracted["date"] else 0.0
        category_score = self._config.category_weight if extracted["category"] else 0.0
        merchant_score = (
            self._config.merchant_weight if extracted["merchant"] else 0.0
        )

        # 總分
        total_confidence = amount_score + date_score + category_score + merchant_score

        # 拆解
        breakdown = {
            "amount": amount_score,
            "date": date_score,
            "category": category_score,
            "merchant": merchant_score,
        }

        return total_confidence, breakdown

    def _apply_confidence_penalties(
        self, confidence: float, breakdown: dict[str, float], extracted: dict
    ) -> tuple[float, dict[str, float]]:
        """
        套用信心度降級規則（V2 新增）

        降級規則：
        - dateparser fallback: -0.1
        - 相對日期: -0.05
        - 模糊匹配類別: -0.1
        - 範圍金額: -0.05
        - 推斷金額: -0.1

        Args:
            confidence: 原始信心度
            breakdown: 原始信心度拆解
            extracted: 抽取結果

        Returns:
            (adjusted_confidence, adjusted_breakdown): 調整後的信心度與拆解
        """
        penalties = []

        # 日期降級
        date_source = extracted["date_source"]
        if date_source == DateSource.DATEPARSER:
            penalties.append(("dateparser_fallback", -0.1))
        elif date_source == DateSource.RELATIVE:
            penalties.append(("relative_date", -0.05))

        # 類別降級
        category_source = extracted["category_source"]
        if category_source == CategorySource.FUZZY:
            penalties.append(("fuzzy_category", -0.1))

        # 金額降級
        amount_source = extracted["amount_source"]
        if amount_source == AmountSource.RANGE:
            penalties.append(("range_amount", -0.05))
        elif amount_source == AmountSource.INFERRED:
            penalties.append(("inferred_amount", -0.1))

        # 套用降級
        total_penalty = sum(penalty for _, penalty in penalties)
        adjusted_confidence = max(0.0, confidence + total_penalty)

        # 拆解中加入 penalty 項目
        adjusted_breakdown = breakdown.copy()
        if penalties:
            adjusted_breakdown["penalties"] = {
                reason: penalty for reason, penalty in penalties
            }
            adjusted_breakdown["total_penalty"] = total_penalty

        return adjusted_confidence, adjusted_breakdown

    def should_auto_approve(self, result: ParseResult) -> bool:
        """
        V4.1: 檢查是否應該自動批准

        護欄條件（全部滿足才 auto-approve）：
        1. 總信心度 ≥ threshold
        2. 金額確定（amount_certain）
        3. 日期確定（date_certain）
        4. 類別確定（category_certain）

        Args:
            result: 解析結果

        Returns:
            bool: 是否應該自動批准
        """
        # 條件 1: 總信心度 ≥ threshold
        if result.confidence < self._config.auto_approve_threshold:
            return False

        # 條件 2-4: 三欄位皆確定
        if not result.all_certain:
            return False

        return True
