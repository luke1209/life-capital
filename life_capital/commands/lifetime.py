"""lifetime 指令

計算終身財務需求，顯示每個目標的儲蓄需求。
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from life_capital.calculators.lifetime import calculate_lifetime_needs
from life_capital.calculators.rounding import RoundingConfig
from life_capital.io import YAMLParseError, YAMLValidationError, load_model
from life_capital.io.registry import ASSUMPTIONS_FILE, TARGETS_FILE
from life_capital.models import LifeAssumptions, LifetimeTargets
from life_capital.models.assumptions import RatesMode
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def lifetime(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="顯示詳細計算過程",
    ),
) -> None:
    """計算終身財務需求

    根據 life_assumptions.yaml 和 lifetime_targets.yaml 計算：
    - 每個目標的未來價值（考慮通膨）
    - 每月需儲蓄金額
    - 總計每月儲蓄需求
    """
    data_dir = resolve_data_dir(path)

    # 載入資料
    try:
        assumptions = _load_assumptions(data_dir)
        targets = _load_targets(data_dir)
    except typer.Exit:
        raise

    # 計算
    rounding_config = RoundingConfig.from_calculation(assumptions.calculation)
    result = calculate_lifetime_needs(
        targets=targets.targets,
        assumptions=assumptions,
        rounding_config=rounding_config,
    )

    # 顯示結果
    _show_header(assumptions)

    if verbose:
        _show_calculation_details(result, rounding_config)

    _show_targets_table(result)
    _show_summary(result, assumptions)


def _load_assumptions(data_dir: Path) -> LifeAssumptions:
    """載入假設檔案"""
    assumptions_path = data_dir / ASSUMPTIONS_FILE

    if not assumptions_path.exists():
        console.print(f"[red]錯誤: 找不到 {ASSUMPTIONS_FILE}[/red]")
        console.print(f"[yellow]路徑: {assumptions_path}[/yellow]")
        console.print("[yellow]提示: 執行 lc init 初始化資料目錄[/yellow]")
        raise typer.Exit(1)

    try:
        return load_model(assumptions_path, LifeAssumptions)
    except (YAMLParseError, YAMLValidationError) as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)


def _load_targets(data_dir: Path) -> LifetimeTargets:
    """載入目標檔案"""
    targets_path = data_dir / TARGETS_FILE

    if not targets_path.exists():
        console.print(f"[red]錯誤: 找不到 {TARGETS_FILE}[/red]")
        console.print(f"[yellow]路徑: {targets_path}[/yellow]")
        console.print("[yellow]提示: 執行 lc init 初始化資料目錄[/yellow]")
        raise typer.Exit(1)

    try:
        return load_model(targets_path, LifetimeTargets)
    except (YAMLParseError, YAMLValidationError) as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)


def _show_header(assumptions: LifeAssumptions) -> None:
    """顯示標題與模式資訊"""
    mode = assumptions.rates.mode
    mode_desc = "名目模式（考慮通膨）" if mode == RatesMode.NOMINAL else "實質模式（固定幣值）"

    console.print()
    console.print(Panel(
        f"[bold]終身財務需求計算[/bold]\n\n"
        f"📐 計算模式: [cyan]{mode.value}[/cyan] - {mode_desc}\n"
        f"📅 基準年份: [cyan]{assumptions.metadata.base_year}[/cyan]\n"
        f"💰 貨幣: [cyan]{assumptions.metadata.currency}[/cyan]",
        title="[bold blue]Life Capital[/bold blue]",
        border_style="blue",
    ))


def _show_calculation_details(result, rounding_config: RoundingConfig) -> None:
    """顯示詳細計算資訊（verbose 模式）"""
    console.print()
    console.print("[bold]計算參數:[/bold]")
    console.print(f"  通膨率: {result.inflation_rate:.2%}")
    console.print(f"  投資報酬率: {result.investment_return:.2%}")
    console.print(f"  Rounding: {rounding_config}")
    console.print()


def _show_targets_table(result) -> None:
    """顯示目標明細表"""
    if not result.target_results:
        console.print("[yellow]沒有設定任何財務目標[/yellow]")
        return

    table = Table(
        title="[bold]財務目標明細[/bold]",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("目標", style="bold")
    table.add_column("優先級", justify="center")
    table.add_column("目標年", justify="center")
    table.add_column("準備期", justify="center")
    table.add_column("目標金額", justify="right")
    table.add_column("未來價值", justify="right")
    table.add_column("每月儲蓄", justify="right", style="green")

    for tr in result.target_results:
        priority_style = {
            "high": "[red]高[/red]",
            "medium": "[yellow]中[/yellow]",
            "low": "[green]低[/green]",
        }
        priority_display = priority_style.get(tr.target.priority.value, tr.target.priority.value)

        # 格式化金額
        base_amount = f"{tr.base_amount:,.0f}"
        future_value = f"{tr.future_value:,.0f}"
        monthly = f"{tr.monthly_payment:,.0f}"

        # 準備期說明
        if tr.years_to_goal == 0:
            period = "[red]立即[/red]"
        else:
            period = f"{tr.years_to_goal} 年"

        table.add_row(
            tr.target.name,
            priority_display,
            str(tr.target.target_year),
            period,
            base_amount,
            future_value,
            monthly,
        )

    console.print()
    console.print(table)


def _show_summary(result, assumptions: LifeAssumptions) -> None:
    """顯示彙總資訊"""
    if not result.target_results:
        return

    console.print()

    # 依優先級統計
    high_priority = result.get_by_priority("high")
    medium_priority = result.get_by_priority("medium")
    low_priority = result.get_by_priority("low")

    high_pmt = sum(tr.monthly_payment for tr in high_priority)
    medium_pmt = sum(tr.monthly_payment for tr in medium_priority)
    low_pmt = sum(tr.monthly_payment for tr in low_priority)

    # 建立摘要面板
    summary_lines = []

    summary_lines.append(f"[bold]目標總額[/bold]: {result.total_base_amount:,.0f} 元")

    if result.mode == RatesMode.NOMINAL:
        summary_lines.append(f"[bold]通膨調整後[/bold]: {result.total_future_value:,.0f} 元")

    summary_lines.append("")
    summary_lines.append(
        "[bold green]每月總儲蓄需求[/bold green]: "
        f"[bold]{result.total_monthly_payment:,.0f}[/bold] 元/月"
    )

    # 優先級分解
    if high_priority:
        summary_lines.append(
            f"  [red]高優先[/red]: {high_pmt:,.0f} 元/月 ({len(high_priority)} 項)"
        )
    if medium_priority:
        summary_lines.append(
            f"  [yellow]中優先[/yellow]: {medium_pmt:,.0f} 元/月 ({len(medium_priority)} 項)"
        )
    if low_priority:
        summary_lines.append(
            f"  [green]低優先[/green]: {low_pmt:,.0f} 元/月 ({len(low_priority)} 項)"
        )

    # 模式說明
    summary_lines.append("")
    if result.mode == RatesMode.NOMINAL:
        summary_lines.append(
            f"[dim]※ 以 {assumptions.rates.annual_inflation:.1%} 年通膨率推算未來價值[/dim]"
        )
        summary_lines.append(
            f"[dim]※ 假設投資年報酬率 {assumptions.rates.nominal_investment_return:.1%}[/dim]"
        )
    else:
        summary_lines.append(f"[dim]※ 金額以 {assumptions.metadata.base_year} 年幣值計算[/dim]")
        summary_lines.append(
            f"[dim]※ 假設實質投資報酬率 {assumptions.rates.real_investment_return:.1%}[/dim]"
        )

    console.print(Panel(
        "\n".join(summary_lines),
        title="[bold]儲蓄需求摘要[/bold]",
        border_style="green",
    ))
