"""Phase 4 CAPTURE - capture 指令

捕捉自然語言支出記錄至 staging，作為 Phase 4 的輸入入口。

用法:
    lc capture "昨天吃了 320 元拉麵"
    lc capture --batch file.txt
"""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from life_capital.capture.expense_parser import ExpenseParser
from life_capital.capture.staging_service import StagingService
from life_capital.interfaces.canonical_reader_impl import CanonicalReaderImpl
from life_capital.io.staging_store import StagingStoreImpl
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


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


def capture(
    text: Optional[str] = typer.Argument(None, help="支出描述文字"),
    batch: Optional[Path] = typer.Option(None, "--batch", help="批次匯入檔案路徑"),
    source: str = typer.Option("cli", "--source", help="來源標記（cli/api/batch）"),
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """捕捉自然語言支出記錄至 staging

    Examples:
        lc capture "昨天吃了 320 元拉麵"
        lc capture "12/25 聖誕禮物 1500"
        lc capture --batch expenses.txt
    """
    # 驗證參數
    if text is None and batch is None:
        console.print("[red]錯誤: 必須提供 TEXT 或 --batch 參數[/red]")
        raise typer.Exit(1)

    if text is not None and batch is not None:
        console.print("[red]錯誤: TEXT 與 --batch 不可同時使用[/red]")
        raise typer.Exit(1)

    # 解析資料目錄
    data_path = resolve_data_dir(path)

    # 初始化服務
    try:
        service = _init_staging_service(data_path)
    except Exception as e:
        console.print(f"[red]初始化失敗: {e}[/red]")
        raise typer.Exit(1)

    # 處理單筆或批次
    if text is not None:
        _capture_single(service, text, source)
    else:
        _capture_batch(service, batch, source)


def _capture_single(service: StagingService, text: str, source: str) -> None:
    """捕捉單筆支出

    Args:
        service: StagingService 實例
        text: 輸入文字
        source: 來源標記
    """
    try:
        # 新增 entry
        entry = service.add_entry(text, source=source)

        # 顯示結果
        console.print()
        console.print(
            Panel(
                f"[bold green]✅ 已加入 staging[/bold green]\n"
                f"Entry ID: [cyan]{entry.entry_id}[/cyan]",
                border_style="green",
                title="[bold]lc capture[/bold]",
            )
        )

        # 顯示基本資訊
        info_lines = [
            f"raw_text: [yellow]{entry.raw_text}[/yellow]",
            f"status: [dim]{entry.status.value}[/dim]",
            f"created_at: [dim]{entry.created_at.isoformat()}[/dim]",
        ]
        console.print(Panel("\n".join(info_lines), border_style="dim"))

        # 提示下一步
        console.print()
        console.print("[dim]下一步: lc staging parse --confirm[/dim]")

    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)


def _capture_batch(
    service: StagingService, batch_file: Path, source: str
) -> None:
    """批次匯入支出

    Args:
        service: StagingService 實例
        batch_file: 批次檔案路徑
        source: 來源標記
    """
    if not batch_file.exists():
        console.print(f"[red]錯誤: 檔案不存在: {batch_file}[/red]")
        raise typer.Exit(1)

    try:
        # 讀取檔案（每行一筆）
        with open(batch_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            console.print("[yellow]警告: 檔案為空[/yellow]")
            return

        # 批次新增
        batch_id = f"batch_{batch_file.stem}"
        entries = []

        with console.status("[bold green]處理中...[/bold green]") as status:
            for i, text in enumerate(lines, 1):
                status.update(f"[bold green]處理 {i}/{len(lines)}...[/bold green]")
                try:
                    entry = service.add_entry(
                        text, source=source, batch_id=batch_id
                    )
                    entries.append(entry)
                except Exception as e:
                    console.print(f"[red]警告: 第 {i} 行失敗: {e}[/red]")
                    continue

        # 顯示結果
        console.print()
        console.print(
            Panel(
                f"[bold green]✅ 批次匯入完成[/bold green]\n"
                f"成功: {len(entries)}/{len(lines)} 筆\n"
                f"Batch ID: [cyan]{batch_id}[/cyan]",
                border_style="green",
                title="[bold]lc capture --batch[/bold]",
            )
        )

        # 顯示統計
        if entries:
            console.print()
            console.print("[dim]下一步: lc staging list --status pending[/dim]")

    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)
