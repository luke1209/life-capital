"""init 指令

初始化專案資料目錄，複製範例檔案。
"""

import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from life_capital.io.raw_handler import save_raw_manifest
from life_capital.io.registry import (
    ASSUMPTIONS_FILE,
    EXPENSES_DIR,
    INCOME_FILE,
    POLICY_FILE,
    TARGETS_FILE,
)
from life_capital.utils.path_resolver import ensure_data_dir, resolve_data_dir

console = Console()


def get_examples_dir() -> Path:
    """取得範例檔案目錄"""
    # 相對於此檔案的位置
    return Path(__file__).parent.parent.parent / "docs" / "examples"


def init(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="強制覆寫已存在的檔案",
    ),
) -> None:
    """初始化 Life Capital 資料目錄

    複製範例檔案到資料目錄，讓你可以立即開始使用。
    """
    try:
        # 解析目標目錄
        data_dir = resolve_data_dir(path)
        examples_dir = get_examples_dir()

        # 檢查範例目錄是否存在
        if not examples_dir.exists():
            console.print(f"[red]錯誤: 找不到範例檔案目錄: {examples_dir}[/red]")
            raise typer.Exit(1)

        # 檢查目錄是否已存在
        if data_dir.exists() and not force:
            # 檢查是否有檔案
            existing_files = list(data_dir.glob("*.yaml"))
            if existing_files:
                console.print(
                    f"[yellow]警告: 目錄已存在且包含檔案: {data_dir}[/yellow]"
                )
                console.print("[yellow]使用 --force 強制覆寫[/yellow]")
                raise typer.Exit(1)

        # 建立目錄結構
        ensure_data_dir(path)
        console.print(f"[green]✓[/green] 建立資料目錄: {data_dir}")

        # 複製檔案列表
        files_to_copy = [
            (ASSUMPTIONS_FILE, ASSUMPTIONS_FILE),
            (TARGETS_FILE, TARGETS_FILE),
            (INCOME_FILE, INCOME_FILE),
            (POLICY_FILE, POLICY_FILE),
        ]

        # 複製 YAML 檔案
        for src_name, dst_name in files_to_copy:
            src = examples_dir / src_name
            dst = data_dir / dst_name

            if src.exists():
                shutil.copy2(src, dst)
                console.print(f"[green]✓[/green] 複製: {dst_name}")
            else:
                console.print(f"[yellow]⚠[/yellow] 找不到範例: {src_name}")

        # 複製支出範例
        expenses_src = examples_dir / "expenses_2025_01.csv"
        expenses_dst = data_dir / EXPENSES_DIR / "expenses_2025_01.csv"

        if expenses_src.exists():
            expenses_dst.parent.mkdir(exist_ok=True)
            shutil.copy2(expenses_src, expenses_dst)
            console.print(f"[green]✓[/green] 複製: {EXPENSES_DIR}/expenses_2025_01.csv")

        # 生成 raw_manifest.json（Phase 1 要求）
        try:
            import os
            import stat

            manifest_path = save_raw_manifest(data_dir)
            # 設為 read-only (444)
            os.chmod(manifest_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            console.print("[green]✓[/green] 生成: raw_manifest.json")
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] 生成 raw_manifest 失敗: {e}")

        # 顯示成功訊息
        console.print()
        console.print(
            Panel(
                f"[bold green]初始化完成！[/bold green]\n\n"
                f"資料目錄: [cyan]{data_dir}[/cyan]\n\n"
                f"[bold]下一步：[/bold]\n"
                f"  1. 編輯 [yellow]life_assumptions.yaml[/yellow] 設定你的基本資料\n"
                f"  2. 編輯 [yellow]lifetime_targets.yaml[/yellow] 設定財務目標\n"
                f"  3. 執行 [cyan]lc validate[/cyan] 驗證資料正確性\n"
                f"  4. 執行 [cyan]lc summary[/cyan] 查看財務總覽",
                title="Life Capital",
                border_style="green",
            )
        )

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)
