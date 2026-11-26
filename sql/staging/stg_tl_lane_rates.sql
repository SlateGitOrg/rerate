SELECT
    trim(carrier_id) AS carrier_id,
    trim(plant_id) AS plant_id,
    trim(consignee_id) AS consignee_id,
    trim(plant_id) || '>' || trim(consignee_id) AS lane_id,
    CAST(trim(rate_per_mile) AS DECIMAL(8, 4)) AS rate_per_mile
FROM raw_tl_lane_rates
