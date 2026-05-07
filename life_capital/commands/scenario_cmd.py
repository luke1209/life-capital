"""scenario 指令

情境分析與比較，評估不同財務假設對未來的影響。
"""

import os
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from life_capital.calculators.scenario import (
    compare_scenarios,
    get_preset_assumption,
)
from life_capital.io.data_fetcher import (
    fetch_historical_expenses,
    fetch_latest_income,
)
from life_capital.io.registry import (
    DEFAULT_HISTORICAL_MONTHS,
    DEFAULT_PROJECTION_MONTHS,
    DERIVED_SCENARIOS_DIR,
)
from life_capital.models.scenario import (
    ProjectionInput,
    ScenarioAssumption,
    ScenarioComparisonResult,
    ScenarioPreset,
    ScenarioType,
)
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def scenario(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    months: int = typer.Option(
        DEFAULT_PROJECTION_MONTHS,
        "--months",
        "-m",
        help=f"預測月數（預設 {DEFAULT_PROJECTION_MONTHS}）",
    ),
    initial_savings: Optional[str] = typer.Option(
        None,
        "--savings",
        "-s",
        help="初始儲蓄金額（預設：0）",
    ),
    income_override: Optional[str] = typer.Option(
        None,
        "--income",
        "-i",
        help="月收入覆寫值",
    ),
    expense_override: Optional[str] = typer.Option(
        None,
        "--expense",
        "-e",
        help="月支出覆寫值",
    ),
    preset: str = typer.Option(
        "all",
        "--preset",
        help="情境預設（conservative/baseline/optimistic/all）",
    ),
    income_change: Optional[str] = typer.Option(
        None,
        "--income-change",
        help="收入變動百分比（如 -0.1 代表 -10%）",
    ),
    expense_change: Optional[str] = typer.Option(
        None,
        "--expense-change",
        help="支出變動百分比（如 0.1 代表 +10%）",
    ),
    historical_months: int = typer.Option(
        DEFAULT_HISTORICAL_MONTHS,
        "--history",
        help="歷史支出參考月數",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="顯示詳細資訊",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="存檔到 derived/scenarios/comparison.json",
    ),
) -> None:
    """情境分析

    比較不同財務假設下的預測結果。

    預設情境：
    - 保守 (conservative): 收入 -10%, 支出 +10%
    - 基準 (baseline): 無變化
    - 樂觀 (optimistic): 收入 +10%, 支出 -5%

    範例：
        lc scenario --preset all
        lc scenario --income 100000 --expense 80000
        lc scenario --income-change -0.2 --expense-change 0.15
    """
    data_dir = resolve_data_dir(path)

    # 解析輸入參數
    try:
        parsed_savings = _parse_decimal(initial_savings, "初始儲蓄", Decimal("0"))
        parsed_income = _parse_decimal(income_override, "月收入", None)
        parsed_expense = _parse_decimal(expense_override, "月支出", None)
        parsed_income_change = _parse_decimal(income_change, "收入變動", None)
        parsed_expense_change = _parse_decimal(expense_change, "支出變動", None)
    except typer.Exit:
        raise

    # 載入資料
    income_data = None
    if parsed_income is None:
        income_data = fetch_latest_income(str(data_dir))
        if income_data is None:
            console.print("[yellow]警告: 找不到 monthly_income.yaml，請使用 --income 指定[/yellow]")
            raise typer.Exit(1)

    historical = []
    if parsed_expense is None:
        historical = fetch_historical_expenses(str(data_dir), months_back=historical_months)
        if not historical:
            console.print("[yellow]警告: 找不到歷史支出資料，請使用 --expense 指定[/yellow]")
            raise typer.Exit(1)

    # 決定起始月份
    today = date.today()
    if today.month == 12:
        start_year, start_month = today.year + 1, 1
    else:
        start_year, start_month = today.year, today.month + 1

    # 建立基礎輸入
    base_input = ProjectionInput(
        start_year=start_year,
        start_month=start_month,
        initial_savings=parsed_savings,
        projection_months=months,
        income=income_data,
        historical_expenses=historical,
        income_override=parsed_income,
        expense_override=parsed_expense,
        expense_estimation_strategy="average",
    )

    # 建立情境清單
    scenarios = _build_scenarios(
        preset=preset,
        income_change=parsed_income_change,
        expense_change=parsed_expense_change,
    )

    if not scenarios:
        console.print("[red]錯誤: 沒有有效的情境[/red]")
        raise typer.Exit(1)

    # 執行比較
    try:
        result = compare_scenarios(base_input, scenarios)
    except Exception as e:
        console.print(f"[red]計算錯誤: {e}[/red]")
        raise typer.Exit(1)

    # 存檔（若要求）
    if save:
        _save_comparison(data_dir, result)

    # 顯示結果
    _show_header(base_input, len(scenarios))

    if verbose:
        _show_scenario_details(scenarios)

    _show_comparison_table(result)
    _show_summary(result)


def _parse_decimal(
    value: Optional[str],
    name: str,
    default: Optional[Decimal],
) -> Optional[Decimal]:
    """解析數值參數"""
    if value is None:
        return default

    try:
        cleaned = value.replace(",", "")
        return Decimal(cleaned)
    except InvalidOperation:
        console.print(f"[red]錯誤: 無效的{name}數值 '{value}'[/red]")
        raise typer.Exit(1)


def _build_scenarios(
    preset: str,
    income_change: Optional[Decimal],
    expense_change: Optional[Decimal],
) -> list[ScenarioAssumption]:
    """建立情境清單"""
    scenarios = []

    # 自訂情境
    if income_change is not None or expense_change is not None:
        custom = ScenarioAssumption(
            name="自訂情境",
            scenario_type=ScenarioType.COMBINED,
            income_change_percent=income_change or Decimal("0"),
            expense_change_percent=expense_change or Decimal("0"),
            description=(
                f"收入 {_format_percent(income_change)}, "
                f"支出 {_format_percent(expense_change)}"
            ),
        )
        scenarios.append(custom)
        return scenarios

    # 預設情境
    preset_lower = preset.lower()

    if preset_lower == "all":
        scenarios.append(get_preset_assumption(ScenarioPreset.CONSERVATIVE))
        scenarios.append(get_preset_assumption(ScenarioPreset.BASELINE))
        scenarios.append(get_preset_assumption(ScenarioPreset.OPTIMISTIC))
    elif preset_lower == "conservative":
        scenarios.append(get_preset_assumption(ScenarioPreset.CONSERVATIVE))
    elif preset_lower == "baseline":
        scenarios.append(get_preset_assumption(ScenarioPreset.BASELINE))
    elif preset_lower == "optimistic":
        scenarios.append(get_preset_assumption(ScenarioPreset.OPTIMISTIC))
    else:
        console.print(f"[red]錯誤: 無效的預設 '{preset}'[/red]")
        console.print("[yellow]有效選項: conservative, baseline, optimistic, all[/yellow]")
        raise typer.Exit(1)

    return scenarios


def _format_percent(value: Optional[Decimal]) -> str:
    """格式化百分比"""
    if value is None or value == Decimal("0"):
        return "不變"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.0f}%"


def _show_header(inputs: ProjectionInput, scenario_count: int) -> None:
    """顯示標題"""
    start = f"{inputs.start_year}/{inputs.start_month:02d}"
    end_year = inputs.start_year + (inputs.start_month + inputs.projection_months - 2) // 12
    end_month = (inputs.start_month + inputs.projection_months - 2) % 12 + 1
    end = f"{end_year}/{end_month:02d}"

    info_lines = [
        "[bold]情境分析[/bold]",
        "",
        f"📅 預測期間: [cyan]{start}[/cyan] → [cyan]{end}[/cyan] ({inputs.projection_months} 個月)",
        f"💰 初始儲蓄: [cyan]{inputs.initial_savings:,.0f}[/cyan] 元",
        f"📊 比較情境數: [cyan]{scenario_count}[/cyan] 個",
    ]

    console.print()
    console.print(Panel(
        "\n".join(info_lines),
        title="[bold blue]Life Capital[/bold blue]",
        border_style="blue",
    ))


def _show_scenario_details(scenarios: list[ScenarioAssumption]) -> None:
    """顯示情境詳細資訊（verbose 模式）"""
    console.print()
    console.print("[bold]情境假設:[/bold]")

    for s in scenarios:
        console.print(f"  • {s.name}")
        console.print(f"    收入變動: {_format_percent(s.income_change_percent)}")
        console.print(f"    支出變動: {_format_percent(s.expense_change_percent)}")
        if s.description:
            console.print(f"    說明: {s.description}")
    console.print()


def _show_comparison_table(result) -> None:
    """顯示情境比較表"""
    table = Table(
        title="[bold]情境比較[/bold]",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("情境", style="bold")
    table.add_column("最終儲蓄", justify="right")
    table.add_column("vs 基準", justify="right")
    table.add_column("赤字月數", justify="center")
    table.add_column("資產耗盡", justify="center")

    # 基準行
    baseline = result.comparison_table["baseline"]
    baseline_savings = Decimal(baseline["final_savings"])
    table.add_row(
        f"[bold]{result.baseline_name}[/bold]",
        f"{baseline_savings:,.0f}",
        "-",
        str(len(baseline["deficit_months"])) if baseline["deficit_months"] else "0",
        _format_depletion(baseline["asset_depletion"]),
    )

    # 各情境行
    for scenario_data in result.comparison_table["scenarios"]:
        final_savings = Decimal(scenario_data["final_savings"])
        diff = scenario_data["diff_savings"]

        # 差異格式化
        if diff is not None:
            diff_decimal = Decimal(diff)
            if diff_decimal >= 0:
                diff_str = f"[green]+{diff_decimal:,.0f}[/green]"
            else:
                diff_str = f"[red]{diff_decimal:,.0f}[/red]"
        else:
            diff_str = "-"

        # 儲蓄格式化
        if final_savings >= 0:
            savings_str = f"{final_savings:,.0f}"
        else:
            savings_str = f"[red]{final_savings:,.0f}[/red]"

        # 赤字月數
        deficit_count = (
            len(scenario_data["deficit_months"]) if scenario_data["deficit_months"] else 0
        )
        deficit_str = (
            str(deficit_count) if deficit_count == 0 else f"[yellow]{deficit_count}[/yellow]"
        )

        table.add_row(
            scenario_data["name"],
            savings_str,
            diff_str,
            deficit_str,
            _format_depletion(scenario_data["asset_depletion"]),
        )

    console.print()
    console.print(table)


def _format_depletion(depletion) -> str:
    """格式化資產耗盡資訊"""
    if depletion is None:
        return "[green]✓ 安全[/green]"
    year, month = depletion
    return f"[red]{year}/{month:02d}[/red]"


def _show_summary(result) -> None:
    """顯示摘要分析"""
    console.print()

    # 找出最佳與最差情境
    all_scenarios = result.scenarios

    if not all_scenarios:
        return

    best = max(all_scenarios, key=lambda s: s.projection.final_cumulative_savings)
    worst = min(all_scenarios, key=lambda s: s.projection.final_cumulative_savings)

    summary_lines = []

    # 最佳情境
    summary_lines.append(
        f"[bold green]最佳情境[/bold green]: {best.scenario.name} "
        f"(最終儲蓄 {best.projection.final_cumulative_savings:,.0f} 元)"
    )

    # 最差情境
    worst_color = "red" if worst.projection.final_cumulative_savings < 0 else "yellow"
    summary_lines.append(
        f"[bold {worst_color}]最差情境[/bold {worst_color}]: {worst.scenario.name} "
        f"(最終儲蓄 {worst.projection.final_cumulative_savings:,.0f} 元)"
    )

    # 落差分析
    diff = best.projection.final_cumulative_savings - worst.projection.final_cumulative_savings
    summary_lines.append("")
    summary_lines.append(f"[bold]情境落差[/bold]: {diff:,.0f} 元")

    # 風險警告
    has_depletion = any(
        s.projection.asset_depletion_month is not None
        for s in all_scenarios
    )
    if has_depletion:
        summary_lines.append("")
        summary_lines.append(
            "[yellow]⚠️ 警告: 部分情境存在資產耗盡風險[/yellow]"
        )

    console.print(Panel(
        "\n".join(summary_lines),
        title="[bold]分析摘要[/bold]",
        border_style="cyan",
    ))


def _save_comparison(data_dir: Path, result: ScenarioComparisonResult) -> None:
    """存檔情境比較結果到 derived/scenarios/comparison.json

    使用原子寫入策略：temp → flush → fsync → os.replace
    """
    scenarios_dir = data_dir / DERIVED_SCENARIOS_DIR
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    target_path = scenarios_dir / "comparison.json"
    temp_path = target_path.with_suffix(f".tmp.{uuid4().hex[:8]}")

    try:
        # 序列化為 JSON（Pydantic model_dump_json）
        content = result.model_dump_json(indent=2)

        # 原子寫入
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, target_path)
        console.print(f"[green]✓ 已存檔: {target_path}[/green]")

    except Exception as e:
        temp_path.unlink(missing_ok=True)
        console.print(f"[red]存檔失敗: {e}[/red]")
