"""生活假設資料模型

定義 life_assumptions.yaml 的資料結構。
包含 rates.mode (nominal/real) 與 calculation 設定。

V1.2 變更：
- 新增 Member 類別（birth_year 取代 current_age）
- 新增 members: dict[str, Member]
- Basic.primary_member 指向 members 中的成員
- 舊版 Basic 欄位（current_age/retirement_age/expected_lifespan）與 members 互斥
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from life_capital.models.base import VersionedModel
from life_capital.models.common import ALLOWED_MEMBER_IDS


class Currency(str, Enum):
    """支援的貨幣類型"""

    TWD = "TWD"
    USD = "USD"


class RatesMode(str, Enum):
    """計算模式

    - nominal: 名目模式 - FV 考慮通膨，使用名目報酬率
    - real: 實質模式 - FV 不調整，使用實質報酬率，報表標註 base_year 幣值
    """

    NOMINAL = "nominal"
    REAL = "real"


class RoundingMethod(str, Enum):
    """捨入方法"""

    ROUND_HALF_UP = "ROUND_HALF_UP"  # 四捨五入
    ROUND_HALF_EVEN = "ROUND_HALF_EVEN"  # 銀行家捨入


class RoundingStage(str, Enum):
    """捨入時機"""

    FINAL = "final"  # 只在最後 round（建議）
    PER_PERIOD = "per_period"  # 每期 round
    PER_YEAR = "per_year"  # 每年 round


class Metadata(BaseModel):
    """元資料"""

    currency: Currency = Currency.TWD
    base_year: int = Field(default_factory=lambda: datetime.now().year)

    @field_validator("base_year")
    @classmethod
    def validate_base_year(cls, v: int) -> int:
        current_year = datetime.now().year
        if v > current_year:
            raise ValueError(f"base_year ({v}) 不能大於當前年份 ({current_year})")
        if v < 1900:
            raise ValueError(f"base_year ({v}) 不能小於 1900")
        return v


class Member(BaseModel):
    """成員資訊（V1.2 新增）

    使用 birth_year 取代 current_age，確保年齡計算的一致性。
    """

    display_name: str = Field(description="UI 顯示名稱")
    birth_year: int = Field(ge=1900, description="出生年份")
    retirement_age: int = Field(ge=1, le=120, description="預計退休年齡")
    expected_lifespan: int = Field(ge=1, le=150, description="預期壽命")
    birth_year_estimated: bool = Field(
        default=False,
        description="是否為推算值（從 current_age 遷移時標記為 true）",
    )

    @model_validator(mode="after")
    def validate_ages(self) -> "Member":
        """驗證年齡邏輯"""
        if self.expected_lifespan <= self.retirement_age:
            raise ValueError(
                f"expected_lifespan ({self.expected_lifespan}) 必須大於 "
                f"retirement_age ({self.retirement_age})"
            )
        return self

    def get_current_age(self, as_of_year: int) -> int:
        """計算指定年份的年齡

        Args:
            as_of_year: 計算基準年份

        Returns:
            該年份的年齡
        """
        return as_of_year - self.birth_year


class Basic(BaseModel):
    """基本資訊

    V1.2：只有 primary_member
    V1.1 legacy：current_age, retirement_age, expected_lifespan（與 members 互斥）
    """

    # V1.2 欄位
    primary_member: Optional[str] = Field(
        default=None,
        description="主要成員 ID，必須存在於 members keys",
    )

    # V1.1 legacy 欄位（與 members 互斥）
    current_age: Optional[int] = Field(default=None, ge=1, le=120)
    expected_lifespan: Optional[int] = Field(default=None, ge=1, le=150)
    retirement_age: Optional[int] = Field(default=None, ge=1, le=120)

    @model_validator(mode="after")
    def validate_legacy_ages(self) -> "Basic":
        """驗證 V1.1 legacy 欄位的年齡邏輯"""
        # 只有當所有 legacy 欄位都存在時才驗證
        if (
            self.current_age is not None
            and self.retirement_age is not None
            and self.expected_lifespan is not None
        ):
            if self.retirement_age <= self.current_age:
                raise ValueError(
                    f"retirement_age ({self.retirement_age}) 必須大於 "
                    f"current_age ({self.current_age})"
                )
            if self.expected_lifespan <= self.retirement_age:
                raise ValueError(
                    f"expected_lifespan ({self.expected_lifespan}) 必須大於 "
                    f"retirement_age ({self.retirement_age})"
                )
        return self


class Rates(BaseModel):
    """利率設定

    mode 決定使用 nominal 或 real 計算模式。
    """

    mode: RatesMode = RatesMode.NOMINAL
    annual_inflation: float = Field(ge=0, le=0.2, default=0.02)

    # 名目模式使用
    nominal_investment_return: Optional[float] = Field(default=None, ge=-0.1, le=0.3)

    # 實質模式使用
    real_investment_return: Optional[float] = Field(default=None, ge=-0.1, le=0.3)

    # 進階設定（可選）
    salary_growth_rate: Optional[float] = Field(default=None, ge=-0.1, le=0.3)
    contribution_growth_rate: Optional[float] = Field(default=None, ge=-0.1, le=0.3)

    @model_validator(mode="after")
    def validate_mode_rates(self) -> "Rates":
        """驗證 mode 對應的報酬率欄位存在"""
        if self.mode == RatesMode.NOMINAL:
            if self.nominal_investment_return is None:
                raise ValueError(
                    "rates.mode 為 'nominal' 時，必須提供 nominal_investment_return"
                )
        elif self.mode == RatesMode.REAL:
            if self.real_investment_return is None:
                raise ValueError(
                    "rates.mode 為 'real' 時，必須提供 real_investment_return"
                )
        return self

    def get_investment_return(self) -> float:
        """根據 mode 取得對應的投資報酬率"""
        if self.mode == RatesMode.NOMINAL:
            return self.nominal_investment_return or 0.0
        else:
            return self.real_investment_return or 0.0


class Calculation(BaseModel):
    """計算設定

    控制 rounding 行為。
    """

    scale: int = Field(default=0, ge=0, le=4)  # 小數位數：0=元，2=角分
    rounding: RoundingMethod = RoundingMethod.ROUND_HALF_UP
    rounding_stage: RoundingStage = RoundingStage.FINAL


class Child(BaseModel):
    """子女資訊"""

    name: str
    birth_year: int = Field(ge=1900)
    university_start_age: int = Field(default=18, ge=16, le=25)
    financial_independence_age: int = Field(default=25, ge=18, le=40)

    @model_validator(mode="after")
    def validate_ages(self) -> "Child":
        if self.financial_independence_age < self.university_start_age:
            raise ValueError(
                f"financial_independence_age ({self.financial_independence_age}) "
                f"不能小於 university_start_age ({self.university_start_age})"
            )
        return self


class Family(BaseModel):
    """家庭資訊"""

    children: list[Child] = Field(default_factory=list)


class LifeAssumptions(VersionedModel):
    """生活假設主模型

    對應 life_assumptions.yaml

    V1.2：使用 members dict 管理成員資訊
    V1.1：使用 basic 中的 current_age/retirement_age/expected_lifespan
    兩者互斥，不可共存。
    """

    metadata: Metadata = Field(default_factory=Metadata)
    basic: Basic
    rates: Rates
    calculation: Calculation = Field(default_factory=Calculation)
    family: Family = Field(default_factory=Family)

    # V1.2 新增：成員資訊
    members: Optional[dict[str, Member]] = Field(
        default=None,
        description="成員資訊，key 必須在 ALLOWED_MEMBER_IDS 中",
    )

    @model_validator(mode="after")
    def validate_schema(self) -> "LifeAssumptions":
        """驗證 schema 一致性"""
        has_members = self.members is not None and len(self.members) > 0
        has_legacy = any(
            [
                self.basic.current_age is not None,
                self.basic.retirement_age is not None,
                self.basic.expected_lifespan is not None,
            ]
        )

        # 互斥檢查：members 與 legacy 不可共存
        if has_members and has_legacy:
            raise ValueError(
                "members 與 legacy 欄位 (current_age/retirement_age/expected_lifespan) "
                "不可共存。請執行 `lc migrate` 升級或移除衝突欄位。"
            )

        # 如果使用 V1.2 結構（有 members）
        if has_members:
            # 驗證 member IDs
            for member_id in self.members.keys():
                if member_id not in ALLOWED_MEMBER_IDS:
                    raise ValueError(
                        f"member_id '{member_id}' 不在允許列表中: {ALLOWED_MEMBER_IDS}"
                    )

            # 驗證 primary_member 存在
            if self.basic.primary_member is None:
                raise ValueError(
                    "使用 members 時，basic.primary_member 必須設定"
                )
            if self.basic.primary_member not in self.members:
                raise ValueError(
                    f"primary_member '{self.basic.primary_member}' "
                    f"不存在於 members keys: {list(self.members.keys())}"
                )

            # 驗證 birth_year 與 base_year 的關係
            base_year = self.metadata.base_year
            for member_id, member in self.members.items():
                current_age = member.get_current_age(base_year)
                if current_age < 1:
                    raise ValueError(
                        f"成員 '{member_id}' 的 birth_year ({member.birth_year}) "
                        f"必須小於 base_year ({base_year})"
                    )
                if member.retirement_age <= current_age:
                    raise ValueError(
                        f"成員 '{member_id}' 的 retirement_age ({member.retirement_age}) "
                        f"必須大於 base_year 時的年齡 ({current_age})"
                    )

        # 如果使用 V1.1 結構（有 legacy），確保三個欄位都存在
        if has_legacy:
            if not all(
                [
                    self.basic.current_age is not None,
                    self.basic.retirement_age is not None,
                    self.basic.expected_lifespan is not None,
                ]
            ):
                raise ValueError(
                    "V1.1 結構必須同時提供 current_age, retirement_age, expected_lifespan"
                )

        return self

    # === Getter 方法（統一存取介面）===

    def get_member(self, member_id: Optional[str] = None) -> Member:
        """取得成員資訊

        Args:
            member_id: 成員 ID，若為 None 則回傳 primary_member

        Returns:
            Member 物件

        Raises:
            ValueError: 成員不存在或使用 V1.1 結構
        """
        if self.members is None:
            raise ValueError(
                "此檔案使用 V1.1 結構，請使用 get_current_age_legacy() 或執行 migration"
            )

        if member_id is None:
            member_id = self.basic.primary_member

        if member_id not in self.members:
            raise ValueError(
                f"成員 '{member_id}' 不存在於 members: {list(self.members.keys())}"
            )

        return self.members[member_id]

    def get_primary_member(self) -> Member:
        """取得主要成員資訊

        Returns:
            主要成員的 Member 物件

        Raises:
            ValueError: 使用 V1.1 結構
        """
        return self.get_member(self.basic.primary_member)

    def get_current_age(
        self,
        member_id: Optional[str] = None,
        as_of_year: Optional[int] = None,
    ) -> int:
        """取得成員的當前年齡

        Args:
            member_id: 成員 ID，若為 None 則使用 primary_member
            as_of_year: 計算基準年份，若為 None 則使用 metadata.base_year

        Returns:
            年齡

        Raises:
            ValueError: 成員不存在
        """
        if as_of_year is None:
            as_of_year = self.metadata.base_year

        # V1.2 結構
        if self.members is not None:
            member = self.get_member(member_id)
            return member.get_current_age(as_of_year)

        # V1.1 legacy 結構
        if self.basic.current_age is not None:
            # legacy 結構沒有 birth_year，假設 base_year 時的年齡就是 current_age
            return self.basic.current_age

        raise ValueError("無法取得年齡：缺少 members 或 legacy 欄位")

    def get_retirement_age(self, member_id: Optional[str] = None) -> int:
        """取得成員的退休年齡

        Args:
            member_id: 成員 ID，若為 None 則使用 primary_member

        Returns:
            退休年齡
        """
        if self.members is not None:
            member = self.get_member(member_id)
            return member.retirement_age

        if self.basic.retirement_age is not None:
            return self.basic.retirement_age

        raise ValueError("無法取得退休年齡：缺少 members 或 legacy 欄位")

    def get_expected_lifespan(self, member_id: Optional[str] = None) -> int:
        """取得成員的預期壽命

        Args:
            member_id: 成員 ID，若為 None 則使用 primary_member

        Returns:
            預期壽命
        """
        if self.members is not None:
            member = self.get_member(member_id)
            return member.expected_lifespan

        if self.basic.expected_lifespan is not None:
            return self.basic.expected_lifespan

        raise ValueError("無法取得預期壽命：缺少 members 或 legacy 欄位")

    def is_v12_structure(self) -> bool:
        """檢查是否使用 V1.2 結構

        Returns:
            True 如果使用 members 結構
        """
        return self.members is not None and len(self.members) > 0

    def get_all_member_ids(self) -> list[str]:
        """取得所有成員 ID

        Returns:
            成員 ID 列表，若為 V1.1 結構則回傳空列表
        """
        if self.members is None:
            return []
        return list(self.members.keys())
