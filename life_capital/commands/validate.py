"""validate 指令

驗證資料完整性與正確性。
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from life_capital.io import YAMLParseError, YAMLValidationError, load_model
from life_capital.io.registry import (
    ASSUMPTIONS_FILE,
    INCOME_FILE,
    POLICY_FILE,
    TARGETS_FILE,
)
from life_capital.models import (
    ExpensePolicy,
    LifeAssumptions,
    LifetimeTargets,
    MonthlyIncome,
)
from life_capital.utils.path_resolver import (
    list_expense_files,
    resolve_data_dir,
)
from life_capital.validators.business_rules import validate_expense_categories

console = Console()


def validate(
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
        help="顯示詳細資訊",
    ),
) -> None:
    """驗證 Life Capital 資料完整性

    檢查所有 YAML 檔案的格式與業務邏輯。
    """
    data_dir = resolve_data_dir(path)

    if not data_dir.exists():
        console.print(f"[red]錯誤: 資料目錄不存在: {data_dir}[/red]")
        console.print("[yellow]提示: 執行 lc init 初始化資料目錄[/yellow]")
        raise typer.Exit(1)

    errors: list[str] = []
    warnings: list[str] = []

    # 驗證結果摘要
    assumptions: Optional[LifeAssumptions] = None
    targets: Optional[LifetimeTargets] = None
    policy: Optional[ExpensePolicy] = None

    # 1. 驗證 life_assumptions.yaml
    assumptions_path = data_dir / ASSUMPTIONS_FILE
    if assumptions_path.exists():
        try:
            assumptions = load_model(assumptions_path, LifeAssumptions)
            if verbose:
                console.print(f"[green]✓[/green] {ASSUMPTIONS_FILE}")
        except (YAMLParseError, YAMLValidationError) as e:
            errors.append(str(e))
    else:
        errors.append(f"找不到 {ASSUMPTIONS_FILE}")

    # 2. 驗證 lifetime_targets.yaml
    targets_path = data_dir / TARGETS_FILE
    if targets_path.exists():
        try:
            targets = load_model(targets_path, LifetimeTargets)
            if verbose:
                console.print(f"[green]✓[/green] {TARGETS_FILE}")

            # 跨檔案驗證
            if assumptions:
                target_errors = targets.validate_against_assumptions(
                    base_year=assumptions.metadata.base_year,
                    expected_lifespan=assumptions.get_expected_lifespan(),
                    current_age=assumptions.get_current_age(),
                )
                errors.extend(target_errors)

        except (YAMLParseError, YAMLValidationError) as e:
            errors.append(str(e))
    else:
        errors.append(f"找不到 {TARGETS_FILE}")

    # 3. 驗證 monthly_income.yaml
    income_path = data_dir / INCOME_FILE
    if income_path.exists():
        try:
            load_model(income_path, MonthlyIncome)
            if verbose:
                console.print(f"[green]✓[/green] {INCOME_FILE}")
        except (YAMLParseError, YAMLValidationError) as e:
            errors.append(str(e))
    else:
        warnings.append(f"找不到 {INCOME_FILE}（可選）")

    # 4. 驗證 expense_policy.yaml
    policy_path = data_dir / POLICY_FILE
    if policy_path.exists():
        try:
            policy = load_model(policy_path, ExpensePolicy)
            if verbose:
                console.print(f"[green]✓[/green] {POLICY_FILE}")
        except (YAMLParseError, YAMLValidationError) as e:
            errors.append(str(e))
    else:
        warnings.append(f"找不到 {POLICY_FILE}（可選）")

    # 5. 檢查支出檔案
    expense_files = list_expense_files(path)
    if verbose and expense_files:
        console.print(f"[green]✓[/green] 找到 {len(expense_files)} 個支出檔案")

    # 6. 跨檔案驗證（CSV category ∈ policy）
    if policy and expense_files:
        br = validate_expense_categories(expense_files=expense_files, policy=policy, dedupe="exact")
        errors.extend(br.errors)
        warnings.extend(br.warnings)

    # 輸出結果
    console.print()

    if errors:
        console.print(Panel(
            "\n".join(f"[red]✗[/red] {e}" for e in errors),
            title="[red]驗證失敗[/red]",
            border_style="red",
        ))
        raise typer.Exit(1)

    # 顯示警告
    if warnings:
        for w in warnings:
            console.print(f"[yellow]⚠[/yellow] {w}")
        console.print()

    # 顯示成功摘要
    _show_summary(data_dir, assumptions, targets, policy, expense_files)


def _show_summary(
    data_dir: Path,
    assumptions: Optional[LifeAssumptions],
    targets: Optional[LifetimeTargets],
    policy: Optional[ExpensePolicy],
    expense_files: list[Path],
) -> None:
    """顯示驗證成功摘要"""

    lines = ["[bold green]✅ 驗證通過[/bold green]\n"]

    lines.append(f"📁 data_dir: [cyan]{data_dir}[/cyan]")

    if assumptions:
        lines.append(f"📐 rates.mode: [yellow]{assumptions.rates.mode.value}[/yellow]")
        lines.append(f"📅 base_year: {assumptions.metadata.base_year}")

    if targets:
        if targets.targets:
            years = [t.target_year for t in targets.targets]
            lines.append(
                f"🎯 targets: {len(targets.targets)} 個"
                f"（{min(years)} - {max(years)}）"
            )
        else:
            lines.append("🎯 targets: 0 個")

    if policy:
        categories = policy.get_all_categories()
        lines.append(f"📊 policy: {len(categories)} 類別，總和 100%")

    if expense_files:
        filenames = [f.name for f in expense_files[-3:]]  # 最近 3 個
        if len(expense_files) > 3:
            lines.append(f"📄 expenses: {len(expense_files)} 個檔案")
        else:
            lines.append(f"📄 expenses: {', '.join(filenames)}")

    console.print(Panel(
        "\n".join(lines),
        border_style="green",
    ))
