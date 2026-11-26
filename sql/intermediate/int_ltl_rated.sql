-- LTL re-rate at the expected weight: CWT rate at the weight's break, deficit-weight
-- rating against the next break, carrier discount, then the absolute minimum charge.
-- Fuel is the in-force FSC percentage of the discounted linehaul.
WITH tariff AS (
    SELECT
        carrier_id,
        zone,
        freight_class,
        break_min_lb,
        rate_cwt,
        lead(break_min_lb) OVER w AS next_break_lb,
        lead(rate_cwt) OVER w AS next_rate_cwt
    FROM stg_ltl_tariff
    WINDOW w AS (PARTITION BY carrier_id, zone, freight_class ORDER BY break_min_lb)
),
base AS (
    SELECT
        w.invoice_id,
        w.shipment_id,
        s.carrier_id,
        s.zone,
        s.freight_class,
        w.expected_weight_lb AS weight_lb
    FROM int_weight_check AS w
    JOIN stg_shipments AS s ON s.shipment_id = w.shipment_id
),
at_break AS (
    SELECT
        b.*,
        t.break_min_lb AS rated_break_lb,
        t.rate_cwt,
        t.next_break_lb,
        t.next_rate_cwt
    FROM base AS b
    ASOF LEFT JOIN tariff AS t
        ON b.carrier_id = t.carrier_id
       AND b.zone = t.zone
       AND b.freight_class = t.freight_class
       AND b.weight_lb >= t.break_min_lb
),
gross AS (
    SELECT
        a.*,
        ROUND(a.weight_lb * a.rate_cwt * 0.01, 2) AS gross_at_break,
        ROUND(a.next_break_lb * a.next_rate_cwt * 0.01, 2) AS gross_at_next_break
    FROM at_break AS a
),
net AS (
    SELECT
        g.*,
        LEAST(g.gross_at_break, COALESCE(g.gross_at_next_break, g.gross_at_break)) AS gross_charge,
        v.ltl_discount,
        v.ltl_min_charge
    FROM gross AS g
    LEFT JOIN int_contract_version AS v ON v.shipment_id = g.shipment_id
)
SELECT
    n.invoice_id,
    n.shipment_id,
    n.carrier_id,
    n.weight_lb,
    n.rated_break_lb,
    n.rate_cwt,
    n.next_break_lb,
    n.next_rate_cwt,
    n.gross_charge,
    n.gross_charge < n.gross_at_break AS deficit_applied,
    n.ltl_discount,
    ROUND(n.gross_charge * (1 - n.ltl_discount), 2) AS net_charge,
    n.ltl_min_charge,
    ROUND(n.gross_charge * (1 - n.ltl_discount), 2) < n.ltl_min_charge AS min_applied,
    GREATEST(ROUND(n.gross_charge * (1 - n.ltl_discount), 2), n.ltl_min_charge) AS expected_linehaul,
    CAST(0 AS DECIMAL(12, 2)) AS expected_stopoff,
    f.fsc_rate,
    ROUND(GREATEST(ROUND(n.gross_charge * (1 - n.ltl_discount), 2), n.ltl_min_charge) * f.fsc_rate, 2)
        AS expected_fuel
FROM net AS n
LEFT JOIN int_fuel_week AS f ON f.shipment_id = n.shipment_id
ORDER BY n.invoice_id
