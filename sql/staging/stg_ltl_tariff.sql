SELECT
    trim(carrier_id) AS carrier_id,
    trim(zone) AS zone,
    CAST(trim(freight_class) AS INTEGER) AS freight_class,
    CAST(trim(break_min_lb) AS INTEGER) AS break_min_lb,
    CAST(trim(rate_cwt) AS DECIMAL(8, 2)) AS rate_cwt
FROM raw_ltl_tariff
