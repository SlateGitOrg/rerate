SELECT
    trim(shipment_id) AS shipment_id,
    trim(bol_number) AS bol_number,
    trim(carrier_id) AS carrier_id,
    upper(trim(mode)) AS mode,
    trim(plant_id) AS plant_id,
    trim(consignee_id) AS consignee_id,
    CAST(trim(ship_date) AS DATE) AS ship_date,
    CAST(NULLIF(trim(freight_class), '') AS INTEGER) AS freight_class,
    CAST(trim(bol_weight_lb) AS INTEGER) AS bol_weight_lb,
    CAST(trim(miles) AS DECIMAL(7, 1)) AS miles,
    trim(zone) AS zone,
    CAST(trim(extra_stops) AS INTEGER) AS extra_stops,
    CAST(trim(gate_in) AS TIMESTAMP) AS gate_in,
    CAST(trim(gate_out) AS TIMESTAMP) AS gate_out,
    CASE WHEN upper(trim(mode)) = 'TL' THEN trim(plant_id) || '>' || trim(consignee_id) END AS lane_id
FROM raw_shipments
