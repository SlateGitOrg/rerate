-- A band covers band_low <= index < band_high. LTL rates are a fraction of linehaul, truckload rates are $/mile.
SELECT
    trim(carrier_id) AS carrier_id,
    CAST(trim(band_low) AS DECIMAL(6, 3)) AS band_low,
    CAST(trim(band_high) AS DECIMAL(6, 3)) AS band_high,
    CAST(trim(fsc_rate) AS DECIMAL(7, 4)) AS fsc_rate
FROM raw_fsc_tables
