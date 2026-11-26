"""Carrier billing, error injection and the ground-truth ledgers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal as D

import numpy as np

from .rating import (
    CENT,
    detention_hours,
    ltl_fuel,
    ltl_linehaul,
    tl_fuel,
    tl_linehaul,
    tl_rate_per_mile,
)
from .reference import (
    ACCESSORIAL_RATES,
    AMENDMENT_CARRIER,
    AMENDMENT_DATE,
    DETENTION_FREE_MINUTES,
    DETENTION_INCREMENT_MINUTES,
    LTL_DISCOUNT,
    LTL_MIN_CHARGE,
    TL_MIN_CHARGE,
    TL_STOP_CHARGE,
    Reference,
    contract_multiplier,
    fsc_rate_for,
)
from .shipments import Shipment

ERROR_COUNTS = {
    "fsc_wrong_week": 60,
    "duplicate": 24,
    "unapproved_accessorial": 40,
    "weight_overbill": 30,
    "contract_rate": 20,
}
LOOKALIKE_COUNTS = {
    "reweigh_certificate": 25,
    "approved_detention": 15,
    "late_billed_correct_fuel": 10,
}
CODES_NOT_ACCESSORIAL = ("LINEHAUL", "STOPOFF", "FUEL")


@dataclass
class Line:
    code: str
    quantity: D | None
    amount: D


@dataclass
class Invoice:
    shipment: Shipment
    invoice_date: date
    lines: list[Line]
    billed_weight: int | None
    pro_digits: int
    pro_style: int
    kind: str = "plain"
    finding_type: str = ""
    overcharge: D = D("0.00")
    note: str = ""
    original: Invoice | None = None
    invoice_id: str = ""
    invoice_number: str = ""
    tags: dict = field(default_factory=dict)

    @property
    def total(self) -> D:
        return sum((ln.amount for ln in self.lines), D("0.00"))


@dataclass
class BillingResult:
    invoices: list[Invoice]
    approvals: list[dict]
    certificates: list[dict]


class Biller:
    """The carrier's billing system: what a correct bill looks like, and how it goes wrong."""

    def __init__(self, ref: Reference):
        self.ref = ref
        self.consignees = {c.consignee_id: c for c in ref.consignees}

    def lines(
        self,
        s: Shipment,
        *,
        weight: int | None = None,
        fuel_on: date | None = None,
        multiplier: D | None = None,
        approved: frozenset[str] = frozenset(),
    ) -> list[Line]:
        fuel_on = fuel_on or s.ship_date
        carrier = s.carrier_id
        fsc = fsc_rate_for(self.ref, carrier, fuel_on)
        out: list[Line] = []
        if s.mode == "LTL":
            w = weight if weight is not None else s.bol_weight_lb
            breaks, rates = self.ref.tariff[(carrier, s.zone, s.freight_class)]
            lh = ltl_linehaul(breaks, rates, w, LTL_DISCOUNT[carrier], LTL_MIN_CHARGE[carrier])
            out.append(Line("LINEHAUL", D(w), lh))
            fuel = ltl_fuel(lh, fsc)
        else:
            mult = (
                multiplier if multiplier is not None else contract_multiplier(carrier, s.ship_date)
            )
            rate = tl_rate_per_mile(s.lane.rate_per_mile, mult)
            out.append(Line("LINEHAUL", s.miles, tl_linehaul(rate, s.miles, TL_MIN_CHARGE)))
            if s.extra_stops:
                out.append(Line("STOPOFF", D(s.extra_stops), TL_STOP_CHARGE * s.extra_stops))
            fuel = tl_fuel(fsc, s.miles)
        out.extend(self.accessorials(s, approved))
        out.append(Line("FUEL", None, fuel))
        return out

    def accessorials(self, s: Shipment, approved: frozenset[str]) -> list[Line]:
        rates = ACCESSORIAL_RATES[s.carrier_id]
        c = self.consignees[s.consignee_id]
        out: list[Line] = []
        if s.mode == "LTL":
            if c.needs_liftgate or "LIFTGATE" in approved:
                out.append(Line("LIFTGATE", D(1), rates["LIFTGATE"]))
            if c.is_residential or "RESIDENTIAL" in approved:
                out.append(Line("RESIDENTIAL", D(1), rates["RESIDENTIAL"]))
        elif "DETENTION" in approved:
            hours = detention_hours(
                s.dwell_minutes, DETENTION_FREE_MINUTES, DETENTION_INCREMENT_MINUTES
            )
            if hours:
                out.append(Line("DETENTION", D(hours), rates["DETENTION"] * hours))
        return out

    def detention_line(self, s: Shipment) -> Line:
        hours = detention_hours(
            s.dwell_minutes, DETENTION_FREE_MINUTES, DETENTION_INCREMENT_MINUTES
        )
        return Line("DETENTION", D(hours), ACCESSORIAL_RATES[s.carrier_id]["DETENTION"] * hours)


def total_of(lines: list[Line]) -> D:
    return sum((ln.amount for ln in lines), D("0.00"))


def pick_role(
    rng: np.random.Generator,
    candidates: list[Shipment],
    used: set[str],
    count: int,
    attempt: Callable[[Shipment], Invoice | None],
    label: str,
) -> list[Invoice]:
    out: list[Invoice] = []
    for i in rng.permutation(len(candidates)):
        s = candidates[int(i)]
        if s.shipment_id in used:
            continue
        inv = attempt(s)
        if inv is None:
            continue
        used.add(s.shipment_id)
        out.append(inv)
        if len(out) == count:
            return out
    raise RuntimeError(f"not enough eligible shipments for {label}: {len(out)} of {count}")


def format_pro(digits: int, style: int) -> str:
    s = str(digits)
    if style == 0:
        return s
    if style == 1:
        z = s.rjust(9, "0")
        return f"{z[:-1]}-{z[-1]}"
    if style == 2:
        return f"PRO {s}"
    return f" {s.rjust(10, '0')} "


def misprint(rng: np.random.Generator, digits: int, taken: set[int]) -> int:
    s = str(digits)
    while True:
        pos = int(rng.integers(1, len(s)))
        new = str((int(s[pos]) + int(rng.integers(1, 10))) % 10)
        candidate = int(s[:pos] + new + s[pos + 1 :])
        if candidate not in taken and candidate != digits:
            taken.add(candidate)
            return candidate


def generate_billing(
    rng: np.random.Generator, ref: Reference, shipments: list[Shipment]
) -> BillingResult:
    biller = Biller(ref)
    used: set[str] = set()
    invoices: list[Invoice] = []
    approvals: list[dict] = []
    certs: list[dict] = []

    def make(s: Shipment, lines: list[Line], delay: int, *, weight: int | None = None) -> Invoice:
        return Invoice(
            shipment=s,
            invoice_date=s.ship_date + timedelta(days=delay),
            lines=lines,
            billed_weight=weight if s.mode == "LTL" else None,
            pro_digits=s.pro_digits,
            pro_style=int(rng.integers(0, 4)),
        )

    ltl = [s for s in shipments if s.mode == "LTL"]
    tl = [s for s in shipments if s.mode == "TL"]

    def correct(s: Shipment) -> D:
        return total_of(biller.lines(s))

    # contract_rate: truckload invoices after the amendment billed at the pre-amendment rate
    def contract_error(s: Shipment) -> Invoice | None:
        billed = biller.lines(s, multiplier=D("1.0000"))
        inv = make(s, billed, int(rng.integers(1, 7)))
        inv.kind, inv.finding_type = "error", "contract_rate"
        inv.overcharge = total_of(billed) - correct(s)
        inv.note = "billed at the pre-amendment truckload rate"
        return inv if inv.overcharge >= D("5.00") else None

    amended = [s for s in tl if s.carrier_id == AMENDMENT_CARRIER and s.ship_date >= AMENDMENT_DATE]
    invoices += pick_role(
        rng, amended, used, ERROR_COUNTS["contract_rate"], contract_error, "contract_rate"
    )

    # weight_overbill: billed weight 3-15% above the BOL with no certificate
    def weight_error(s: Shipment) -> Invoice | None:
        if s.bol_weight_lb < 300:
            return None
        billed_w = int(np.ceil(s.bol_weight_lb * (1 + float(rng.uniform(0.03, 0.15)))))
        billed = biller.lines(s, weight=billed_w)
        over = total_of(billed) - correct(s)
        if over < D("2.00"):
            return None
        inv = make(s, billed, int(rng.integers(1, 7)), weight=billed_w)
        inv.kind, inv.finding_type, inv.overcharge = "error", "weight_overbill", over
        inv.note = f"billed {billed_w} lb against {s.bol_weight_lb} lb on the BOL"
        return inv

    invoices += pick_role(
        rng, ltl, used, ERROR_COUNTS["weight_overbill"], weight_error, "weight_overbill"
    )

    # fsc_wrong_week: fuel taken from the index week of the invoice date
    def fuel_pair(s: Shipment, lo: int, hi: int, floor: D) -> tuple[int, list[Line]] | None:
        base_fuel = correct(s)
        for delay in rng.permutation(np.arange(lo, hi + 1)):
            lines = biller.lines(s, fuel_on=s.ship_date + timedelta(days=int(delay)))
            if total_of(lines) - base_fuel >= floor:
                return int(delay), lines
        return None

    def fsc_error(s: Shipment) -> Invoice | None:
        found = fuel_pair(s, 7, 21, D("1.00"))
        if found is None:
            return None
        delay, lines = found
        inv = make(s, lines, delay, weight=s.bol_weight_lb)
        inv.kind, inv.finding_type = "error", "fsc_wrong_week"
        inv.overcharge = total_of(lines) - correct(s)
        inv.note = "fuel surcharge taken from the invoice week instead of the ship week"
        return inv

    invoices += pick_role(
        rng, shipments, used, ERROR_COUNTS["fsc_wrong_week"], fsc_error, "fsc_wrong_week"
    )

    # unapproved_accessorial: liftgate and residential on LTL, detention on truckload
    def acc_error(code: str) -> Callable[[Shipment], Invoice | None]:
        def attempt(s: Shipment) -> Invoice | None:
            c = biller.consignees[s.consignee_id]
            if code == "LIFTGATE" and c.needs_liftgate:
                return None
            if code == "RESIDENTIAL" and c.is_residential:
                return None
            if code == "DETENTION":
                if s.dwell_minutes <= DETENTION_FREE_MINUTES:
                    return None
                extra = biller.detention_line(s)
            else:
                extra = Line(code, D(1), ACCESSORIAL_RATES[s.carrier_id][code])
            lines = biller.lines(s)
            lines.insert(len(lines) - 1, extra)
            inv = make(s, lines, int(rng.integers(1, 7)), weight=s.bol_weight_lb)
            inv.kind, inv.finding_type = "error", "unapproved_accessorial"
            inv.overcharge = extra.amount
            inv.note = f"{code} billed with no approval and no schedule rule"
            return inv

        return attempt

    n_acc = ERROR_COUNTS["unapproved_accessorial"]
    for code, pool, count in (
        ("LIFTGATE", ltl, 14),
        ("RESIDENTIAL", ltl, 14),
        ("DETENTION", tl, n_acc - 28),
    ):
        invoices += pick_role(rng, pool, used, count, acc_error(code), f"accessorial {code}")

    # look-alikes: reweigh with certificate, approved detention, late billing with the right week
    def cert_lookalike(s: Shipment) -> Invoice | None:
        if s.bol_weight_lb < 300:
            return None
        cert_w = int(np.ceil(s.bol_weight_lb * (1 + float(rng.uniform(0.03, 0.15)))))
        billed = biller.lines(s, weight=cert_w)
        if total_of(billed) - correct(s) < D("2.00"):
            return None
        inv = make(s, billed, int(rng.integers(1, 7)), weight=cert_w)
        inv.kind, inv.finding_type = "lookalike", "reweigh_certificate"
        certs.append(
            {
                "shipment_id": s.shipment_id,
                "cert_weight_lb": cert_w,
                "cert_date": (s.ship_date + timedelta(days=int(rng.integers(1, 4)))).isoformat(),
            }
        )
        return inv

    invoices += pick_role(
        rng, ltl, used, LOOKALIKE_COUNTS["reweigh_certificate"], cert_lookalike, "reweigh"
    )

    def detention_lookalike(s: Shipment) -> Invoice | None:
        if s.dwell_minutes <= DETENTION_FREE_MINUTES:
            return None
        inv = make(s, biller.lines(s, approved=frozenset({"DETENTION"})), int(rng.integers(1, 7)))
        inv.kind, inv.finding_type = "lookalike", "approved_detention"
        approvals.append(
            {
                "shipment_id": s.shipment_id,
                "charge_code": "DETENTION",
                "approved_on": (s.ship_date + timedelta(days=int(rng.integers(1, 3)))).isoformat(),
            }
        )
        return inv

    invoices += pick_role(
        rng,
        tl,
        used,
        LOOKALIKE_COUNTS["approved_detention"],
        detention_lookalike,
        "approved detention",
    )

    def late_lookalike(s: Shipment) -> Invoice | None:
        found = fuel_pair(s, 14, 28, D("1.00"))
        if found is None:
            return None
        delay, _wrong = found
        inv = make(s, biller.lines(s), delay, weight=s.bol_weight_lb)
        inv.kind, inv.finding_type = "lookalike", "late_billed_correct_fuel"
        return inv

    invoices += pick_role(
        rng,
        shipments,
        used,
        LOOKALIKE_COUNTS["late_billed_correct_fuel"],
        late_lookalike,
        "late billing",
    )

    # everything else is billed correctly, with within-tolerance reweighs and cent rounding
    plain: list[Invoice] = []
    for s in shipments:
        if s.shipment_id in used:
            continue
        weight = s.bol_weight_lb if s.mode == "LTL" else None
        if s.mode == "LTL" and rng.random() < 0.06:
            weight = s.bol_weight_lb + max(
                1, int(s.bol_weight_lb * float(rng.uniform(0.003, 0.018)))
            )
        inv = make(s, biller.lines(s, weight=weight), int(rng.integers(1, 7)), weight=weight)
        if rng.random() < 0.15:
            target = inv.lines[0] if rng.random() < 0.5 else inv.lines[-1]
            target.amount += CENT if rng.random() < 0.5 else -CENT
        plain.append(inv)
    invoices += plain

    # duplicates of plain invoices: exact re-bills and mistyped-PRO re-bills with a near total
    taken_pro: dict[str, set[int]] = {}
    for s in shipments:
        taken_pro.setdefault(s.carrier_id, set()).add(s.pro_digits)
    originals = [plain[int(i)] for i in rng.permutation(len(plain))[: ERROR_COUNTS["duplicate"]]]
    for n, orig in enumerate(originals):
        mistyped = n >= 16
        digits = orig.pro_digits
        lines = [Line(ln.code, ln.quantity, ln.amount) for ln in orig.lines]
        if mistyped:
            digits = misprint(rng, digits, taken_pro[orig.shipment.carrier_id])
            shift = D(f"{float(rng.uniform(0.02, 0.60)):.2f}")
            lines[-1].amount += shift if rng.random() < 0.5 else -shift
        dup = Invoice(
            shipment=orig.shipment,
            invoice_date=orig.invoice_date + timedelta(days=int(rng.integers(7, 36))),
            lines=lines,
            billed_weight=orig.billed_weight,
            pro_digits=digits,
            pro_style=int(rng.integers(0, 4)),
            kind="error",
            finding_type="duplicate",
            original=orig,
            note=(
                "re-bill with a mistyped PRO"
                if mistyped
                else "exact re-bill under a new invoice number"
            ),
        )
        dup.overcharge = dup.total
        invoices.append(dup)

    number_invoices(invoices)
    return BillingResult(invoices, approvals, certs)


CARRIER_PREFIX = {"LTL1": "HLF", "LTL2": "RWL", "LTL3": "CDX", "TL1": "PRH", "TL2": "RWT"}


def number_invoices(invoices: list[Invoice]) -> None:
    invoices.sort(
        key=lambda i: (i.invoice_date, i.shipment.shipment_id, i.finding_type == "duplicate")
    )
    counters: dict[str, int] = {}
    for n, inv in enumerate(invoices, start=1):
        inv.invoice_id = f"INV-{n:06d}"
        carrier = inv.shipment.carrier_id
        counters[carrier] = counters.get(carrier, 100000) + 1
        inv.invoice_number = f"{CARRIER_PREFIX[carrier]}-{counters[carrier]}"
