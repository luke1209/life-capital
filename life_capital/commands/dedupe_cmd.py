"""dedupe 指令 (Phase 1.5)

掃描 raw/imports/ 中的 CSV 檔案，建立 proposals。

使用方式：
    lc dedupe [--path PATH]                    # 掃描並顯示待處理記錄
    lc dedupe --write-proposals [--path PATH]  # 建立 proposals 到 proposals/pending/
    lc dedupe --resolve [--path PATH]          # 互動式裁決（未來功能）
"""

import csv
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from life_capital.io.csv_handler import normalize_payer, normalize_text, parse_amount, parse_date
from life_capital.io.dedupe import (
    DedupeDecision,
    DedupeResult,
    summarize_dedupe_results,
)
from life_capital.io.proposals_handler import (
    count_pending_proposals,
    create_expense_proposals,
)
from life_capital.io.registry import RAW_IMPORTS_DIR
from life_capital.models.expense import ExpenseRecord
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def dedupe(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    write_proposals: bool = typer.Option(
        False,
        "--write-proposals",
        "-w",
        help="將記錄寫入 proposals/pending/（待 lc apply 確認）",
    ),
    resolve: bool = typer.Option(
        False,
        "--resolve",
        "-r",
        help="互動式裁決模式（未來功能）",
    ),
    auto: bool = typer.Option(
        False,
        "--auto",
        "-a",
        help="自動處理高相似度項目（需 --yes 確認）",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="跳過確認提示（與 --auto 搭配使用）",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="顯示詳細資訊",
    ),
) -> None:
    """掃描 raw/imports/ 並建立 proposals

    從 raw/imports/ 中的 CSV 檔案讀取支出記錄，
    按月份分組後建立 proposals，等待 lc apply 確認。

    Examples:
        lc dedupe                    # 掃描並顯示待處理記錄
        lc dedupe --write-proposals  # 建立 proposals
        lc dedupe -w -v              # 建立 proposals 並顯示詳細資訊
    """
    data_dir = resolve_data_dir(path)

    if not data_dir.exists():
        console.print(f"[red]錯誤: 資料目錄不存在: {data_dir}[/red]")
        console.print("[yellow]提示: 執行 lc init 初始化資料目錄[/yellow]")
        raise typer.Exit(1)

    # 護欄：--auto 需要 --yes 確認
    if auto and not yes:
        console.print(
            Panel(
                "[yellow]⚠️  --auto 模式會自動合併高相似度記錄[/yellow]\n\n"
                "這是高風險操作，可能影響資料完整性。\n"
                "請使用 --yes 確認執行，或使用 --resolve 進行互動式裁決。",
                title="確認提示",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    # 顯示操作資訊
    mode_desc = "建立 proposals" if write_proposals else "僅掃描"
    console.print(
        Panel(
            f"📁 資料目錄: {data_dir}\n"
            f"📊 操作模式: {mode_desc}\n"
            f"📂 來源目錄: {RAW_IMPORTS_DIR}",
            title="去重掃描",
            border_style="blue",
        )
    )

    # 掃描 raw/imports/ 目錄
    imports_dir = data_dir / RAW_IMPORTS_DIR
    if not imports_dir.exists():
        console.print(f"[yellow]{RAW_IMPORTS_DIR} 目錄不存在[/yellow]")
        console.print("[yellow]提示: 使用 lc import 匯入 CSV 檔案[/yellow]")
        raise typer.Exit(0)

    # 列出所有 CSV 檔案
    csv_files = list(imports_dir.glob("*.csv"))
    if not csv_files:
        console.print(f"[yellow]{RAW_IMPORTS_DIR} 中沒有 CSV 檔案[/yellow]")
        console.print("[yellow]提示: 使用 lc import 匯入 CSV 檔案[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[dim]找到 {len(csv_files)} 個 CSV 檔案...[/dim]\n")

    # 讀取所有 CSV 檔案中的記錄
    all_records: list[ExpenseRecord] = []
    source_files: list[Path] = []

    for csv_file in sorted(csv_files):
        try:
            records = _load_raw_csv(csv_file)
            if records:
                all_records.extend(records)
                source_files.append(csv_file)
                if verbose:
                    console.print(f"  [green]✓[/green] {csv_file.name}: {len(records)} 筆記錄")
        except Exception as e:
            console.print(f"  [yellow]⚠[/yellow] {csv_file.name}: {e}")

    if not all_records:
        console.print("[yellow]沒有找到有效記錄[/yellow]")
        raise typer.Exit(0)

    # 顯示摘要
    _display_records_summary(all_records, verbose)

    # 檢查是否已有 pending proposals
    pending_count = count_pending_proposals(data_dir)
    if pending_count > 0:
        console.print(
            f"\n[yellow]⚠️  已有 {pending_count} 個待確認的 proposals[/yellow]"
        )
        console.print("[dim]使用 lc apply --confirm 套用現有 proposals[/dim]")

    # 若指定 --write-proposals，建立 proposals
    if write_proposals:
        console.print("\n[cyan]正在建立 proposals...[/cyan]")

        try:
            # 使用第一個 CSV 檔案作為來源標記（實際會按月份分組）
            source_desc = (
                csv_files[0] if len(csv_files) == 1 else Path(f"{len(csv_files)}_csv_files")
            )

            proposal_files = create_expense_proposals(
                records=all_records,
                source_file=source_desc,
                actor="cli:dedupe",
                base_dir=data_dir,
            )

            if proposal_files:
                console.print(
                    Panel(
                        f"[green]✓ 成功建立 {len(proposal_files)} 個 proposals[/green]\n\n"
                        f"📂 位置: proposals/pending/\n"
                        f"📝 記錄數: {len(all_records)} 筆\n\n"
                        f"[bold]下一步：[/bold]\n"
                        f"  執行 [cyan]lc apply --confirm[/cyan] 套用變更",
                        title="Proposals 建立完成",
                        border_style="green",
                    )
                )

                if verbose:
                    console.print("\n[dim]建立的 proposals:[/dim]")
                    for pf in proposal_files:
                        console.print(f"  • {pf.name}")
            else:
                console.print("[yellow]沒有建立任何 proposals[/yellow]")

        except Exception as e:
            console.print(f"[red]建立 proposals 失敗: {e}[/red]")
            raise typer.Exit(1)
    else:
        # 僅掃描模式
        console.print(
            Panel(
                f"[green]✓ 掃描完成[/green]\n\n"
                f"找到 {len(all_records)} 筆記錄，來自 {len(source_files)} 個檔案。\n\n"
                f"[bold]下一步：[/bold]\n"
                f"  執行 [cyan]lc dedupe --write-proposals[/cyan] 建立 proposals",
                title="結果",
                border_style="green",
            )
        )


def _load_raw_csv(csv_path: Path) -> list[ExpenseRecord]:
    """從 raw/imports/ 的 CSV 檔案載入記錄

    處理帶有 Provenance 註解的 CSV 格式。

    Args:
        csv_path: CSV 檔案路徑

    Returns:
        ExpenseRecord 列表
    """
    records: list[ExpenseRecord] = []

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        # 跳過 Provenance 註解行
        first_line = f.readline()
        if not first_line.startswith("# Provenance:"):
            # 不是 Provenance 註解，重置檔案指標
            f.seek(0)

        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []

        for row in reader:
            try:
                record = ExpenseRecord(
                    date=parse_date(row["date"]),
                    amount=parse_amount(row["amount"]),
                    category=normalize_text(row["category"]),
                    payer=normalize_payer(row.get("payer", "")),
                    note=normalize_text(row.get("note", "")) or None,
                    merchant=normalize_text(row.get("merchant", "")) or None,
                )
                records.append(record)
            except Exception:
                # 跳過無法解析的行
                continue

    return records


def _display_records_summary(records: list[ExpenseRecord], verbose: bool) -> None:
    """顯示記錄摘要

    Args:
        records: ExpenseRecord 列表
        verbose: 是否顯示詳細資訊
    """
    # 按月份分組統計
    monthly_counts: dict[tuple[int, int], int] = {}
    for r in records:
        key = (r.date.year, r.date.month)
        monthly_counts[key] = monthly_counts.get(key, 0) + 1

    # 顯示統計表
    table = Table(title="記錄統計")
    table.add_column("年月", style="cyan")
    table.add_column("記錄數", justify="right", style="magenta")

    for (year, month), count in sorted(monthly_counts.items()):
        table.add_row(f"{year}-{month:02d}", str(count))

    table.add_row("─" * 10, "─" * 5)
    table.add_row("[bold]總計[/bold]", f"[bold]{len(records)}[/bold]")

    console.print(table)


def _display_decisions(decisions: list[DedupeDecision]) -> None:
    """顯示去重決策結果

    Args:
        decisions: 去重決策列表
    """
    if not decisions:
        console.print("[green]✓ 無需處理的去重衝突[/green]")
        return

    # 統計結果
    summary = summarize_dedupe_results(decisions)

    # 顯示統計表
    table = Table(title="去重結果統計")
    table.add_column("類型", style="cyan")
    table.add_column("數量", style="magenta")
    table.add_column("說明", style="dim")

    table.add_row(
        "AUTO_MERGE",
        str(summary.get("auto_merge", 0)),
        "相似度 ≥95%，建議自動合併",
    )
    table.add_row(
        "MANUAL_REVIEW",
        str(summary.get("manual_review", 0)),
        "相似度 70-95% 或潛在退款，需人工確認",
    )
    table.add_row(
        "KEEP_BOTH",
        str(summary.get("keep_both", 0)),
        "相似度 <70%，保留兩筆",
    )

    console.print(table)

    # 顯示需要關注的項目
    review_items = [d for d in decisions if d.result == DedupeResult.MANUAL_REVIEW]
    if review_items:
        console.print(f"\n[yellow]⚠️  有 {len(review_items)} 筆記錄需要人工裁決[/yellow]")
        console.print("[dim]使用 lc dedupe --resolve 進行互動式裁決[/dim]")


def _interactive_resolve(decision: DedupeDecision) -> Optional[str]:
    """互動式裁決單筆記錄

    Args:
        decision: 去重決策

    Returns:
        使用者選擇: "M" (merge), "K" (keep both), "R" (reversal), "S" (skip)
    """
    record = decision.record

    console.print(
        Panel(
            f"📅 日期: {record.occurred_at}\n"
            f"💰 金額: {record.amount} {record.currency}\n"
            f"📁 類別: {record.category}\n"
            f"👤 支付者: {record.payer}\n"
            f"🏪 商家: {record.merchant or '(無)'}",
            title="待裁決記錄",
            border_style="yellow",
        )
    )

    # 顯示候選項
    if decision.candidates:
        console.print("\n[bold]候選重複項:[/bold]")
        for i, candidate in enumerate(decision.candidates, 1):
            t = candidate.transaction
            console.print(
                f"  [{i}] 相似度 {candidate.similarity:.0%} | "
                f"{t.occurred_at} | {t.amount} | {t.category} | "
                f"{candidate.match_reason}"
            )

    # 顯示建議
    if decision.recommendation:
        console.print(f"\n[dim]💡 建議: {decision.recommendation}[/dim]")

    # 提示選項
    console.print("\n選擇操作:")
    console.print("  [M] 合併 (Merge)")
    console.print("  [K] 保留兩筆 (Keep both)")
    console.print("  [R] 標記為退款/沖正 (Reversal)")
    console.print("  [S] 跳過 (Skip)")

    choice = typer.prompt("選擇", default="S").upper()

    if choice not in ("M", "K", "R", "S"):
        console.print("[yellow]無效選擇，跳過此筆[/yellow]")
        return "S"

    return choice
