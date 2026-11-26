"""Seeded synthetic data for the freight audit: raw tables plus the error ledger."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np

from .billing import (
    ACCESSORIAL_RATES,
    DETENTION_FREE_MINUTES,
    DETENTION_INCREMENT_MINUTES,
    BillingResult,
    format_pro,
    generate_billing,
)
from .reference import (
    CARRIERS,
    PLANTS,
    Reference,
    build_reference,
    contract_versions,
)
from .shipments import Shipment, generate_shipments

N_SHIPMENTS = 4000
LTL_SHARE = 0.60


def _fmt(v: object) -> str:
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, date):
        return v.isoformat()
    if v is None:
        return ""
    return str(v)


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow([_fmt(v) for v in row])


def _write_reference(out: Path, ref: Reference) -> None:
    write_csv(
        out / "carriers.csv", ["carrier_id", "carrier_name", "mode"], [list(c) for c in CARRIERS]
    )
    write_csv(
        out / "plants.csv", ["plant_id", "plant_name", "lat", "lon"], [list(p) for p in PLANTS]
    )
    write_csv(
        out / "consignees.csv",
        ["consignee_id", "consignee_name", "lat", "lon", "is_residential", "needs_liftgate"],
        [
            [c.consignee_id, c.name, c.lat, c.lon, int(c.is_residential), int(c.needs_liftgate)]
            for c in ref.consignees
        ],
    )
    cv = contract_versions()
    write_csv(out / "contract_versions.csv", list(cv[0].keys()), [list(r.values()) for r in cv])
    write_csv(
        out / "ltl_tariff.csv",
        ["carrier_id", "zone", "freight_class", "break_min_lb", "rate_cwt"],
        [list(r) for r in ref.tariff_rows],
    )
    write_csv(
        out / "tl_lane_rates.csv",
        ["carrier_id", "plant_id", "consignee_id", "rate_per_mile"],
        [[ln.carrier_id, ln.plant_id, ln.consignee_id, ln.rate_per_mile] for ln in ref.lanes],
    )
    write_csv(
        out / "diesel_index.csv",
        ["effective_date", "diesel_price"],
        [[d, p] for d, p in sorted(ref.diesel.items())],
    )
    write_csv(
        out / "fsc_tables.csv",
        ["carrier_id", "band_low", "band_high", "fsc_rate"],
        [[c, lo, hi, r] for c, rows in ref.fsc.items() for lo, hi, r in rows],
    )
    sched = []
    for carrier, codes in ACCESSORIAL_RATES.items():
        for code, rate in codes.items():
            if code == "DETENTION":
                sched.append(
                    [
                        carrier,
                        code,
                        rate,
                        "hour",
                        "approval_only",
                        DETENTION_FREE_MINUTES,
                        DETENTION_INCREMENT_MINUTES,
                    ]
                )
            else:
                sched.append([carrier, code, rate, "flat", "consignee_flag", "", ""])
    write_csv(
        out / "accessorial_schedule.csv",
        ["carrier_id", "charge_code", "rate", "unit", "rule", "free_minutes", "increment_minutes"],
        sched,
    )


def _write_shipments(out: Path, shipments: list[Shipment]) -> None:
    write_csv(
        out / "shipments.csv",
        [
            "shipment_id",
            "bol_number",
            "carrier_id",
            "mode",
            "plant_id",
            "consignee_id",
            "ship_date",
            "freight_class",
            "bol_weight_lb",
            "miles",
            "zone",
            "extra_stops",
            "gate_in",
            "gate_out",
        ],
        [
            [
                s.shipment_id,
                s.bol_number,
                s.carrier_id,
                s.mode,
                s.plant_id,
                s.consignee_id,
                s.ship_date,
                s.freight_class,
                s.bol_weight_lb,
                s.miles,
                s.zone,
                s.extra_stops,
                s.gate_in.strftime("%Y-%m-%d %H:%M:%S"),
                s.gate_out.strftime("%Y-%m-%d %H:%M:%S"),
            ]
            for s in shipments
        ],
    )


def _write_billing(out: Path, result: BillingResult) -> None:
    invoices = result.invoices
    write_csv(
        out / "invoices.csv",
        [
            "invoice_id",
            "invoice_number",
            "carrier_id",
            "invoice_date",
            "bol_number",
            "pro_number",
            "billed_weight_lb",
            "invoice_total",
        ],
        [
            [
                i.invoice_id,
                i.invoice_number,
                i.shipment.carrier_id,
                i.invoice_date,
                i.shipment.bol_number,
                format_pro(i.pro_digits, i.pro_style),
                i.billed_weight,
                i.total,
            ]
            for i in invoices
        ],
    )
    lines: list[list[object]] = []
    n = 0
    for i in invoices:
        for no, ln in enumerate(i.lines, start=1):
            n += 1
            lines.append([f"L-{n:07d}", i.invoice_id, no, ln.code, ln.quantity, ln.amount])
    write_csv(
        out / "invoice_lines.csv",
        ["line_id", "invoice_id", "line_no", "charge_code", "quantity", "amount"],
        lines,
    )
    write_csv(
        out / "approvals.csv",
        ["approval_id", "shipment_id", "charge_code", "approved_on"],
        [
            [f"APR-{k:04d}", a["shipment_id"], a["charge_code"], a["approved_on"]]
            for k, a in enumerate(sorted(result.approvals, key=lambda a: a["shipment_id"]), start=1)
        ],
    )
    write_csv(
        out / "reweigh_certificates.csv",
        ["cert_id", "shipment_id", "cert_weight_lb", "cert_date"],
        [
            [f"CRT-{k:04d}", c["shipment_id"], c["cert_weight_lb"], c["cert_date"]]
            for k, c in enumerate(
                sorted(result.certificates, key=lambda c: c["shipment_id"]), start=1
            )
        ],
    )
    errors = [i for i in invoices if i.kind == "error"]
    write_csv(
        out / "ground_truth_errors.csv",
        [
            "error_id",
            "invoice_id",
            "shipment_id",
            "carrier_id",
            "finding_type",
            "overcharge",
            "note",
        ],
        [
            [
                f"E-{k:04d}",
                i.invoice_id,
                i.shipment.shipment_id,
                i.shipment.carrier_id,
                i.finding_type,
                i.overcharge,
                i.note,
            ]
            for k, i in enumerate(errors, start=1)
        ],
    )
    write_csv(
        out / "ground_truth_lookalikes.csv",
        ["invoice_id", "shipment_id", "kind"],
        [
            [i.invoice_id, i.shipment.shipment_id, i.finding_type]
            for i in invoices
            if i.kind == "lookalike"
        ],
    )


def generate(seed: int, out: Path) -> dict[str, int]:
    """Write every raw table and both ledgers to `out`. Returns row counts for the summary."""
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    n_tl = N_SHIPMENTS - int(round(N_SHIPMENTS * LTL_SHARE))
    ref = build_reference(rng, n_tl)
    shipments = generate_shipments(rng, ref, N_SHIPMENTS, LTL_SHARE)
    result = generate_billing(rng, ref, shipments)
    _write_reference(out, ref)
    _write_shipments(out, shipments)
    _write_billing(out, result)
    return {
        "shipments": len(shipments),
        "invoices": len(result.invoices),
        "invoice_lines": sum(len(i.lines) for i in result.invoices),
        "errors": sum(1 for i in result.invoices if i.kind == "error"),
        "lookalikes": sum(1 for i in result.invoices if i.kind == "lookalike"),
    }
