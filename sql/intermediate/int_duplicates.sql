-- An invoice is a duplicate when an earlier-billed invoice from the same carrier, under a
-- different invoice number, has the same normalised PRO, or the same BOL with a total within
-- the window. The earliest-billed invoice is the original and is never listed here.
WITH totals AS (
    SELECT
        i.invoice_id,
        i.invoice_number,
        i.carrier_id,
        i.invoice_date,
        i.bol_number,
        i.pro_key,
        COALESCE(sum(l.amount), 0) AS billed_total
    FROM stg_invoices AS i
    LEFT JOIN stg_invoice_lines AS l ON l.invoice_id = i.invoice_id
    GROUP BY ALL
),
matches AS (
    SELECT a.invoice_id, b.invoice_id AS original_invoice_id, b.invoice_date AS original_date, 'pro' AS rule
    FROM totals AS a
    JOIN totals AS b
        ON a.carrier_id = b.carrier_id
       AND a.pro_key = b.pro_key
       AND a.pro_key <> ''
       AND a.invoice_number <> b.invoice_number
    WHERE (b.invoice_date, b.invoice_id) < (a.invoice_date, a.invoice_id)
    UNION ALL
    SELECT a.invoice_id, b.invoice_id, b.invoice_date, 'bol_total'
    FROM totals AS a
    JOIN totals AS b
        ON a.carrier_id = b.carrier_id
       AND a.bol_number = b.bol_number
       AND a.invoice_number <> b.invoice_number
    CROSS JOIN stg_audit_params AS p
    WHERE (b.invoice_date, b.invoice_id) < (a.invoice_date, a.invoice_id)
      AND abs(a.billed_total - b.billed_total) <= p.duplicate_total_window_usd
)
SELECT
    m.invoice_id,
    arg_min(m.original_invoice_id, (m.original_date, m.original_invoice_id)) AS original_invoice_id,
    string_agg(DISTINCT m.rule, '+' ORDER BY m.rule) AS matched_on,
    any_value(t.billed_total) AS billed_total
FROM matches AS m
JOIN totals AS t ON t.invoice_id = m.invoice_id
GROUP BY m.invoice_id
ORDER BY m.invoice_id
