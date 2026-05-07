"""Redaction 規則定義

此模組定義隱私保護的三層規則：
1. FORBIDDEN_FIELDS：絕對禁止輸出
2. SENSITIVE_FIELDS：需要泛化處理
3. COMPOSITION_RULES：禁止的欄位組合

設計原則:
- 安全優先：寧可過濾過多，不可洩漏敏感資訊
- 版本化：規則變更需追蹤
- 可測試：所有規則都有對應的測試案例

版本歷程:
- V1.0 (2025-12-29): 初版
"""

from dataclasses import dataclass
from typing import FrozenSet, Tuple

# === 絕對禁止輸出的欄位（FORBIDDEN）===
# 這些欄位永遠不可出現在任何輸出中

FORBIDDEN_FIELDS: FrozenSet[str] = frozenset({
    # 個人識別
    "name", "full_name", "first_name", "last_name",
    "id_number", "national_id", "passport_number", "driver_license",
    "birth_date", "date_of_birth", "birthday", "gender", "sex",

    # 聯絡方式
    "email", "email_address", "phone", "phone_number", "mobile",
    "address", "street_address", "postal_code", "zip_code",
    "home_address", "company_address",  # 測試用
    "company_name", "employer", "workplace",

    # 金融識別
    "bank_account", "account_number", "card_number", "credit_card",
    "iban", "swift_code", "api_key", "secret_key", "token",
    "tax_id", "tax_number",

    # 交易細節
    "merchant_name", "shop_name", "store_name",
    "invoice_number", "receipt_number", "order_id", "transaction_id",

    # 行蹤資訊
    "exact_location", "gps", "latitude", "longitude",
    "flight_number", "booking_reference", "hotel_name",
})


# === 需要泛化處理的欄位（SENSITIVE）===
# 這些欄位可以輸出，但必須經過泛化處理

SENSITIVE_FIELDS: FrozenSet[str] = frozenset({
    # 金額相關（改為區間）
    "amount", "income", "salary", "expense", "payment",
    "price", "cost", "value", "balance",

    # 時間相關（改為月份級）
    "date", "datetime", "timestamp", "occurred_at", "posted_at",
    "birth_date",  # 測試用 - 出生日期需泛化至年份

    # 地點相關（改為城市/區域級）
    "city", "district", "region", "location",

    # 職業相關（改為行業級）
    "occupation", "job_title", "position", "role",
})


# === 禁止的欄位組合（COMPOSITION_RULES）===
# 這些欄位組合一旦同時出現，可能導致身份識別

COMPOSITION_RULES: Tuple[Tuple[str, ...], ...] = (
    # 職業 + 薪資 → 可識別身份
    ("occupation", "salary"),
    ("job_title", "income"),
    ("position", "salary_range"),

    # 城市 + 職稱 + 薪資 → 可識別身份
    ("city", "job_title", "salary"),
    ("city", "occupation", "income"),
    ("region", "position", "salary_range"),

    # 精確時間 + 大額支出 → 可追蹤特定事件
    ("exact_date", "large_expense"),
    ("timestamp", "significant_payment"),

    # 年齡 + 所得級距 + 地區 → 可識別身份
    ("age", "income_bracket", "city"),
    ("age_range", "salary_range", "region"),
)


@dataclass(frozen=True)
class RedactionProfile:
    """Redaction 規則版本化 Profile

    用於追蹤規則版本，支援規則變更時的差異比對。

    Attributes:
        version: Profile 版本號
        forbidden_fields: 禁止欄位集合
        sensitive_fields: 敏感欄位集合
        composition_rules: 禁止組合規則
    """
    version: str
    forbidden_fields: FrozenSet[str]
    sensitive_fields: FrozenSet[str]
    composition_rules: Tuple[Tuple[str, ...], ...]

    def diff(self, other: "RedactionProfile") -> dict:
        """比對兩個版本的差異

        Args:
            other: 要比對的另一個 Profile

        Returns:
            差異字典，包含 added/removed 的欄位
        """
        return {
            "version_change": f"{other.version} -> {self.version}",
            "added_forbidden": self.forbidden_fields - other.forbidden_fields,
            "removed_forbidden": other.forbidden_fields - self.forbidden_fields,
            "added_sensitive": self.sensitive_fields - other.sensitive_fields,
            "removed_sensitive": other.sensitive_fields - self.sensitive_fields,
        }

    def is_forbidden(self, field: str) -> bool:
        """檢查欄位是否禁止輸出"""
        return field.lower() in self.forbidden_fields

    def is_sensitive(self, field: str) -> bool:
        """檢查欄位是否需要泛化"""
        return field.lower() in self.sensitive_fields

    def violates_composition(self, fields: set[str]) -> list[tuple[str, ...]]:
        """檢查欄位組合是否違反規則

        Args:
            fields: 要檢查的欄位集合

        Returns:
            違反的組合規則列表
        """
        violations = []
        fields_lower = {f.lower() for f in fields}

        for rule in self.composition_rules:
            if all(f in fields_lower for f in rule):
                violations.append(rule)

        return violations


# === 預設 Profile（V1.0）===

REDACTION_PROFILE_V1_0 = RedactionProfile(
    version="1.0",
    forbidden_fields=FORBIDDEN_FIELDS,
    sensitive_fields=SENSITIVE_FIELDS,
    composition_rules=COMPOSITION_RULES,
)

# 當前使用的 Profile
CURRENT_REDACTION_PROFILE = REDACTION_PROFILE_V1_0
