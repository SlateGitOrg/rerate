"""A small SQL runner: load raw CSVs, build each model in order, run the data tests.

There is no templating. Raw CSVs become raw_<name> tables (all VARCHAR), and every model
file is a single SELECT that the runner wraps as CREATE OR REPLACE TABLE <file stem> AS ...
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

LEDGER_PREFIX = "ground_truth_"


def default_sql_dir() -> Path:
    """The repo's sql/ directory, or the copy shipped inside an installed wheel."""
    repo = Path(__file__).resolve().parents[2] / "sql"
    return repo if repo.exists() else Path(__file__).resolve().parent / "_sql"


def read_model_list(sql_dir: Path) -> list[Path]:
    paths = []
    for raw in (sql_dir / "models.txt").read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            paths.append(sql_dir / line)
    return paths


def load_raw(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> list[str]:
    """Load every CSV except the error ledgers, which the audit must not see."""
    loaded = []
    for csv_path in sorted(raw_dir.glob("*.csv")):
        if csv_path.stem.startswith(LEDGER_PREFIX):
            continue
        table = f"raw_{csv_path.stem}"
        con.execute(
            f"CREATE OR REPLACE TABLE {table} AS "
            "SELECT * FROM read_csv(?, header = true, all_varchar = true)",
            [str(csv_path)],
        )
        loaded.append(table)
    return loaded


def run_models(con: duckdb.DuckDBPyConnection, sql_dir: Path) -> list[str]:
    built = []
    for path in read_model_list(sql_dir):
        select = path.read_text().strip().rstrip(";")
        con.execute(f"CREATE OR REPLACE TABLE {path.stem} AS\n{select}")
        built.append(path.stem)
    return built


@dataclass
class TestFailure:
    name: str
    columns: list[str]
    rows: list[tuple]

    def render(self, limit: int = 20) -> str:
        out = [
            f"FAIL {self.name}: {len(self.rows)} violating row(s)",
            "  " + " | ".join(self.columns),
        ]
        out += ["  " + " | ".join(str(v) for v in row) for row in self.rows[:limit]]
        if len(self.rows) > limit:
            out.append(f"  ... {len(self.rows) - limit} more")
        return "\n".join(out)


def run_tests(con: duckdb.DuckDBPyConnection, sql_dir: Path) -> list[TestFailure]:
    """Each file in sql/tests returns violating rows; any row is a failure."""
    failures = []
    for path in sorted((sql_dir / "tests").glob("*.sql")):
        cur = con.execute(path.read_text().strip().rstrip(";"))
        rows = cur.fetchall()
        if rows:
            failures.append(TestFailure(path.stem, [d[0] for d in cur.description], rows))
    return failures


def build(
    raw_dir: Path, db_path: Path, sql_dir: Path | None = None
) -> tuple[list[str], list[TestFailure]]:
    """Build the database from raw CSVs and run the data tests."""
    sql_dir = sql_dir or default_sql_dir()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        con.execute("SET threads TO 1")  # fixed evaluation order, so two builds match exactly
        load_raw(con, raw_dir)
        built = run_models(con, sql_dir)
        failures = run_tests(con, sql_dir)
    finally:
        con.close()
    return built, failures
