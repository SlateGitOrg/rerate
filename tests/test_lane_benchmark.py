"""The lane benchmark model against a hand-built set of lanes lying on an exact line."""

from __future__ import annotations

import duckdb
import pytest


@pytest.fixture()
def con(sql_dir):
    c = duckdb.connect()
    path = sql_dir / "staging" / "stg_audit_params.sql"
    c.execute(f"CREATE TABLE stg_audit_params AS {path.read_text()}")
    c.execute(
        "CREATE TABLE stg_shipments (shipment_id VARCHAR, mode VARCHAR, lane_id VARCHAR, "
        "carrier_id VARCHAR, plant_id VARCHAR, consignee_id VARCHAR, miles DECIMAL(7,1))"
    )
    c.execute(
        "CREATE TABLE fct_invoice_audit (invoice_id VARCHAR, shipment_id VARCHAR, "
        "is_duplicate BOOLEAN, billed_linehaul DECIMAL(12,2))"
    )
    c.execute("CREATE TABLE fct_findings (invoice_id VARCHAR)")
    yield c
    c.close()


def add_lane(con, lane, miles, linehaul, n, flagged_noise=()):
    """n finding-free shipments at `linehaul`, plus shipments with a finding at a wild amount."""
    for k in range(n):
        sid = f"{lane}-{k}"
        con.execute(
            "INSERT INTO stg_shipments VALUES (?, 'TL', ?, 'TL1', 'P1', ?, ?)",
            [sid, lane, lane, miles],
        )
        con.execute(
            "INSERT INTO fct_invoice_audit VALUES (?, ?, FALSE, ?)", [f"I-{sid}", sid, linehaul]
        )
    for k, wild in enumerate(flagged_noise):
        sid = f"{lane}-f{k}"
        con.execute(
            "INSERT INTO stg_shipments VALUES (?, 'TL', ?, 'TL1', 'P1', ?, ?)",
            [sid, lane, lane, miles],
        )
        con.execute(
            "INSERT INTO fct_invoice_audit VALUES (?, ?, FALSE, ?)", [f"I-{sid}", sid, wild]
        )
        con.execute("INSERT INTO fct_findings VALUES (?)", [f"I-{sid}"])


def run_model(con, sql_dir):
    sql = (sql_dir / "marts" / "fct_lane_benchmark.sql").read_text()
    con.execute(f"CREATE TABLE fct_lane_benchmark AS {sql}")
    cols = [d[0] for d in con.execute("SELECT * FROM fct_lane_benchmark").description]
    return {
        r[0]: dict(zip(cols, r, strict=True))
        for r in con.execute("SELECT * FROM fct_lane_benchmark").fetchall()
    }


def test_refit_after_dropping_the_overpriced_lane_recovers_the_exact_curve(con, sql_dir):
    # market curve 300 + 2 x miles; lane L8 is contracted 30% above it
    for i, miles in enumerate([80, 150, 300, 450, 600, 750, 900, 1100, 1300, 1500]):
        base = 300 + 2 * miles
        add_lane(con, f"L{i}", miles, base * (1.3 if i == 7 else 1.0), 10, flagged_noise=[99999.0])
    lanes = run_model(con, sql_dir)
    assert len(lanes) == 10
    expected = lanes["L0"]
    assert expected["fit_intercept"] == pytest.approx(300.0, abs=1e-6)
    assert expected["fit_slope"] == pytest.approx(2.0, abs=1e-9)
    assert lanes["L7"]["lane_index"] == pytest.approx(1.3, abs=1e-9)
    assert lanes["L7"]["dropped_from_refit"] is True
    assert (
        lanes["L7"]["index_pass1"] < 1.3
    )  # the overpriced lane pulled the first fit toward itself
    for name, row in lanes.items():
        if name != "L7":
            assert row["lane_index"] == pytest.approx(1.0, abs=1e-9)
            assert row["flagged"] is False
    assert [n for n, r in lanes.items() if r["flagged"]] == ["L7"]


def test_the_short_haul_has_the_top_raw_cost_per_mile_but_an_index_of_one(con, sql_dir):
    for i, miles in enumerate([60, 300, 600, 900, 1200]):
        add_lane(con, f"L{i}", miles, 300 + 2 * miles, 9)
    lanes = run_model(con, sql_dir)
    assert lanes["L0"]["raw_cost_per_mile_rank"] == 1
    assert lanes["L0"]["raw_cost_per_mile"] == pytest.approx(7.0)
    assert lanes["L0"]["lane_index"] == pytest.approx(1.0, abs=1e-9)
    assert lanes["L0"]["flagged"] is False


def test_lanes_with_fewer_than_eight_finding_free_shipments_are_not_scored(con, sql_dir):
    for i, miles in enumerate([100, 400, 800, 1200]):
        add_lane(con, f"L{i}", miles, 300 + 2 * miles, 8 if i else 7)
    assert sorted(run_model(con, sql_dir)) == ["L1", "L2", "L3"]


def test_a_lane_just_below_the_flag_threshold_is_not_flagged(con, sql_dir):
    for i, miles in enumerate([100, 300, 500, 700, 900, 1100, 1300, 1500]):
        add_lane(con, f"L{i}", miles, (300 + 2 * miles) * (1.10 if i == 3 else 1.0), 12)
    lanes = run_model(con, sql_dir)
    # one 10% lane among eight barely moves the line, so its index stays under 1.12
    assert 1.05 < lanes["L3"]["lane_index"] < 1.12
    assert lanes["L3"]["flagged"] is False
