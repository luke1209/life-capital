"""apply 指令 (Phase 1.3)

從 proposals/pending/ 套用變更到 canonical/

支援兩種模式：
1. 傳統模式：YAML/JSON proposals → canonical/ (YAML/JSON)
2. JSONL 模式：CSV proposals → canonical/expenses/*.jsonl (Transaction)
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from life_capital.io.canonical_handler import (
    append_operation_log,
    write_canonical,
)
from life_capital.io.registry import (
    OPERATION_LOG_FILE,
    PROPOSALS_DIR,
    PROPOSALS_PENDING_DIR,
)
from life_capital.models.operation import Operation, OperationLogEntry
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def apply(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="確認套用變更（必填，避免誤操作）",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="自動確認所有提示（非互動模式）",
    ),
    proposal_id: Optional[str] = typer.Option(
        None,
        "--proposal-id",
        help="指定 proposal ID（若未指定則列出所有待確認的 proposals）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="預覽模式：顯示將執行的操作但不實際修改",
    ),
) -> None:
    """從 proposals/ 套用變更到 canonical/

    此指令會：
    1. 列出待確認的 proposals（或處理指定的 proposal）
    2. 顯示變更預覽
    3. 套用變更到 canonical/
    4. 移動 proposal 到 proposals/applied/

    使用 --dry-run 預覽將執行的操作但不實際修改。
    """
    # 護欄：必須 --confirm 或 --dry-run 才能執行
    if not confirm and not dry_run:
        console.print("[red]錯誤: 必須使用 --confirm 旗標才能套用變更[/red]")
        console.print("[yellow]範例: lc apply --confirm[/yellow]")
        console.print("[yellow]      lc apply --confirm --proposal-id <id>[/yellow]")
        console.print("[yellow]      lc apply --dry-run  (預覽模式)[/yellow]")
        raise typer.Exit(1)

    # dry-run 模式提示
    if dry_run:
        console.print("[cyan]━━━ DRY-RUN 模式：僅預覽，不實際執行 ━━━[/cyan]")
        console.print()

    data_dir = resolve_data_dir(path)
    pending_dir = data_dir / PROPOSALS_PENDING_DIR

    # 檢查 proposals/pending/ 目錄是否存在
    if not pending_dir.exists():
        console.print(f"[yellow]提示: {PROPOSALS_PENDING_DIR} 目錄不存在[/yellow]")
        console.print("[yellow]沒有待確認的 proposals[/yellow]")
        raise typer.Exit(0)

    # 掃描 pending proposals
    proposal_files = list(pending_dir.glob("*.json"))

    if not proposal_files:
        console.print("[green]✓ 沒有待確認的 proposals[/green]")
        raise typer.Exit(0)

    # 若指定 proposal_id，過濾
    if proposal_id:
        proposal_files = [
            f for f in proposal_files if f.stem.startswith(proposal_id)
        ]
        if not proposal_files:
            console.print(f"[red]錯誤: 找不到 proposal ID: {proposal_id}[/red]")
            raise typer.Exit(1)

    # 顯示 proposal 清單
    _show_proposals_table(proposal_files)

    # 處理每個 proposal
    for proposal_file in proposal_files:
        _process_proposal(proposal_file, data_dir, yes=yes, dry_run=dry_run)

    console.print()
    if dry_run:
        console.print(
            f"[cyan]━━━ DRY-RUN 完成：{len(proposal_files)} 個 proposals 待套用 ━━━[/cyan]"
        )
        console.print("[yellow]使用 --confirm 執行實際套用[/yellow]")
    else:
        console.print(f"[green]✓ 成功套用 {len(proposal_files)} 個 proposals[/green]")


def _show_proposals_table(proposal_files: list[Path]) -> None:
    """顯示待確認 proposals 清單"""
    table = Table(
        title="[bold]待確認 Proposals[/bold]",
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Proposal ID", style="bold")
    table.add_column("Operation Type", justify="center")
    table.add_column("Target Path")
    table.add_column("Description")
    table.add_column("Created At", justify="center")

    for proposal_file in proposal_files:
        try:
            with open(proposal_file, "r", encoding="utf-8") as f:
                proposal_data = json.load(f)

            operation = proposal_data.get("operation", {})
            proposal_id = operation.get("operation_id", "N/A")[:8]
            operation_type = operation.get("operation_type", "N/A")
            target_path = operation.get("target_path", "N/A")
            description = operation.get("description", "N/A")
            created_at = operation.get("created_at", "N/A")

            # 格式化時間
            if created_at != "N/A":
                try:
                    dt = datetime.fromisoformat(created_at)
                    created_at = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass

            table.add_row(
                proposal_id,
                operation_type,
                target_path,
                description,
                created_at,
            )
        except Exception as e:
            console.print(f"[yellow]警告: 無法讀取 {proposal_file.name}: {e}[/yellow]")
            continue

    console.print()
    console.print(table)
    console.print()


def _process_proposal(
    proposal_file: Path, data_dir: Path, yes: bool = False, dry_run: bool = False
) -> None:
    """處理單個 proposal

    Args:
        proposal_file: Proposal JSON 檔案路徑
        data_dir: 資料目錄根路徑
        yes: 是否自動確認（非互動模式）
        dry_run: 是否為預覽模式（不實際執行）

    Raises:
        typer.Exit: 處理失敗時退出
    """
    try:
        # 載入 proposal
        with open(proposal_file, "r", encoding="utf-8") as f:
            proposal_data = json.load(f)

        # 解析 Operation
        operation_dict = proposal_data.get("operation")
        if not operation_dict:
            console.print(f"[red]錯誤: {proposal_file.name} 缺少 operation 欄位[/red]")
            raise typer.Exit(1)

        operation = Operation.model_validate(operation_dict)

        # 解析資料內容
        data_content = proposal_data.get("data")
        if not data_content:
            console.print(f"[red]錯誤: {proposal_file.name} 缺少 data 欄位[/red]")
            raise typer.Exit(1)

        # 顯示詳細資訊
        _show_proposal_details(operation, data_content, proposal_file)

        # 準備目標路徑
        target_path = data_dir / operation.target_path

        # Dry-run 模式：只顯示預覽，不實際執行
        if dry_run:
            console.print(f"[cyan]  → 將寫入: {target_path}[/cyan]")
            if target_path.exists():
                console.print("[cyan]  → 將覆寫現有檔案[/cyan]")
            console.print("[cyan]  → 將移動 proposal 到 applied/[/cyan]")
            console.print("[dim]  （dry-run 跳過實際執行）[/dim]")
            return

        # 詢問確認（除非使用 --yes）
        if not yes:
            if not Confirm.ask(
                f"[yellow]確認套用此 proposal? ({proposal_file.stem[:8]})[/yellow]",
                default=False,
            ):
                console.print("[yellow]跳過此 proposal[/yellow]")
                return
        else:
            console.print(f"[dim]自動確認套用 proposal: {proposal_file.stem[:8]}[/dim]")

        # 檢查檔案是否已存在
        if target_path.exists():
            if not yes:
                overwrite = Confirm.ask(
                    f"[yellow]目標檔案已存在: {target_path}\n是否覆寫?[/yellow]",
                    default=False,
                )
                if not overwrite:
                    console.print("[yellow]跳過此 proposal[/yellow]")
                    return
            else:
                console.print(f"[dim]目標檔案已存在，自動覆寫: {target_path.name}[/dim]")

        # 更新 created_at 為當前時間（確保與檔案 mtime 一致，通過 bypass 偵測）
        operation = operation.model_copy(update={"created_at": datetime.now()})

        # 寫入 canonical/（使用原始字典資料）
        _write_proposal_to_canonical(data_content, target_path, operation, data_dir)

        # 移動 proposal 到 applied/
        _move_to_applied(proposal_file, data_dir)

        console.print(f"[green]✓ 已套用: {proposal_file.stem[:8]}[/green]")

    except Exception as e:
        console.print(f"[red]錯誤: 處理 {proposal_file.name} 失敗: {e}[/red]")
        raise typer.Exit(1)


def _show_proposal_details(
    operation: Operation, data_content: dict, proposal_file: Path
) -> None:
    """顯示 proposal 詳細資訊"""
    # 操作資訊面板
    info_lines = [
        f"[bold]Proposal ID:[/bold] {str(operation.operation_id)[:8]}...",
        f"[bold]Operation Type:[/bold] {operation.operation_type.value}",
        f"[bold]Target Path:[/bold] {operation.target_path}",
        f"[bold]Description:[/bold] {operation.description}",
        f"[bold]Actor:[/bold] {operation.actor}",
        f"[bold]Created At:[/bold] {operation.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    console.print()
    console.print(Panel(
        "\n".join(info_lines),
        title="[bold blue]Proposal Details[/bold blue]",
        border_style="blue",
    ))

    # 資料預覽（YAML 格式）
    console.print()
    console.print("[bold]Data Preview:[/bold]")
    console.print("[dim]" + "─" * 60 + "[/dim]")

    # 將 data_content 轉為 YAML 格式顯示
    yaml_preview = yaml.dump(
        data_content,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    # 限制預覽行數
    preview_lines = yaml_preview.split("\n")[:20]
    console.print("\n".join(preview_lines))

    if len(yaml_preview.split("\n")) > 20:
        console.print("[dim]... (省略部分內容)[/dim]")

    console.print("[dim]" + "─" * 60 + "[/dim]")


def _write_proposal_to_canonical(
    data_content: dict, target_path: Path, operation: Operation, data_dir: Path
) -> None:
    """將 proposal 資料寫入 canonical/

    Phase 1.3: 使用 canonical_handler API，確保所有寫入經過追蹤。

    Args:
        data_content: 資料內容字典
        target_path: 目標路徑
        operation: 操作物件
        data_dir: 資料目錄根路徑（用於 operation log）

    Raises:
        ValueError: 不支援的檔案格式或資料類型
        CanonicalError: 寫入失敗
    """
    from life_capital.models.expense import MonthlyExpenses

    log_path = data_dir / OPERATION_LOG_FILE

    # 根據目標路徑判斷資料類型並使用對應的 Pydantic 模型
    if target_path.suffix == ".yaml" and "expenses" in str(target_path):
        # 支出資料：轉換為 MonthlyExpenses 模型
        monthly_expenses = MonthlyExpenses.model_validate(data_content)

        # 使用 canonical_handler API 寫入（包含 operation log 記錄）
        write_canonical(
            data=monthly_expenses,
            target_path=target_path,
            operation=operation,
            log_path=log_path,
        )

    elif target_path.suffix == ".json":
        # JSON 格式：使用原子寫入（未來擴充）
        _atomic_write_json(data_content, target_path)

        # 記錄 operation log
        log_entry = OperationLogEntry(operation=operation)
        append_operation_log(log_entry, log_path=log_path)

    else:
        raise ValueError(f"不支援的檔案格式或資料類型: {target_path}")


def _atomic_write_json(data: dict, target_path: Path) -> None:
    """原子寫入 JSON 檔案

    使用臨時檔案確保寫入的原子性。

    Args:
        data: 資料字典
        target_path: 目標路徑
    """
    import os
    import tempfile

    # 使用臨時檔案
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        prefix=".tmp_",
        dir=target_path.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # 原子重命名
        os.replace(tmp_path, target_path)
    except Exception:
        # 清理臨時檔案
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _move_to_applied(proposal_file: Path, data_dir: Path) -> None:
    """移動 proposal 到 applied/ 目錄

    Args:
        proposal_file: Proposal 檔案路徑
        data_dir: 資料目錄根路徑
    """
    applied_dir = data_dir / PROPOSALS_DIR / "applied"
    applied_dir.mkdir(parents=True, exist_ok=True)

    dest_path = applied_dir / proposal_file.name
    shutil.move(str(proposal_file), str(dest_path))

    console.print(f"[dim]  已移動到: {dest_path.relative_to(data_dir)}[/dim]")
