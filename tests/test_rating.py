"""The Python mirror of the contract arithmetic, checked against hand-worked numbers."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from rerate.generator.rating import (
    detention_hours,
    ltl_fuel,
    ltl_gross,
    ltl_linehaul,
    q2,
    tl_fuel,
    tl_linehaul,
    tl_rate_per_mile,
)
from rerate.generator.reference import great_circle_miles, offset_point, road_miles

BREAKS = [0, 500, 1000, 2000, 5000, 10000]
RATES = [D("48.20"), D("39.10"), D("31.75"), D("27.00"), D("22.00"), D("18.00")]


def test_ltl_nine_hundred_pounds_is_rated_at_the_thousand_pound_break():
    assert ltl_gross(BREAKS, RATES, 900) == D("317.50")
    assert ltl_linehaul(BREAKS, RATES, 900, D("0.66"), D("95.00")) == D("107.95")


def test_ltl_light_shipment_returns_the_absolute_minimum():
    assert ltl_gross(BREAKS, RATES, 120) == D("57.84")
    assert ltl_linehaul(BREAKS, RATES, 120, D("0.66"), D("95.00")) == D("95.00")


def test_ltl_actual_break_wins_when_it_is_cheaper_than_the_deficit_rate():
    # 600 lb at the 500 break is $234.60, cheaper than 1000 lb at the next break ($317.50)
    assert ltl_gross(BREAKS, RATES, 600) == D("234.60")


@pytest.mark.parametrize(
    ("linehaul", "pct", "fuel"),
    [(D("107.95"), D("0.2200"), D("23.75")), (D("107.95"), D("0.2100"), D("22.67"))],
)
def test_ltl_fuel_rounds_half_up_to_the_cent(linehaul, pct, fuel):
    assert ltl_fuel(linehaul, pct) == fuel


def test_truckload_rate_minimum_and_fuel():
    rate = tl_rate_per_mile(D("2.0000"), D("0.9500"))
    assert rate == D("1.9000")
    assert tl_linehaul(rate, D("500.0"), D("350.00")) == D("950.00")
    assert tl_linehaul(D("0.4750"), D("100.0"), D("350.00")) == D("350.00")
    assert tl_fuel(D("0.400"), D("250.0")) == D("100.00")


@pytest.mark.parametrize(
    ("dwell", "hours"), [(0, 0), (120, 0), (121, 1), (180, 1), (181, 2), (300, 3)]
)
def test_detention_counts_started_hours_after_two_free_hours(dwell, hours):
    assert detention_hours(dwell) == hours


def test_q2_rounds_half_up():
    assert q2(D("0.125")) == D("0.13")
    assert q2(D("2.675")) == D("2.68")


def test_great_circle_one_degree_of_longitude_on_the_equator():
    assert great_circle_miles(0, 0, 0, 1) == pytest.approx(69.09, abs=0.01)


def test_road_miles_apply_the_eighteen_percent_factor():
    assert road_miles(0, 0, 0, 1) == D("81.5")  # 69.09 x 1.18


def test_offset_point_lands_at_the_requested_road_distance():
    lat, lon = offset_point(41.8, -87.7, 110.0, 123.0)
    assert float(road_miles(41.8, -87.7, lat, lon)) == pytest.approx(110.0, abs=0.1)
