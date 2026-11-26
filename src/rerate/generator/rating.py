"""Decimal mirror of the contract arithmetic.

The carrier's billing system in the generator and the error ledger both use these
functions. The SQL models re-implement the same rules independently, so agreement
between the two to the cent is a real check rather than shared code.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
FOUR_DP = Decimal("0.0001")
ONE_PCT = Decimal("0.01")


def q2(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def q4(x: Decimal) -> Decimal:
    return x.quantize(FOUR_DP, rounding=ROUND_HALF_UP)


def ltl_gross(breaks: list[int], rates: list[Decimal], weight_lb: int) -> Decimal:
    """Gross LTL charge: the cheaper of the actual break and the next break at its minimum."""
    i = bisect_right(breaks, weight_lb) - 1
    actual = q2(Decimal(weight_lb) * rates[i] * ONE_PCT)
    if i + 1 < len(breaks):
        deficit = q2(Decimal(breaks[i + 1]) * rates[i + 1] * ONE_PCT)
        return min(actual, deficit)
    return actual


def ltl_linehaul(
    breaks: list[int],
    rates: list[Decimal],
    weight_lb: int,
    discount: Decimal,
    min_charge: Decimal,
) -> Decimal:
    net = q2(ltl_gross(breaks, rates, weight_lb) * (1 - discount))
    return max(net, min_charge)


def ltl_fuel(linehaul: Decimal, fsc_pct: Decimal) -> Decimal:
    return q2(linehaul * fsc_pct)


def tl_rate_per_mile(lane_rate: Decimal, multiplier: Decimal) -> Decimal:
    return q4(lane_rate * multiplier)


def tl_linehaul(rate_per_mile: Decimal, miles: Decimal, min_charge: Decimal) -> Decimal:
    return max(q2(rate_per_mile * miles), min_charge)


def tl_fuel(fsc_per_mile: Decimal, miles: Decimal) -> Decimal:
    return q2(fsc_per_mile * miles)


def detention_hours(dwell_minutes: int, free_minutes: int = 120, increment: int = 60) -> int:
    """Started increments after the free time."""
    if dwell_minutes <= free_minutes:
        return 0
    return math.ceil((dwell_minutes - free_minutes) / increment)
