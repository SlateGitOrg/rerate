-- ASOF join of the ship date to the Monday-effective diesel index, then the carrier's
-- FSC band for that index. The invoice date plays no part: that is the whole point.
WITH weekly AS (
    SELECT
        s.shipment_id,
        s.carrier_id,
        s.mode,
        s.ship_date,
        d.effective_date AS index_effective_date,
        d.diesel_price
    FROM stg_shipments AS s
    ASOF LEFT JOIN stg_diesel_index AS d
        ON s.ship_date >= d.effective_date
)
SELECT
    w.shipment_id,
    w.carrier_id,
    w.mode,
    w.ship_date,
    w.index_effective_date,
    w.diesel_price,
    f.band_low,
    f.band_high,
    f.fsc_rate
FROM weekly AS w
LEFT JOIN stg_fsc_tables AS f
    ON f.carrier_id = w.carrier_id
   AND w.diesel_price >= f.band_low
   AND w.diesel_price < f.band_high
ORDER BY w.shipment_id
