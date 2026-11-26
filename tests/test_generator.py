"""The generator: structure, determinism and the properties the brief promises."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path

from rerate.generator import generate
from rerate.generator.reference import road_miles


def rows(raw: Path, name: str) -> list[dict]:
    with (raw / f"{name}.csv").open() as fh:
        return list(csv.DictReader(fh))


def test_two_runs_with_the_same_seed_are_byte_identical(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(7, a)
    generate(7, b)
    names = sorted(p.name for p in a.iterdir())
    assert names == sorted(p.name for p in b.iterdir())
    assert len(names) == 16
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_a_different_seed_gives_different_data(tmp_path, seed7):
    generate(8, tmp_path)
    assert (tmp_path / "shipments.csv").read_bytes() != (
        seed7["raw"] / "shipments.csv"
    ).read_bytes()


def test_network_and_volume_match_the_brief(seed7):
    raw = seed7["raw"]
    ships = rows(raw, "shipments")
    assert len(ships) == 4000
    assert Counter(s["mode"] for s in ships) == {"LTL": 2400, "TL": 1600}
    assert len(rows(raw, "carriers")) == 5 and len(rows(raw, "plants")) == 3
    assert len(rows(raw, "consignees")) == 60
    assert min(s["ship_date"] for s in ships) >= "2025-07-01"
    assert max(s["ship_date"] for s in ships) <= "2026-06-30"
    counts = seed7["counts"]
    assert counts["invoices"] == 4024 and 9000 <= counts["invoice_lines"] <= 10500
    tl_lanes = {(s["plant_id"], s["consignee_id"]) for s in ships if s["mode"] == "TL"}
    assert len(tl_lanes) == 30


def test_miles_are_great_circle_times_the_road_factor(seed7):
    raw = seed7["raw"]
    plants = {p["plant_id"]: p for p in rows(raw, "plants")}
    cons = {c["consignee_id"]: c for c in rows(raw, "consignees")}
    for s in rows(raw, "shipments")[::25]:
        p, c = plants[s["plant_id"]], cons[s["consignee_id"]]
        want = road_miles(float(p["lat"]), float(p["lon"]), float(c["lat"]), float(c["lon"]))
        assert D(s["miles"]) == want


def test_two_short_haul_lanes_are_eighty_and_one_hundred_ten_miles(seed7):
    ships = [s for s in rows(seed7["raw"], "shipments") if s["mode"] == "TL"]
    miles = sorted({float(s["miles"]) for s in ships})
    assert abs(miles[0] - 80.0) <= 0.2 and abs(miles[1] - 110.0) <= 0.2
    assert miles[2] > 140


def test_ledger_has_174_errors_in_the_stated_mix_and_one_per_invoice(seed7):
    ledger = rows(seed7["raw"], "ground_truth_errors")
    assert len(ledger) == 174
    assert Counter(r["finding_type"] for r in ledger) == {
        "fsc_wrong_week": 60,
        "duplicate": 24,
        "unapproved_accessorial": 40,
        "weight_overbill": 30,
        "contract_rate": 20,
    }
    assert len({r["invoice_id"] for r in ledger}) == 174
    assert all(D(r["overcharge"]) > 0 for r in ledger)


def test_fifty_lookalikes_in_the_stated_mix_never_overlap_the_errors(seed7):
    look = rows(seed7["raw"], "ground_truth_lookalikes")
    assert Counter(r["kind"] for r in look) == {
        "reweigh_certificate": 25,
        "approved_detention": 15,
        "late_billed_correct_fuel": 10,
    }
    err = {r["invoice_id"] for r in rows(seed7["raw"], "ground_truth_errors")}
    assert not err & {r["invoice_id"] for r in look}
    assert len(rows(seed7["raw"], "reweigh_certificates")) == 25
    assert len(rows(seed7["raw"], "approvals")) == 15


def test_late_billed_lookalikes_are_billed_two_to_four_weeks_after_shipping(seed7):
    raw = seed7["raw"]
    ships = {s["shipment_id"]: s for s in rows(raw, "shipments")}
    inv = {i["invoice_id"]: i for i in rows(raw, "invoices")}
    for r in rows(raw, "ground_truth_lookalikes"):
        if r["kind"] == "late_billed_correct_fuel":
            gap = (
                date.fromisoformat(inv[r["invoice_id"]]["invoice_date"])
                - date.fromisoformat(ships[r["shipment_id"]]["ship_date"])
            ).days
            assert 14 <= gap <= 28


def test_weight_errors_are_three_to_fifteen_percent_over_with_no_certificate(seed7):
    raw = seed7["raw"]
    ships = {s["shipment_id"]: s for s in rows(raw, "shipments")}
    inv = {i["invoice_id"]: i for i in rows(raw, "invoices")}
    certified = {c["shipment_id"] for c in rows(raw, "reweigh_certificates")}
    for r in rows(raw, "ground_truth_errors"):
        if r["finding_type"] == "weight_overbill":
            bol = int(ships[r["shipment_id"]]["bol_weight_lb"])
            billed = int(inv[r["invoice_id"]]["billed_weight_lb"])
            assert 1.03 <= billed / bol <= 1.1501
            assert r["shipment_id"] not in certified


def test_contract_rate_errors_are_amended_carrier_truckload_after_the_amendment(seed7):
    ships = {s["shipment_id"]: s for s in rows(seed7["raw"], "shipments")}
    for r in rows(seed7["raw"], "ground_truth_errors"):
        if r["finding_type"] == "contract_rate":
            s = ships[r["shipment_id"]]
            assert s["carrier_id"] == "TL2" and s["mode"] == "TL" and s["ship_date"] >= "2026-01-01"


def test_diesel_index_is_weekly_on_mondays_and_covers_the_invoice_tail(seed7):
    idx = rows(seed7["raw"], "diesel_index")
    dates = [date.fromisoformat(r["effective_date"]) for r in idx]
    assert all(d.weekday() == 0 for d in dates)
    assert all((b - a).days == 7 for a, b in zip(dates, dates[1:], strict=False))
    assert dates[0] <= date(2025, 7, 1) and dates[-1] >= date(2026, 8, 1)


def test_pro_numbers_are_unique_per_carrier_among_original_invoices(seed7):
    raw = seed7["raw"]
    dup_ids = {
        r["invoice_id"]
        for r in rows(raw, "ground_truth_errors")
        if r["finding_type"] == "duplicate"
    }
    seen = set()
    for i in rows(raw, "invoices"):
        if i["invoice_id"] in dup_ids:
            continue
        key = (i["carrier_id"], "".join(ch for ch in i["pro_number"] if ch.isdigit()).lstrip("0"))
        assert key not in seen
        seen.add(key)


def test_gate_timestamps_are_ordered(seed7):
    for s in rows(seed7["raw"], "shipments")[::10]:
        assert datetime.fromisoformat(s["gate_out"]) > datetime.fromisoformat(s["gate_in"])
