-- pro_key: digits only, leading zeros stripped, so '0012345-6' and '123456' meet.
SELECT
    trim(invoice_id) AS invoice_id,
    trim(invoice_number) AS invoice_number,
    trim(carrier_id) AS carrier_id,
    CAST(trim(invoice_date) AS DATE) AS invoice_date,
    trim(bol_number) AS bol_number,
    trim(pro_number) AS pro_raw,
    regexp_replace(regexp_replace(pro_number, '[^0-9]', '', 'g'), '^0+', '') AS pro_key,
    CAST(NULLIF(trim(billed_weight_lb), '') AS INTEGER) AS billed_weight_lb,
    CAST(trim(invoice_total) AS DECIMAL(12, 2)) AS invoice_total
FROM raw_invoices
