SELECT
    CAST(trim(effective_date) AS DATE) AS effective_date,
    CAST(trim(diesel_price) AS DECIMAL(6, 3)) AS diesel_price
FROM raw_diesel_index
