"""migrate 指令 (Phase 1.4)

執行 schema 遷移，將 canonical/ 資料升級到當前版本。

安全機制：
1. 自動備份：遷移前備份到 canonical/.migrations/
2. 回滾支援：遷移失敗自動還原
3. Dry-run：可預覽遷移結果
4. 護欄：需 --confirm 確認執行
"""

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from life_capital.io.migration import (
    MigrationError,
    get_migration_status,
    needs_migration,
    read_migration_log,
    run_migration,
)
from life_capital.io.registry import CURRENT_SCHEMA_VERSION
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()

app = typer.Typer(
    name="migrate",
    help="Schema 遷移工具",
    no_args_is_help=True,
)


@app.command(name="status")
def status(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """顯示遷移狀態

    檢查 canonical/ 內檔案的 schema 版本分佈，
    並顯示是否需要遷移。
    """
    data_dir = resolve_data_dir(path)

    try:
        status_info = get_migration_status(data_dir)

        # 顯示版本資訊
        console.print()
        console.print(Panel(
            f"[bold]當前 Schema 版本:[/bold] {status_info['current_schema_version']}\n"
            f"[bold]資料結構版本:[/bold] {status_info['data_layout_version']}",
            title="[bold blue]版本資訊[/bold blue]",
            border_style="blue",
        ))

        # 顯示版本分佈
        if status_info["version_distribution"]:
            table = Table(
                title="[bold]檔案版本分佈[/bold]",
                show_header=True,
                header_style="bold cyan",
            )
            table.add_column("Schema Version", style="bold")
            table.add_column("檔案數量", justify="right")
            table.add_column("狀態")

            for version, count in sorted(status_info["version_distribution"].items()):
                if version == CURRENT_SCHEMA_VERSION:
                    status_str = "[green]✅ 當前版本[/green]"
                elif version == "unknown":
                    status_str = "[yellow]⚠️ 無版本標記[/yellow]"
                else:
                    status_str = "[red]❌ 需遷移[/red]"

                table.add_row(version, str(count), status_str)

            console.print()
            console.print(table)
        else:
            console.print()
            console.print("[yellow]沒有找到 canonical/ 檔案[/yellow]")

        # 顯示遷移建議
        console.print()
        if status_info["needs_migration"]:
            console.print(f"[yellow]⚠️ 需要遷移:[/yellow] {status_info['migration_reason']}")
            console.print(f"[dim]待遷移檔案數: {status_info['outdated_file_count']}[/dim]")
            console.print()
            console.print("[cyan]執行遷移:[/cyan] lc migrate run --confirm")
        else:
            console.print(f"[green]✅ {status_info['migration_reason']}[/green]")

        # 顯示最近遷移
        if status_info["last_migration"]:
            last = status_info["last_migration"]
            console.print()
            console.print(f"[dim]最近遷移: {last['migration_id'][:8]} "
                          f"({last['from_version']} → {last['to_version']}) "
                          f"狀態: {last['status']}[/dim]")

    except MigrationError as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="run")
def run(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="確認執行遷移（必填，避免誤操作）",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="自動確認所有提示（非互動模式）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="只顯示會遷移的檔案，不實際執行",
    ),
    target_version: Optional[str] = typer.Option(
        None,
        "--to",
        help=f"目標版本（預設：{CURRENT_SCHEMA_VERSION}）",
    ),
) -> None:
    """執行 schema 遷移

    此指令會：
    1. 檢查需要遷移的檔案
    2. 建立 canonical/ 備份
    3. 執行遷移
    4. 記錄遷移日誌

    使用 --dry-run 預覽遷移效果。
    """
    # 護欄：必須 --confirm 才能執行（除非 dry-run）
    if not confirm and not dry_run:
        console.print("[red]錯誤: 必須使用 --confirm 旗標才能執行遷移[/red]")
        console.print("[yellow]範例: lc migrate run --confirm[/yellow]")
        console.print("[yellow]或使用 --dry-run 預覽: lc migrate run --dry-run[/yellow]")
        raise typer.Exit(1)

    data_dir = resolve_data_dir(path)

    try:
        # 檢查是否需要遷移
        needs, reason, outdated_files = needs_migration(data_dir)

        if not needs:
            console.print(f"[green]✅ 不需要遷移: {reason}[/green]")
            raise typer.Exit(0)

        # 顯示待遷移檔案
        console.print()
        console.print(f"[yellow]發現 {len(outdated_files)} 個需要遷移的檔案:[/yellow]")
        for f in outdated_files[:10]:
            console.print(f"  - {f.relative_to(data_dir)}")
        if len(outdated_files) > 10:
            console.print(f"  ... 還有 {len(outdated_files) - 10} 個檔案")

        console.print()
        console.print(f"[bold]目標版本:[/bold] {target_version or CURRENT_SCHEMA_VERSION}")

        if dry_run:
            console.print()
            console.print("[cyan]🔍 Dry-run 模式: 不會實際執行遷移[/cyan]")
            result = run_migration(data_dir, target_version, dry_run=True)
            console.print(f"[dim]預計遷移 {len(result.files_migrated)} 個檔案[/dim]")
            raise typer.Exit(0)

        # 確認執行
        console.print()
        if not yes:
            if not Confirm.ask(
                "[yellow]確認執行遷移? 將自動備份 canonical/[/yellow]",
                default=False,
            ):
                console.print("[yellow]已取消遷移[/yellow]")
                raise typer.Exit(0)

        # 執行遷移
        console.print()
        console.print("[bold]開始遷移...[/bold]")

        result = run_migration(data_dir, target_version, actor="cli")

        # 顯示結果
        console.print()
        if result.status == "completed":
            console.print("[green]✅ 遷移完成[/green]")
            console.print(f"[dim]遷移 ID: {result.migration_id[:8]}[/dim]")
            console.print(f"[dim]備份位置: {result.backup_path}[/dim]")
            console.print(f"[dim]遷移檔案數: {len(result.files_migrated)}[/dim]")
        else:
            console.print(f"[red]遷移狀態: {result.status}[/red]")
            if result.error_message:
                console.print(f"[red]錯誤: {result.error_message}[/red]")

    except MigrationError as e:
        console.print(f"[red]遷移錯誤: {e}[/red]")
        raise typer.Exit(1)


@app.command(name="history")
def history(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        help="顯示最近 N 筆遷移記錄",
    ),
) -> None:
    """顯示遷移歷史"""
    data_dir = resolve_data_dir(path)

    try:
        entries = read_migration_log(data_dir)

        if not entries:
            console.print("[yellow]沒有遷移記錄[/yellow]")
            raise typer.Exit(0)

        # 取最近 N 筆
        entries = entries[-limit:]

        table = Table(
            title="[bold]遷移歷史[/bold]",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("遷移 ID", style="bold")
        table.add_column("版本變更")
        table.add_column("檔案數", justify="right")
        table.add_column("狀態")
        table.add_column("時間")
        table.add_column("執行者")

        for entry in reversed(entries):
            # 狀態樣式
            if entry.status == "completed":
                status_str = "[green]✅ 完成[/green]"
            elif entry.status == "failed":
                status_str = "[red]❌ 失敗[/red]"
            elif entry.status == "rolled_back":
                status_str = "[yellow]⏪ 已回滾[/yellow]"
            elif entry.status == "dry_run":
                status_str = "[cyan]🔍 模擬[/cyan]"
            else:
                status_str = f"[dim]{entry.status}[/dim]"

            # 時間格式
            time_str = entry.started_at.strftime("%Y-%m-%d %H:%M")

            table.add_row(
                entry.migration_id[:8],
                f"{entry.from_version} → {entry.to_version}",
                str(len(entry.files_migrated)),
                status_str,
                time_str,
                entry.actor,
            )

        console.print()
        console.print(table)
        console.print()

    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)


# 獨立函式版本（供直接調用）
def migrate(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """顯示遷移狀態（預設行為）

    使用 'lc migrate status' 查看詳細狀態
    使用 'lc migrate run --confirm' 執行遷移
    """
    status(path)
