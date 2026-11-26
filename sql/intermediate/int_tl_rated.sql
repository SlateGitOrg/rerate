-- Truckload re-rate: lane rate per mile (scaled by the contract version in force) times
-- miles, the minimum charge, stop-off charges, and FSC dollars per mile times miles.
WITH base AS (
    SELECT
        i.invoice_id,
        s.shipment_id,
        s.carrier_id,
        s.lane_id,
        s.miles,
        s.extra_stops,
        r.rate_per_mile AS lane_rate_per_mile
    FROM stg_invoices AS i
    JOIN int_invoice_shipment AS m ON m.invoice_id = i.invoice_id
    JOIN stg_shipments AS s ON s.shipment_id = m.shipment_id
    LEFT JOIN stg_tl_lane_rates AS r ON r.carrier_id = s.carrier_id AND r.lane_id = s.lane_id
    WHERE s.mode = 'TL'
),
rated AS (
    SELECT
        b.*,
        v.version_label,
        v.tl_rate_multiplier,
        v.tl_min_charge,
        v.tl_stop_charge,
        ROUND(b.lane_rate_per_mile * v.tl_rate_multiplier, 4) AS rate_per_mile
    FROM base AS b
    LEFT JOIN int_contract_version AS v ON v.shipment_id = b.shipment_id
)
SELECT
    r.invoice_id,
    r.shipment_id,
    r.carrier_id,
    r.lane_id,
    r.miles,
    r.version_label,
    r.lane_rate_per_mile,
    r.tl_rate_multiplier,
    r.rate_per_mile,
    ROUND(r.rate_per_mile * r.miles, 2) AS linehaul_before_min,
    r.tl_min_charge,
    ROUND(r.rate_per_mile * r.miles, 2) < r.tl_min_charge AS min_applied,
    GREATEST(ROUND(r.rate_per_mile * r.miles, 2), r.tl_min_charge) AS expected_linehaul,
    r.extra_stops,
    CAST(r.extra_stops * r.tl_stop_charge AS DECIMAL(12, 2)) AS expected_stopoff,
    f.fsc_rate,
    ROUND(f.fsc_rate * r.miles, 2) AS expected_fuel
FROM rated AS r
LEFT JOIN int_fuel_week AS f ON f.shipment_id = r.shipment_id
ORDER BY r.invoice_id
