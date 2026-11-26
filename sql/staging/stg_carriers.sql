SELECT
    trim(carrier_id) AS carrier_id,
    trim(carrier_name) AS carrier_name,
    upper(trim(mode)) AS mode
FROM raw_carriers
