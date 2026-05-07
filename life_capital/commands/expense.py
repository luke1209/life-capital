"""expense 指令

支出占比檢查：讀取 expenses_YYYY_MM.csv，去重後統計並與 expense_policy.yaml 比對。
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from life_capital.calculators.budget import BudgetCheckResult, check_budget
from life_capital.calculators.rounding import RoundingConfig
from life_capital.io import YAMLParseError, YAMLValidationError, load_model
from life_capital.io.csv_handler import CSVParseError, DedupeMode, load_monthly_expenses
from life_capital.io.registry import INCOME_FILE, POLICY_FILE
from life_capital.models import ExpensePolicy, LifeAssumptions, MonthlyIncome
from life_capital.utils.path_resolver import (
    assumptions_file,
    expenses_file,
    list_expense_files,
    policy_file,
    resolve_data_dir,
)

console = Console()
app = typer.Typer(help="支出分析")


def _parse_yyyy_mm(value: str) -> tuple[int, int]:
    if not re.match(r"^\d{4}-\d{2}$", value):
        raise ValueError("月份格式必須為 YYYY-MM（例如 2024-12）")
    year_s, month_s = value.split("-")
    year = int(year_s)
    month = int(month_s)
    if month < 1 or month > 12:
        raise ValueError("月份必須在 01-12 之間")
    return year, month


def _list_available_months(path: Optional[str]) -> List[str]:
    files = list_expense_files(path)
    months: List[str] = []
    for f in files:
        m = re.match(r"expenses_(\d{4})_(\d{2})\.csv$", f.name)
        if m:
            months.append(f"{m.group(1)}-{m.group(2)}")
    return sorted(set(months))


@app.command("check")
def check_cmd(
    yyyy_mm: Optional[str] = typer.Argument(
        None,
        help="指定月份（YYYY-MM），不填則使用本機「本月」",
    ),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    dedupe: DedupeMode = typer.Option(
        "exact",
        "--dedupe",
        help="CSV 去重模式（預設 exact）",
    ),
) -> None:
    data_dir = resolve_data_dir(path)

    if yyyy_mm is None:
        today = date.today()
        year, month = today.year, today.month
    else:
        try:
            year, month = _parse_yyyy_mm(yyyy_mm)
        except ValueError as e:
            console.print(f"[red]錯誤: {e}[/red]")
            raise typer.Exit(1)

    csv_path = expenses_file(year, month, path)
    if not csv_path.exists():
        expected = csv_path.name
        available = _list_available_months(path)
        lines = [
            f"[red]找不到支出檔案[/red]: {expected}",
            f"資料目錄: [cyan]{data_dir}[/cyan]",
        ]
        if available:
            lines.append("")
            lines.append("已存在月份：")
            lines.extend([f"- {m}" for m in available])
        console.print(
            Panel(
                "\n".join(lines),
                border_style="red",
                title="[bold]expense check[/bold]",
            )
        )
        raise typer.Exit(1)

    try:
        monthly_expenses, duplicates = load_monthly_expenses(
            csv_path, year=year, month=month, dedupe=dedupe
        )
    except (FileNotFoundError, CSVParseError) as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    # 讀取 assumptions（用於 rounding 與顯示）
    rounding_config = RoundingConfig.default()
    assumptions_path = assumptions_file(path)
    if assumptions_path.exists():
        try:
            assumptions = load_model(assumptions_path, LifeAssumptions)
            rounding_config = RoundingConfig.from_calculation(assumptions.calculation)
        except (YAMLParseError, YAMLValidationError):
            assumptions = None
    else:
        assumptions = None

    # 讀取 policy（必須）
    try:
        policy = load_model(policy_file(path), ExpensePolicy)
    except (YAMLParseError, YAMLValidationError) as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    # ratio_base=income 時需要 income 檔
    income: MonthlyIncome | None = None
    if policy.metadata.ratio_base.value == "income":
        income_path = data_dir / INCOME_FILE
        if not income_path.exists():
            console.print(
                f"[red]錯誤: {POLICY_FILE} 設定 ratio_base=income，"
                f"但找不到 {INCOME_FILE}[/red]"
            )
            raise typer.Exit(1)
        try:
            income = load_model(income_path, MonthlyIncome)
        except (YAMLParseError, YAMLValidationError) as e:
            console.print(f"[red]錯誤: {e}[/red]")
            raise typer.Exit(1)

    try:
        result = check_budget(expenses=monthly_expenses, policy=policy, income=income)
    except ValueError as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    _render_budget_result(
        yyyy_mm=f"{year:04d}-{month:02d}",
        result=result,
        rounding_config=rounding_config,
        duplicates=duplicates,
    )


def _fmt_amount(rounding_config: RoundingConfig, value: Decimal) -> str:
    return f"{rounding_config.quantize(value):,.0f}"


def _fmt_pct(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{(value * Decimal('100')):.1f}%"


def _render_budget_result(
    *,
    yyyy_mm: str,
    result: BudgetCheckResult,
    rounding_config: RoundingConfig,
    duplicates: int,
) -> None:
    console.print()
    console.print(Panel(f"[bold]支出占比檢查[/bold]\n{yyyy_mm}", border_style="blue"))

    header_lines = [
        f"ratio_base: [yellow]{result.base.value}[/yellow]",
        f"base_amount: {_fmt_amount(rounding_config, result.base_amount)}",
        f"total_expenses: {_fmt_amount(rounding_config, result.total_expenses)}",
    ]
    if duplicates > 0:
        header_lines.append(f"dedupe: 忽略 {duplicates} 筆重複")
    console.print(Panel("\n".join(header_lines), border_style="dim"))

    table = Table(title="[bold]類別明細[/bold]")
    table.add_column("category")
    table.add_column("group", style="dim")
    table.add_column("amount", justify="right")
    table.add_column("actual", justify="right")
    table.add_column("target", justify="right")
    table.add_column("delta", justify="right")
    table.add_column("status")

    for row in result.categories:
        amount = _fmt_amount(rounding_config, row.amount)
        actual = _fmt_pct(row.actual_ratio)
        target = _fmt_pct(row.target_ratio)
        delta = _fmt_pct(row.delta_ratio)

        status_style = {
            "ok": "green",
            "over": "red",
            "under": "yellow",
            "unknown": "dim",
        }.get(row.status, "dim")

        table.add_row(
            row.category,
            row.group or "-",
            amount,
            actual,
            target,
            delta,
            f"[{status_style}]{row.status}[/{status_style}]",
        )

    console.print(table)
