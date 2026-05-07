from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from life_capital.cli import app

runner = CliRunner()


def test_e2e_init_validate_summary(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout

    result = runner.invoke(app, ["validate", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout

    result = runner.invoke(app, ["summary", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout


def test_e2e_expense_check(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--path", str(tmp_path)])

    result = runner.invoke(app, ["expense", "check", "2025-01", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout


def test_schema_export() -> None:
    result = runner.invoke(app, ["schema", "export", "--model", "assumptions"])
    assert result.exit_code == 0, result.stdout
    assert "LifeAssumptions" in result.stdout or "\"title\": \"LifeAssumptions\"" in result.stdout

