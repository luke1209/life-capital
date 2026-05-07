"""undo 指令

回滾指定 operation
"""

import getpass
import json
import shutil
from pathlib import Path
from typing import Optional, Union

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from life_capital.io.canonical_handler import (
    CanonicalError,
    append_operation_log,
    read_operation_log,
)
from life_capital.io.registry import OPERATION_LOG_FILE, PROPOSALS_DIR
from life_capital.models.operation import (
    Operation,
    OperationLogEntry,
    OperationType,
)
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def undo(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    operation: Optional[str] = typer.Option(
        None,
        "--operation",
        "-o",
        help="指定要回滾的 operation_id（可使用前綴）",
    ),
    latest: bool = typer.Option(
        False,
        "--latest",
        help="回滾最新一筆操作",
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
        "-n",
        help="預覽模式：顯示將執行的回滾但不實際修改",
    ),
) -> None:
    """回滾指定 operation

    此指令會：
    1. 讀取 operation log
    2. 顯示操作資訊
    3. 詢問確認
    4. 執行回滾邏輯
    5. 記錄 undo 操作

    回滾邏輯：
    - apply 操作：刪除 canonical 檔案，恢復 proposal
    - import 操作：刪除 raw 檔案（警告不可恢復）
    - rebuild 操作：刪除 derived 檔案
    - undo 操作：重新套用被回滾的操作（使用 rollback_data）

    使用 --dry-run 預覽將執行的回滾但不實際修改。
    """
    # dry-run 模式提示
    if dry_run:
        console.print("[cyan]━━━ DRY-RUN 模式：僅預覽，不實際執行 ━━━[/cyan]")
        console.print()

    data_dir = resolve_data_dir(path)

    # 護欄：必須指定 --operation 或 --latest
    if not operation and not latest:
        console.print("[red]錯誤: 必須指定 --operation <id> 或 --latest[/red]")
        console.print("[yellow]範例: lc undo --operation abc123[/yellow]")
        console.print("[yellow]      lc undo --latest[/yellow]")
        raise typer.Exit(1)

    if operation and latest:
        console.print("[red]錯誤: --operation 與 --latest 不可同時使用[/red]")
        raise typer.Exit(1)

    # 讀取 operation log
    log_path = data_dir / OPERATION_LOG_FILE
    try:
        log_entries = read_operation_log(log_path=log_path)
    except CanonicalError as e:
        console.print(f"[red]錯誤: 讀取 operation log 失敗: {e}[/red]")
        raise typer.Exit(1)

    if not log_entries:
        console.print("[yellow]提示: operation log 為空，沒有可回滾的操作[/yellow]")
        raise typer.Exit(0)

    # 選擇要回滾的 operation
    if latest:
        target_entry = log_entries[-1]
    else:
        # 搜尋匹配的 operation_id（支援前綴匹配）
        matching_entries = [
            entry
            for entry in log_entries
            if str(entry.operation.operation_id).startswith(operation)
        ]

        if not matching_entries:
            console.print(f"[red]錯誤: 找不到 operation ID: {operation}[/red]")
            _show_recent_operations(log_entries)
            raise typer.Exit(1)

        if len(matching_entries) > 1:
            console.print("[yellow]警告: 找到多個匹配的 operations[/yellow]")
            _show_matching_operations(matching_entries)
            console.print(
                "[yellow]請提供更完整的 operation_id 前綴以唯一識別[/yellow]"
            )
            raise typer.Exit(1)

        target_entry = matching_entries[0]

    # 顯示操作資訊
    _show_operation_details(target_entry, data_dir)

    # Dry-run 模式：顯示預覽後結束
    if dry_run:
        _show_rollback_preview(target_entry, data_dir)
        console.print()
        console.print("[cyan]━━━ DRY-RUN 完成：以上為將執行的回滾操作 ━━━[/cyan]")
        console.print("[yellow]移除 --dry-run 並使用 --latest 或 --operation 執行實際回滾[/yellow]")
        raise typer.Exit(0)

    # 詢問確認
    if not yes:
        if not Confirm.ask(
            f"[yellow]確認回滾此操作? ({str(target_entry.operation.operation_id)[:8]})[/yellow]",
            default=False,
        ):
            console.print("[yellow]已取消回滾[/yellow]")
            raise typer.Exit(0)
    else:
        console.print(
            f"[dim]自動確認回滾操作: {str(target_entry.operation.operation_id)[:8]}[/dim]"
        )

    # 執行回滾
    try:
        _execute_rollback(target_entry, data_dir, yes=yes)
        console.print()
        console.print(
            f"[green]✓ 成功回滾操作: {str(target_entry.operation.operation_id)[:8]}[/green]"
        )
    except Exception as e:
        console.print(f"[red]錯誤: 回滾失敗: {e}[/red]")
        raise typer.Exit(1)


def _show_rollback_preview(entry: OperationLogEntry, data_dir: Path) -> None:
    """顯示回滾操作預覽（dry-run 模式）"""
    operation = entry.operation
    operation_type = operation.operation_type
    target_path = data_dir / operation.target_path

    console.print()
    console.print("[bold cyan]回滾操作預覽：[/bold cyan]")

    if operation_type == OperationType.APPLY:
        console.print(f"[cyan]  → 將刪除 canonical 檔案: {target_path}[/cyan]")
        proposal_id = operation.metadata.get("proposal_id")
        if proposal_id:
            console.print(f"[cyan]  → 將恢復 proposal: {proposal_id}[/cyan]")
        else:
            console.print("[yellow]  → 無法恢復 proposal（metadata 缺少 proposal_id）[/yellow]")

    elif operation_type == OperationType.IMPORT:
        console.print("[red]  ⚠️  將永久刪除匯入的資料（不可恢復）[/red]")
        console.print(f"[cyan]  → 將刪除 raw 檔案: {target_path}[/cyan]")

    elif operation_type == OperationType.REBUILD:
        console.print(f"[cyan]  → 將刪除 derived 檔案: {target_path}[/cyan]")

    elif operation_type == OperationType.UNDO:
        console.print("[cyan]  → 將重新執行被回滾的原始操作[/cyan]")
        if operation.rollback_data:
            console.print(
                f"[cyan]  → 原始操作類型: {operation.rollback_data.get('operation_type')}[/cyan]"
            )
        else:
            console.print("[yellow]  → 缺少 rollback_data，可能無法完整恢復[/yellow]")

    else:
        console.print(f"[yellow]  → 未知操作類型: {operation_type}[/yellow]")

    console.print("[cyan]  → 將記錄 undo 操作到 operation log[/cyan]")


def _show_operation_details(entry: OperationLogEntry, data_dir: Path) -> None:
    """顯示操作詳細資訊"""
    operation = entry.operation

    # 操作資訊面板
    info_lines = [
        f"[bold]Operation ID:[/bold] {str(operation.operation_id)[:8]}...",
        f"[bold]Operation Type:[/bold] {operation.operation_type.value}",
        f"[bold]Target Path:[/bold] {operation.target_path}",
        f"[bold]Description:[/bold] {operation.description}",
        f"[bold]Actor:[/bold] {operation.actor}",
        f"[bold]Created At:[/bold] {operation.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    # 若有 rollback_data，顯示預覽
    if operation.rollback_data:
        info_lines.append("")
        info_lines.append("[bold]Rollback Data:[/bold]")
        rollback_preview = json.dumps(operation.rollback_data, indent=2, ensure_ascii=False)
        preview_lines = rollback_preview.split("\n")[:10]
        info_lines.extend(f"  {line}" for line in preview_lines)
        if len(rollback_preview.split("\n")) > 10:
            info_lines.append("  ... (省略部分內容)")

    console.print()
    console.print(
        Panel(
            "\n".join(info_lines),
            title="[bold yellow]⚠️  Operation Details[/bold yellow]",
            border_style="yellow",
        )
    )

    # 檢查目標檔案是否存在
    target_path = data_dir / operation.target_path
    if target_path.exists():
        console.print(f"[dim]目標檔案存在: {target_path}[/dim]")
    else:
        console.print(f"[yellow]警告: 目標檔案不存在: {target_path}[/yellow]")


def _show_recent_operations(log_entries: list[OperationLogEntry], limit: int = 5) -> None:
    """顯示最近的操作列表"""
    console.print()
    console.print(f"[bold]最近 {limit} 筆操作:[/bold]")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Operation ID", style="bold")
    table.add_column("Type", justify="center")
    table.add_column("Target Path")
    table.add_column("Created At", justify="center")

    for entry in log_entries[-limit:]:
        operation = entry.operation
        table.add_row(
            str(operation.operation_id)[:8],
            operation.operation_type.value,
            str(operation.target_path),
            operation.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)
    console.print()


def _show_matching_operations(matching_entries: list[OperationLogEntry]) -> None:
    """顯示匹配的操作列表"""
    console.print()
    console.print(f"[bold]找到 {len(matching_entries)} 個匹配的 operations:[/bold]")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Operation ID", style="bold")
    table.add_column("Type", justify="center")
    table.add_column("Target Path")
    table.add_column("Created At", justify="center")

    for entry in matching_entries:
        operation = entry.operation
        table.add_row(
            str(operation.operation_id),
            operation.operation_type.value,
            str(operation.target_path),
            operation.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)
    console.print()


def _execute_rollback(entry: OperationLogEntry, data_dir: Path, yes: bool = False) -> None:
    """執行回滾邏輯

    Args:
        entry: 要回滾的操作日誌條目
        data_dir: 資料目錄根路徑
        yes: 是否自動確認（非互動模式）

    Raises:
        Exception: 回滾失敗
    """
    operation = entry.operation
    operation_type = operation.operation_type
    target_path = data_dir / operation.target_path

    console.print()
    console.print("[bold]執行回滾...[/bold]")

    # 根據操作類型執行不同的回滾邏輯
    if operation_type == OperationType.APPLY:
        _rollback_apply(operation, target_path, data_dir, yes=yes)

    elif operation_type == OperationType.IMPORT:
        _rollback_import(operation, target_path, data_dir, yes=yes)

    elif operation_type == OperationType.REBUILD:
        _rollback_rebuild(operation, target_path, data_dir, yes=yes)

    elif operation_type == OperationType.UNDO:
        _rollback_undo(operation, target_path, data_dir, yes=yes)

    else:
        raise ValueError(f"不支援的操作類型: {operation_type}")

    # 記錄 undo 操作到 operation log
    _log_undo_operation(operation, data_dir)


def _rollback_apply(
    operation: Operation, target_path: Path, data_dir: Path, yes: bool = False
) -> None:
    """回滾 apply 操作

    邏輯：
    1. 刪除 canonical/ 檔案
    2. 恢復 proposal（從 proposals/applied/ 移回 proposals/pending/）

    Args:
        operation: 原始操作物件
        target_path: 目標檔案路徑
        data_dir: 資料目錄根路徑
        yes: 是否自動確認
    """
    # 1. 刪除 canonical/ 檔案
    if target_path.exists():
        console.print(f"[dim]  刪除 canonical 檔案: {target_path.name}[/dim]")
        target_path.unlink()
    else:
        console.print("[yellow]  警告: canonical 檔案不存在，跳過刪除[/yellow]")

    # 2. 恢復 proposal
    # 從 metadata 取得 proposal_id（若有記錄）
    proposal_id = operation.metadata.get("proposal_id")
    if proposal_id:
        applied_proposal_path = (
            data_dir / PROPOSALS_DIR / "applied" / f"{proposal_id}.json"
        )
        pending_proposal_path = (
            data_dir / PROPOSALS_DIR / "pending" / f"{proposal_id}.json"
        )

        if applied_proposal_path.exists():
            console.print(f"[dim]  恢復 proposal: {applied_proposal_path.name}[/dim]")
            pending_proposal_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(applied_proposal_path), str(pending_proposal_path))
        else:
            console.print(
                "[yellow]  警告: 找不到 applied proposal，無法恢復[/yellow]"
            )
    else:
        console.print("[yellow]  警告: metadata 缺少 proposal_id，無法恢復 proposal[/yellow]")


def _rollback_import(
    operation: Operation, target_path: Path, data_dir: Path, yes: bool = False
) -> None:
    """回滾 import 操作

    邏輯：
    1. 刪除 raw/ 檔案（警告不可恢復）

    Args:
        operation: 原始操作物件
        target_path: 目標檔案路徑
        data_dir: 資料目錄根路徑
        yes: 是否自動確認
    """
    # 警告：import 操作的回滾是不可逆的
    console.print(
        "[bold red]⚠️  警告: 回滾 import 操作會永久刪除匯入的資料[/bold red]"
    )
    console.print(f"[yellow]  即將刪除: {target_path}[/yellow]")

    if not yes:
        if not Confirm.ask(
            "[red]確認永久刪除此檔案?[/red]",
            default=False,
        ):
            console.print("[yellow]已取消回滾[/yellow]")
            raise typer.Exit(0)

    # 刪除 raw/ 檔案
    if target_path.exists():
        console.print(f"[dim]  刪除 raw 檔案: {target_path.name}[/dim]")
        target_path.unlink()
    else:
        console.print("[yellow]  警告: raw 檔案不存在，跳過刪除[/yellow]")


def _rollback_rebuild(
    operation: Operation, target_path: Path, data_dir: Path, yes: bool = False
) -> None:
    """回滾 rebuild 操作

    邏輯：
    1. 刪除 derived/ 檔案

    Args:
        operation: 原始操作物件
        target_path: 目標檔案路徑
        data_dir: 資料目錄根路徑
        yes: 是否自動確認
    """
    # 刪除 derived/ 檔案
    if target_path.exists():
        console.print(f"[dim]  刪除 derived 檔案: {target_path.name}[/dim]")
        target_path.unlink()
    else:
        console.print("[yellow]  警告: derived 檔案不存在，跳過刪除[/yellow]")


def _rollback_undo(
    operation: Operation, target_path: Path, data_dir: Path, yes: bool = False
) -> None:
    """回滾 undo 操作

    邏輯：
    1. 重新套用被回滾的操作（使用 rollback_data）

    Args:
        operation: 原始操作物件
        target_path: 目標檔案路徑
        data_dir: 資料目錄根路徑
        yes: 是否自動確認
    """
    # 從 rollback_data 恢復被回滾的操作
    if not operation.rollback_data:
        raise ValueError("undo 操作缺少 rollback_data，無法回滾")

    console.print("[yellow]  警告: 回滾 undo 操作會重新執行原始操作[/yellow]")
    console.print(f"[dim]  原始操作類型: {operation.rollback_data.get('operation_type')}[/dim]")

    if not yes:
        if not Confirm.ask(
            "[yellow]確認重新執行原始操作?[/yellow]",
            default=False,
        ):
            console.print("[yellow]已取消回滾[/yellow]")
            raise typer.Exit(0)

    # 根據 rollback_data 恢復檔案
    restored_content = operation.rollback_data.get("content")
    if restored_content:
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Phase 1.3: 使用原子寫入
        _atomic_write_restored(restored_content, target_path)

        console.print(f"[dim]  恢復檔案: {target_path.name}[/dim]")
    else:
        console.print("[yellow]  警告: rollback_data 缺少 content，無法恢復檔案[/yellow]")


def _atomic_write_restored(content: Union[dict, str], target_path: Path) -> None:
    """原子寫入恢復內容

    Phase 1.3: 使用臨時檔案確保寫入的原子性。

    Args:
        content: 要恢復的內容（dict 或 str）
        target_path: 目標路徑
    """
    import os
    import tempfile

    # 使用臨時檔案
    fd, tmp_path = tempfile.mkstemp(
        suffix=target_path.suffix,
        prefix=".tmp_",
        dir=target_path.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            if target_path.suffix == ".json" and isinstance(content, dict):
                json.dump(content, f, indent=2, ensure_ascii=False)
            elif isinstance(content, dict):
                # 其他格式但 content 是 dict
                json.dump(content, f, indent=2, ensure_ascii=False)
            else:
                # 字串內容
                f.write(content)
        # 原子重命名
        os.replace(tmp_path, target_path)
    except Exception:
        # 清理臨時檔案
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _log_undo_operation(original_operation: Operation, data_dir: Path) -> None:
    """記錄 undo 操作到 operation log

    Args:
        original_operation: 被回滾的原始操作
        data_dir: 資料目錄根路徑
    """
    # 建立 undo 操作
    undo_operation = Operation(
        actor=getpass.getuser(),
        operation_type=OperationType.UNDO,
        target_path=original_operation.target_path,
        description=f"Undo operation: {str(original_operation.operation_id)[:8]}",
        metadata={
            "undone_operation_id": str(original_operation.operation_id),
            "undone_operation_type": original_operation.operation_type.value,
        },
        rollback_data={
            "operation_id": str(original_operation.operation_id),
            "operation_type": original_operation.operation_type.value,
            "target_path": str(original_operation.target_path),
            "description": original_operation.description,
        },
    )

    # 記錄到 operation log
    from life_capital.io.registry import OPERATION_LOG_FILE

    log_entry = OperationLogEntry(operation=undo_operation)
    log_path = data_dir / OPERATION_LOG_FILE
    append_operation_log(log_entry, log_path=log_path)

    console.print(
        f"[dim]  已記錄 undo 操作: {str(undo_operation.operation_id)[:8]}[/dim]"
    )
