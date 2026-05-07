"""Advisor CLI 指令

Phase 5 AI 顧問系統的命令行介面。

指令:
- lc advisor suggest <query>: 生成決策建議
- lc advisor context: 顯示決策上下文
- lc advisor templates: 列出可用模板
- lc advisor history: 查看決策歷史（Stage 3）
- lc advisor explain <id>: 解釋決策（Stage 3）
- lc advisor wiki: 生成 Decision Wiki（Stage 3）
"""

import json
from pathlib import Path
from typing import Annotated, Any, Dict, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

# 建立子應用
app = typer.Typer(
    name="advisor",
    help="AI 決策顧問系統",
    no_args_is_help=True,
)

console = Console()


# === 模板對應表（查詢關鍵字 → 模板 ID）===
QUERY_TEMPLATE_MAP: Dict[str, str] = {
    # 買房相關
    "買房": "buying_house",
    "購房": "buying_house",
    "買屋": "buying_house",
    "買樓": "buying_house",
    "house": "buying_house",
    "home": "buying_house",
    # 投資相關
    "投資": "investment",
    "理財": "investment",
    "invest": "investment",
    # 購車相關
    "買車": "car_purchase",
    "購車": "car_purchase",
    "car": "car_purchase",
    # 旅行相關
    "旅行": "travel",
    "旅遊": "travel",
    "出遊": "travel",
    "travel": "travel",
    # 儲蓄目標
    "儲蓄": "savings_target",
    "存錢": "savings_target",
    "savings": "savings_target",
}


def _detect_template(query: str) -> str:
    """根據查詢自動偵測模板

    Args:
        query: 使用者查詢字串

    Returns:
        模板 ID
    """
    query_lower = query.lower()
    for keyword, template_id in QUERY_TEMPLATE_MAP.items():
        if keyword in query_lower:
            return template_id
    return "default"


def _format_option_rich(
    option: Any,
    is_comparable: bool,
    label: str,
) -> Panel:
    """格式化選項為 Rich Panel

    Args:
        option: DecisionOptionSchema
        is_comparable: 是否可比較
        label: 選項標籤（A 或 B）

    Returns:
        Rich Panel
    """
    direction_emoji = "🛡️" if option.direction == "conservative" else "🚀"
    status_color = "green" if option.status == "comparable" else "yellow"

    content_lines = [
        f"[bold]{direction_emoji} {option.label}[/bold]",
        "",
    ]

    if is_comparable and option.recommendation:
        content_lines.append(f"[{status_color}]建議：[/{status_color}]")
        content_lines.append(f"  {option.recommendation}")
        if option.score is not None:
            score_pct = int(option.score * 100)
            content_lines.append(f"\n[dim]適合度：{score_pct}%[/dim]")
    elif option.to_comparable_guidance:
        content_lines.append("[yellow]補件指引：[/yellow]")
        content_lines.append(f"  {option.to_comparable_guidance}")

    return Panel(
        "\n".join(content_lines),
        title=f"方案 {label}",
        border_style=status_color,
    )


def _format_payload_json(payload: Any) -> str:
    """格式化 Payload 為 JSON

    Args:
        payload: AdvisorProposalPayload

    Returns:
        JSON 字串
    """
    return json.dumps(payload.to_dict(), ensure_ascii=False, indent=2)


def _format_payload_markdown(payload: Any) -> str:
    """格式化 Payload 為 Markdown

    Args:
        payload: AdvisorProposalPayload

    Returns:
        Markdown 字串
    """
    lines = [
        "# 決策建議報告",
        "",
        f"**模板**: {payload.template_id}",
        f"**可比較性**: {'✅ 可比較' if payload.is_comparable else '⚠️ 不可比較'}",
        f"**可比較性分數**: {payload.comparability_score:.2f}",
        "",
        "## 方案比較",
        "",
    ]

    # 方案 A
    opt_a = payload.option_a
    lines.append(f"### 方案 A：{opt_a.label}")
    if opt_a.recommendation:
        lines.append(f"- **建議**: {opt_a.recommendation}")
    if opt_a.score is not None:
        lines.append(f"- **適合度**: {int(opt_a.score * 100)}%")
    if opt_a.to_comparable_guidance:
        lines.append(f"- **補件指引**: {opt_a.to_comparable_guidance}")
    lines.append("")

    # 方案 B
    opt_b = payload.option_b
    lines.append(f"### 方案 B：{opt_b.label}")
    if opt_b.recommendation:
        lines.append(f"- **建議**: {opt_b.recommendation}")
    if opt_b.score is not None:
        lines.append(f"- **適合度**: {int(opt_b.score * 100)}%")
    if opt_b.to_comparable_guidance:
        lines.append(f"- **補件指引**: {opt_b.to_comparable_guidance}")
    lines.append("")

    # 風險
    if payload.risk_tags:
        lines.append("## 風險提示")
        lines.append("")
        lines.append(f"**風險標籤**: {', '.join(payload.risk_tags)}")
        lines.append(f"**說明**: {payload.risk_explanation}")
        lines.append("")

    # 元資料
    lines.append("---")
    lines.append(f"*Operation ID: {payload.operation_id}*")
    lines.append(f"*生成時間: {payload.created_at}*")

    return "\n".join(lines)


@app.command()
def suggest(
    query: Annotated[str, typer.Argument(help="決策查詢（如：買房、投資）")],
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            "-p",
            help="資料目錄路徑",
        ),
    ] = Path.home() / ".life-capital",
    template: Annotated[
        Optional[str],
        typer.Option(
            "--template",
            "-t",
            help="指定決策模板 ID",
        ),
    ] = None,
    redacted: Annotated[
        bool,
        typer.Option(
            "--redacted",
            help="顯示去識別化的決策上下文",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="預覽模式，不產生 proposal",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="跳過確認提示（危險操作需額外確認）",
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="輸出格式：rich, json, markdown",
        ),
    ] = "rich",
) -> None:
    """生成決策建議

    根據查詢內容與財務狀況，生成「2 個可比較方案 + 風險說明」。

    範例:
        lc advisor suggest "買房"
        lc advisor suggest "投資" --template investment --dry-run
        lc advisor suggest "買車" --redacted --format json
    """
    from life_capital.advisor.context_builder import ContextBuilder
    from life_capital.advisor.proposal_generator import ProposalGenerator

    # 自動偵測模板
    template_id = template or _detect_template(query)

    console.print(f"[cyan]查詢：{query}[/cyan]")
    console.print(f"[dim]使用模板：{template_id}[/dim]\n")

    # 檢查資料路徑
    if not path.exists():
        console.print(
            f"[red]錯誤：資料目錄不存在：{path}[/red]\n"
            f"[yellow]請先執行 `lc init` 初始化資料目錄[/yellow]"
        )
        raise typer.Exit(1)

    try:
        # 建構上下文
        builder = ContextBuilder.from_path(path)
        redacted_context = builder.build()

        # 顯示去識別化上下文（如果要求）
        if redacted:
            console.print(Panel(
                f"風險等級：{redacted_context.get_risk_level()}\n"
                f"連續赤字月數：{redacted_context.consecutive_deficit_months}\n"
                f"收入波動度：{redacted_context.income_volatility}\n"
                f"儲蓄率區間：{redacted_context.savings_rate_band}\n"
                f"支出趨勢：{redacted_context.expense_trend}\n"
                f"跑道月數：{redacted_context.runway_months or '> 120'}",
                title="去識別化決策上下文",
                border_style="blue",
            ))
            console.print()

        # 生成提案
        generator = ProposalGenerator()
        payload = generator.generate_from_context(
            redacted_context=redacted_context,
            template_id=template_id,
        )

        # 輸出結果
        if output_format == "json":
            console.print(_format_payload_json(payload))
        elif output_format == "markdown":
            md_content = _format_payload_markdown(payload)
            console.print(Markdown(md_content))
        else:
            # Rich 格式
            # 可比較性狀態
            status_text = "✅ 可比較" if payload.is_comparable else "⚠️ 不可比較"
            status_color = "green" if payload.is_comparable else "yellow"

            console.print(Panel(
                f"[{status_color}]{status_text}[/{status_color}]  "
                f"[dim]（分數：{payload.comparability_score:.2f}）[/dim]",
                title="決策建議",
                border_style=status_color,
            ))

            # 選項比較
            console.print()
            console.print(_format_option_rich(payload.option_a, payload.is_comparable, "A"))
            console.print(_format_option_rich(payload.option_b, payload.is_comparable, "B"))

            # 風險提示
            if payload.risk_tags:
                console.print()
                console.print(Panel(
                    f"[yellow]風險標籤：[/yellow]{', '.join(payload.risk_tags)}\n\n"
                    f"{payload.risk_explanation}",
                    title="風險提示",
                    border_style="yellow",
                ))

            # 不可比較時的補件指引
            if not payload.is_comparable and payload.blocking_details:
                console.print()
                blocking_lines = []
                for detail in payload.blocking_details:
                    severity_icon = "🚫" if detail.severity == "blocking" else "⚠️"
                    blocking_lines.append(f"{severity_icon} {detail.message}")
                console.print(Panel(
                    "\n".join(blocking_lines),
                    title="阻擋原因",
                    border_style="red",
                ))

        # Dry-run 提示
        if dry_run:
            console.print("\n[yellow]Dry-run 模式：未產生 proposal 檔案[/yellow]")
        else:
            console.print(f"\n[dim]Operation ID: {payload.operation_id}[/dim]")

    except FileNotFoundError as e:
        console.print(f"[red]錯誤：找不到必要檔案：{e}[/red]")
        console.print("[yellow]提示：請確認已有支出記錄（執行 `lc import` 匯入資料）[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]錯誤：{e}[/red]")
        raise typer.Exit(1)


@app.command()
def context(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            "-p",
            help="資料目錄路徑",
        ),
    ] = Path.home() / ".life-capital",
    redacted: Annotated[
        bool,
        typer.Option(
            "--redacted",
            help="顯示去識別化版本",
        ),
    ] = True,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="輸出格式：rich, json, markdown",
        ),
    ] = "rich",
) -> None:
    """顯示決策上下文

    輸出去識別化的財務狀況摘要，用於決策分析。

    範例:
        lc advisor context --redacted
        lc advisor context --format json
    """
    from life_capital.advisor.context_builder import ContextBuilder

    # 檢查資料路徑
    if not path.exists():
        console.print(
            f"[red]錯誤：資料目錄不存在：{path}[/red]\n"
            f"[yellow]請先執行 `lc init` 初始化資料目錄[/yellow]"
        )
        raise typer.Exit(1)

    try:
        builder = ContextBuilder.from_path(path)

        if redacted:
            # 取得去識別化上下文
            ctx = builder.build()
            view = builder.build_with_view()

            if output_format == "json":
                data = {
                    "risk_level": ctx.get_risk_level(),
                    "expense_distribution": ctx.expense_distribution,
                    "deficit_month_count": ctx.deficit_month_count,
                    "runway_months": ctx.runway_months,
                    "consecutive_deficit_months": ctx.consecutive_deficit_months,
                    "income_volatility": ctx.income_volatility,
                    "savings_rate_band": ctx.savings_rate_band,
                    "expense_trend": ctx.expense_trend,
                    "field_provenance": ctx.field_provenance,
                }
                console.print(json.dumps(data, ensure_ascii=False, indent=2))

            elif output_format == "markdown":
                lines = [
                    "# 決策上下文",
                    "",
                    "## 摘要",
                    f"{view.summary_text}",
                    "",
                    "## 風險說明",
                    f"{view.risk_explanation}",
                    "",
                    "## 比較說明",
                    f"{view.comparison_narrative}",
                    "",
                    "## 詳細指標",
                    f"- 風險等級：{ctx.get_risk_level()}",
                    f"- 連續赤字月數：{ctx.consecutive_deficit_months}",
                    f"- 收入波動度：{ctx.income_volatility}",
                    f"- 儲蓄率區間：{ctx.savings_rate_band}",
                    f"- 支出趨勢：{ctx.expense_trend}",
                    f"- 跑道月數：{ctx.runway_months or '> 120'}",
                ]
                console.print(Markdown("\n".join(lines)))

            else:
                # Rich 格式
                console.print(Panel(
                    f"[bold]{view.summary_text}[/bold]",
                    title="財務狀況摘要",
                    border_style="cyan",
                ))

                console.print(Panel(
                    view.risk_explanation,
                    title="風險說明",
                    border_style="yellow",
                ))

                # 詳細指標表格
                table = Table(title="詳細指標", show_header=True)
                table.add_column("指標", style="cyan")
                table.add_column("值", style="green")
                table.add_column("來源", style="dim")

                table.add_row(
                    "風險等級",
                    ctx.get_risk_level(),
                    ctx.field_provenance.get("risk_level", "-"),
                )
                table.add_row(
                    "連續赤字月數",
                    str(ctx.consecutive_deficit_months),
                    ctx.field_provenance.get("consecutive_deficit_months", "-"),
                )
                table.add_row(
                    "收入波動度",
                    ctx.income_volatility,
                    ctx.field_provenance.get("income_volatility", "-"),
                )
                table.add_row(
                    "儲蓄率區間",
                    ctx.savings_rate_band,
                    ctx.field_provenance.get("savings_rate_band", "-"),
                )
                table.add_row(
                    "支出趨勢",
                    ctx.expense_trend,
                    ctx.field_provenance.get("expense_trend", "-"),
                )
                table.add_row(
                    "跑道月數",
                    str(ctx.runway_months) if ctx.runway_months else "> 120",
                    ctx.field_provenance.get("runway_months", "-"),
                )

                console.print()
                console.print(table)

                # 支出分佈
                if ctx.expense_distribution:
                    console.print()
                    dist_table = Table(title="支出分佈", show_header=True)
                    dist_table.add_column("類別", style="cyan")
                    dist_table.add_column("比例", style="green")

                    sorted_dist = sorted(
                        ctx.expense_distribution.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )
                    for cat, pct in sorted_dist:
                        dist_table.add_row(cat, f"{pct:.1%}")

                    console.print(dist_table)

                console.print(Panel(
                    view.comparison_narrative,
                    title="比較說明",
                    border_style="blue",
                ))

        else:
            console.print("[yellow]非去識別化輸出不支援（隱私保護）[/yellow]")

    except FileNotFoundError as e:
        console.print(f"[red]錯誤：找不到必要檔案：{e}[/red]")
        console.print("[yellow]提示：請確認已有支出記錄（執行 `lc import` 匯入資料）[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]錯誤：{e}[/red]")
        raise typer.Exit(1)


@app.command()
def templates(
    category: Annotated[
        Optional[str],
        typer.Option(
            "--category",
            "-c",
            help="篩選分類",
        ),
    ] = None,
) -> None:
    """列出可用的決策模板

    顯示所有已註冊的決策模板及其說明。

    範例:
        lc advisor templates
        lc advisor templates --category major_purchase
    """
    from life_capital.advisor.templates import get_all_templates

    all_templates = get_all_templates()

    if category:
        all_templates = [t for t in all_templates if t.category == category]

    table = Table(title="決策模板", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("名稱", style="green")
    table.add_column("分類", style="yellow")
    table.add_column("說明")

    for template in all_templates:
        table.add_row(
            template.id,
            template.name,
            template.category,
            template.description,
        )

    console.print(table)
    console.print(f"\n[dim]共 {len(all_templates)} 個模板[/dim]")


@app.command()
def history(
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            "-p",
            help="資料目錄路徑",
        ),
    ] = Path.home() / ".life-capital",
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="顯示筆數",
        ),
    ] = 10,
) -> None:
    """查看決策歷史

    顯示過去的決策建議記錄。

    範例:
        lc advisor history
        lc advisor history --limit 20
    """
    console.print(
        Panel(
            f"[bold cyan]Decision History[/bold cyan]\n\n"
            f"資料路徑: {path}\n"
            f"顯示筆數: {limit}\n\n"
            f"[yellow]此功能將在 Stage 3 實作完成[/yellow]",
            title="Decision History",
            border_style="cyan",
        )
    )


@app.command()
def explain(
    decision_id: Annotated[str, typer.Argument(help="決策 ID")],
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            "-p",
            help="資料目錄路徑",
        ),
    ] = Path.home() / ".life-capital",
) -> None:
    """解釋特定決策

    顯示決策的詳細假設與計算過程。

    範例:
        lc advisor explain dec_01HXYZ...
    """
    console.print(
        Panel(
            f"[bold cyan]Decision Explanation[/bold cyan]\n\n"
            f"決策 ID: {decision_id}\n"
            f"資料路徑: {path}\n\n"
            f"[yellow]此功能將在 Stage 3 實作完成[/yellow]",
            title="Decision Explanation",
            border_style="cyan",
        )
    )


@app.command()
def wiki(
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="資料目錄路徑"),
    ] = Path.home() / ".life-capital",
    rebuild: Annotated[
        bool,
        typer.Option("--rebuild", help="強制重建 Wiki"),
    ] = False,
) -> None:
    """生成 Decision Wiki

    將決策記憶編譯成 Markdown Wiki。

    範例:
        lc advisor wiki
        lc advisor wiki --rebuild
    """
    from life_capital.generation.decision_wiki import save_wiki
    from life_capital.io.decisions_handler import DecisionsHandler

    # 檢查資料路徑
    if not path.exists():
        console.print(
            f"[red]錯誤：資料目錄不存在：{path}[/red]\n"
            f"[yellow]請先執行 `lc init` 初始化資料目錄[/yellow]"
        )
        raise typer.Exit(1)

    try:
        # 讀取決策記錄
        handler = DecisionsHandler(path)
        decisions = handler.read_all()

        if not decisions:
            console.print(
                "[yellow]⚠️  尚無決策記錄[/yellow]\n"
                "[dim]提示：使用 `lc advisor suggest` 生成決策建議[/dim]"
            )
            raise typer.Exit(0)

        # 生成並儲存 Wiki
        console.print("[cyan]正在生成 Decision Wiki...[/cyan]")
        wiki_path = save_wiki(decisions, path)

        console.print(f"[green]✅ Wiki 已生成：{wiki_path}[/green]")
        console.print(f"[dim]共 {len(decisions)} 個決策記錄[/dim]")

        # 顯示 Wiki 路徑
        meta_path = wiki_path.with_suffix(".md.meta.json")
        if meta_path.exists():
            console.print(f"[dim]Provenance: {meta_path}[/dim]")

    except FileNotFoundError as e:
        console.print(f"[red]錯誤：找不到必要檔案：{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]錯誤：{e}[/red]")
        raise typer.Exit(1)
