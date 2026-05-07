"""project 指令

執行現金流預測，顯示未來財務狀況。
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

from life_capital.calculators.projection import (
    calculate_projection,
    estimate_monthly_expenses,
)
from life_capital.io.data_fetcher import (
    fetch_historical_expenses,
    fetch_latest_income,
)
from life_capital.io.registry import (
    DEFAULT_HISTORICAL_MONTHS,
    DEFAULT_PROJECTION_MONTHS,
    DERIVED_SCENARIOS_DIR,
    MAX_PROJECTION_MONTHS,
    MIN_PROJECTION_MONTHS,
)
from life_capital.models.scenario import ProjectionInput, ProjectionResult
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def project(
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
        help=(
            f"預測月數（{MIN_PROJECTION_MONTHS}-{MAX_PROJECTION_MONTHS}，"
            f"預設 {DEFAULT_PROJECTION_MONTHS}）"
        ),
        min=MIN_PROJECTION_MONTHS,
        max=MAX_PROJECTION_MONTHS,
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
        help="月收入覆寫值（忽略 monthly_income.yaml）",
    ),
    expense_override: Optional[str] = typer.Option(
        None,
        "--expense",
        "-e",
        help="月支出覆寫值（忽略歷史資料估算）",
    ),
    strategy: str = typer.Option(
        "average",
        "--strategy",
        help="支出估算策略（average/median/max/latest）",
    ),
    historical_months: int = typer.Option(
        DEFAULT_HISTORICAL_MONTHS,
        "--history",
        help=f"歷史支出參考月數（預設 {DEFAULT_HISTORICAL_MONTHS}）",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="顯示詳細預測資訊",
    ),
    show_monthly: bool = typer.Option(
        False,
        "--monthly",
        help="顯示每月明細",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        help="存檔到 derived/scenarios/projection_baseline.json",
    ),
) -> None:
    """現金流預測

    根據歷史支出與收入資料，預測未來財務狀況。

    範例：
        lc project --months 12
        lc project --income 100000 --expense 80000
        lc project --savings 500000 --strategy median
    """
    data_dir = resolve_data_dir(path)

    # 解析輸入參數
    try:
        parsed_savings = _parse_decimal(initial_savings, "初始儲蓄", Decimal("0"))
        parsed_income = _parse_decimal(income_override, "月收入", None)
        parsed_expense = _parse_decimal(expense_override, "月支出", None)
    except typer.Exit:
        raise

    # 驗證策略
    valid_strategies = ["average", "median", "max", "latest"]
    if strategy not in valid_strategies:
        console.print(f"[red]錯誤: 無效的策略 '{strategy}'[/red]")
        console.print(f"[yellow]有效選項: {', '.join(valid_strategies)}[/yellow]")
        raise typer.Exit(1)

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

    # 決定起始月份（下個月）
    today = date.today()
    if today.month == 12:
        start_year, start_month = today.year + 1, 1
    else:
        start_year, start_month = today.year, today.month + 1

    # 建立輸入
    projection_input = ProjectionInput(
        start_year=start_year,
        start_month=start_month,
        initial_savings=parsed_savings,
        projection_months=months,
        income=income_data,
        historical_expenses=historical,
        income_override=parsed_income,
        expense_override=parsed_expense,
        expense_estimation_strategy=strategy,
    )

    # 執行計算
    try:
        result = calculate_projection(projection_input)
    except Exception as e:
        console.print(f"[red]計算錯誤: {e}[/red]")
        raise typer.Exit(1)

    # 存檔（若要求）
    if save:
        _save_projection(data_dir, result)

    # 顯示結果
    _show_header(projection_input, result, strategy, historical_months)

    if verbose:
        _show_input_details(projection_input, historical)

    if show_monthly:
        _show_monthly_table(result)

    _show_summary(result)

    if result.deficit_months:
        _show_warnings(result)


def _parse_decimal(
    value: Optional[str],
    name: str,
    default: Optional[Decimal],
) -> Optional[Decimal]:
    """解析金額參數"""
    if value is None:
        return default

    try:
        # 移除千分位逗號
        cleaned = value.replace(",", "")
        return Decimal(cleaned)
    except InvalidOperation:
        console.print(f"[red]錯誤: 無效的{name}金額 '{value}'[/red]")
        raise typer.Exit(1)


def _show_header(
    inputs: ProjectionInput,
    result,
    strategy: str,
    historical_months: int,
) -> None:
    """顯示標題"""
    start = f"{inputs.start_year}/{inputs.start_month:02d}"
    end_year = inputs.start_year + (inputs.start_month + inputs.projection_months - 2) // 12
    end_month = (inputs.start_month + inputs.projection_months - 2) % 12 + 1
    end = f"{end_year}/{end_month:02d}"

    strategy_names = {
        "average": "平均值",
        "median": "中位數",
        "max": "最大值",
        "latest": "最近月份",
    }

    info_lines = [
        "[bold]現金流預測[/bold]",
        "",
        f"📅 預測期間: [cyan]{start}[/cyan] → [cyan]{end}[/cyan] ({inputs.projection_months} 個月)",
        f"💰 初始儲蓄: [cyan]{inputs.initial_savings:,.0f}[/cyan] 元",
    ]

    if inputs.income_override:
        info_lines.append(f"📈 月收入: [cyan]{inputs.income_override:,.0f}[/cyan] 元 (覆寫)")
    elif inputs.income:
        total = inputs.income.total_monthly()
        info_lines.append(f"📈 月收入: [cyan]{total:,.0f}[/cyan] 元 (從 yaml)")

    if inputs.expense_override:
        info_lines.append(f"📉 月支出: [cyan]{inputs.expense_override:,.0f}[/cyan] 元 (覆寫)")
    else:
        info_lines.append(
            f"📉 支出估算: [cyan]{strategy_names[strategy]}[/cyan] "
            f"(參考 {historical_months} 個月)"
        )

    console.print()
    console.print(Panel(
        "\n".join(info_lines),
        title="[bold blue]Life Capital[/bold blue]",
        border_style="blue",
    ))


def _show_input_details(inputs: ProjectionInput, historical: list) -> None:
    """顯示詳細輸入資訊（verbose 模式）"""
    console.print()
    console.print("[bold]輸入參數:[/bold]")

    if historical:
        console.print(f"  歷史資料月數: {len(historical)}")
        estimated = estimate_monthly_expenses(historical, inputs.expense_estimation_strategy)
        console.print(f"  估算月支出: {estimated:,.0f} 元")

    console.print(f"  Input Hash: {inputs.income_override or '(from yaml)'}")
    console.print()


def _show_monthly_table(result) -> None:
    """顯示每月明細表"""
    if not result.monthly_projections:
        return

    table = Table(
        title="[bold]每月預測明細[/bold]",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("年/月", justify="center")
    table.add_column("收入", justify="right")
    table.add_column("常規支出", justify="right")
    table.add_column("一次性", justify="right")
    table.add_column("淨現金流", justify="right")
    table.add_column("累積儲蓄", justify="right")
    table.add_column("狀態", justify="center")

    for mp in result.monthly_projections:
        year_month = f"{mp.year}/{mp.month:02d}"

        # 格式化金額
        income = f"{mp.income:,.0f}"
        regular = f"{mp.regular_expenses:,.0f}"
        one_time = f"{mp.one_time_expenses:,.0f}" if mp.one_time_expenses else "-"
        cashflow = f"{mp.net_cashflow:,.0f}"
        savings = f"{mp.cumulative_savings:,.0f}"

        # 狀態指示
        if mp.cumulative_savings < 0:
            status = "[red]⚠️ 耗盡[/red]"
            savings = f"[red]{savings}[/red]"
        elif mp.is_deficit:
            status = "[yellow]📉 赤字[/yellow]"
            cashflow = f"[yellow]{cashflow}[/yellow]"
        else:
            status = "[green]✓[/green]"

        table.add_row(
            year_month,
            income,
            regular,
            one_time,
            cashflow,
            savings,
            status,
        )

    console.print()
    console.print(table)


def _show_summary(result) -> None:
    """顯示彙總資訊"""
    summary_lines = []

    summary_lines.append(f"[bold]預測期間總收入[/bold]: {result.total_income:,.0f} 元")
    summary_lines.append(f"[bold]預測期間總支出[/bold]: {result.total_expenses:,.0f} 元")
    summary_lines.append("")

    # 最終儲蓄
    final = result.final_cumulative_savings
    if final >= 0:
        summary_lines.append(
            f"[bold green]最終累積儲蓄[/bold green]: [bold]{final:,.0f}[/bold] 元"
        )
    else:
        summary_lines.append(
            f"[bold red]最終累積儲蓄[/bold red]: [bold red]{final:,.0f}[/bold red] 元"
        )

    # 平均現金流
    avg_cf = result.average_monthly_cashflow
    cf_color = "green" if avg_cf >= 0 else "red"
    summary_lines.append(
        f"[bold]平均月現金流[/bold]: [{cf_color}]{avg_cf:,.0f}[/{cf_color}] 元/月"
    )

    console.print()
    console.print(Panel(
        "\n".join(summary_lines),
        title="[bold]預測結果摘要[/bold]",
        border_style="green" if result.final_cumulative_savings >= 0 else "red",
    ))


def _show_warnings(result) -> None:
    """顯示警告資訊"""
    console.print()

    if result.asset_depletion_month:
        year, month = result.asset_depletion_month
        console.print(
            f"[bold red]⚠️ 警告: 資產將於 {year}/{month:02d} 耗盡![/bold red]"
        )

    if result.deficit_months:
        console.print(
            f"[yellow]📉 赤字月份數: {len(result.deficit_months)} 個月[/yellow]"
        )

        if result.first_deficit_month:
            year, month = result.first_deficit_month
            console.print(
                f"[yellow]   首次赤字: {year}/{month:02d}[/yellow]"
            )


def _save_projection(data_dir: Path, result: ProjectionResult) -> None:
    """存檔預測結果到 derived/scenarios/projection_baseline.json

    使用原子寫入策略：temp → flush → fsync → os.replace
    """
    scenarios_dir = data_dir / DERIVED_SCENARIOS_DIR
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    target_path = scenarios_dir / "projection_baseline.json"
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
