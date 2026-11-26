SELECT
    trim(line_id) AS line_id,
    trim(invoice_id) AS invoice_id,
    CAST(trim(line_no) AS INTEGER) AS line_no,
    upper(trim(charge_code)) AS charge_code,
    CAST(NULLIF(trim(quantity), '') AS DECIMAL(10, 1)) AS quantity,
    CAST(trim(amount) AS DECIMAL(12, 2)) AS amount
FROM raw_invoice_lines
