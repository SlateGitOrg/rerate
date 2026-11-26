"""Model behaviour on hand-built worlds: every expected number is worked out by hand."""

from __future__ import annotations

from decimal import Decimal as D

from world import World, ltl_lines, ltl_pct, tl_lines, tl_per_mile  # noqa: I001


def pct(price: str) -> D:
    """FSC fraction for the band containing a diesel price, per the fixture table."""
    low = (D(price) // D("0.05")) * D("0.05")
    return ltl_pct(low)


# --- LTL rating -----------------------------------------------------------------------------


def test_ltl_deficit_weight_rating_picks_the_next_break(tmp_path):
    w = World()
    s = w.shipment(weight=900, ship="2026-03-10")
    w.invoice(s, [("LINEHAUL", D(900), D("107.95")), ("FUEL", None, D("23.75"))], days_after=14)
    b = w.build(tmp_path)
    row = b.q(
        "SELECT rated_break_lb, rate_cwt, next_break_lb, next_rate_cwt, gross_charge, "
        "deficit_applied, net_charge, min_applied, expected_linehaul FROM int_ltl_rated"
    )[0]
    assert row == (
        500,
        D("39.10"),
        1000,
        D("31.75"),
        D("317.50"),
        True,
        D("107.95"),
        False,
        D("107.95"),
    )
    assert b.findings() == []


def test_ltl_absolute_minimum_applies_to_a_light_shipment(tmp_path):
    w = World()
    s = w.shipment(weight=120, ship="2026-03-10")
    w.invoice(s, [("LINEHAUL", D(120), D("95.00")), ("FUEL", None, D("20.90"))])
    b = w.build(tmp_path)
    row = b.q(
        "SELECT rate_cwt, gross_charge, net_charge, min_applied, expected_linehaul "
        "FROM int_ltl_rated"
    )[0]
    assert row == (D("48.20"), D("57.84"), D("19.67"), True, D("95.00"))


def test_ltl_top_break_has_no_deficit_comparison(tmp_path):
    w = World()
    s = w.shipment(weight=12000)
    w.invoice(s, ltl_lines(12000, pct("3.66")))
    row = w.build(tmp_path).q(
        "SELECT rated_break_lb, next_break_lb, gross_charge, deficit_applied FROM int_ltl_rated"
    )[0]
    assert row == (10000, None, D("2160.00"), False)


# --- fuel week ------------------------------------------------------------------------------


def test_asof_join_uses_the_ship_week_not_the_invoice_week(tmp_path):
    w = World()
    late = w.shipment(ship="2026-03-10")  # Tuesday, index $3.66 effective 2026-03-09
    sunday = w.shipment(ship="2026-03-08")  # Sunday, index $3.58 effective 2026-03-02
    w.invoice(late, [("LINEHAUL", D(900), D("107.95")), ("FUEL", None, D("23.75"))], days_after=14)
    w.invoice(sunday, [("LINEHAUL", D(900), D("107.95")), ("FUEL", None, D("22.67"))])
    b = w.build(tmp_path)
    got = {
        r[0]: r[1:]
        for r in b.q(
            "SELECT shipment_id, index_effective_date::VARCHAR, diesel_price, fsc_rate "
            "FROM int_fuel_week"
        )
    }
    assert got[late] == ("2026-03-09", D("3.660"), D("0.2200"))
    assert got[sunday] == ("2026-03-02", D("3.580"), D("0.2100"))
    fuel = dict(b.q("SELECT shipment_id, expected_fuel FROM int_ltl_rated"))
    assert fuel == {late: D("23.75"), sunday: D("22.67")}
    assert b.findings() == []


def test_fuel_from_the_invoice_week_is_a_finding_and_late_billing_is_not(tmp_path):
    w = World()
    right = w.shipment(ship="2026-03-10")
    wrong = w.shipment(ship="2026-03-10")
    base = D("107.95")
    # invoiced 2026-03-24, whose index week (3.75) sits in a higher band than the ship week (3.66)
    w.invoice(right, [("LINEHAUL", D(900), base), ("FUEL", None, D("23.75"))], days_after=14)
    wrong_fuel = (base * pct("3.75")).quantize(D("0.01"))
    w.invoice(wrong, [("LINEHAUL", D(900), base), ("FUEL", None, wrong_fuel)], days_after=14)
    b = w.build(tmp_path)
    assert wrong_fuel == D("24.83")
    assert b.findings() == [("I002", "fsc_wrong_week", D("1.08"))]


def test_every_shipment_gets_one_fuel_week_in_the_fixture_world(tmp_path):
    w = World()
    w.invoice(w.shipment(), ltl_lines(900, pct("3.66")))
    b = w.build(tmp_path)
    assert b.failures == []


# --- contract versions ----------------------------------------------------------------------


def test_truckload_contract_version_follows_the_ship_date(tmp_path):
    w = World()
    old = w.shipment(mode="TL", ship="2025-12-31", consignee="C1", miles="500.0", weight=30000)
    new = w.shipment(mode="TL", ship="2026-01-02", consignee="C1", miles="500.0", weight=30000)
    fsc = tl_per_mile(D("3.50"))
    w.invoice(old, tl_lines(D("500.0"), D("2.0000"), fsc))
    w.invoice(new, tl_lines(D("500.0"), D("1.9000"), fsc))
    b = w.build(tmp_path)
    rows = {
        r[0]: r[1:]
        for r in b.q(
            "SELECT shipment_id, version_label, rate_per_mile, expected_linehaul "
            "FROM int_tl_rated ORDER BY 1"
        )
    }
    assert rows[old] == ("v1", D("2.0000"), D("1000.00"))
    assert rows[new] == ("v2", D("1.9000"), D("950.00"))
    assert b.findings() == []


def test_billing_the_old_rate_after_the_amendment_is_a_contract_rate_finding(tmp_path):
    w = World()
    s = w.shipment(mode="TL", ship="2026-01-02", miles="500.0", weight=30000)
    fsc = tl_per_mile(D("3.50"))
    w.invoice(s, tl_lines(D("500.0"), D("2.0000"), fsc))
    assert w.build(tmp_path).findings() == [("I001", "contract_rate", D("50.00"))]


def test_overlapping_contract_version_fails_the_uniqueness_test_and_prints_the_shipment(tmp_path):
    w = World()
    s = w.shipment(mode="TL", ship="2026-01-02", miles="500.0", weight=30000)
    w.invoice(s, tl_lines(D("500.0"), D("1.9000"), tl_per_mile(D("3.50"))))
    w.t["contract_versions"].append(
        ["CV4", "TL1", "v3", "2026-01-01", "9999-12-31", "", "", "0.9000", "350.00", "75.00"]
    )
    b = w.build(tmp_path)
    failed = {f.name: f for f in b.failures}
    assert "one_contract_version_per_shipment" in failed
    text = failed["one_contract_version_per_shipment"].render()
    assert s in text and "2" in text


# --- truckload rating -----------------------------------------------------------------------


def test_truckload_minimum_charge_and_stop_offs(tmp_path):
    w = World()
    s = w.shipment(mode="TL", ship="2026-03-10", miles="100.0", weight=30000, stops=2)
    w.t["tl_lane_rates"][0][3] = D("0.5000")  # x 0.95 after the amendment = 0.4750 per mile
    fsc = tl_per_mile(D("3.65"))
    w.invoice(s, tl_lines(D("100.0"), D("0.4750"), fsc, stops=2))
    b = w.build(tmp_path)
    row = b.q(
        "SELECT linehaul_before_min, min_applied, expected_linehaul, expected_stopoff, "
        "expected_fuel "
        "FROM int_tl_rated"
    )[0]
    assert row == (D("47.50"), True, D("350.00"), D("150.00"), D("40.00"))
    assert b.findings() == []


# --- weight check ---------------------------------------------------------------------------


def test_weight_tolerance_certificate_and_overbilling(tmp_path):
    w = World()
    fuel = pct("3.66")
    near = w.shipment(weight=1000)
    w.invoice(near, ltl_lines(1015, fuel), weight=1015)  # 1.5% over: accepted
    over = w.shipment(weight=1000)
    w.invoice(over, ltl_lines(1100, fuel), weight=1100)  # 10% over, no certificate
    cert = w.shipment(weight=1000)
    w.certify(cert, 1100)
    w.invoice(cert, ltl_lines(1100, fuel), weight=1100)  # reweighed, certificate on file
    above = w.shipment(weight=1000)
    w.certify(above, 1100)
    w.invoice(above, ltl_lines(1200, fuel), weight=1200)  # above even the certificate
    b = w.build(tmp_path)
    status = dict(b.q("SELECT shipment_id, weight_status FROM int_weight_check"))
    assert status == {
        near: "within_tolerance",
        over: "overbilled",
        cert: "certified",
        above: "overbilled",
    }
    expected_w = dict(b.q("SELECT shipment_id, expected_weight_lb FROM int_weight_check"))
    assert expected_w == {near: 1015, over: 1000, cert: 1100, above: 1100}

    billed = lambda wt: sum(a for _c, _q, a in ltl_lines(wt, fuel))  # noqa: E731
    assert b.findings() == [
        ("I002", "weight_overbill", billed(1100) - billed(1000)),
        ("I004", "weight_overbill", billed(1200) - billed(1100)),
    ]


# --- accessorials ---------------------------------------------------------------------------


def test_accessorials_need_an_approval_or_a_schedule_rule(tmp_path):
    w = World()
    fuel = pct("3.66")
    lift = w.shipment(consignee="C2")  # liftgate consignee: schedule rule
    w.invoice(lift, ltl_lines(900, fuel, [("LIFTGATE", D("45.00"))]))
    plain = w.shipment(consignee="C1")
    w.invoice(plain, ltl_lines(900, fuel, [("LIFTGATE", D("45.00"))]))  # nothing covers it
    approved = w.shipment(consignee="C1")
    w.approve(approved, "RESIDENTIAL")
    w.invoice(approved, ltl_lines(900, fuel, [("RESIDENTIAL", D("60.00"))]))
    b = w.build(tmp_path)
    rows = b.q(
        "SELECT shipment_id, charge_code, basis, expected_amount "
        "FROM int_accessorial_expected ORDER BY 1, 2"
    )
    assert rows == [
        (lift, "LIFTGATE", "schedule", D("45.00")),
        (approved, "RESIDENTIAL", "approval", D("60.00")),
    ]
    assert b.findings() == [("I002", "unapproved_accessorial", D("45.00"))]


def test_detention_is_priced_per_started_hour_after_two_free_hours(tmp_path):
    w = World()
    ids = {}
    for dwell in (120, 121, 180, 190):
        s = w.shipment(mode="TL", miles="500.0", weight=30000, dwell=dwell)
        w.approve(s, "DETENTION")
        ids[dwell] = s
        w.invoice(s, tl_lines(D("500.0"), D("1.9000"), tl_per_mile(D("3.65"))))
    rows = dict(w.build(tmp_path).q("SELECT shipment_id, quantity FROM int_accessorial_expected"))
    assert [rows[ids[d]] for d in (120, 121, 180, 190)] == [0, 1, 1, 2]


def test_approved_detention_is_clean_and_unapproved_detention_is_a_finding(tmp_path):
    w = World()
    fsc = tl_per_mile(D("3.65"))
    ok = w.shipment(mode="TL", miles="500.0", weight=30000, dwell=190)
    w.approve(ok, "DETENTION")
    w.invoice(ok, tl_lines(D("500.0"), D("1.9000"), fsc, extras=[("DETENTION", D(2), D("130.00"))]))
    bad = w.shipment(mode="TL", miles="500.0", weight=30000, dwell=190)
    w.invoice(
        bad, tl_lines(D("500.0"), D("1.9000"), fsc, extras=[("DETENTION", D(2), D("130.00"))])
    )
    assert w.build(tmp_path).findings() == [("I002", "unapproved_accessorial", D("130.00"))]


# --- rounding -------------------------------------------------------------------------------


def test_cent_rounding_is_not_a_finding_but_a_nickel_over_is(tmp_path):
    w = World()
    lines = ltl_lines(900, pct("3.66"))
    cents = [lines[0], ("FUEL", None, lines[1][2] + D("0.01"))]
    w.invoice(w.shipment(), cents)
    over = [lines[0], ("FUEL", None, lines[1][2] + D("0.06"))]
    w.invoice(w.shipment(), over)
    b = w.build(tmp_path)
    assert b.findings() == [("I002", "fsc_wrong_week", D("0.06"))]
    variance = dict(b.q("SELECT invoice_id, variance FROM fct_invoice_audit"))
    assert variance == {"I001": D("0.01"), "I002": D("0.06")}


# --- duplicates -----------------------------------------------------------------------------


def test_pro_numbers_normalise_to_the_same_key(tmp_path):
    w = World()
    s = w.shipment()
    w.invoice(s, ltl_lines(900, pct("3.66")), pro="0012345-6", number="A-1")
    w.invoice(s, ltl_lines(900, pct("3.66")), pro=" 123456 ", number="A-2", days_after=9)
    keys = w.build(tmp_path).q("SELECT pro_key FROM stg_invoices ORDER BY invoice_id")
    assert keys == [("123456",), ("123456",)]


def test_duplicates_by_pro_and_by_bol_with_a_near_total(tmp_path):
    w = World()
    fuel = pct("3.66")
    exact = w.shipment()
    first = w.invoice(exact, ltl_lines(900, fuel), pro="0012345-6", number="A-1")
    second = w.invoice(exact, ltl_lines(900, fuel), pro="123456", number="A-2", days_after=9)
    typo = w.shipment()
    t1 = w.invoice(typo, ltl_lines(900, fuel), pro="777001", number="B-1")
    near = ltl_lines(900, fuel)
    near[-1] = ("FUEL", None, near[-1][2] + D("0.60"))
    t2 = w.invoice(typo, near, pro="777010", number="B-2", days_after=12)
    far = w.shipment()
    f1 = w.invoice(far, ltl_lines(900, fuel), pro="888001", number="C-1")
    bigger = ltl_lines(900, fuel)
    bigger[-1] = ("FUEL", None, bigger[-1][2] + D("5.00"))
    w.invoice(far, bigger, pro="888010", number="C-2", days_after=12)
    b = w.build(tmp_path)
    dups = {
        r[0]: r[1:]
        for r in b.q("SELECT invoice_id, original_invoice_id, matched_on FROM int_duplicates")
    }
    assert dups[second] == (first, "bol_total+pro")
    assert dups[t2] == (t1, "bol_total")
    assert first not in dups and t1 not in dups and f1 not in dups
    assert "I006" not in dups  # same BOL but a $5 different total: a correction, not a re-bill


def test_a_duplicate_is_flagged_for_the_full_invoice_and_suppresses_other_findings(tmp_path):
    w = World()
    s = w.shipment(consignee="C1")
    good = ltl_lines(900, pct("3.66"))
    first = w.invoice(s, good, number="A-1", pro="500100")
    # the re-bill also carries an unapproved liftgate, but only the duplicate finding is kept
    with_extra = ltl_lines(900, pct("3.66"), [("LIFTGATE", D("45.00"))])
    second = w.invoice(s, with_extra, number="A-2", pro="500100", days_after=10)
    b = w.build(tmp_path)
    total = sum(a for _c, _q, a in with_extra)
    assert b.findings() == [(second, "duplicate", total)]
    assert first not in [r[0] for r in b.findings()]
    assert b.q(f"SELECT expected_total FROM fct_invoice_audit WHERE invoice_id = '{second}'") == [
        (D("0.00"),)
    ]


def test_same_pro_at_a_different_carrier_is_not_a_duplicate(tmp_path):
    w = World()
    a = w.shipment()
    b_ship = w.shipment(mode="TL", miles="500.0", weight=30000)
    w.invoice(a, ltl_lines(900, pct("3.66")), pro="424242", number="A-1")
    w.invoice(
        b_ship,
        tl_lines(D("500.0"), D("1.9000"), tl_per_mile(D("3.65"))),
        pro="424242",
        number="B-1",
        days_after=5,
    )
    assert w.build(tmp_path).q("SELECT count(*) FROM int_duplicates") == [(0,)]


# --- data tests -----------------------------------------------------------------------------


def test_orphan_invoice_lines_fail_the_join_test(tmp_path):
    w = World()
    w.invoice(w.shipment(), ltl_lines(900, pct("3.66")))
    w.t["invoice_lines"].append(["L9999", "I999", 1, "LINEHAUL", "", D("10.00")])
    failed = {f.name: f for f in w.build(tmp_path).failures}
    assert "invoice_lines_join_shipment" in failed
    assert "L9999" in failed["invoice_lines_join_shipment"].render()


def test_a_fixture_world_with_clean_data_passes_every_sql_test(tmp_path):
    w = World()
    w.invoice(w.shipment(), ltl_lines(900, pct("3.66")))
    w.invoice(
        w.shipment(mode="TL", miles="500.0", weight=30000),
        tl_lines(D("500.0"), D("1.9000"), tl_per_mile(D("3.65"))),
    )
    assert w.build(tmp_path).failures == []


# --- bounded residual -----------------------------------------------------------------------


def test_a_small_leftover_is_rounding_and_joins_the_largest_finding(tmp_path):
    w = World()
    lines = ltl_lines(900, pct("3.66"))
    # fuel $1.00 over (a finding) and linehaul $0.04 over (inside the tolerance)
    billed = [
        ("LINEHAUL", D(900), lines[0][2] + D("0.04")),
        ("FUEL", None, lines[1][2] + D("1.00")),
    ]
    w.invoice(w.shipment(), billed)
    b = w.build(tmp_path)
    assert b.findings() == [("I001", "fsc_wrong_week", D("1.04"))]
    assert b.failures == []


def test_a_larger_unmodelled_variance_is_its_own_finding_not_a_plug(tmp_path):
    w = World()
    lines = ltl_lines(900, pct("3.66"))
    # each component is inside the tolerance, but together they are $0.08 over the contract
    billed = [
        ("LINEHAUL", D(900), lines[0][2] + D("0.04")),
        ("FUEL", None, lines[1][2] + D("0.04")),
    ]
    w.invoice(w.shipment(), billed)
    b = w.build(tmp_path)
    assert b.findings() == [("I001", "unexplained_variance", D("0.08"))]
    assert b.failures == []


def test_unexplained_variance_next_to_a_typed_finding_does_not_inflate_the_typed_one(tmp_path):
    w = World()
    s = w.shipment(mode="TL", miles="500.0", weight=30000, stops=1)
    lines = tl_lines(D("500.0"), D("1.9000"), tl_per_mile(D("3.65")), stops=1)
    # fuel $1.00 over is a finding; linehaul and stop-off are each $0.05 over (inside the
    # tolerance), so $0.10 is left that no modelled cause accounts for
    billed = [
        ("LINEHAUL", D("500.0"), lines[0][2] + D("0.05")),
        ("STOPOFF", D(1), lines[1][2] + D("0.05")),
        ("FUEL", None, lines[2][2] + D("1.00")),
    ]
    w.invoice(s, billed)
    b = w.build(tmp_path)
    assert b.findings() == [
        ("I001", "fsc_wrong_week", D("1.00")),
        ("I001", "unexplained_variance", D("0.10")),
    ]
    assert b.failures == []


def test_under_billing_the_findings_cannot_explain_fails_the_data_tests(tmp_path):
    w = World()
    lines = ltl_lines(900, pct("3.66"))
    w.invoice(w.shipment(), [lines[0], ("FUEL", None, lines[1][2] - D("0.50"))])  # unflagged
    over = w.shipment()
    big = [("LINEHAUL", D(900), lines[0][2] - D("50.00")), ("FUEL", None, lines[1][2] + D("1.00"))]
    w.invoice(over, big)  # a $1 fuel finding hiding $50 of under-billing
    b = w.build(tmp_path)
    failed = {f.name: f for f in b.failures}
    assert "unflagged_invoice_matches_contract" in failed
    assert "I001" in failed["unflagged_invoice_matches_contract"].render()
    assert "flagged_invoice_overcharge_reconciles" in failed
    assert "I002" in failed["flagged_invoice_overcharge_reconciles"].render()
    # the $50 is not attached to the $1 finding
    assert b.findings() == [("I002", "fsc_wrong_week", D("1.00"))]
