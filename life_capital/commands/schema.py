"""schema 指令

從 Pydantic models 匯出 JSON Schema。
"""

from __future__ import annotations

import json
from typing import Literal

import typer
from rich.console import Console

from life_capital.models import ExpensePolicy, LifeAssumptions, LifetimeTargets, MonthlyIncome

console = Console()
app = typer.Typer(help="Schema 工具")

ModelName = Literal["assumptions", "targets", "income", "policy", "all"]


def _schema_for(name: ModelName) -> dict:
    mapping = {
        "assumptions": LifeAssumptions,
        "targets": LifetimeTargets,
        "income": MonthlyIncome,
        "policy": ExpensePolicy,
    }
    if name == "all":
        return {k: v.model_json_schema() for k, v in mapping.items()}
    return mapping[name].model_json_schema()


@app.command("export")
def export_schema(
    model: ModelName = typer.Option(
        "all",
        "--model",
        help="要輸出的 schema（預設 all）",
    ),
    indent: int = typer.Option(
        2,
        "--indent",
        help="JSON indent（預設 2）",
    ),
) -> None:
    schema = _schema_for(model)
    console.print_json(json.dumps(schema, ensure_ascii=False, indent=indent))

