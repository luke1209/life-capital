"""lc rebuild 指令實作

功能: 從 raw/ + canonical/ 重建 derived/

重建策略:
1. 清理目標 derived/ 子目錄
2. 從 canonical/ 讀取資料
3. 生成 reports（基本版本）
4. 記錄 operation log

冪等性保證:
- 使用確定性排序
- 固定時間戳格式
- 多次執行結果一致
"""

from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import typer
from rich.console import Console

from life_capital.io.registry import (
    DERIVED_DIR,
    DERIVED_REPORTS_DIR,
    DERIVED_SCENARIOS_DIR,
)
from life_capital.models.operation import Operation, OperationType
from life_capital.utils.path_resolver import resolve_data_dir

console = Console()


def rebuild(
    target: Literal["reports", "scenarios", "all"] = typer.Option(
        "all",
        "--target",
        help="重建目標 (reports|scenarios|all)",
    ),
    data_dir: Optional[Path] = typer.Option(
        None,
        "--data-dir",
        help="資料目錄路徑（預設: ~/.life-capital）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="預覽模式：顯示將清理/重建的檔案但不實際修改",
    ),
) -> None:
    """從 raw/ + canonical/ 重建 derived/

    重建流程:
    1. 清理目標 derived/ 子目錄
    2. 掃描 canonical/ 資料
    3. 生成 reports（月度現金流）
    4. 記錄 operation log

    範例:
        lc rebuild --target reports     # 只重建 reports
        lc rebuild --target scenarios   # 只重建 scenarios
        lc rebuild --target all         # 重建所有 derived/
        lc rebuild --dry-run            # 預覽將執行的操作

    使用 --dry-run 預覽將清理/重建的檔案但不實際修改。
    """
    # dry-run 模式提示
    if dry_run:
        console.print("[cyan]━━━ DRY-RUN 模式：僅預覽，不實際執行 ━━━[/cyan]")
        console.print()

    try:
        # 解析資料目錄
        data_root = resolve_data_dir(data_dir)

        # 護欄: 檢查 canonical/ 是否存在
        canonical_dir = data_root / "canonical"
        if not canonical_dir.exists():
            console.print(
                "[red]錯誤:[/red] canonical/ 目錄不存在，請先執行 lc init",
                style="bold red",
            )
            raise typer.Exit(1)

        if dry_run:
            # Dry-run 模式：只顯示預覽
            _preview_rebuild(data_root, target)
            console.print()
            console.print("[cyan]━━━ DRY-RUN 完成：以上為將執行的操作 ━━━[/cyan]")
            console.print("[yellow]移除 --dry-run 執行實際重建[/yellow]")
            return

        # Step 1: 清理目標目錄
        cleaned_count = _clean_derived(data_root, target)
        console.print(f"[green]✓[/green] 清理 derived/ 完成: {cleaned_count} 個檔案")

        # Step 2: 重建 reports
        if target in ("reports", "all"):
            report_count = _rebuild_reports(data_root)
            console.print(
                f"[green]✓[/green] 重建 reports 完成: {report_count} 個報表"
            )

        # Step 3: 重建 scenarios (Phase 0: Placeholder)
        if target in ("scenarios", "all"):
            _create_scenarios_placeholder(data_root)
            console.print("[yellow]ℹ[/yellow] Scenario 重建功能將在 Phase 2 實作")

        # Step 4: 記錄 operation
        _record_rebuild_operation(data_root, target)

        console.print("\n[bold green]✓ Rebuild 完成[/bold green]")

    except Exception as e:
        console.print(f"[red]錯誤:[/red] {e}", style="bold red")
        raise typer.Exit(1)


def _preview_rebuild(
    data_root: Path, target: Literal["reports", "scenarios", "all"]
) -> None:
    """顯示重建操作預覽（dry-run 模式）

    Args:
        data_root: 資料根目錄
        target: 重建目標
    """
    console.print("[bold cyan]重建操作預覽：[/bold cyan]")
    console.print()

    # 預覽 Step 1: 將清理的檔案
    console.print("[cyan]Step 1: 清理目標目錄[/cyan]")
    files_to_clean = []

    if target == "all":
        derived_dir = data_root / DERIVED_DIR
        if derived_dir.exists():
            for file_path in derived_dir.rglob("*"):
                if file_path.is_file():
                    files_to_clean.append(file_path)
    else:
        subdir_map = {
            "reports": DERIVED_REPORTS_DIR,
            "scenarios": DERIVED_SCENARIOS_DIR,
        }
        target_dir = data_root / subdir_map[target]
        if target_dir.exists():
            for file_path in target_dir.rglob("*"):
                if file_path.is_file():
                    files_to_clean.append(file_path)

    if files_to_clean:
        for f in files_to_clean[:5]:  # 只顯示前 5 個
            console.print(f"  [cyan]→ 將刪除: {f.relative_to(data_root)}[/cyan]")
        if len(files_to_clean) > 5:
            console.print(f"  [dim]... 還有 {len(files_to_clean) - 5} 個檔案[/dim]")
        console.print(f"  [dim]共 {len(files_to_clean)} 個檔案將被清理[/dim]")
    else:
        console.print("  [dim]（無檔案需要清理）[/dim]")

    # 預覽 Step 2: 將重建的 reports
    if target in ("reports", "all"):
        console.print()
        console.print("[cyan]Step 2: 重建 reports[/cyan]")
        report_path = data_root / DERIVED_REPORTS_DIR / "monthly_cashflow.yaml"
        console.print(f"  [cyan]→ 將生成: {report_path.relative_to(data_root)}[/cyan]")

    # 預覽 Step 3: Scenarios placeholder
    if target in ("scenarios", "all"):
        console.print()
        console.print("[cyan]Step 3: 重建 scenarios[/cyan]")
        placeholder_path = data_root / DERIVED_SCENARIOS_DIR / ".placeholder"
        console.print(f"  [cyan]→ 將生成: {placeholder_path.relative_to(data_root)}[/cyan]")
        console.print("  [dim]（Scenario 重建功能將在 Phase 2 實作）[/dim]")

    # 預覽 Step 4: Operation log
    console.print()
    console.print("[cyan]Step 4: 記錄 operation[/cyan]")
    console.print("  [cyan]→ 將記錄 rebuild 操作到 operation log[/cyan]")


def _clean_derived(
    data_root: Path, target: Literal["reports", "scenarios", "all"]
) -> int:
    """清理 derived/ 目標目錄

    Args:
        data_root: 資料根目錄
        target: 清理目標

    Returns:
        清理的檔案數量
    """
    cleaned_count = 0

    if target == "all":
        # 刪除整個 derived/ 目錄
        derived_dir = data_root / DERIVED_DIR
        if derived_dir.exists():
            for file_path in derived_dir.rglob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    cleaned_count += 1
            # 清理空目錄
            for dir_path in sorted(derived_dir.rglob("*"), reverse=True):
                if dir_path.is_dir() and not any(dir_path.iterdir()):
                    dir_path.rmdir()
    else:
        # 刪除特定子目錄
        subdir_map = {
            "reports": DERIVED_REPORTS_DIR,
            "scenarios": DERIVED_SCENARIOS_DIR,
        }
        target_dir = data_root / subdir_map[target]
        if target_dir.exists():
            for file_path in target_dir.rglob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    cleaned_count += 1
            # 清理空目錄
            for dir_path in sorted(target_dir.rglob("*"), reverse=True):
                if dir_path.is_dir() and not any(dir_path.iterdir()):
                    dir_path.rmdir()

    return cleaned_count


def _rebuild_reports(data_root: Path) -> int:
    """重建 reports（Phase 3: 使用 ReportGenerator）

    Contract 8: Rebuild 整合
    - 使用 Phase 3 的 ReportGenerator
    - 強制覆蓋（ignore cache）
    - 產出與 lc report 相同的 3 個固定報表

    Args:
        data_root: 資料根目錄

    Returns:
        生成的報表數量

    Raises:
        Exception: 若 Phase 2 輸出缺失或生成失敗
    """
    from life_capital.generation import (
        InputMissingError,
        ReportGenerator,
        load_comparison_from_derived,
        load_projection_from_derived,
    )

    try:
        # 載入 Phase 2 輸入（Contract 2: 唯一入口）
        projection = load_projection_from_derived(data_root)
        comparison = load_comparison_from_derived(data_root)

        # 建立報表生成器
        generator = ReportGenerator(data_root)

        # 生成所有報表（強制覆蓋，忽略 cache）
        reports = generator.generate_all(
            projection=projection,
            comparison=comparison,
            format="md",  # 預設使用 Markdown 格式
            save=True,  # 存檔到 derived/reports/
            force=True,  # 強制覆蓋（Contract 8: 不檢查 cache）
        )

        return len(reports)

    except InputMissingError:
        # Phase 2 輸出缺失 → 建立 placeholder（避免 rebuild 失敗）
        console.print(
            "[yellow]⚠[/yellow] Phase 2 輸出缺失，跳過 reports 重建"
        )
        console.print(
            "[yellow]提示:[/yellow] 執行 'lc project --save' 生成預測資料"
        )
        # 建立 placeholder 標記
        reports_dir = data_root / DERIVED_REPORTS_DIR
        reports_dir.mkdir(parents=True, exist_ok=True)
        placeholder_path = reports_dir / ".placeholder"
        placeholder_path.write_text(
            "# Phase 2 輸出缺失，跳過 reports 重建\n"
            "# 執行 'lc project --save' 生成預測資料\n",
            encoding="utf-8",
        )
        return 0


def _create_scenarios_placeholder(data_root: Path) -> None:
    """建立 scenarios placeholder

    Args:
        data_root: 資料根目錄
    """
    scenarios_dir = data_root / DERIVED_SCENARIOS_DIR
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    placeholder_path = scenarios_dir / ".placeholder"
    placeholder_path.write_text(
        "# Scenario 重建功能將在 Phase 2 實作\n# 此檔案僅作為目錄標記\n",
        encoding="utf-8",
    )


def _record_rebuild_operation(
    data_root: Path, target: Literal["reports", "scenarios", "all"]
) -> None:
    """記錄 rebuild operation

    Args:
        data_root: 資料根目錄
        target: 重建目標
    """
    from life_capital.io.canonical_handler import append_operation_log
    from life_capital.models.operation import OperationLogEntry

    operation = Operation(
        actor="cli",
        operation_type=OperationType.REBUILD,
        target_path=Path(DERIVED_DIR),
        description=f"Rebuild derived/ (target={target})",
        metadata={
            "rebuild_target": target,
            "timestamp": datetime.now().isoformat(),
        },
    )

    log_entry = OperationLogEntry(operation=operation)
    log_path = data_root / "canonical" / ".operation_log.jsonl"
    append_operation_log(log_entry, log_path=log_path)
