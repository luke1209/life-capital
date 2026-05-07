"""summary 指令

顯示完整財務總覽，整合基本資料、終身需求與收入資訊。
"""

from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from life_capital.calculators.lifetime import calculate_lifetime_needs
from life_capital.calculators.rounding import RoundingConfig
from life_capital.io import YAMLParseError, YAMLValidationError, load_model
from life_capital.io.registry import ASSUMPTIONS_FILE, INCOME_FILE, TARGETS_FILE
from life_capital.models import LifeAssumptions, LifetimeTargets, MonthlyIncome
from life_capital.models.assumptions import RatesMode
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def summary(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """顯示財務總覽

    整合以下資訊：
    - 基本資料（年齡、退休年齡）
    - 終身財務需求
    - 月收入狀況
    - 儲蓄缺口分析
    """
    data_dir = resolve_data_dir(path)

    # 載入資料
    assumptions = _load_assumptions(data_dir)
    if assumptions is None:
        raise typer.Exit(1)

    targets = _load_targets(data_dir)
    income = _load_income(data_dir)  # 可選

    # 計算終身需求
    rounding_config = RoundingConfig.from_calculation(assumptions.calculation)

    lifetime_result = None
    if targets and targets.targets:
        lifetime_result = calculate_lifetime_needs(
            targets=targets.targets,
            assumptions=assumptions,
            rounding_config=rounding_config,
        )

    # 顯示總覽
    _show_title()
    _show_basic_info(assumptions)
    _show_lifetime_summary(lifetime_result, assumptions)
    _show_income_analysis(income, lifetime_result, rounding_config)
    _show_footer(assumptions)


def _load_assumptions(data_dir: Path) -> Optional[LifeAssumptions]:
    """載入假設檔案"""
    assumptions_path = data_dir / ASSUMPTIONS_FILE

    if not assumptions_path.exists():
        console.print(f"[red]錯誤: 找不到 {ASSUMPTIONS_FILE}[/red]")
        console.print("[yellow]提示: 執行 lc init 初始化資料目錄[/yellow]")
        return None

    try:
        return load_model(assumptions_path, LifeAssumptions)
    except (YAMLParseError, YAMLValidationError) as e:
        console.print(f"[red]錯誤: {e}[/red]")
        return None


def _load_targets(data_dir: Path) -> Optional[LifetimeTargets]:
    """載入目標檔案"""
    targets_path = data_dir / TARGETS_FILE

    if not targets_path.exists():
        console.print(f"[yellow]警告: 找不到 {TARGETS_FILE}[/yellow]")
        return None

    try:
        return load_model(targets_path, LifetimeTargets)
    except (YAMLParseError, YAMLValidationError) as e:
        console.print(f"[red]錯誤: {e}[/red]")
        return None


def _load_income(data_dir: Path) -> Optional[MonthlyIncome]:
    """載入收入檔案（可選）"""
    income_path = data_dir / INCOME_FILE

    if not income_path.exists():
        return None

    try:
        return load_model(income_path, MonthlyIncome)
    except (YAMLParseError, YAMLValidationError):
        return None


def _show_title() -> None:
    """顯示標題"""
    console.print()
    console.print(Panel(
        "[bold]Life Capital 財務總覽[/bold]",
        border_style="blue",
    ))


def _show_basic_info(assumptions: LifeAssumptions) -> None:
    """顯示基本資訊（使用 getter 方法支援 V1.1/V1.2）"""
    current_age = assumptions.get_current_age()
    retirement_age = assumptions.get_retirement_age()
    expected_lifespan = assumptions.get_expected_lifespan()

    years_to_retirement = retirement_age - current_age
    years_in_retirement = expected_lifespan - retirement_age

    table = Table(
        title="[bold]基本資訊[/bold]",
        show_header=False,
        box=None,
    )
    table.add_column("項目", style="dim")
    table.add_column("數值", justify="right")

    table.add_row("目前年齡", f"[cyan]{current_age}[/cyan] 歲")
    table.add_row("退休年齡", f"[cyan]{retirement_age}[/cyan] 歲")
    table.add_row("預期壽命", f"[cyan]{expected_lifespan}[/cyan] 歲")
    table.add_row("", "")
    table.add_row("距離退休", f"[green]{years_to_retirement}[/green] 年")
    table.add_row("退休後生活", f"[yellow]{years_in_retirement}[/yellow] 年")

    console.print()
    console.print(table)


def _show_lifetime_summary(lifetime_result, assumptions: LifeAssumptions) -> None:
    """顯示終身需求摘要"""
    console.print()

    if lifetime_result is None or not lifetime_result.target_results:
        console.print(Panel(
            "[yellow]尚未設定財務目標[/yellow]\n\n"
            "編輯 lifetime_targets.yaml 新增目標後，\n"
            "執行 lc lifetime 查看詳細計算。",
            title="[bold]終身需求[/bold]",
            border_style="yellow",
        ))
        return

    mode = lifetime_result.mode
    mode_label = "名目" if mode == RatesMode.NOMINAL else "實質"

    # 統計各優先級
    high = lifetime_result.get_by_priority("high")
    medium = lifetime_result.get_by_priority("medium")
    low = lifetime_result.get_by_priority("low")

    lines = []
    lines.append(f"[bold]目標總額[/bold]: {lifetime_result.total_base_amount:,.0f} 元")

    if mode == RatesMode.NOMINAL:
        lines.append(f"[bold]通膨調整後[/bold]: {lifetime_result.total_future_value:,.0f} 元")

    lines.append("")
    lines.append(f"📊 目標數量: [cyan]{len(lifetime_result.target_results)}[/cyan] 個")

    if high:
        lines.append(f"   ├ [red]高優先[/red]: {len(high)} 個")
    if medium:
        lines.append(f"   ├ [yellow]中優先[/yellow]: {len(medium)} 個")
    if low:
        lines.append(f"   └ [green]低優先[/green]: {len(low)} 個")

    lines.append("")
    lines.append(
        "💰 [bold green]每月儲蓄需求[/bold green]: "
        f"[bold]{lifetime_result.total_monthly_payment:,.0f}[/bold] 元"
    )
    lines.append(f"[dim]（{mode_label}模式，基準年 {assumptions.metadata.base_year}）[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]終身需求[/bold]",
        border_style="cyan",
    ))


def _show_income_analysis(
    income: Optional[MonthlyIncome],
    lifetime_result,
    rounding_config: RoundingConfig,
) -> None:
    """顯示收入分析"""
    console.print()

    if income is None:
        console.print(Panel(
            "[yellow]尚未設定月收入資料[/yellow]\n\n"
            "編輯 monthly_income.yaml 後可查看缺口分析。",
            title="[bold]收入分析[/bold]",
            border_style="yellow",
        ))
        return

    total_income = Decimal(str(income.total_monthly()))
    total_income = rounding_config.quantize(total_income)

    lines = []
    lines.append(f"[bold]月總收入[/bold]: {total_income:,.0f} 元")

    # 收入來源明細
    if income.sources:
        lines.append("")
        for source in income.sources:
            amount = rounding_config.quantize(Decimal(str(source.amount)))
            lines.append(f"   • {source.name}: {amount:,.0f} 元")

    # 缺口分析
    if lifetime_result and lifetime_result.target_results:
        required = lifetime_result.total_monthly_payment
        gap = required - total_income

        lines.append("")
        lines.append(f"[bold]需求儲蓄[/bold]: {required:,.0f} 元/月")

        if gap > 0:
            gap_pct = (gap / total_income * 100) if total_income > 0 else Decimal("100")
            lines.append("")
            lines.append(f"[bold red]⚠️ 缺口[/bold red]: [red]{gap:,.0f}[/red] 元/月")
            lines.append(f"[dim]（佔收入 {gap_pct:.1f}%）[/dim]")

            # 建議
            lines.append("")
            lines.append("[dim]建議：[/dim]")
            lines.append("[dim]  • 增加收入來源[/dim]")
            lines.append("[dim]  • 調整目標優先級或時程[/dim]")
            lines.append("[dim]  • 重新評估目標金額[/dim]")
        else:
            surplus = -gap
            lines.append("")
            lines.append(f"[bold green]✅ 盈餘[/bold green]: [green]{surplus:,.0f}[/green] 元/月")
            lines.append("[dim]儲蓄能力充足，可考慮提前達成目標或增加投資[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]收入分析[/bold]",
        border_style=(
            "green"
            if (
                income
                and lifetime_result
                and Decimal(str(income.total_monthly()))
                >= lifetime_result.total_monthly_payment
            )
            else "red"
        ),
    ))


def _show_footer(assumptions: LifeAssumptions) -> None:
    """顯示頁尾資訊"""
    mode = assumptions.rates.mode
    console.print()
    console.print(Panel(
        f"[dim]計算模式: {mode.value} | "
        f"基準年: {assumptions.metadata.base_year} | "
        f"貨幣: {assumptions.metadata.currency}[/dim]\n"
        f"[dim]執行 lc lifetime 查看詳細目標計算 | "
        f"lc expense check 查看支出分析[/dim]",
        border_style="dim",
    ))
