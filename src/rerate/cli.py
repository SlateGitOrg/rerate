"""Command line: generate synthetic data, build the SQL models, report, export."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import runner
from .generator import generate as generate_data
from .report import export_marts, write_report

app = typer.Typer(
    help="Freight invoice audit in DuckDB SQL.", no_args_is_help=True, add_completion=False
)

RawDir = Annotated[Path, typer.Option("--raw", help="Directory of raw CSVs.")]
DbPath = Annotated[Path, typer.Option("--db", help="DuckDB file the models are built into.")]


@app.command()
def generate(
    seed: Annotated[int, typer.Option(help="Seed for the synthetic data.")] = 7,
    out: Annotated[Path, typer.Option(help="Output directory for raw CSVs.")] = Path("data/raw"),
) -> None:
    """Write seeded raw tables and the error ledger."""
    counts = generate_data(seed, out)
    typer.echo(f"wrote {out}: " + ", ".join(f"{k}={v:,}" for k, v in counts.items()))


@app.command()
def build(
    raw: RawDir = Path("data/raw"),
    db: DbPath = Path("build/rerate.duckdb"),
    sql_dir: Annotated[Path | None, typer.Option(help="Directory holding models.txt.")] = None,
) -> None:
    """Run the SQL models in order, then the data tests."""
    built, failures = runner.build(raw, db, sql_dir)
    typer.echo(f"built {len(built)} models into {db}")
    if failures:
        for f in failures:
            typer.echo(f.render(), err=True)
        raise typer.Exit(code=1)
    typer.echo("data tests: all passed")


@app.command()
def report(
    db: DbPath = Path("build/rerate.duckdb"),
    out: Annotated[Path, typer.Option(help="Markdown file to write.")] = Path("reports/audit.md"),
    top: Annotated[int, typer.Option(help="Lanes shown in each ranking.")] = 5,
) -> None:
    """Write the recovery and lane report."""
    write_report(db, out, top)
    typer.echo(f"wrote {out}")


@app.command()
def export(
    db: DbPath = Path("build/rerate.duckdb"),
    out: Annotated[Path, typer.Option(help="Directory for mart CSVs.")] = Path("export"),
) -> None:
    """Write the marts as CSV."""
    for path in export_marts(db, out):
        typer.echo(f"wrote {path}")


if __name__ == "__main__":
    app()
