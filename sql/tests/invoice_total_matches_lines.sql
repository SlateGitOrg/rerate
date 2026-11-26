-- The carrier's header total equals the sum of its lines.
SELECT i.invoice_id, i.invoice_total, COALESCE(sum(l.amount), 0) AS lines_total
FROM stg_invoices AS i
LEFT JOIN stg_invoice_lines AS l ON l.invoice_id = i.invoice_id
GROUP BY i.invoice_id, i.invoice_total
HAVING i.invoice_total <> COALESCE(sum(l.amount), 0)
ORDER BY i.invoice_id
