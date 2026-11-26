"""Seed 7, end to end: the audit is scored against the generator's error ledger."""

from __future__ import annotations

from decimal import Decimal as D

import duckdb
import pytest

from rerate import runner


@pytest.fixture(scope="module")
def con(seed7):
    c = duckdb.connect(str(seed7["db"]), read_only=True)
    c.execute(
        "CREATE TEMP TABLE gt AS SELECT * FROM read_csv(?, header = true, "
        "types = {'overcharge': 'DECIMAL(12,2)'})",
        [str(seed7["raw"] / "ground_truth_errors.csv")],
    )
    c.execute(
        "CREATE TEMP TABLE look AS SELECT * FROM read_csv(?, header = true)",
        [str(seed7["raw"] / "ground_truth_lookalikes.csv")],
    )
    yield c
    c.close()


def test_every_data_test_passes_on_generated_data(seed7):
    assert seed7["failures"] == []
    assert len(seed7["built"]) == 26


def test_findings_match_the_ledger_exactly_on_invoice_and_type(con):
    found = set(con.execute("SELECT invoice_id, finding_type FROM fct_findings").fetchall())
    truth = set(con.execute("SELECT invoice_id, finding_type FROM gt").fetchall())
    assert len(truth) == 174
    assert found == truth
    assert con.execute("SELECT count(*) FROM fct_findings").fetchone()[0] == 174


def test_the_fifty_lookalikes_produce_zero_findings(con):
    assert con.execute("SELECT count(*) FROM look").fetchone()[0] == 50
    assert (
        con.execute("SELECT count(*) FROM fct_findings JOIN look USING (invoice_id)").fetchone()[0]
        == 0
    )


def test_total_overcharge_equals_the_ledger_within_a_cent(con):
    audit = con.execute("SELECT sum(overcharge) FROM fct_findings").fetchone()[0]
    truth = con.execute("SELECT sum(overcharge) FROM gt").fetchone()[0]
    assert abs(audit - truth) <= D("0.01")


def test_each_finding_type_total_matches_the_ledger_within_a_cent(con):
    audit = dict(
        con.execute("SELECT finding_type, sum(overcharge) FROM fct_findings GROUP BY 1").fetchall()
    )
    truth = dict(con.execute("SELECT finding_type, sum(overcharge) FROM gt GROUP BY 1").fetchall())
    assert set(audit) == set(truth) and len(truth) == 5
    for kind, amount in truth.items():
        assert abs(audit[kind] - amount) <= D("0.01"), kind


def test_each_finding_amount_equals_its_ledger_row(con):
    bad = con.execute(
        "SELECT f.invoice_id, f.overcharge, g.overcharge FROM fct_findings AS f "
        "JOIN gt AS g USING (invoice_id, finding_type) "
        "WHERE abs(f.overcharge - g.overcharge) > 0.01"
    ).fetchall()
    assert bad == []


def test_all_24_duplicates_are_flagged_for_the_full_amount_and_no_original_is(con):
    dups = con.execute(
        "SELECT f.invoice_id, f.overcharge, a.billed_total, a.original_invoice_id "
        "FROM fct_findings AS f JOIN fct_invoice_audit AS a USING (invoice_id) "
        "WHERE f.finding_type = 'duplicate'"
    ).fetchall()
    assert len(dups) == 24
    assert all(over == billed and over > 0 for _i, over, billed, _o in dups)
    originals = {o for *_x, o in dups}
    assert len(originals) == 24
    flagged = {r[0] for r in con.execute("SELECT invoice_id FROM fct_findings").fetchall()}
    assert not originals & flagged


def test_both_duplicate_rules_are_exercised(con):
    rules = dict(
        con.execute("SELECT matched_on, count(*) FROM int_duplicates GROUP BY 1").fetchall()
    )
    assert rules == {"bol_total+pro": 16, "bol_total": 8}


def test_unflagged_invoices_agree_with_the_contract_to_within_a_nickel(con):
    worst = con.execute(
        "SELECT max(abs(variance)) FROM fct_invoice_audit "
        "WHERE invoice_id NOT IN (SELECT invoice_id FROM fct_findings)"
    ).fetchone()[0]
    assert worst <= D("0.05")


def test_cent_rounding_noise_is_present_and_ignored(con):
    noisy = con.execute(
        "SELECT count(*) FROM fct_invoice_audit WHERE variance <> 0 "
        "AND invoice_id NOT IN (SELECT invoice_id FROM fct_findings)"
    ).fetchone()[0]
    assert noisy > 100


def test_lane_benchmark_flags_exactly_the_three_overpriced_lanes(con, seed7):
    # lane overpricing is read from the raw tables, independent of the audit
    over = con.execute(
        """
        WITH lane AS (
            SELECT r.plant_id || '>' || r.consignee_id AS lane_id,
                   CAST(r.rate_per_mile AS DOUBLE) * CAST(any_value(s.miles) AS DOUBLE)
                       / (310 + 2.05 * CAST(any_value(s.miles) AS DOUBLE)) AS contract_vs_market
            FROM read_csv(?, all_varchar = true) AS r
            JOIN read_csv(?, all_varchar = true) AS s
              ON s.plant_id = r.plant_id AND s.consignee_id = r.consignee_id AND s.mode = 'TL'
            GROUP BY r.plant_id, r.consignee_id, r.rate_per_mile
        )
        SELECT lane_id FROM lane WHERE contract_vs_market > 1.15 ORDER BY 1
        """,
        [str(seed7["raw"] / "tl_lane_rates.csv"), str(seed7["raw"] / "shipments.csv")],
    ).fetchall()
    flagged = con.execute(
        "SELECT lane_id, lane_index FROM fct_lane_benchmark WHERE flagged ORDER BY 1"
    ).fetchall()
    assert [r[0] for r in flagged] == [r[0] for r in over]
    assert len(flagged) == 3
    assert all(1.15 <= idx <= 1.25 for _l, idx in flagged)


def test_short_hauls_top_the_raw_ranking_but_sit_at_market_on_the_index(con):
    rows = con.execute(
        "SELECT miles, raw_cost_per_mile_rank, lane_index FROM fct_lane_benchmark "
        "WHERE miles < 120 ORDER BY miles"
    ).fetchall()
    assert len(rows) == 2
    assert [round(m) for m, _r, _i in rows] == [80, 110]
    assert all(rank <= 5 for _m, rank, _i in rows)
    assert all(0.93 <= idx <= 1.07 for _m, _r, idx in rows)


def test_overpriced_lanes_rank_top_three_on_the_index_but_not_in_the_raw_top_five(con):
    top = con.execute(
        "SELECT lane_index_rank, raw_cost_per_mile_rank, flagged FROM fct_lane_benchmark "
        "WHERE lane_index_rank <= 3 ORDER BY 1"
    ).fetchall()
    assert [t[2] for t in top] == [True, True, True]
    assert all(raw > 5 for _i, raw, _f in top)


def test_lane_fit_recovers_the_market_curve(con):
    a, b = con.execute(
        "SELECT any_value(fit_intercept), any_value(fit_slope) FROM fct_lane_benchmark"
    ).fetchone()
    assert a == pytest.approx(310, rel=0.12)
    assert b == pytest.approx(2.05, rel=0.03)


def test_two_builds_give_identical_marts(seed7, tmp_path):
    second = tmp_path / "again.duckdb"
    runner.build(seed7["raw"], second)
    one = duckdb.connect(str(seed7["db"]), read_only=True)
    two = duckdb.connect(str(second), read_only=True)
    try:
        for mart in (
            "fct_invoice_audit",
            "fct_findings",
            "rpt_recovery_by_carrier",
            "fct_lane_benchmark",
        ):
            sql = f"SELECT * FROM {mart} ORDER BY ALL"
            assert one.execute(sql).fetchall() == two.execute(sql).fetchall(), mart
    finally:
        one.close()
        two.close()


def test_no_finding_is_a_plug_or_an_unexplained_remainder_on_seed_7(con):
    kinds = {r[0] for r in con.execute("SELECT DISTINCT finding_type FROM fct_findings").fetchall()}
    assert "unexplained_variance" not in kinds
    # the bound holds: flagged invoices reconcile and unflagged ones sit inside the tolerance
    assert (
        con.execute("SELECT count(*) FROM fct_findings WHERE overcharge <= 0.05").fetchone()[0] == 0
    )
