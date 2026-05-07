"""JSON 格式化器

提供財務報表的 JSON 格式化功能。

V4.1.1 輸出規範：
- 結構化資料輸出
- 金額使用字串（保留 Decimal 精度）
- 與 Markdown 格式保持指標一致性（E2 要求）
"""

import json
from decimal import Decimal

from life_capital.models.scenario import ProjectionResult, ScenarioComparisonResult


class JSONFormatter:
    """JSON 格式化器（V4.1.1 輸出規範）

    提供符合 Contract 6 規範的 JSON 輸出。
    """

    @staticmethod
    def decimal_to_str(value: Decimal) -> str:
        """Decimal 轉字串（保留精度）

        Args:
            value: Decimal 值

        Returns:
            字串表示（如 "1234567"）
        """
        return str(int(value))

    def format_monthly_summary(self, projection: ProjectionResult) -> str:
        """格式化月度現金流摘要（V4.1.1 規範）

        Args:
            projection: Phase 2 預測結果

        Returns:
            JSON 格式的月度摘要
        """
        # 計算關鍵指標（與 Markdown 一致）
        deficit_count = len(projection.deficit_months)
        has_depletion = projection.asset_depletion_month is not None

        data = {
            "report_type": "monthly_summary",
            "projection_months": len(projection.monthly_projections),
            "indicators": {
                "total_income": self.decimal_to_str(projection.total_income),
                "total_expenses": self.decimal_to_str(projection.total_expenses),
                "final_savings": self.decimal_to_str(projection.final_cumulative_savings),
                "average_monthly_cashflow": self.decimal_to_str(
                    projection.average_monthly_cashflow
                ),
                "deficit_months": deficit_count,
            },
            "status": {
                "has_depletion": has_depletion,
                "depletion_month": (
                    f"{projection.asset_depletion_month[0]}/{projection.asset_depletion_month[1]:02d}"
                    if has_depletion
                    else None
                ),
            },
        }

        # V4.1.1: 不包含 generated_at（只在 .meta.json）
        return json.dumps(data, ensure_ascii=False, indent=2)

    def format_projection_table(
        self, projection: ProjectionResult, max_months: int = 12
    ) -> str:
        """格式化預測表（V4.1.1 規範）

        Args:
            projection: Phase 2 預測結果
            max_months: 最多顯示月數（預設 12 個月）

        Returns:
            JSON 格式的預測表
        """
        monthly_data = []
        for mp in projection.monthly_projections[:max_months]:
            monthly_data.append(
                {
                    "year": mp.year,
                    "month": mp.month,
                    "income": self.decimal_to_str(mp.income),
                    "total_expenses": self.decimal_to_str(mp.total_expenses),
                    "net_cashflow": self.decimal_to_str(mp.net_cashflow),
                    "cumulative_savings": self.decimal_to_str(mp.cumulative_savings),
                    "is_deficit": mp.is_deficit,
                    "is_depleted": mp.cumulative_savings < 0,
                }
            )

        data = {"report_type": "projection_table", "monthly_data": monthly_data}

        # V4.1.1: 不包含 generated_at
        return json.dumps(data, ensure_ascii=False, indent=2)

    def format_scenario_comparison(
        self, comparison: ScenarioComparisonResult
    ) -> str:
        """格式化情境比較（V4.1.1 規範）

        Args:
            comparison: Phase 2 情境比較結果

        Returns:
            JSON 格式的情境比較
        """
        # 生成情境假設資料
        scenario_assumptions = []
        for scenario in comparison.scenarios:
            s = scenario.scenario
            scenario_assumptions.append(
                {
                    "name": s.name,
                    "income_change_percent": float(s.income_change_percent),
                    "expense_change_percent": float(s.expense_change_percent),
                    "description": s.description,
                }
            )

        # 生成結果比較資料
        comparison_results = []
        table = comparison.comparison_table

        # 處理各情境
        for row in table.get("scenarios", []):
            name = row["name"]
            final_savings = int(Decimal(row["final_savings"]))
            deficit_months = row.get("deficit_months", [])
            deficit_count = (
                len(deficit_months) if isinstance(deficit_months, list) else deficit_months
            )
            depletion = row.get("asset_depletion")

            # 使用已計算的差異（與 Markdown 一致）
            diff = row.get("diff_savings")
            if diff:
                diff = int(Decimal(diff))

            comparison_results.append(
                {
                    "name": name,
                    "final_savings": str(final_savings),
                    "vs_baseline_diff": str(diff) if diff is not None else None,
                    "deficit_months": deficit_count,
                    "depletion_month": (
                        f"{depletion[0]}/{depletion[1]:02d}" if depletion else None
                    ),
                }
            )

        data = {
            "report_type": "scenario_comparison",
            "baseline_name": comparison.baseline_name,
            "scenario_assumptions": scenario_assumptions,
            "comparison_results": comparison_results,
        }

        # V4.1.1: 不包含 generated_at
        return json.dumps(data, ensure_ascii=False, indent=2)
