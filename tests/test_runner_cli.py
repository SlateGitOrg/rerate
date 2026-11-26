"""The runner and the command line."""

from __future__ import annotations

from decimal import Decimal as D

import duckdb
from typer.testing import CliRunner
from world import World, ltl_lines, tl_lines, tl_per_mile  # noqa: I001

from rerate import runner
from rerate.cli import app


def test_model_list_skips_comments_and_keeps_order():
    paths = runner.read_model_list(runner.default_sql_dir())
    names = [p.stem for p in paths]
    assert names[0] == "stg_audit_params"
    assert names.index("int_weight_check") < names.index("int_ltl_rated")
    assert (
        names.index("fct_invoice_audit")
        < names.index("fct_findings")
        < names.index("fct_lane_benchmark")
    )
    assert all(p.exists() for p in paths)


def test_each_model_file_becomes_a_table_named_after_its_stem(tmp_path):
    sql = tmp_path / "sql"
    (sql / "tests").mkdir(parents=True)
    (sql / "a.sql").write_text("SELECT 1 AS x;")
    (sql / "b.sql").write_text("SELECT x + 1 AS y FROM a")
    (sql / "models.txt").write_text("# comment\n\na.sql\nb.sql\n")
    con = duckdb.connect()
    assert runner.run_models(con, sql) == ["a", "b"]
    assert con.execute("SELECT y FROM b").fetchall() == [(2,)]


def test_a_failing_sql_test_returns_and_prints_its_violating_rows(tmp_path):
    sql = tmp_path / "sql"
    (sql / "tests").mkdir(parents=True)
    (sql / "tests" / "no_zero.sql").write_text("SELECT 'S-42' AS shipment_id, 0 AS n")
    (sql / "tests" / "fine.sql").write_text("SELECT 1 WHERE FALSE")
    failures = runner.run_tests(duckdb.connect(), sql)
    assert [f.name for f in failures] == ["no_zero"]
    text = failures[0].render()
    assert "S-42" in text and "shipment_id" in text


def test_ledger_files_are_never_loaded_into_the_audit_database(seed7):
    con = duckdb.connect(str(seed7["db"]), read_only=True)
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    con.close()
    assert not any(t.startswith("raw_ground_truth") for t in tables)
    assert "raw_shipments" in tables and "fct_findings" in tables


def test_cli_generate_build_report_export(tmp_path):
    cli = CliRunner()
    raw, db = tmp_path / "raw", tmp_path / "audit.duckdb"
    r = cli.invoke(app, ["generate", "--seed", "7", "--out", str(raw)])
    assert r.exit_code == 0, r.output
    assert "shipments=4,000" in r.output and "errors=174" in r.output
    r = cli.invoke(app, ["build", "--raw", str(raw), "--db", str(db)])
    assert r.exit_code == 0, r.output
    assert "26 models" in r.output and "all passed" in r.output
    rep = tmp_path / "out" / "audit.md"
    r = cli.invoke(app, ["report", "--db", str(db), "--out", str(rep)])
    assert r.exit_code == 0, r.output
    text = rep.read_text()
    assert "## Recovery by finding type" in text and "| duplicate | 24 |" in text
    assert "P1>C001" in text  # the 80-mile lane leads the raw cost per mile ranking
    r = cli.invoke(app, ["export", "--db", str(db), "--out", str(tmp_path / "csv")])
    assert r.exit_code == 0, r.output
    findings = (tmp_path / "csv" / "fct_findings.csv").read_text().splitlines()
    assert len(findings) == 175 and findings[0].startswith("finding_id,invoice_id")


def test_cli_build_exits_nonzero_and_names_the_shipment_when_a_data_test_fails(tmp_path):
    w = World()
    s = w.shipment(mode="TL", ship="2026-01-02", miles="500.0", weight=30000)
    w.invoice(s, tl_lines(D("500.0"), D("1.9000"), tl_per_mile(D("3.50"))))
    w.t["contract_versions"].append(
        ["CV4", "TL1", "v3", "2026-01-01", "9999-12-31", "", "", "0.9000", "350.00", "75.00"]
    )
    raw = tmp_path / "raw"
    from world import HEADERS  # noqa: I001

    from rerate.generator import write_csv

    raw.mkdir()
    for name, header in HEADERS.items():
        write_csv(raw / f"{name}.csv", header, w.t[name])
    r = CliRunner().invoke(app, ["build", "--raw", str(raw), "--db", str(tmp_path / "x.duckdb")])
    assert r.exit_code == 1
    assert "one_contract_version_per_shipment" in r.output and s in r.output


def test_ltl_lines_helper_matches_the_model(tmp_path):
    # guards the fixture helper itself: a clean LTL invoice from the helper has no variance
    w = World()
    w.invoice(w.shipment(), ltl_lines(900, D("0.2200")))
    b = w.build(tmp_path)
    assert b.q("SELECT variance FROM fct_invoice_audit") == [(D("0.00"),)]
