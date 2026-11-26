"""Hand-built raw tables for fixture tests: a tiny network where every number is checkable."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

import duckdb

from rerate import runner
from rerate.generator import write_csv
from rerate.generator.rating import ltl_fuel, ltl_linehaul, tl_fuel, tl_linehaul

HEADERS = {
    "carriers": ["carrier_id", "carrier_name", "mode"],
    "plants": ["plant_id", "plant_name", "lat", "lon"],
    "consignees": [
        "consignee_id",
        "consignee_name",
        "lat",
        "lon",
        "is_residential",
        "needs_liftgate",
    ],
    "shipments": [
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
    "invoices": [
        "invoice_id",
        "invoice_number",
        "carrier_id",
        "invoice_date",
        "bol_number",
        "pro_number",
        "billed_weight_lb",
        "invoice_total",
    ],
    "invoice_lines": ["line_id", "invoice_id", "line_no", "charge_code", "quantity", "amount"],
    "contract_versions": [
        "contract_version_id",
        "carrier_id",
        "version_label",
        "effective_from",
        "effective_to",
        "ltl_discount",
        "ltl_min_charge",
        "tl_rate_multiplier",
        "tl_min_charge",
        "tl_stop_charge",
    ],
    "ltl_tariff": ["carrier_id", "zone", "freight_class", "break_min_lb", "rate_cwt"],
    "tl_lane_rates": ["carrier_id", "plant_id", "consignee_id", "rate_per_mile"],
    "diesel_index": ["effective_date", "diesel_price"],
    "fsc_tables": ["carrier_id", "band_low", "band_high", "fsc_rate"],
    "accessorial_schedule": [
        "carrier_id",
        "charge_code",
        "rate",
        "unit",
        "rule",
        "free_minutes",
        "increment_minutes",
    ],
    "approvals": ["approval_id", "shipment_id", "charge_code", "approved_on"],
    "reweigh_certificates": ["cert_id", "shipment_id", "cert_weight_lb", "cert_date"],
}

# 900 lb, class 70: $39.10/cwt at the 500 break, $31.75/cwt at the 1000 break
LTL_BREAKS = [0, 500, 1000, 2000, 5000, 10000]
LTL_RATES = [D("48.20"), D("39.10"), D("31.75"), D("27.00"), D("22.00"), D("18.00")]
LTL_DISCOUNT = D("0.66")
LTL_MIN = D("95.00")
TL_RATE = D("2.0000")

# Monday-effective diesel index
INDEX = {
    date(2025, 12, 22): D("3.50"),
    date(2025, 12, 29): D("3.50"),
    date(2026, 1, 5): D("3.52"),
    date(2026, 2, 23): D("3.52"),
    date(2026, 3, 2): D("3.58"),
    date(2026, 3, 9): D("3.66"),
    date(2026, 3, 16): D("3.70"),
    date(2026, 3, 23): D("3.75"),
    date(2026, 3, 30): D("3.75"),
}


def ltl_pct(low: D) -> D:
    return D("0.21") + D("0.005") * int((low - D("3.55")) / D("0.05"))


def tl_per_mile(low: D) -> D:
    return ((low - D("1.25")) / D("6.0")).quantize(D("0.001"))


def fsc_rows() -> list[list]:
    rows = []
    low = D("3.40")
    while low < D("4.00"):
        rows.append(["LTL1", low, low + D("0.05"), ltl_pct(low)])
        rows.append(["TL1", low, low + D("0.05"), tl_per_mile(low)])
        low += D("0.05")
    return rows


def ltl_lines(weight: int, fuel_pct: D, extras: list[tuple[str, D]] = ()) -> list[tuple]:
    """LTL lines the way the contract prices them (using the generator's reference arithmetic)."""
    lh = ltl_linehaul(LTL_BREAKS, LTL_RATES, weight, LTL_DISCOUNT, LTL_MIN)
    lines = [("LINEHAUL", D(weight), lh)]
    lines += [(code, D(1), amt) for code, amt in extras]
    lines.append(("FUEL", None, ltl_fuel(lh, fuel_pct)))
    return lines


def tl_lines(miles: D, rate: D, fsc_per_mile: D, stops: int = 0, extras=()) -> list[tuple]:
    lines = [("LINEHAUL", miles, tl_linehaul(rate, miles, D("350.00")))]
    if stops:
        lines.append(("STOPOFF", D(stops), D("75.00") * stops))
    lines += list(extras)
    lines.append(("FUEL", None, tl_fuel(fsc_per_mile, miles)))
    return lines


@dataclass
class World:
    t: dict[str, list[list]] = field(default_factory=dict)
    n_shipments: int = 0
    n_invoices: int = 0
    n_lines: int = 0

    def __post_init__(self):
        t = self.t
        t["carriers"] = [["LTL1", "Test LTL", "LTL"], ["TL1", "Test TL", "TL"]]
        t["plants"] = [["P1", "Plant", 40.0, -90.0]]
        t["consignees"] = [
            ["C1", "Plain", 41.0, -90.0, 0, 0],
            ["C2", "Liftgate", 41.5, -90.0, 0, 1],
            ["C3", "Residential", 42.0, -90.0, 1, 0],
        ]
        t["contract_versions"] = [
            ["CV1", "LTL1", "v1", "2025-01-01", "9999-12-31", LTL_DISCOUNT, LTL_MIN, "", "", ""],
            ["CV2", "TL1", "v1", "2025-01-01", "2025-12-31", "", "", "1.0000", "350.00", "75.00"],
            ["CV3", "TL1", "v2", "2026-01-01", "9999-12-31", "", "", "0.9500", "350.00", "75.00"],
        ]
        t["ltl_tariff"] = [
            ["LTL1", "Z2", 70, brk, rate] for brk, rate in zip(LTL_BREAKS, LTL_RATES, strict=True)
        ]
        t["tl_lane_rates"] = [["TL1", "P1", "C1", TL_RATE]]
        t["diesel_index"] = [[d, p] for d, p in INDEX.items()]
        t["fsc_tables"] = fsc_rows()
        t["accessorial_schedule"] = [
            ["LTL1", "LIFTGATE", "45.00", "flat", "consignee_flag", "", ""],
            ["LTL1", "RESIDENTIAL", "60.00", "flat", "consignee_flag", "", ""],
            ["TL1", "DETENTION", "65.00", "hour", "approval_only", 120, 60],
        ]
        for name in ("shipments", "invoices", "invoice_lines", "approvals", "reweigh_certificates"):
            t[name] = []

    def shipment(
        self,
        *,
        mode="LTL",
        ship="2026-03-10",
        weight=900,
        consignee="C1",
        miles="500.0",
        stops=0,
        dwell=30,
    ) -> str:
        self.n_shipments += 1
        sid = f"S{self.n_shipments:03d}"
        carrier = "LTL1" if mode == "LTL" else "TL1"
        gate_in = f"{ship} 10:00:00"
        h, m = divmod(10 * 60 + dwell, 60)
        gate_out = f"{ship} {h:02d}:{m:02d}:00"
        self.t["shipments"].append(
            [
                sid,
                f"BOL-{self.n_shipments:03d}",
                carrier,
                mode,
                "P1",
                consignee,
                ship,
                70 if mode == "LTL" else "",
                weight,
                miles,
                "Z2",
                stops,
                gate_in,
                gate_out,
            ]
        )
        return sid

    def invoice(
        self,
        sid: str,
        lines: list[tuple],
        *,
        days_after=2,
        number=None,
        pro=None,
        weight=None,
        invoice_date=None,
    ) -> str:
        ship = next(r for r in self.t["shipments"] if r[0] == sid)
        self.n_invoices += 1
        iid = f"I{self.n_invoices:03d}"
        when = (
            invoice_date or (date.fromisoformat(ship[6]) + timedelta(days=days_after)).isoformat()
        )
        total = sum((ln[2] for ln in lines), D("0.00"))
        billed_w = (weight if weight is not None else ship[8]) if ship[3] == "LTL" else ""
        self.t["invoices"].append(
            [
                iid,
                number or f"N{self.n_invoices:03d}",
                ship[2],
                when,
                ship[1],
                pro or str(100000 + self.n_invoices),
                billed_w,
                total,
            ]
        )
        for no, (code, qty, amount) in enumerate(lines, start=1):
            self.n_lines += 1
            self.t["invoice_lines"].append([f"L{self.n_lines:04d}", iid, no, code, qty, amount])
        return iid

    def approve(self, sid: str, code: str) -> None:
        self.t["approvals"].append([f"A{len(self.t['approvals']) + 1}", sid, code, "2026-03-11"])

    def certify(self, sid: str, weight: int) -> None:
        self.t["reweigh_certificates"].append(
            [f"R{len(self.t['reweigh_certificates']) + 1}", sid, weight, "2026-03-11"]
        )

    def build(self, directory: Path) -> Built:
        raw = directory / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        for name, header in HEADERS.items():
            write_csv(raw / f"{name}.csv", header, self.t[name])
        db = directory / "world.duckdb"
        _built, failures = runner.build(raw, db)
        return Built(raw, db, failures)


@dataclass
class Built:
    raw: Path
    db: Path
    failures: list

    def q(self, sql: str) -> list[tuple]:
        con = duckdb.connect(str(self.db), read_only=True)
        try:
            return con.execute(sql).fetchall()
        finally:
            con.close()

    def findings(self) -> list[tuple]:
        return self.q("SELECT invoice_id, finding_type, overcharge FROM fct_findings ORDER BY 1, 2")
