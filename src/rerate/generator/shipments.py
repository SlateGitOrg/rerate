"""Shipment generation: 60% LTL to any consignee, 40% truckload on the fixed lanes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal as D

import numpy as np

from .reference import (
    PLANTS,
    SHIP_END,
    SHIP_START,
    Lane,
    Reference,
    road_miles,
)

LTL_CARRIERS = ["LTL1", "LTL2", "LTL3"]
LTL_CARRIER_SHARE = [0.40, 0.35, 0.25]
FREIGHT_CLASSES = [55, 70, 85, 100]
CLASS_SHARE = [0.30, 0.35, 0.20, 0.15]


@dataclass
class Shipment:
    shipment_id: str
    bol_number: str
    carrier_id: str
    mode: str
    plant_id: str
    consignee_id: str
    ship_date: date
    freight_class: int | None
    bol_weight_lb: int
    miles: D
    zone: str
    extra_stops: int
    gate_in: datetime
    gate_out: datetime
    lane: Lane | None
    pro_digits: int = 0

    @property
    def dwell_minutes(self) -> int:
        return int((self.gate_out - self.gate_in).total_seconds() // 60)


def zone_for(miles: D) -> str:
    if miles < 400:
        return "Z1"
    if miles < 1000:
        return "Z2"
    return "Z3"


def ship_days() -> list[date]:
    days = []
    d = SHIP_START
    while d <= SHIP_END:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def generate_shipments(
    rng: np.random.Generator, ref: Reference, n_total: int = 4000, ltl_share: float = 0.60
) -> list[Shipment]:
    n_ltl = int(round(n_total * ltl_share))
    days = ship_days()
    plants = {p[0]: (p[2], p[3]) for p in PLANTS}
    cons = {c.consignee_id: c for c in ref.consignees}
    raw: list[tuple] = []

    for _ in range(n_ltl):
        carrier = str(rng.choice(LTL_CARRIERS, p=LTL_CARRIER_SHARE))
        plant = PLANTS[int(rng.integers(len(PLANTS)))][0]
        consignee = ref.consignees[int(rng.integers(len(ref.consignees)))]
        weight = int(min(max(rng.lognormal(mean=7.0, sigma=1.0), 60), 14000))
        cls = int(rng.choice(FREIGHT_CLASSES, p=CLASS_SHARE))
        raw.append(("LTL", carrier, plant, consignee.consignee_id, cls, weight, 0, None))
    for lane in ref.lanes:
        for _ in range(lane.shipments):
            weight = int(rng.integers(8000, 44000))
            stops = int(rng.choice([0, 1, 2], p=[0.85, 0.11, 0.04]))
            raw.append(
                ("TL", lane.carrier_id, lane.plant_id, lane.consignee_id, None, weight, stops, lane)
            )

    order = rng.permutation(len(raw))
    dates = sorted(days[int(i)] for i in rng.integers(len(days), size=len(raw)))
    shipments: list[Shipment] = []
    bol_numbers = rng.choice(9_000_000, size=len(raw), replace=False) + 1_000_000
    for n, (idx, ship_date) in enumerate(zip(order, dates, strict=True), start=1):
        mode, carrier, plant, cid, cls, weight, stops, lane = raw[int(idx)]
        plat, plon = plants[plant]
        c = cons[cid]
        miles = lane.miles if lane else road_miles(plat, plon, c.lat, c.lon)
        transit = 1 + int(float(miles) // 500)
        gate_in = datetime.combine(ship_date + timedelta(days=transit), datetime.min.time())
        gate_in += timedelta(minutes=int(rng.integers(7 * 60, 16 * 60)))
        if mode == "TL" and rng.random() < 0.12:
            dwell = int(rng.integers(125, 301))
        elif mode == "TL":
            dwell = int(rng.integers(25, 111))
        else:
            dwell = int(rng.integers(15, 91))
        shipments.append(
            Shipment(
                shipment_id=f"SHP-{n:06d}",
                bol_number=f"BOL-{int(bol_numbers[int(idx)]):07d}",
                carrier_id=carrier,
                mode=mode,
                plant_id=plant,
                consignee_id=cid,
                ship_date=ship_date,
                freight_class=cls,
                bol_weight_lb=weight,
                miles=miles,
                zone=zone_for(miles),
                extra_stops=stops,
                gate_in=gate_in,
                gate_out=gate_in + timedelta(minutes=dwell),
                lane=lane,
            )
        )
    assign_pro_numbers(rng, shipments)
    return shipments


def assign_pro_numbers(rng: np.random.Generator, shipments: list[Shipment]) -> None:
    """A unique PRO number per carrier and shipment."""
    used: dict[str, set[int]] = {}
    for s in shipments:
        taken = used.setdefault(s.carrier_id, set())
        while True:
            digits = int(rng.integers(100_000, 99_999_999))
            if digits not in taken:
                taken.add(digits)
                s.pro_digits = digits
                break
