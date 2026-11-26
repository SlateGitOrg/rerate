-- Truckload lane benchmark. Expected linehaul is a + b x miles, fitted with regr_* on one point
-- per lane (median billed linehaul of finding-free shipments). Lanes above the drop index in
-- the first fit are removed and the line is refitted once; the lane index is median actual
-- over expected on the refitted line. Raw cost per mile and its rank sit alongside.
WITH p AS (SELECT * FROM stg_audit_params),
clean AS (
    SELECT s.lane_id, s.carrier_id, s.plant_id, s.consignee_id, s.miles, a.billed_linehaul
    FROM fct_invoice_audit AS a
    JOIN stg_shipments AS s ON s.shipment_id = a.shipment_id
    WHERE s.mode = 'TL'
      AND NOT a.is_duplicate
      AND NOT EXISTS (SELECT 1 FROM fct_findings AS f WHERE f.invoice_id = a.invoice_id)
),
lanes AS (
    SELECT
        lane_id,
        any_value(carrier_id) AS carrier_id,
        any_value(plant_id) AS plant_id,
        any_value(consignee_id) AS consignee_id,
        any_value(CAST(miles AS DOUBLE)) AS miles,
        count(*) AS shipments,
        median(CAST(billed_linehaul AS DOUBLE)) AS median_linehaul
    FROM clean
    GROUP BY lane_id
),
scored AS (SELECT l.* FROM lanes AS l CROSS JOIN p WHERE l.shipments >= p.min_lane_shipments),
fit1 AS (
    SELECT regr_intercept(median_linehaul, miles) AS a, regr_slope(median_linehaul, miles) AS b FROM scored
),
pass1 AS (
    SELECT s.*, s.median_linehaul / (f.a + f.b * s.miles) AS index_pass1
    FROM scored AS s CROSS JOIN fit1 AS f
),
fit2 AS (
    SELECT regr_intercept(median_linehaul, miles) AS a, regr_slope(median_linehaul, miles) AS b
    FROM pass1 CROSS JOIN p
    WHERE index_pass1 <= p.lane_refit_drop_index
)
SELECT
    l.lane_id,
    l.carrier_id,
    l.plant_id,
    l.consignee_id,
    l.miles,
    l.shipments,
    l.median_linehaul,
    f.a AS fit_intercept,
    f.b AS fit_slope,
    f.a + f.b * l.miles AS expected_linehaul,
    l.median_linehaul / (f.a + f.b * l.miles) AS lane_index,
    q.index_pass1,
    q.index_pass1 > p.lane_refit_drop_index AS dropped_from_refit,
    l.median_linehaul / l.miles AS raw_cost_per_mile,
    rank() OVER (ORDER BY l.median_linehaul / l.miles DESC) AS raw_cost_per_mile_rank,
    rank() OVER (ORDER BY l.median_linehaul / (f.a + f.b * l.miles) DESC) AS lane_index_rank,
    l.median_linehaul / (f.a + f.b * l.miles) >= p.lane_flag_index AS flagged
FROM scored AS l
JOIN pass1 AS q ON q.lane_id = l.lane_id
CROSS JOIN fit2 AS f
CROSS JOIN p
ORDER BY l.lane_id
