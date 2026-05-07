"""報表生成器核心邏輯測試

測試 Phase 3 報表生成的核心功能：
- 輸入邊界 enforcement（Contract 2）
- input_sources_hash 計算（Contract 4）
- ReportProvenance 追蹤（Contract 3）
- 報表生成基本功能
"""

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from life_capital.generation.models import ReportProvenance
from life_capital.generation.report_generator import (
    InputMissingError,
    ReportGenerator,
    compute_input_sources_hash,
    load_comparison_from_derived,
    load_projection_from_derived,
)
from life_capital.io.registry import REPORT_HASH_LEN
from life_capital.models.scenario import (
    MonthlyProjection,
    ProjectionResult,
    ScenarioComparisonResult,
)


def test_compute_input_sources_hash_monthly_summary():
    """測試 monthly_summary 的 input_sources_hash 計算（Contract 4）"""
    # 建立測試 projection
    projection = ProjectionResult(
        monthly_projections=[],
        total_income=Decimal("100000"),
        total_expenses=Decimal("80000"),
        final_cumulative_savings=Decimal("20000"),
        average_monthly_cashflow=Decimal("1667"),
        deficit_months=[],
        first_deficit_month=None,
        asset_depletion_month=None,
        input_hash="test_hash_123",
        calculation_timestamp="2025-12-28T12:00:00",
    )

    # 計算 hash
    result = compute_input_sources_hash("monthly_summary", projection)

    # 驗證：應該是 projection.input_hash 的 sha256[:12]
    expected = hashlib.sha256("test_hash_123".encode()).hexdigest()[:REPORT_HASH_LEN]
    assert result == expected
    assert len(result) == REPORT_HASH_LEN


def test_compute_input_sources_hash_projection_table():
    """測試 projection_table 的 input_sources_hash 計算（Contract 4）"""
    projection = ProjectionResult(
        monthly_projections=[],
        total_income=Decimal("100000"),
        total_expenses=Decimal("80000"),
        final_cumulative_savings=Decimal("20000"),
        average_monthly_cashflow=Decimal("1667"),
        deficit_months=[],
        first_deficit_month=None,
        asset_depletion_month=None,
        input_hash="test_hash_456",
        calculation_timestamp="2025-12-28T12:00:00",
    )

    result = compute_input_sources_hash("projection_table", projection)

    expected = hashlib.sha256("test_hash_456".encode()).hexdigest()[:REPORT_HASH_LEN]
    assert result == expected


def test_compute_input_sources_hash_scenario_comparison():
    """測試 scenario_comparison 的 input_sources_hash 計算（Contract 4）"""
    projection = ProjectionResult(
        monthly_projections=[],
        total_income=Decimal("100000"),
        total_expenses=Decimal("80000"),
        final_cumulative_savings=Decimal("20000"),
        average_monthly_cashflow=Decimal("1667"),
        deficit_months=[],
        first_deficit_month=None,
        asset_depletion_month=None,
        input_hash="proj_hash",
        calculation_timestamp="2025-12-28T12:00:00",
    )

    comparison = ScenarioComparisonResult(
        baseline_name="baseline",
        scenarios=[],
        comparison_table={"baseline": {}, "scenarios": []},
        input_hash="comp_hash",
    )

    result = compute_input_sources_hash("scenario_comparison", projection, comparison)

    # 驗證：應該是 projection.input_hash + comparison.input_hash 的組合 hash
    combined = "proj_hash:comp_hash"
    expected = hashlib.sha256(combined.encode()).hexdigest()[:REPORT_HASH_LEN]
    assert result == expected


def test_compute_input_sources_hash_scenario_comparison_missing_comparison():
    """測試 scenario_comparison 缺少 comparison 時應拋出錯誤"""
    projection = ProjectionResult(
        monthly_projections=[],
        total_income=Decimal("100000"),
        total_expenses=Decimal("80000"),
        final_cumulative_savings=Decimal("20000"),
        average_monthly_cashflow=Decimal("1667"),
        deficit_months=[],
        first_deficit_month=None,
        asset_depletion_month=None,
        input_hash="test_hash",
        calculation_timestamp="2025-12-28T12:00:00",
    )

    with pytest.raises(ValueError, match="scenario_comparison requires comparison input"):
        compute_input_sources_hash("scenario_comparison", projection, None)


def test_compute_input_sources_hash_unknown_type():
    """測試未知 report_type 應拋出錯誤"""
    projection = ProjectionResult(
        monthly_projections=[],
        total_income=Decimal("100000"),
        total_expenses=Decimal("80000"),
        final_cumulative_savings=Decimal("20000"),
        average_monthly_cashflow=Decimal("1667"),
        deficit_months=[],
        first_deficit_month=None,
        asset_depletion_month=None,
        input_hash="test_hash",
        calculation_timestamp="2025-12-28T12:00:00",
    )

    with pytest.raises(ValueError, match="Unknown report_type"):
        compute_input_sources_hash("unknown_type", projection)


def test_report_generator_generate_monthly_summary():
    """測試生成月度摘要報表"""
    # 建立測試資料
    mp1 = MonthlyProjection(
        year=2026,
        month=1,
        income=Decimal("100000"),
        regular_expenses=Decimal("80000"),
        one_time_expenses=Decimal("0"),
        total_expenses=Decimal("80000"),
        net_cashflow=Decimal("20000"),
        cumulative_savings=Decimal("20000"),
        is_deficit=False,
    )

    projection = ProjectionResult(
        monthly_projections=[mp1],
        total_income=Decimal("100000"),
        total_expenses=Decimal("80000"),
        final_cumulative_savings=Decimal("20000"),
        average_monthly_cashflow=Decimal("20000"),
        deficit_months=[],
        first_deficit_month=None,
        asset_depletion_month=None,
        input_hash="test_hash",
        calculation_timestamp="2025-12-28T12:00:00",
    )

    # 建立生成器（使用 tmp_path）
    generator = ReportGenerator(Path("/tmp"))

    # 生成報表
    report = generator.generate_monthly_summary(projection, format="md")

    # 驗證
    assert report.report_type == "monthly_summary"
    assert report.format == "md"
    assert "財務預測摘要" in report.content
    assert "100,000" in report.content  # 總收入
    assert isinstance(report.provenance, ReportProvenance)
    assert report.provenance.generation_version == "1.0"


def test_report_generator_generate_projection_table():
    """測試生成預測表報表"""
    mp1 = MonthlyProjection(
        year=2026,
        month=1,
        income=Decimal("100000"),
        regular_expenses=Decimal("80000"),
        one_time_expenses=Decimal("0"),
        total_expenses=Decimal("80000"),
        net_cashflow=Decimal("20000"),
        cumulative_savings=Decimal("20000"),
        is_deficit=False,
    )

    projection = ProjectionResult(
        monthly_projections=[mp1],
        total_income=Decimal("100000"),
        total_expenses=Decimal("80000"),
        final_cumulative_savings=Decimal("20000"),
        average_monthly_cashflow=Decimal("20000"),
        deficit_months=[],
        first_deficit_month=None,
        asset_depletion_month=None,
        input_hash="test_hash",
        calculation_timestamp="2025-12-28T12:00:00",
    )

    generator = ReportGenerator(Path("/tmp"))
    report = generator.generate_projection_table(projection, format="md")

    # 驗證
    assert report.report_type == "projection_table"
    assert report.format == "md"
    assert "月度預測明細" in report.content
    assert "2026/01" in report.content
    assert isinstance(report.provenance, ReportProvenance)


def test_load_projection_from_derived_missing_file(tmp_path):
    """測試缺少 projection_baseline.json 時應拋出 InputMissingError（Contract 2）"""
    with pytest.raises(InputMissingError, match="projection_baseline.json not found"):
        load_projection_from_derived(tmp_path)


def test_load_comparison_from_derived_missing_file(tmp_path):
    """測試缺少 comparison.json 時應返回 None（Contract 2）"""
    result = load_comparison_from_derived(tmp_path)
    assert result is None
