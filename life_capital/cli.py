"""Life Capital CLI 入口

使用 Typer 建立命令行介面。
"""

from typing import Optional

import typer
from rich.console import Console

from life_capital import __version__
from life_capital.commands import (
    advisor_cmd,
    apply_cmd,
    capture_cmd,
    dedupe_cmd,
    import_cmd,
    migrate_cmd,
    project_cmd,
    rebuild_cmd,
    report_cmd,
    scenario_cmd,
    staging_cmd,
    undo_cmd,
)
from life_capital.commands import doctor as doctor_cmd
from life_capital.commands import expense as expense_cmd
from life_capital.commands import init as init_cmd
from life_capital.commands import lifetime as lifetime_cmd
from life_capital.commands import schema as schema_cmd
from life_capital.commands import summary as summary_cmd
from life_capital.commands import validate as validate_cmd

# 建立主應用
app = typer.Typer(
    name="lc",
    help="Life Capital - 終身財務規劃系統",
    no_args_is_help=True,
)

# Rich console 用於美化輸出
console = Console()


def version_callback(value: bool) -> None:
    """顯示版本資訊"""
    if value:
        console.print(f"Life Capital v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="顯示版本資訊",
    ),
) -> None:
    """Life Capital - 終身財務規劃系統

    使用 --help 查看可用指令。
    """
    pass


# 註冊子指令
app.command(name="init")(init_cmd.init)
app.command(name="validate")(validate_cmd.validate)
app.command(name="doctor")(doctor_cmd.doctor)
app.command(name="import")(import_cmd.import_csv)
app.command(name="apply")(apply_cmd.apply)
app.command(name="undo")(undo_cmd.undo)
app.command(name="dedupe")(dedupe_cmd.dedupe)
app.command(name="rebuild")(rebuild_cmd.rebuild)
app.command(name="lifetime")(lifetime_cmd.lifetime)
app.command(name="summary")(summary_cmd.summary)
app.command(name="project")(project_cmd.project)
app.command(name="scenario")(scenario_cmd.scenario)
app.command(name="report")(report_cmd.report)  # Phase 3: Report Generation
app.command(name="capture")(capture_cmd.capture)  # Phase 4: CAPTURE
app.add_typer(expense_cmd.app, name="expense")
app.add_typer(schema_cmd.app, name="schema")
app.add_typer(migrate_cmd.app, name="migrate")
app.add_typer(staging_cmd.app, name="staging")  # Phase 4: CAPTURE
app.add_typer(advisor_cmd.app, name="advisor")  # Phase 5: AI Advisor


if __name__ == "__main__":
    app()
