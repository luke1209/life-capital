"""doctor 指令

MVP 最小版環境檢查：
- Python 版本
- data dir 可寫
- YAML 可讀取
- validate 可跑通

Phase 0 擴展檢查：
- 資料三層結構完整性
- operation log 完整性
- bypass 繞過偵測
- raw/ read-only 檢查
- derived/ 可重建提示
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from life_capital.commands import validate as validate_cmd
from life_capital.io import canonical_handler
from life_capital.io.registry import (
    ALLOWED_DEDUPE_KEY_VERSIONS,
    CANONICAL_DECISIONS_DIR,
    CANONICAL_DIR,
    CANONICAL_EXPENSES_DIR,
    CURRENT_SCHEMA_VERSION,
    DERIVED_DIR,
    DERIVED_REPORTS_DIR,
    DERIVED_SCENARIOS_DIR,
    OPERATION_LOG_FILE,
    RAW_DIR,
    RAW_IMPORTS_DIR,
    RAW_MANIFEST_FILE,
    RAW_MANUAL_DIR,
)
from life_capital.utils.path_resolver import resolve_data_dir, validate_data_dir

console = Console()


def _check_directory_structure(data_root: Path) -> tuple[bool, list[str]]:
    """檢查資料三層結構完整性"""
    ok = True
    lines = []

    # 建立目錄樹視圖
    tree = Tree("📁 資料目錄結構", guide_style="dim")

    # 定義必要目錄
    required_dirs = [
        (RAW_DIR, [RAW_IMPORTS_DIR, RAW_MANUAL_DIR]),
        (CANONICAL_DIR, [CANONICAL_EXPENSES_DIR, CANONICAL_DECISIONS_DIR]),
        (DERIVED_DIR, [DERIVED_REPORTS_DIR, DERIVED_SCENARIOS_DIR]),
    ]

    for parent_dir, subdirs in required_dirs:
        parent_path = data_root / parent_dir
        parent_exists = parent_path.exists()

        # 父目錄節點
        parent_node = tree.add(
            f"{'[green]✓[/green]' if parent_exists else '[red]✗[/red]'} {parent_dir}/"
        )

        if parent_exists:
            # 統計檔案數量
            file_count = len(
                [f for f in parent_path.rglob("*") if f.is_file() and not f.name.startswith(".")]
            )
            parent_node.add(f"[dim]({file_count} 個檔案)[/dim]")

        # 子目錄節點
        for subdir in subdirs:
            subdir_path = data_root / subdir
            subdir_exists = subdir_path.exists()

            if not subdir_exists:
                ok = False

            subdir_name = subdir.split("/")[-1]
            status = "[green]✓[/green]" if subdir_exists else "[red]✗[/red]"
            subdir_node = parent_node.add(f"{status} {subdir_name}/")

            if subdir_exists:
                file_count = len(
                    [
                        f
                        for f in subdir_path.rglob("*")
                        if f.is_file() and not f.name.startswith(".")
                    ]
                )
                subdir_node.add(f"[dim]({file_count} 個檔案)[/dim]")

    console.print(tree)

    if ok:
        lines.append("[green]✓[/green] 資料三層結構完整")
    else:
        lines.append("[red]✗[/red] 資料三層結構不完整（請執行 lc init）")

    return ok, lines


def _check_operation_log(data_root: Path) -> tuple[bool, list[str]]:
    """檢查 operation log 完整性"""
    ok = True
    lines = []

    log_path = data_root / OPERATION_LOG_FILE

    if not log_path.exists():
        lines.append("[yellow]⚠[/yellow] operation log 不存在（尚未有 canonical 寫入操作）")
        return ok, lines

    # 讀取並驗證 JSONL 格式
    corrupted_lines = []
    total_operations = 0
    recent_operations = []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    total_operations += 1

                    # 收集最近 5 筆操作
                    if len(recent_operations) < 5:
                        recent_operations.append(entry)
                except json.JSONDecodeError:
                    corrupted_lines.append(line_num)

        # 建立摘要表格
        table = Table(title="Operation Log 摘要", show_header=True, header_style="bold cyan")
        table.add_column("項目", style="dim")
        table.add_column("數值")

        table.add_row("總操作數量", str(total_operations))
        table.add_row("損壞行數", str(len(corrupted_lines)))
        table.add_row("最近操作", str(len(recent_operations)))

        console.print(table)

        # 顯示最近 5 筆操作
        if recent_operations:
            recent_table = Table(
                title="最近 5 筆操作", show_header=True, header_style="bold yellow"
            )
            recent_table.add_column("時間", style="dim")
            recent_table.add_column("類型")
            recent_table.add_column("路徑")

            for entry in recent_operations:
                op = entry.get("operation", {})
                recent_table.add_row(
                    op.get("created_at", "N/A")[:19],  # 顯示到秒
                    op.get("operation_type", "N/A"),
                    str(op.get("target_path", "N/A")),
                )

            console.print(recent_table)

        if corrupted_lines:
            ok = False
            lines.append(f"[red]✗[/red] operation log 有 {len(corrupted_lines)} 行損壞")
        else:
            lines.append("[green]✓[/green] operation log 格式正確")

    except Exception as e:
        ok = False
        lines.append(f"[red]✗[/red] operation log 讀取失敗: {e}")

    return ok, lines


def _check_bypass_detection(data_root: Path) -> tuple[bool, list[str]]:
    """檢查 bypass 繞過偵測（Hard Fail）"""
    ok = True
    lines = []

    try:
        bypass_files = canonical_handler.detect_bypass(data_root)

        if bypass_files:
            ok = False
            bypass_list = "\n  - ".join(str(p.relative_to(data_root)) for p in bypass_files)

            # 使用 Panel 顯示警告
            console.print(
                Panel(
                    f"[bold red]偵測到繞過 canonical_handler 的直接修改！[/bold red]\n\n"
                    f"疑似繞過檔案:\n  - {bypass_list}\n\n"
                    f"[yellow]請使用 canonical_handler.write_canonical() 進行所有修改[/yellow]",
                    title="🚨 Bypass Detection",
                    border_style="red",
                )
            )

            lines.append(f"[red]✗[/red] 偵測到 {len(bypass_files)} 個繞過檔案（Hard Fail）")
        else:
            lines.append("[green]✓[/green] 未偵測到繞過寫入")

    except Exception as e:
        lines.append(f"[yellow]⚠[/yellow] bypass 檢查失敗: {e}")

    return ok, lines


def _check_raw_readonly(data_root: Path) -> tuple[bool, list[str]]:
    """檢查 raw/ read-only 權限（Soft Warning）"""
    lines = []

    raw_dir = data_root / RAW_DIR
    if not raw_dir.exists():
        lines.append("[yellow]⚠[/yellow] raw/ 目錄不存在")
        return True, lines

    non_readonly_files = []

    for file_path in raw_dir.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            file_mode = file_path.stat().st_mode
            # 檢查是否為 read-only (444 or r--r--r--)
            if file_mode & stat.S_IWUSR or file_mode & stat.S_IWGRP or file_mode & stat.S_IWOTH:
                non_readonly_files.append(file_path)

    if non_readonly_files:
        files_list = "\n  - ".join(str(p.relative_to(data_root)) for p in non_readonly_files)
        console.print(
            Panel(
                f"[yellow]以下檔案不是 read-only：[/yellow]\n  - {files_list}\n\n"
                f"[dim]建議設為 read-only 以防止意外修改[/dim]",
                title="⚠️  Raw Directory Permissions",
                border_style="yellow",
            )
        )
        lines.append(f"[yellow]⚠[/yellow] {len(non_readonly_files)} 個檔案不是 read-only")
    else:
        lines.append("[green]✓[/green] raw/ 所有檔案為 read-only")

    return True, lines  # Soft warning，不影響 ok 狀態


def _check_raw_manifest(data_root: Path) -> tuple[bool, list[str]]:
    """檢查 raw_manifest.json 存在與一致性（Phase 1）

    Hard Check: manifest 中記錄的檔案必須與實際檔案 hash 一致
    """
    from life_capital.io.raw_handler import (
        load_raw_manifest,
        verify_raw_manifest,
    )

    ok = True
    lines = []

    manifest_path = data_root / RAW_MANIFEST_FILE

    if not manifest_path.exists():
        # manifest 不存在時生成建議
        console.print(
            Panel(
                "[yellow]raw_manifest.json 不存在[/yellow]\n\n"
                "[dim]建議執行: lc init（會自動生成 manifest）[/dim]",
                title="⚠️ Raw Manifest",
                border_style="yellow",
            )
        )
        lines.append("[yellow]⚠[/yellow] raw_manifest.json 不存在（建議執行 lc init）")
        return ok, lines

    # 載入並驗證 manifest
    try:
        manifest = load_raw_manifest(data_root)
        result = verify_raw_manifest(data_root)

        if result.passed:
            console.print(
                Panel(
                    f"[green]raw_manifest.json 驗證通過[/green]\n\n"
                    f"  - 記錄檔案數: {len(manifest.get('files', []))}\n"
                    f"  - 生成時間: {manifest.get('generated_at', 'N/A')}",
                    title="✅ Raw Manifest",
                    border_style="green",
                )
            )
            lines.append(f"[green]✓[/green] {result.message}")
        else:
            ok = False
            all_issues = result.modified_files + result.missing_files + result.new_files
            issue_list = "\n  - ".join(str(f) for f in all_issues[:5])
            if len(all_issues) > 5:
                issue_list += f"\n  ... 還有 {len(all_issues) - 5} 個檔案"

            console.print(
                Panel(
                    f"[red]raw/ 內容與 manifest 不一致！[/red]\n\n"
                    f"問題檔案:\n  - {issue_list}\n\n"
                    f"[yellow]raw/ 應該是不可變的，請檢查是否有意外修改[/yellow]",
                    title="🚨 Raw Immutable Violation",
                    border_style="red",
                )
            )
            lines.append(f"[red]✗[/red] {result.message}")

    except Exception as e:
        lines.append(f"[yellow]⚠[/yellow] raw_manifest 驗證失敗: {e}")

    return ok, lines


def _check_schema_version(data_root: Path) -> tuple[bool, list[str]]:
    """檢查 Schema 版本一致性（Phase 1）"""
    from life_capital.io.migration import check_schema_version, needs_migration

    ok = True
    lines = []

    try:
        version_map = check_schema_version(data_root)

        if not version_map:
            lines.append("[yellow]⚠[/yellow] 沒有 canonical/ 檔案需要檢查")
            return ok, lines

        # 建立版本分佈表
        table = Table(
            title="Schema 版本分佈",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("版本", style="bold")
        table.add_column("檔案數", justify="right")
        table.add_column("狀態")

        for version, files in sorted(version_map.items()):
            if version == CURRENT_SCHEMA_VERSION:
                status = "[green]✅ 當前版本[/green]"
            elif version == "unknown":
                status = "[yellow]⚠️ 無版本標記[/yellow]"
            else:
                status = "[red]❌ 需遷移[/red]"

            table.add_row(version, str(len(files)), status)

        console.print(table)

        # 檢查是否需要遷移
        needs, reason, outdated = needs_migration(data_root)

        if needs:
            lines.append(f"[yellow]⚠[/yellow] {reason}")
            lines.append("[dim]  建議: lc migrate run --confirm[/dim]")
        else:
            lines.append(f"[green]✓[/green] {reason}")

    except Exception as e:
        lines.append(f"[yellow]⚠[/yellow] Schema 版本檢查失敗: {e}")

    return ok, lines


def _check_dedupe_key_version(data_root: Path) -> tuple[bool, list[str]]:
    """檢查 dedupe_key_version 可治理性（Phase 1）

    Hard Check: 版本必須在 ALLOWED_VERSIONS 內
    Soft Check: 混版本警告，提示 lc migrate --rekey
    """
    ok = True
    lines = []

    canonical_expenses = data_root / CANONICAL_EXPENSES_DIR

    if not canonical_expenses.exists():
        lines.append("[yellow]⚠[/yellow] canonical/expenses/ 不存在，跳過檢查")
        return ok, lines

    # 掃描所有 JSONL 檔案中的 dedupe_key_version
    versions_found: dict[str, int] = {}
    unknown_versions: list[str] = []
    files_checked = 0

    for jsonl_file in canonical_expenses.glob("*.jsonl"):
        files_checked += 1
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                        version = data.get("dedupe_key_version", "unknown")

                        if version not in versions_found:
                            versions_found[version] = 0
                        versions_found[version] += 1

                        # Hard Check: 版本必須在允許集合內
                        if version not in ALLOWED_DEDUPE_KEY_VERSIONS:
                            unknown_versions.append(f"{jsonl_file.name}:{line_num}")
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    if files_checked == 0:
        lines.append("[yellow]⚠[/yellow] 沒有 JSONL 檔案需要檢查")
        return ok, lines

    # 顯示版本分佈
    if versions_found:
        table = Table(
            title="Dedupe Key Version 分佈",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("版本", style="bold")
        table.add_column("記錄數", justify="right")
        table.add_column("狀態")

        for version, count in sorted(versions_found.items()):
            if version in ALLOWED_DEDUPE_KEY_VERSIONS:
                status = "[green]✅ 允許[/green]"
            else:
                status = "[red]❌ 不允許[/red]"

            table.add_row(version, str(count), status)

        console.print(table)

    # Hard Check: 未知版本
    if unknown_versions:
        ok = False
        unknown_list = ", ".join(unknown_versions[:5])
        if len(unknown_versions) > 5:
            unknown_list += f" ... 還有 {len(unknown_versions) - 5} 筆"

        lines.append(f"[red]✗[/red] 發現 {len(unknown_versions)} 筆未知版本（Hard Fail）")
        lines.append(f"[dim]  位置: {unknown_list}[/dim]")
    else:
        lines.append("[green]✓[/green] 所有 dedupe_key_version 在允許範圍內")

    # Soft Check: 混版本警告
    valid_versions = {v for v in versions_found.keys() if v in ALLOWED_DEDUPE_KEY_VERSIONS}
    if len(valid_versions) > 1:
        lines.append(f"[yellow]⚠[/yellow] 發現混合版本: {', '.join(sorted(valid_versions))}")
        lines.append("[dim]  建議: lc migrate --rekey 統一版本[/dim]")

    return ok, lines


def _check_migration_status(data_root: Path) -> tuple[bool, list[str]]:
    """檢查遷移狀態（僅提示，不影響 ok）"""
    from life_capital.io.migration import get_migration_status

    lines = []

    try:
        status = get_migration_status(data_root)

        if status["needs_migration"]:
            console.print(
                Panel(
                    f"[yellow]需要遷移:[/yellow] {status['migration_reason']}\n\n"
                    f"  - 待遷移檔案: {status['outdated_file_count']} 個\n\n"
                    f"[dim]執行: lc migrate run --confirm[/dim]",
                    title="⚠️ Migration Needed",
                    border_style="yellow",
                )
            )
            lines.append(f"[yellow]⚠[/yellow] {status['migration_reason']}")
        else:
            lines.append("[green]✓[/green] 不需要遷移")

        # 顯示最近遷移
        if status["last_migration"]:
            last = status["last_migration"]
            lines.append(
                f"[dim]最近遷移: {last['migration_id'][:8]} "
                f"({last['status']})[/dim]"
            )

    except Exception as e:
        lines.append(f"[yellow]⚠[/yellow] 遷移狀態檢查失敗: {e}")

    return True, lines  # 不影響 ok


def _check_derived_rebuild_hint(data_root: Path) -> tuple[bool, list[str]]:
    """提示 derived/ 可重建檢查"""
    lines = []

    derived_dir = data_root / DERIVED_DIR
    if not derived_dir.exists():
        lines.append("[yellow]⚠[/yellow] derived/ 目錄不存在")
        return True, lines

    # 統計檔案數量和最新更新時間
    file_count = 0
    latest_mtime = None

    for file_path in derived_dir.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith("."):
            file_count += 1
            mtime = file_path.stat().st_mtime
            if latest_mtime is None or mtime > latest_mtime:
                latest_mtime = mtime

    # 顯示狀態
    from datetime import datetime

    if latest_mtime:
        latest_time = datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M:%S")
    else:
        latest_time = "N/A"

    console.print(
        Panel(
            f"[cyan]Derived 目錄狀態：[/cyan]\n"
            f"  - 檔案數量: {file_count}\n"
            f"  - 最新更新: {latest_time}\n\n"
            f"[dim]💡 建議定期執行 `lc rebuild` 驗證可重建性[/dim]",
            title="♻️  Derived Directory",
            border_style="cyan",
        )
    )

    lines.append("[cyan]ℹ[/cyan] derived/ 可重建提示已顯示")

    return True, lines


def doctor(
    path: Optional[str] = typer.Option(
        None,
        "--path",
        "-p",
        help="資料目錄路徑（預設：~/.life-capital/）",
    ),
) -> None:
    """環境與資料完整性檢查"""
    ok = True
    lines: list[str] = []

    # === MVP 基本檢查 ===
    console.print("\n[bold cyan]═══ MVP 環境檢查 ═══[/bold cyan]\n")

    # 1) Python 版本
    required = (3, 9)
    current = sys.version_info[:3]
    if current < required:
        ok = False
        lines.append(
            f"[red]✗[/red] Python {required[0]}.{required[1]}+"
            f"（目前 {current[0]}.{current[1]}.{current[2]}）"
        )
    else:
        lines.append(f"[green]✓[/green] Python {current[0]}.{current[1]}.{current[2]}")

    # 2) data dir 可寫
    valid, message = validate_data_dir(path)
    if not valid:
        ok = False
        lines.append(f"[red]✗[/red] data dir 不可用：{message}")
    else:
        lines.append("[green]✓[/green] data dir 可用")

    # 3) validate 可跑通
    try:
        validate_cmd.validate(path=path, verbose=False)
        lines.append("[green]✓[/green] lc validate 可跑通")
    except typer.Exit as e:
        code = int(getattr(e, "exit_code", 1) or 1)
        if code != 0:
            ok = False
            lines.append("[red]✗[/red] lc validate 失敗（請先修正資料或執行 lc init）")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold]MVP 基本檢查[/bold]",
            border_style="green" if ok else "red",
        )
    )

    # === Phase 0 資料完整性檢查 ===
    console.print("\n[bold cyan]═══ Phase 0 資料完整性檢查 ═══[/bold cyan]\n")

    data_root = resolve_data_dir(path)
    phase0_lines: list[str] = []

    # 1) 資料三層結構檢查
    console.print("[bold]1. 資料三層結構檢查[/bold]\n")
    struct_ok, struct_lines = _check_directory_structure(data_root)
    ok = ok and struct_ok
    phase0_lines.extend(struct_lines)

    # 2) operation log 完整性
    console.print("\n[bold]2. Operation Log 完整性[/bold]\n")
    log_ok, log_lines = _check_operation_log(data_root)
    ok = ok and log_ok
    phase0_lines.extend(log_lines)

    # 3) bypass 繞過偵測（Hard Fail）
    console.print("\n[bold]3. Bypass 繞過偵測[/bold]\n")
    bypass_ok, bypass_lines = _check_bypass_detection(data_root)
    ok = ok and bypass_ok
    phase0_lines.extend(bypass_lines)

    # 4) raw/ read-only 檢查（Soft Warning）
    console.print("\n[bold]4. Raw Directory Read-Only 檢查[/bold]\n")
    readonly_ok, readonly_lines = _check_raw_readonly(data_root)
    # readonly_ok 不影響總體 ok（Soft Warning）
    phase0_lines.extend(readonly_lines)

    # 5) derived/ 可重建提示
    console.print("\n[bold]5. Derived Directory 可重建提示[/bold]\n")
    rebuild_ok, rebuild_lines = _check_derived_rebuild_hint(data_root)
    # rebuild_ok 不影響總體 ok（僅提示）
    phase0_lines.extend(rebuild_lines)

    console.print(
        Panel(
            "\n".join(phase0_lines),
            title="[bold]Phase 0 資料完整性[/bold]",
            border_style="green" if ok else "red",
        )
    )

    # === Phase 1 DATA 強化檢查 ===
    console.print("\n[bold cyan]═══ Phase 1 DATA 強化檢查 ═══[/bold cyan]\n")

    phase1_lines: list[str] = []

    # 6) raw_manifest 存在與一致性檢查
    console.print("[bold]6. Raw Manifest 檢查[/bold]\n")
    manifest_ok, manifest_lines = _check_raw_manifest(data_root)
    ok = ok and manifest_ok
    phase1_lines.extend(manifest_lines)

    # 7) Schema 版本檢查
    console.print("\n[bold]7. Schema 版本檢查[/bold]\n")
    schema_ok, schema_lines = _check_schema_version(data_root)
    ok = ok and schema_ok
    phase1_lines.extend(schema_lines)

    # 8) dedupe_key_version 可治理檢查
    console.print("\n[bold]8. Dedupe Key Version 可治理檢查[/bold]\n")
    dedupe_ok, dedupe_lines = _check_dedupe_key_version(data_root)
    ok = ok and dedupe_ok
    phase1_lines.extend(dedupe_lines)

    # 9) 遷移狀態檢查
    console.print("\n[bold]9. 遷移狀態檢查[/bold]\n")
    migrate_ok, migrate_lines = _check_migration_status(data_root)
    # migrate_ok 不影響總體 ok（僅提示）
    phase1_lines.extend(migrate_lines)

    console.print(
        Panel(
            "\n".join(phase1_lines),
            title="[bold]Phase 1 DATA 強化[/bold]",
            border_style="green" if ok else "red",
        )
    )

    # === 最終結果 ===
    console.print()
    if ok:
        console.print("[bold green]✓ 所有檢查通過[/bold green]")
    else:
        console.print("[bold red]✗ 檢查失敗，請修正上述問題[/bold red]")
        raise typer.Exit(1)
