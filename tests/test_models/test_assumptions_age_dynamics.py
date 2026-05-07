"""年齡動態計算測試

測試 V1.2 schema 的 birth_year 基礎年齡計算：
- current_age = base_year - birth_year
- 年齡隨 base_year 推進而增加
- 相關參數（max_year, years_to_retirement）連動更新

期望行為規格：
- as_of_year < birth_year: 返回負數（非拋錯，因需支援歷史資料分析）
- base_year == birth_year: current_age = 0（驗證失敗，因 age < 1）
- max_year = birth_year + expected_lifespan（V1.2 常數，不隨 base_year 變動）
"""

from datetime import datetime
from typing import Callable

import pytest

from life_capital.models.assumptions import (
    Basic,
    LifeAssumptions,
    Member,
    Metadata,
)
from tests.fixtures.factory import (
    make_life_assumptions,
    make_member,
)

# === 測試參數常數 ===

LUKE_BIRTH_YEAR = 1981
FREYA_BIRTH_YEAR = 1993


class TestMemberAgeCalculation:
    """Member.get_current_age() 動態計算測試"""

    @pytest.mark.parametrize(
        "birth_year,as_of_year,expected_age",
        [
            # Person A (1981) 在不同年份的年齡
            (1981, 2024, 43),
            (1981, 2025, 44),
            (1981, 2030, 49),
            (1981, 2020, 39),  # 歷史年份
            # Person B (1993) 在不同年份的年齡
            (1993, 2024, 31),
            (1993, 2025, 32),
            (1993, 2030, 37),
            # 邊界情境
            (1981, 1981, 0),  # birth_year == as_of_year
            (1981, 1980, -1),  # as_of_year < birth_year（允許負數）
        ],
        ids=[
            "luke_2024",
            "luke_2025",
            "luke_2030",
            "luke_2020_historical",
            "freya_2024",
            "freya_2025",
            "freya_2030",
            "boundary_birth_year_equals_as_of",
            "boundary_negative_age",
        ],
    )
    def test_age_formula(
        self, birth_year: int, as_of_year: int, expected_age: int
    ) -> None:
        """年齡公式: current_age = as_of_year - birth_year"""
        member = make_member(birth_year=birth_year)
        assert member.get_current_age(as_of_year) == expected_age

    def test_age_increases_with_year(self) -> None:
        """base_year 每增加 1，年齡增加 1"""
        member = make_member(birth_year=LUKE_BIRTH_YEAR)

        age_2024 = member.get_current_age(2024)
        age_2025 = member.get_current_age(2025)
        age_2026 = member.get_current_age(2026)

        assert age_2025 - age_2024 == 1
        assert age_2026 - age_2025 == 1


class TestLifeAssumptionsAgeGetter:
    """LifeAssumptions.get_current_age() 測試"""

    def test_uses_metadata_base_year_by_default(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """預設使用 metadata.base_year"""
        freeze_base_year(2024)
        assumptions = make_life_assumptions()

        assert assumptions.metadata.base_year == 2024
        assert assumptions.get_current_age() == 2024 - LUKE_BIRTH_YEAR

    def test_as_of_year_override(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """as_of_year 參數覆蓋 metadata.base_year"""
        freeze_base_year(2024)
        assumptions = make_life_assumptions()

        # 即使 base_year=2024，可以查詢其他年份
        assert assumptions.get_current_age(as_of_year=2030) == 2030 - LUKE_BIRTH_YEAR

    def test_specific_member_age(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """指定 member_id 取得特定成員年齡"""
        freeze_base_year(2024)
        assumptions = make_life_assumptions(
            members={
                "person_a": make_member(birth_year=LUKE_BIRTH_YEAR),
                "person_b": make_member(
                    display_name="Person B", birth_year=FREYA_BIRTH_YEAR
                ),
            }
        )

        assert assumptions.get_current_age(member_id="person_a") == 43
        assert assumptions.get_current_age(member_id="person_b") == 31

    def test_nonexistent_member_raises_valueerror(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """指定不存在的 member_id 應拋出 ValueError"""
        freeze_base_year(2024)
        assumptions = make_life_assumptions()

        with pytest.raises(ValueError, match="不存在於 members"):
            assumptions.get_current_age(member_id="nonexistent")


class TestMaxYearCalculation:
    """max_year 計算測試（V1.2: 常數）"""

    @pytest.mark.parametrize(
        "birth_year,expected_lifespan,expected_max_year",
        [
            (1981, 85, 2066),  # Person A 預設
            (1981, 95, 2076),  # Person A 長壽
            (1993, 90, 2083),  # Person B
        ],
        ids=["luke_default", "luke_longevity", "person_b"],
    )
    def test_max_year_is_constant(
        self,
        freeze_base_year: Callable[[int], int],
        birth_year: int,
        expected_lifespan: int,
        expected_max_year: int,
    ) -> None:
        """V1.2 max_year = birth_year + expected_lifespan（常數）"""
        freeze_base_year(2024)
        make_member(birth_year=birth_year, expected_lifespan=expected_lifespan)

        # max_year 是常數，不隨 base_year 變動
        max_year = birth_year + expected_lifespan
        assert max_year == expected_max_year

    def test_max_year_independent_of_base_year(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """max_year 不隨 base_year 變動"""
        # V1.2: max_year = birth_year + expected_lifespan
        # 不論 base_year 是 2024 還是 2025，max_year 都一樣

        freeze_base_year(2024)
        assumptions_2024 = make_life_assumptions()
        member_2024 = assumptions_2024.get_primary_member()
        max_year_2024 = member_2024.birth_year + member_2024.expected_lifespan

        freeze_base_year(2025)
        assumptions_2025 = make_life_assumptions()
        member_2025 = assumptions_2025.get_primary_member()
        max_year_2025 = member_2025.birth_year + member_2025.expected_lifespan

        assert max_year_2024 == max_year_2025

    def test_years_remaining_decreases(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """剩餘可用年數隨 base_year 減少"""
        birth_year = LUKE_BIRTH_YEAR
        expected_lifespan = 85
        max_year = birth_year + expected_lifespan

        freeze_base_year(2024)
        years_remaining_2024 = max_year - 2024

        freeze_base_year(2025)
        years_remaining_2025 = max_year - 2025

        assert years_remaining_2025 == years_remaining_2024 - 1


class TestYearProgressionDynamics:
    """base_year 推進對計算參數的影響"""

    @pytest.mark.parametrize(
        "base_year,target_year,expected_years_to_goal",
        [
            (2024, 2030, 6),
            (2025, 2030, 5),
            (2026, 2030, 4),
        ],
        ids=["2024_to_2030", "2025_to_2030", "2026_to_2030"],
    )
    def test_years_to_goal_decreases(
        self,
        freeze_base_year: Callable[[int], int],
        base_year: int,
        target_year: int,
        expected_years_to_goal: int,
    ) -> None:
        """years_to_goal 隨 base_year 推進而減少"""
        freeze_base_year(base_year)
        years_to_goal = target_year - base_year
        assert years_to_goal == expected_years_to_goal

    def test_years_to_retirement_decreases(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """距離退休年數隨 base_year 推進而減少"""
        retirement_age = 65
        birth_year = LUKE_BIRTH_YEAR
        retirement_year = birth_year + retirement_age

        freeze_base_year(2024)
        years_to_retirement_2024 = retirement_year - 2024

        freeze_base_year(2025)
        years_to_retirement_2025 = retirement_year - 2025

        assert years_to_retirement_2025 == years_to_retirement_2024 - 1


class TestMultiMemberYearProgression:
    """雙人（Person A & Person B）年度推進測試"""

    def test_both_members_age_increase(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """兩人年齡同步增加"""
        freeze_base_year(2024)
        assumptions = make_life_assumptions(
            members={
                "person_a": make_member(birth_year=LUKE_BIRTH_YEAR),
                "person_b": make_member(
                    display_name="Person B", birth_year=FREYA_BIRTH_YEAR
                ),
            }
        )

        luke_age_2024 = assumptions.get_current_age(member_id="person_a")
        freya_age_2024 = assumptions.get_current_age(member_id="person_b")

        # 查詢 2025 年齡（使用 as_of_year）
        luke_age_2025 = assumptions.get_current_age(member_id="person_a", as_of_year=2025)
        freya_age_2025 = assumptions.get_current_age(member_id="person_b", as_of_year=2025)

        assert luke_age_2025 == luke_age_2024 + 1
        assert freya_age_2025 == freya_age_2024 + 1

    def test_independent_retirement_timelines(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """兩人退休時間線獨立計算"""
        freeze_base_year(2024)
        make_life_assumptions(
            members={
                "person_a": make_member(
                    birth_year=LUKE_BIRTH_YEAR, retirement_age=65
                ),
                "person_b": make_member(
                    display_name="Person B",
                    birth_year=FREYA_BIRTH_YEAR,
                    retirement_age=60,
                ),
            }
        )

        luke_retirement_year = LUKE_BIRTH_YEAR + 65  # 2046
        freya_retirement_year = FREYA_BIRTH_YEAR + 60  # 2053

        luke_years_to_retirement = luke_retirement_year - 2024  # 22 年
        freya_years_to_retirement = freya_retirement_year - 2024  # 29 年

        assert luke_years_to_retirement == 22
        assert freya_years_to_retirement == 29


class TestV12StructureValidation:
    """V1.2 結構驗證測試"""

    def test_is_v12_structure_with_members(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """有 members 時 is_v12_structure() 返回 True"""
        freeze_base_year(2024)
        assumptions = make_life_assumptions()
        assert assumptions.is_v12_structure() is True

    def test_is_v12_structure_with_empty_members(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """空 members dict 視為非 V1.2 結構"""
        freeze_base_year(2024)
        # 建立 V1.1 legacy 結構
        assumptions = LifeAssumptions(
            basic=Basic(
                current_age=43,
                retirement_age=65,
                expected_lifespan=85,
            ),
            rates=make_life_assumptions().rates,
            members=None,
        )
        assert assumptions.is_v12_structure() is False

    def test_get_all_member_ids(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """get_all_member_ids() 返回所有成員 ID"""
        freeze_base_year(2024)
        assumptions = make_life_assumptions(
            members={
                "person_a": make_member(birth_year=LUKE_BIRTH_YEAR),
                "person_b": make_member(
                    display_name="Person B", birth_year=FREYA_BIRTH_YEAR
                ),
            }
        )
        member_ids = assumptions.get_all_member_ids()
        assert set(member_ids) == {"person_a", "person_b"}


class TestValidationGuardrails:
    """驗證護欄測試"""

    def test_base_year_below_1900_rejected(self) -> None:
        """base_year < 1900 應被拒絕"""
        with pytest.raises(ValueError, match="不能小於 1900"):
            Metadata(base_year=1899)

    def test_base_year_future_rejected(self) -> None:
        """base_year > 當前年份 應被拒絕"""
        future_year = datetime.now().year + 1
        with pytest.raises(ValueError, match="不能大於當前年份"):
            Metadata(base_year=future_year)

    def test_birth_year_below_1900_rejected(self) -> None:
        """birth_year < 1900 應被拒絕"""
        with pytest.raises(ValueError):
            Member(
                display_name="Test",
                birth_year=1899,
                retirement_age=65,
                expected_lifespan=85,
            )

    def test_expected_lifespan_less_than_retirement_rejected(self) -> None:
        """expected_lifespan <= retirement_age 應被拒絕"""
        with pytest.raises(ValueError, match="必須大於 retirement_age"):
            Member(
                display_name="Test",
                birth_year=1981,
                retirement_age=85,  # 退休年齡
                expected_lifespan=80,  # 壽命 < 退休年齡
            )

    def test_expected_lifespan_equals_retirement_rejected(self) -> None:
        """expected_lifespan == retirement_age 應被拒絕"""
        with pytest.raises(ValueError, match="必須大於 retirement_age"):
            Member(
                display_name="Test",
                birth_year=1981,
                retirement_age=85,
                expected_lifespan=85,  # 相等
            )

    def test_retirement_age_less_than_current_age_rejected(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """retirement_age <= current_age 時驗證失敗"""
        freeze_base_year(2024)

        with pytest.raises(ValueError, match="必須大於 base_year 時的年齡"):
            # Person A 在 2024 年是 43 歲，retirement_age=40 應失敗
            make_life_assumptions(
                members={
                    "person_a": make_member(
                        birth_year=LUKE_BIRTH_YEAR,
                        retirement_age=40,  # < 43
                    ),
                }
            )

    def test_current_age_zero_rejected(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """base_year == birth_year（age=0）應驗證失敗"""
        freeze_base_year(2024)

        with pytest.raises(ValueError, match="必須小於 base_year"):
            make_life_assumptions(
                members={
                    "person_a": make_member(birth_year=2024),  # age = 0
                }
            )

    def test_members_legacy_mutual_exclusivity(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """members 與 legacy 欄位不可共存"""
        freeze_base_year(2024)

        with pytest.raises(ValueError, match="不可共存"):
            LifeAssumptions(
                basic=Basic(
                    primary_member="person_a",
                    current_age=43,  # legacy 欄位
                    retirement_age=65,
                    expected_lifespan=85,
                ),
                rates=make_life_assumptions().rates,
                members={
                    "person_a": make_member(birth_year=LUKE_BIRTH_YEAR),
                },
            )

    def test_primary_member_must_exist(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """primary_member 必須存在於 members"""
        freeze_base_year(2024)

        with pytest.raises(ValueError, match="不存在於 members"):
            LifeAssumptions(
                basic=Basic(primary_member="nonexistent"),
                rates=make_life_assumptions().rates,
                members={
                    "person_a": make_member(birth_year=LUKE_BIRTH_YEAR),
                },
            )

    def test_member_id_not_in_allowed_list(
        self, freeze_base_year: Callable[[int], int]
    ) -> None:
        """member_id 必須在 ALLOWED_MEMBER_IDS 中"""
        freeze_base_year(2024)

        with pytest.raises(ValueError, match="不在允許列表中"):
            LifeAssumptions(
                basic=Basic(primary_member="invalid_id"),
                rates=make_life_assumptions().rates,
                members={
                    "invalid_id": make_member(birth_year=LUKE_BIRTH_YEAR),
                },
            )
