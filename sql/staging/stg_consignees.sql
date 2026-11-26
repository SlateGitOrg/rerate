SELECT
    trim(consignee_id) AS consignee_id,
    trim(consignee_name) AS consignee_name,
    CAST(trim(lat) AS DOUBLE) AS lat,
    CAST(trim(lon) AS DOUBLE) AS lon,
    trim(is_residential) = '1' AS is_residential,
    trim(needs_liftgate) = '1' AS needs_liftgate
FROM raw_consignees
