"""Reference data: network geometry, tariffs, fuel tables, contracts and truckload lanes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal as D

import numpy as np

from .rating import q4

ROAD_FACTOR = 1.18
EARTH_RADIUS_MI = 3958.8

PLANTS = [
    ("P1", "North plant", 41.80, -87.70),
    ("P2", "Southeast plant", 33.70, -84.40),
    ("P3", "Southwest plant", 32.80, -96.80),
]

CARRIERS = [
    ("LTL1", "Harborline Freight", "LTL"),
    ("LTL2", "Ridgeway LTL", "LTL"),
    ("LTL3", "Cedar Express", "LTL"),
    ("TL1", "Prairie Haul", "TL"),
    ("TL2", "Redwood Truckload", "TL"),
]

LTL_BREAKS = [0, 500, 1000, 2000, 5000, 10000]
LTL_CLASSES = [55, 70, 85, 100]
ZONES = ["Z1", "Z2", "Z3"]
CLASS_FACTOR = {55: 1.00, 70: 1.30, 85: 1.55, 100: 1.85}
ZONE_FACTOR = {"Z1": 1.00, "Z2": 1.30, "Z3": 1.70}
BREAK_FACTOR = [1.00, 0.82, 0.66, 0.54, 0.43, 0.35]
CARRIER_TARIFF_FACTOR = {"LTL1": 1.00, "LTL2": 0.96, "LTL3": 1.05}
BASE_CWT = 34.0

LTL_DISCOUNT = {"LTL1": D("0.66"), "LTL2": D("0.64"), "LTL3": D("0.70")}
LTL_MIN_CHARGE = {"LTL1": D("95.00"), "LTL2": D("100.00"), "LTL3": D("110.00")}
TL_MIN_CHARGE = D("350.00")
TL_STOP_CHARGE = D("75.00")
AMENDMENT_DATE = date(2026, 1, 1)
AMENDMENT_CARRIER = "TL2"
AMENDMENT_MULTIPLIER = D("0.95")

LTL_FSC_BASE = {"LTL1": D("0.2100"), "LTL2": D("0.2050"), "LTL3": D("0.2200")}
TL_FSC_MPG = {"TL1": D("6.0"), "TL2": D("6.4")}
BAND_WIDTH = D("0.05")

MARKET_FIXED = 310.0
MARKET_PER_MILE = 2.05
PREMIUM_FACTOR = 1.20

# charge code, flat or per-hour rate by carrier
ACCESSORIAL_RATES = {
    "LTL1": {"LIFTGATE": D("45.00"), "RESIDENTIAL": D("60.00")},
    "LTL2": {"LIFTGATE": D("50.00"), "RESIDENTIAL": D("65.00")},
    "LTL3": {"LIFTGATE": D("55.00"), "RESIDENTIAL": D("70.00")},
    "TL1": {"DETENTION": D("65.00")},
    "TL2": {"DETENTION": D("70.00")},
}
DETENTION_FREE_MINUTES = 120
DETENTION_INCREMENT_MINUTES = 60

SHIP_START = date(2025, 7, 1)
SHIP_END = date(2026, 6, 30)
INDEX_START = date(2025, 6, 23)
INDEX_END = date(2026, 9, 28)


def great_circle_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def road_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> D:
    """Great-circle distance times the road factor, to one decimal."""
    return D(f"{great_circle_miles(lat1, lon1, lat2, lon2) * ROAD_FACTOR:.1f}")


def offset_point(
    lat: float, lon: float, road_target: float, bearing_deg: float
) -> tuple[float, float]:
    """A point whose road miles from (lat, lon) equal the target, found by scaling the offset."""
    gc = road_target / ROAD_FACTOR
    b = math.radians(bearing_deg)
    for _ in range(6):
        dlat = gc * math.cos(b) / 69.0
        dlon = gc * math.sin(b) / (69.17 * math.cos(math.radians(lat)))
        p_lat, p_lon = lat + dlat, lon + dlon
        got = great_circle_miles(lat, lon, p_lat, p_lon) * ROAD_FACTOR
        gc *= road_target / got
    return round(p_lat, 4), round(p_lon, 4)


@dataclass(frozen=True)
class Consignee:
    consignee_id: str
    name: str
    lat: float
    lon: float
    is_residential: bool
    needs_liftgate: bool


@dataclass(frozen=True)
class Lane:
    carrier_id: str
    plant_id: str
    consignee_id: str
    role: str  # short, overpriced, regular
    miles: D
    rate_per_mile: D
    shipments: int

    @property
    def lane_id(self) -> str:
        return f"{self.plant_id}>{self.consignee_id}"


@dataclass
class Reference:
    consignees: list[Consignee]
    lanes: list[Lane]
    tariff: dict[tuple[str, str, int], tuple[list[int], list[D]]]
    tariff_rows: list[tuple]
    diesel: dict[date, D]
    fsc: dict[str, list[tuple[D, D, D]]]


def build_tariff() -> tuple[dict, list[tuple]]:
    table: dict[tuple[str, str, int], tuple[list[int], list[D]]] = {}
    rows: list[tuple] = []
    for carrier, cf in CARRIER_TARIFF_FACTOR.items():
        for zone in ZONES:
            for cls in LTL_CLASSES:
                rates = [
                    D(f"{BASE_CWT * CLASS_FACTOR[cls] * ZONE_FACTOR[zone] * bf * cf:.2f}")
                    for bf in BREAK_FACTOR
                ]
                table[(carrier, zone, cls)] = (list(LTL_BREAKS), rates)
                for brk, rate in zip(LTL_BREAKS, rates, strict=True):
                    rows.append((carrier, zone, cls, brk, rate))
    return table, rows


def build_diesel(rng: np.random.Generator) -> dict[date, D]:
    out: dict[date, D] = {}
    price = 3.62
    d = INDEX_START
    while d <= INDEX_END:
        out[d] = D(f"{price:.2f}")
        price += float(rng.normal(0, 0.035)) + 0.12 * (3.65 - price)
        price = min(max(price, 3.15), 4.40)
        d += timedelta(days=7)
    return out


def build_fsc() -> dict[str, list[tuple[D, D, D]]]:
    """Per carrier: (band_low, band_high, rate). LTL is a fraction of linehaul, TL is $/mile."""
    out: dict[str, list[tuple[D, D, D]]] = {}
    lows = [D("2.50") + BAND_WIDTH * k for k in range(60)]
    for carrier, _name, mode in CARRIERS:
        rows = []
        for low in lows:
            if mode == "LTL":
                k = int((low - D("3.55")) / BAND_WIDTH)
                rate = LTL_FSC_BASE[carrier] + D("0.005") * k
            else:
                rate = ((low - D("1.25")) / TL_FSC_MPG[carrier]).quantize(D("0.001"))
            rows.append((low, low + BAND_WIDTH, q4(rate)))
        out[carrier] = rows
    return out


def build_lanes_and_consignees(
    rng: np.random.Generator, n_tl_shipments: int
) -> tuple[list[Consignee], list[Lane]]:
    """30 truckload lanes (2 short hauls, 3 overpriced) plus 30 consignees used only by LTL."""
    specs: list[tuple[str, float, str]] = []  # role, miles, carrier
    specs += [("short", 80.0, "TL1"), ("short", 110.0, "TL1")]
    specs += [("overpriced", m, "TL1") for m in (640.0, 900.0, 1250.0)]
    # stratified across the range so the cost curve is anchored at both ends
    regular_miles = (140 + (1500 - 140) * (np.arange(25) + rng.uniform(0, 1, 25)) / 25).round(0)
    regular_carriers = ["TL1"] * 11 + ["TL2"] * 14
    rng.shuffle(regular_carriers)
    specs += [
        ("regular", float(m), c) for m, c in zip(regular_miles, regular_carriers, strict=True)
    ]

    flags = rng.random(60)
    consignees: list[Consignee] = []
    lanes: list[Lane] = []
    base = 30
    extra = rng.multinomial(n_tl_shipments - base * len(specs), rng.dirichlet(np.ones(len(specs))))
    for i, (role, miles, carrier) in enumerate(specs):
        plant_id, _n, plat, plon = PLANTS[i % len(PLANTS)]
        lat, lon = offset_point(plat, plon, miles, float(rng.uniform(0, 360)))
        cid = f"C{i + 1:03d}"
        consignees.append(
            Consignee(
                cid,
                f"Site {i + 1:03d}",
                lat,
                lon,
                bool(flags[i] > 0.80),
                bool(flags[i] < 0.40),
            )
        )
        real_miles = float(road_miles(plat, plon, lat, lon))
        market = MARKET_FIXED + MARKET_PER_MILE * real_miles
        if role == "overpriced":
            noise = PREMIUM_FACTOR * (1 + float(rng.uniform(-0.01, 0.01)))
        elif role == "short":
            noise = 1 + float(rng.uniform(-0.02, 0.02))
        else:
            noise = 1 + float(rng.uniform(-0.05, 0.05))
        rate = q4(D(f"{market * noise / real_miles:.6f}"))
        lanes.append(
            Lane(carrier, plant_id, cid, role, D(f"{real_miles:.1f}"), rate, base + int(extra[i]))
        )
    for j in range(30, 60):
        lat = float(rng.uniform(29.0, 48.0))
        lon = float(rng.uniform(-123.0, -69.0))
        consignees.append(
            Consignee(
                f"C{j + 1:03d}",
                f"Site {j + 1:03d}",
                round(lat, 4),
                round(lon, 4),
                bool(flags[j] > 0.80),
                bool(flags[j] < 0.40),
            )
        )
    return consignees, lanes


def contract_versions() -> list[dict]:
    rows = []
    n = 0
    for carrier, _name, mode in CARRIERS:
        spans = [("v1", date(2025, 1, 1), date(9999, 12, 31), D("1.0000"))]
        if carrier == AMENDMENT_CARRIER:
            spans = [
                ("v1", date(2025, 1, 1), AMENDMENT_DATE - timedelta(days=1), D("1.0000")),
                ("v2", AMENDMENT_DATE, date(9999, 12, 31), AMENDMENT_MULTIPLIER),
            ]
        for label, start, end, mult in spans:
            n += 1
            rows.append(
                {
                    "contract_version_id": f"CV{n:02d}",
                    "carrier_id": carrier,
                    "version_label": label,
                    "effective_from": start.isoformat(),
                    "effective_to": end.isoformat(),
                    "ltl_discount": LTL_DISCOUNT.get(carrier, "") if mode == "LTL" else "",
                    "ltl_min_charge": LTL_MIN_CHARGE.get(carrier, "") if mode == "LTL" else "",
                    "tl_rate_multiplier": mult if mode == "TL" else "",
                    "tl_min_charge": TL_MIN_CHARGE if mode == "TL" else "",
                    "tl_stop_charge": TL_STOP_CHARGE if mode == "TL" else "",
                }
            )
    return rows


def contract_multiplier(carrier: str, ship_date: date) -> D:
    if carrier == AMENDMENT_CARRIER and ship_date >= AMENDMENT_DATE:
        return AMENDMENT_MULTIPLIER
    return D("1.0000")


def index_week(d: date) -> date:
    """Monday-effective week containing a date."""
    return d - timedelta(days=d.weekday())


def fsc_rate_for(ref: Reference, carrier: str, on: date) -> D:
    price = ref.diesel[index_week(on)]
    for low, high, rate in ref.fsc[carrier]:
        if low <= price < high:
            return rate
    raise ValueError(f"no FSC band for {carrier} at {price}")


def build_reference(rng: np.random.Generator, n_tl_shipments: int) -> Reference:
    tariff, tariff_rows = build_tariff()
    consignees, lanes = build_lanes_and_consignees(rng, n_tl_shipments)
    return Reference(consignees, lanes, tariff, tariff_rows, build_diesel(rng), build_fsc())
