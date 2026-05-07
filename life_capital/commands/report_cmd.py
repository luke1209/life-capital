"""report 指令

從 Phase 2 計算結果生成財務報表。
"""

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from life_capital.generation import (
    InputMissingError,
    ReportGenerator,
    load_comparison_from_derived,
    load_projection_from_derived,
)
from life_capital.io.registry import CLI_TYPE_MAPPING
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def report(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    report_type: str = typer.Option(
        "all",
        "--type",
        "-t",
        help="報表類型（all/monthly/projection/comparison）",
    ),
    format: str = typer.Option(
        "md",
        "--format",
        "-f",
        help="輸出格式（md/json）",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        "-s",
        help="存檔到 derived/reports/",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="顯示 provenance 資訊",
    ),
) -> None:
    """生成財務報表

    從 Phase 2 計算結果生成可讀報表。

    範例：
        lc report                      # 所有報表到 stdout
        lc report --type monthly       # 只生成月度摘要
        lc report --format json --save # JSON 格式存檔
    """
    data_dir = resolve_data_dir(path)

    # 驗證參數
    if report_type not in CLI_TYPE_MAPPING:
        console.print(f"[red]✗[/red] 無效的報表類型: {report_type}")
        console.print(f"[yellow]可用類型:[/yellow] {', '.join(CLI_TYPE_MAPPING.keys())}")
        raise typer.Exit(1)

    if format not in ("md", "json"):
        console.print(f"[red]✗[/red] 無效的格式: {format}")
        console.print("[yellow]可用格式:[/yellow] md, json")
        raise typer.Exit(1)

    # V4.1.1: 非 --save 時限制單一格式（多格式須配合 --save）
    if not save and "," in format:
        console.print("[red]✗[/red] 非 --save 模式只允許單一格式")
        console.print("[yellow]提示:[/yellow] 使用 --save 可同時輸出多種格式")
        raise typer.Exit(1)

    try:
        # 載入 Phase 2 輸入（Contract 2: 唯一入口）
        projection = load_projection_from_derived(data_dir)
        comparison = load_comparison_from_derived(data_dir)

        # 建立報表生成器
        generator = ReportGenerator(data_dir)

        # 使用 CLI_TYPE_MAPPING 轉換（V4.1.1）
        target_types = CLI_TYPE_MAPPING[report_type]

        # 生成報表
        reports = []
        for target in target_types:
            if target == "monthly_summary":
                reports.append(generator.generate_monthly_summary(projection, format))
            elif target == "projection_table":
                reports.append(generator.generate_projection_table(projection, format))
            elif target == "scenario_comparison":
                if comparison:
                    reports.append(generator.generate_scenario_comparison(comparison, format))
                else:
                    console.print(
                        "[yellow]⏭️[/yellow] 跳過 scenario_comparison（缺少 comparison 資料）"
                    )
                    console.print(
                        "[yellow]提示:[/yellow] 執行 'lc scenario --preset all --save' 生成比較資料"
                    )
            else:
                console.print(f"[red]✗[/red] 未知報表類型: {target}")
                raise typer.Exit(1)

        # 存檔或輸出
        if save:
            for report in reports:
                # 使用 _save_report 方法存檔
                target_path = generator._save_report(report)
                console.print(f"[green]✓[/green] 已存檔: {target_path.name}")

                # Verbose 模式顯示 provenance
                if verbose:
                    provenance_path = target_path.with_suffix(
                        target_path.suffix + ".meta.json"
                    )
                    console.print(
                        Panel(
                            f"[cyan]Report Type:[/cyan] {report.provenance.report_type}\n"
                            f"[cyan]Input Hash:[/cyan] {report.provenance.input_hash}\n"
                            f"[cyan]Generated At:[/cyan] {report.provenance.generated_at}\n"
                            f"[cyan]Provenance:[/cyan] {provenance_path.name}",
                            title="Provenance",
                            border_style="cyan",
                        )
                    )
        else:
            # 輸出到 stdout
            for i, report in enumerate(reports):
                if i > 0:
                    # V4.1.1: 報表邊界分隔符
                    console.print(
                        f"\n<!-- LC_REPORT_BOUNDARY: {report.report_type} -->\n"
                    )

                console.print(report.content)

                # Verbose 模式顯示 provenance
                if verbose:
                    console.print(
                        Panel(
                            f"[cyan]Report Type:[/cyan] {report.provenance.report_type}\n"
                            f"[cyan]Input Hash:[/cyan] {report.provenance.input_hash}\n"
                            f"[cyan]Generated At:[/cyan] {report.provenance.generated_at}",
                            title="Provenance",
                            border_style="cyan",
                        )
                    )

            # V4.1.1: 結束標記
            console.print("\n<!-- LC_REPORT_END -->")

        # 成功訊息
        if save:
            console.print(
                Panel(
                    f"[green]✓[/green] 成功生成 {len(reports)} 個報表",
                    title="完成",
                    border_style="green",
                )
            )
        else:
            # stdout 模式不顯示額外訊息（避免干擾輸出）
            pass

    except InputMissingError as e:
        console.print(f"[red]✗[/red] {e}")
        console.print(
            "[yellow]提示:[/yellow] 執行 'lc project --save' 生成預測資料"
        )
        raise typer.Exit(2)

    except Exception as e:
        console.print(f"[red]✗[/red] 錯誤: {e}")
        if verbose:
            import traceback

            console.print(traceback.format_exc())
        raise typer.Exit(1)
