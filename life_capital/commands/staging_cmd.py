"""Phase 4 CAPTURE - staging 管理指令

管理 staging entries 的 CRUD 操作與狀態轉移。

用法:
    lc staging list [--status STATUS]
    lc staging show <entry_id>
    lc staging parse [--confirm]
    lc staging approve <entry_id>
    lc staging reject <entry_id> --reason "..."
    lc staging ignore <entry_id> --reason "..."
    lc staging delete <entry_id>
    lc staging clear [--status STATUS]
    lc staging repair [--dry-run]
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from life_capital.capture.expense_parser import ExpenseParser
from life_capital.capture.models import StagingEntry, StagingStatus
from life_capital.capture.staging_service import (
    EntryNotFound,
    InvalidStateTransition,
    StagingService,
)
from life_capital.interfaces.canonical_reader_impl import CanonicalReaderImpl
from life_capital.io.staging_store import StagingStoreImpl
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()
app = typer.Typer(help="Staging 管理指令")


def _init_staging_service(data_path: Path) -> StagingService:
    """初始化 StagingService（共用邏輯）

    Args:
        data_path: 資料根目錄

    Returns:
        StagingService 實例
    """
    # 1. 初始化 CanonicalReader
    reader = CanonicalReaderImpl(data_path)

    # 2. 初始化 StagingStore
    store = StagingStoreImpl(data_path)

    # 3. 初始化 ExpenseParser
    parser = ExpenseParser(reader)

    # 4. 初始化 StagingService
    return StagingService(store, parser, reader)


# === 狀態 emoji 對照表 ===
STATUS_EMOJI = {
    StagingStatus.PENDING: "⏳",
    StagingStatus.PARSED: "🔍",
    StagingStatus.ERROR: "❌",
    StagingStatus.APPROVED: "✅",
    StagingStatus.REJECTED: "🚫",
    StagingStatus.IGNORED: "⚠️",
    StagingStatus.DUPLICATE: "🔄",
    StagingStatus.APPLIED: "📦",
}


@app.command("list")
def staging_list(
    status: Optional[str] = typer.Option(None, "--status", help="狀態過濾"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """列出 staging entries

    Examples:
        lc staging list
        lc staging list --status pending
        lc staging list --status parsed
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 狀態枚舉轉換
    status_enum = None
    if status is not None:
        try:
            status_enum = StagingStatus(status)
        except ValueError:
            console.print(f"[red]錯誤: 無效的狀態值: {status}[/red]")
            valid = ", ".join(s.value for s in StagingStatus)
            console.print(f"[yellow]有效值: {valid}[/yellow]")
            raise typer.Exit(1)

    # 列出 entries
    try:
        entries = service.list_entries(status=status_enum)
    except FileNotFoundError:
        console.print("[yellow]尚無 staging entries[/yellow]")
        return
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    if not entries:
        console.print("[yellow]尚無符合條件的 entries[/yellow]")
        return

    # 顯示表格
    table = Table(title=f"[bold]Staging Entries ({len(entries)})[/bold]")
    table.add_column("Status", style="dim")
    table.add_column("ID", style="cyan")
    table.add_column("Raw Text", style="yellow")
    table.add_column("Confidence", justify="right")
    table.add_column("Created", style="dim")

    for entry in entries:
        emoji = STATUS_EMOJI.get(entry.status, "")
        status_str = f"{emoji} {entry.status.value}"
        id_short = entry.entry_id[:8]
        raw_text = (
            entry.raw_text[:40] + "..."
            if len(entry.raw_text) > 40
            else entry.raw_text
        )
        confidence = (
            f"{entry.confidence:.1%}" if entry.confidence > 0 else "-"
        )
        created = entry.created_at.strftime("%Y-%m-%d %H:%M")

        table.add_row(status_str, id_short, raw_text, confidence, created)

    console.print()
    console.print(table)
    console.print()


@app.command("show")
def staging_show(
    entry_id: str = typer.Argument(..., help="Entry ID"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """顯示 entry 詳細資訊

    Examples:
        lc staging show abc12345
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 讀取 entry
    try:
        entry = service.get_entry(entry_id)
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    if entry is None:
        console.print(f"[red]❌ Entry not found: {entry_id}[/red]")
        raise typer.Exit(1)

    # 顯示詳細資訊
    _render_entry_detail(entry)


def _render_entry_detail(entry: StagingEntry) -> None:
    """渲染 entry 詳細資訊

    Args:
        entry: StagingEntry 實例
    """
    emoji = STATUS_EMOJI.get(entry.status, "")
    console.print()
    console.print(
        Panel(
            f"[bold]{emoji} {entry.status.value}[/bold]\n"
            f"Entry ID: [cyan]{entry.entry_id}[/cyan]",
            border_style="blue",
            title="[bold]Staging Entry[/bold]",
        )
    )

    # 基本資訊
    console.print("\n[bold]基本資訊[/bold]")
    console.print(f"  raw_text: [yellow]{entry.raw_text}[/yellow]")
    console.print(f"  created_at: {entry.created_at.isoformat()}")
    console.print(f"  source: {entry.source}")
    if entry.batch_id:
        console.print(f"  batch_id: {entry.batch_id}")

    # 解析結果
    if entry.parsed_date or entry.parsed_amount or entry.parsed_category:
        console.print("\n[bold]解析結果[/bold]")
        if entry.parsed_date:
            certain = "✓" if entry.date_certain else "~"
            console.print(
                f"  📅 date: {entry.parsed_date} [{certain}] "
                f"(source: {entry.date_source.value})"
            )
        if entry.parsed_amount:
            certain = "✓" if entry.amount_certain else "~"
            console.print(
                f"  💰 amount: {entry.parsed_amount} [{certain}] "
                f"(source: {entry.amount_source.value})"
            )
        if entry.parsed_category:
            certain = "✓" if entry.category_certain else "~"
            console.print(
                f"  📂 category: {entry.parsed_category} [{certain}] "
                f"(source: {entry.category_source.value})"
            )
        if entry.parsed_merchant:
            console.print(f"  🏪 merchant: {entry.parsed_merchant}")
        if entry.parsed_note:
            console.print(f"  📝 note: {entry.parsed_note}")

    # 信心度
    if entry.confidence > 0:
        console.print(f"\n[bold]信心度[/bold]: {entry.confidence:.1%}")
        if entry.confidence_breakdown:
            for key, value in entry.confidence_breakdown.items():
                console.print(f"  {key}: {value:.2f}")

    # 狀態資訊
    if entry.status == StagingStatus.ERROR and entry.error_message:
        console.print(f"\n[bold red]錯誤訊息[/bold red]: {entry.error_message}")

    if entry.reviewed_at:
        console.print("\n[bold]決策記錄[/bold]")
        console.print(f"  reviewed_at: {entry.reviewed_at.isoformat()}")
        console.print(f"  reviewed_by: {entry.reviewed_by}")
        if entry.rejection_reason:
            console.print(f"  reason: {entry.rejection_reason}")

    # 判重資訊
    if entry.duplicate_of:
        console.print("\n[bold]判重資訊[/bold]")
        console.print(f"  duplicate_of: {entry.duplicate_of}")
        if entry.duplicate_reason:
            console.print(f"  reason: {entry.duplicate_reason.value}")

    # 終態追蹤
    if entry.proposal_id or entry.canonical_record_id:
        console.print("\n[bold]終態追蹤[/bold]")
        if entry.proposal_id:
            console.print(f"  proposal_id: {entry.proposal_id}")
        if entry.canonical_record_id:
            console.print(f"  canonical_record_id: {entry.canonical_record_id}")

    console.print()


@app.command("parse")
def staging_parse(
    confirm: bool = typer.Option(
        False, "--confirm", help="確認執行（預設 dry-run）"
    ),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """解析 pending entries（V4.1: 唯一解析路徑）

    Examples:
        lc staging parse           # dry-run
        lc staging parse --confirm # 執行
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 列出 pending entries
    try:
        pending_entries = service.list_entries(status=StagingStatus.PENDING)
    except FileNotFoundError:
        console.print("[yellow]尚無 pending entries[/yellow]")
        return
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    if not pending_entries:
        console.print("[yellow]尚無 pending entries[/yellow]")
        return

    # Dry-run 模式
    if not confirm:
        console.print(
            f"[yellow]🔍 發現 {len(pending_entries)} 筆 pending entries[/yellow]"
        )
        console.print("[dim]使用 --confirm 執行解析[/dim]")
        return

    # 執行解析
    console.print("[bold green]🔄 解析中...[/bold green]")
    console.print()

    results = service.parse_all_pending()

    # 統計結果
    success = sum(
        1
        for r in results
        if r.status
        in (StagingStatus.PARSED, StagingStatus.APPROVED, StagingStatus.DUPLICATE)
    )
    errors = sum(1 for r in results if r.status == StagingStatus.ERROR)

    # 顯示結果
    for entry in results:
        emoji = STATUS_EMOJI.get(entry.status, "")
        status_str = f"{emoji} {entry.status.value}"
        id_short = entry.entry_id[:8]

        if entry.status == StagingStatus.ERROR:
            console.print(
                f"[red]{status_str}[/red] {id_short}: {entry.error_message}"
            )
        elif entry.status == StagingStatus.APPROVED:
            console.print(
                f"[green]{status_str}[/green] {id_short}: "
                f"⚠️ Proposal creation pending"
            )
        elif entry.status == StagingStatus.DUPLICATE:
            console.print(
                f"[yellow]{status_str}[/yellow] {id_short}: "
                f"duplicate of {entry.duplicate_of[:8]}"
            )
        else:
            console.print(f"[cyan]{status_str}[/cyan] {id_short}")

    # 顯示統計
    console.print()
    console.print(
        Panel(
            f"[bold green]✅ 解析完成[/bold green]\n"
            f"成功: {success}/{len(results)} | 失敗: {errors}/{len(results)}",
            border_style="green",
            title="[bold]lc staging parse[/bold]",
        )
    )


@app.command("approve")
def staging_approve(
    entry_id: str = typer.Argument(..., help="Entry ID"),
    actor: str = typer.Option("user", "--actor", help="操作者"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """手動批准 entry

    Examples:
        lc staging approve abc12345
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 批准 entry
    try:
        entry = service.approve_entry(entry_id, actor=actor)
    except EntryNotFound:
        console.print(f"[red]❌ Entry not found: {entry_id}[/red]")
        raise typer.Exit(1)
    except InvalidStateTransition as e:
        console.print(f"[red]❌ Invalid state transition: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    # 顯示結果
    console.print()
    console.print(
        Panel(
            f"[bold green]✅ 已批准[/bold green]\n"
            f"Entry ID: [cyan]{entry.entry_id}[/cyan]\n"
            f"⚠️ Proposal creation pending",
            border_style="green",
            title="[bold]lc staging approve[/bold]",
        )
    )


@app.command("reject")
def staging_reject(
    entry_id: str = typer.Argument(..., help="Entry ID"),
    reason: str = typer.Option(..., "--reason", help="拒絕原因"),
    actor: str = typer.Option("user", "--actor", help="操作者"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """拒絕 entry

    Examples:
        lc staging reject abc12345 --reason "金額錯誤"
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 拒絕 entry
    try:
        entry = service.reject_entry(entry_id, actor=actor, reason=reason)
    except EntryNotFound:
        console.print(f"[red]❌ Entry not found: {entry_id}[/red]")
        raise typer.Exit(1)
    except InvalidStateTransition as e:
        console.print(f"[red]❌ Invalid state transition: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    # 顯示結果
    console.print()
    console.print(
        Panel(
            f"[bold red]🚫 已拒絕[/bold red]\n"
            f"Entry ID: [cyan]{entry.entry_id}[/cyan]\n"
            f"Reason: {reason}",
            border_style="red",
            title="[bold]lc staging reject[/bold]",
        )
    )


@app.command("ignore")
def staging_ignore(
    entry_id: str = typer.Argument(..., help="Entry ID"),
    reason: str = typer.Option(..., "--reason", help="忽略原因"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """忽略 entry（非支出）

    Examples:
        lc staging ignore abc12345 --reason "非支出記錄"
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 忽略 entry
    try:
        entry = service.ignore_entry(entry_id, reason=reason)
    except EntryNotFound:
        console.print(f"[red]❌ Entry not found: {entry_id}[/red]")
        raise typer.Exit(1)
    except InvalidStateTransition as e:
        console.print(f"[red]❌ Invalid state transition: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    # 顯示結果
    console.print()
    console.print(
        Panel(
            f"[bold yellow]⚠️ 已忽略[/bold yellow]\n"
            f"Entry ID: [cyan]{entry.entry_id}[/cyan]\n"
            f"Reason: {reason}",
            border_style="yellow",
            title="[bold]lc staging ignore[/bold]",
        )
    )


@app.command("delete")
def staging_delete(
    entry_id: str = typer.Argument(..., help="Entry ID"),
    yes: bool = typer.Option(False, "--yes", help="跳過確認"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """刪除 staging entry

    Examples:
        lc staging delete abc12345
        lc staging delete abc12345 --yes
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 確認提示
    if not yes:
        confirm = typer.confirm(f"確定要刪除 entry {entry_id}？")
        if not confirm:
            console.print("[yellow]已取消[/yellow]")
            return

    # 刪除 entry
    try:
        service.delete_entry(entry_id)
    except EntryNotFound:
        console.print(f"[red]❌ Entry not found: {entry_id}[/red]")
        raise typer.Exit(1)
    except NotImplementedError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    # 顯示結果
    console.print(f"[green]✅ 已刪除 entry {entry_id}[/green]")


@app.command("clear")
def staging_clear(
    status: Optional[str] = typer.Option(None, "--status", help="僅清除指定狀態"),
    yes: bool = typer.Option(False, "--yes", help="跳過確認"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """清除所有 entries

    Examples:
        lc staging clear
        lc staging clear --status pending
        lc staging clear --yes
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 狀態枚舉轉換
    status_enum = None
    if status is not None:
        try:
            status_enum = StagingStatus(status)
        except ValueError:
            console.print(f"[red]錯誤: 無效的狀態值: {status}[/red]")
            valid = ", ".join(s.value for s in StagingStatus)
            console.print(f"[yellow]有效值: {valid}[/yellow]")
            raise typer.Exit(1)

    # 確認提示
    if not yes:
        msg = (
            "確定要清除所有 entries？"
            if status is None
            else f"確定要清除所有 {status} entries？"
        )
        confirm = typer.confirm(msg)
        if not confirm:
            console.print("[yellow]已取消[/yellow]")
            return

    # 清除 entries
    try:
        count = service.clear_all(status=status_enum)
    except NotImplementedError as e:
        console.print(f"[red]❌ {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)

    # 顯示結果
    console.print(f"[green]✅ 已清除 {count} 筆 entries[/green]")


@app.command("repair")
def staging_repair(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="僅檢查不一致，不實際修復"
    ),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """偵測並修復 staging entries 的不一致狀態

    檢查 3 種不一致類型：
    1. approved_without_proposal: status=approved 但 proposal_id=None
    2. proposal_without_approved: proposal_id 存在但 status≠approved/applied
    3. applied_without_canonical: status=applied 但 canonical_record_id=None

    Examples:
        lc staging repair --dry-run  # 僅檢查，不修復
        lc staging repair             # 偵測並修復
    """
    data_path = resolve_data_dir(path)

    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 偵測不一致
    try:
        inconsistencies = service.detect_inconsistencies()
    except Exception as e:
        console.print(f"[red]偵測失敗: {e}[/red]")
        raise typer.Exit(1)

    # 顯示不一致報告
    if not inconsistencies:
        console.print("[green]✅ 無偵測到不一致狀態[/green]")
        return

    console.print(
        f"[yellow]⚠️ 偵測到 {len(inconsistencies)} 筆不一致狀態[/yellow]\n"
    )

    # 建立報告表格
    table = Table(title="不一致報告")
    table.add_column("Entry ID", style="cyan")
    table.add_column("類型", style="magenta")
    table.add_column("當前狀態", style="yellow")
    table.add_column("說明", style="white")
    table.add_column("建議修復", style="green")

    for report in inconsistencies:
        table.add_row(
            report.entry_id[:8] + "...",
            report.inconsistency_type,
            report.current_status,
            report.description,
            report.suggested_fix,
        )

    console.print(table)
    console.print()

    # Dry-run 模式：只顯示報告
    if dry_run:
        console.print(
            "[yellow]🔍 Dry-run 模式：未執行修復\n"
            "執行 `lc staging repair` 以進行修復[/yellow]"
        )
        return

    # 執行修復
    try:
        results = service.repair_inconsistencies(dry_run=False)
    except Exception as e:
        console.print(f"[red]修復失敗: {e}[/red]")
        raise typer.Exit(1)

    # 顯示修復結果
    success_count = sum(1 for r in results if r.success)
    failure_count = len(results) - success_count

    console.print(f"[green]✅ 修復成功: {success_count}/{len(results)}[/green]")
    if failure_count > 0:
        console.print(f"[red]❌ 修復失敗: {failure_count}/{len(results)}[/red]\n")

    # 建立結果表格
    result_table = Table(title="修復結果")
    result_table.add_column("Entry ID", style="cyan")
    result_table.add_column("類型", style="magenta")
    result_table.add_column("修復動作", style="white")
    result_table.add_column("結果", style="green")

    for result in results:
        status_emoji = "✅" if result.success else "❌"
        status_color = "green" if result.success else "red"
        result_table.add_row(
            result.entry_id[:8] + "...",
            result.inconsistency_type,
            result.action_taken,
            f"[{status_color}]{status_emoji}[/{status_color}]",
        )

    console.print(result_table)
