"""import 指令

匯入 CSV 檔案到 raw/imports/ 目錄。

Phase 1.5: 新增重複匯入偵測功能。
"""

import hashlib
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from life_capital.io.csv_handler import CSVParseError, DedupeMode, load_csv
from life_capital.io.raw_handler import (
    check_duplicate_import,
    save_raw_manifest,
    write_raw,
)
from life_capital.models.operation import Provenance, SourceType


def _compute_file_sha256(file_path: Path) -> str:
    """計算檔案的 SHA-256 hash"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

console = Console()


def import_csv(
    csv_path: str = typer.Argument(
        ...,
        help="CSV 檔案路徑",
    ),
    dedupe: DedupeMode = typer.Option(
        "exact",
        "--dedupe",
        help="去重模式：exact (完整 hash) 或 key (date+amount+category+payer+merchant)",
    ),
    parser_version: str = typer.Option(
        "1.0",
        "--parser-version",
        help="解析器版本（用於 Provenance 記錄）",
    ),
    data_dir: Optional[str] = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="強制匯入（跳過重複檢查）",
    ),
) -> None:
    """匯入 CSV 檔案到 raw/imports/ 目錄

    讀取支出 CSV 檔案，進行去重處理後寫入 raw/imports/ 目錄。
    每次匯入會建立新的 timestamped 檔案，並記錄 Provenance 資訊。

    範例：
        lc import expenses.csv
        lc import expenses.csv --dedupe key
        lc import expenses.csv --parser-version 1.1
        lc import expenses.csv --force  # 強制重新匯入
    """
    try:
        # 解析 CSV 路徑
        csv_file = Path(csv_path)
        if not csv_file.exists():
            console.print(f"[red]錯誤: 檔案不存在: {csv_path}[/red]")
            raise typer.Exit(1)

        # 解析資料目錄
        if data_dir:
            from life_capital.utils.path_resolver import resolve_data_dir

            base_dir = resolve_data_dir(data_dir)
        else:
            base_dir = None

        # 檢查重複匯入（Phase 1.5）
        if not force:
            dup_result = check_duplicate_import(csv_file, base_dir)
            if dup_result.is_duplicate:
                console.print(
                    "[yellow]警告: 此 CSV 已匯入過[/yellow]"
                )
                console.print(
                    f"  已存在檔案: [cyan]{dup_result.existing_file}[/cyan]"
                )
                console.print(
                    f"  檔案 hash: [dim]{dup_result.existing_hash[:16]}...[/dim]"
                )
                console.print()
                console.print(
                    "[yellow]使用 --force 或 -f 強制重新匯入[/yellow]"
                )
                raise typer.Exit(1)

        # 顯示匯入資訊
        console.print(f"[cyan]正在匯入:[/cyan] {csv_file}")
        console.print(f"[cyan]去重模式:[/cyan] {dedupe}")

        # 讀取 CSV
        try:
            records, duplicates = load_csv(csv_file, dedupe=dedupe)
        except CSVParseError as e:
            console.print(f"[red]CSV 解析錯誤: {e}[/red]")
            raise typer.Exit(1)

        # 顯示讀取統計
        total_rows = len(records) + duplicates
        console.print("\n[green]✓[/green] CSV 讀取完成")
        console.print(f"  總行數: {total_rows}")
        console.print(f"  有效記錄: {len(records)}")

        if duplicates > 0:
            console.print(f"  [yellow]跳過重複: {duplicates}[/yellow]")

        # 檢查是否有資料
        if len(records) == 0:
            console.print("[yellow]警告: 沒有有效記錄可匯入[/yellow]")
            raise typer.Exit(0)

        # 計算原始檔案 hash（用於重複匯入偵測）
        source_hash = _compute_file_sha256(csv_file)

        # 建立 Provenance（包含 source_hash）
        provenance = Provenance(
            source_type=SourceType.CSV_IMPORT,
            parser_version=parser_version,
            source_hash=source_hash,
        )

        # 準備寫入資料
        # 將 ExpenseRecord 列表轉換為可序列化的字典格式
        data = {
            "headers": ["date", "amount", "category", "payer", "note", "merchant"],
            "rows": [record.to_csv_row() for record in records],
        }

        # 寫入 raw/imports/
        try:
            written_path = write_raw(
                data=data,
                target="imports",
                provenance=provenance,
                format="csv",
                base_dir=base_dir,
            )

            console.print("\n[green]✓[/green] 匯入成功")
            console.print(f"  寫入檔案: [cyan]{written_path}[/cyan]")
            console.print(f"  來源 ID: [dim]{provenance.source_id}[/dim]")
            console.print(f"  匯入時間: [dim]{provenance.import_time.isoformat()}[/dim]")

            # 更新 raw_manifest.json（Phase 1.5）
            try:
                save_raw_manifest(base_dir)
                console.print("  manifest: [dim]已更新[/dim]")
            except Exception as e:
                console.print(f"  [yellow]警告: manifest 更新失敗: {e}[/yellow]")

        except Exception as e:
            console.print(f"[red]寫入失敗: {e}[/red]")
            raise typer.Exit(1)

        # 顯示摘要
        console.print(
            f"\n[bold green]✓ 成功匯入 {len(records)} 筆記錄[/bold green]"
        )

        if duplicates > 0:
            console.print(
                f"[dim]（{duplicates} 筆重複記錄已跳過，使用 {dedupe} 去重模式）[/dim]"
            )

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]錯誤: {e}[/red]")
        raise typer.Exit(1)
