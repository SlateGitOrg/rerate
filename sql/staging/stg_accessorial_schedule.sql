SELECT
    trim(carrier_id) AS carrier_id,
    upper(trim(charge_code)) AS charge_code,
    CAST(trim(rate) AS DECIMAL(8, 2)) AS rate,
    lower(trim(unit)) AS unit,
    lower(trim(rule)) AS rule,
    CAST(NULLIF(trim(free_minutes), '') AS INTEGER) AS free_minutes,
    CAST(NULLIF(trim(increment_minutes), '') AS INTEGER) AS increment_minutes
FROM raw_accessorial_schedule
