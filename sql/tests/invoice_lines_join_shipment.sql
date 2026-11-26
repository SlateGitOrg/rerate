-- Every invoice line belongs to an invoice that resolves to a shipment.
SELECT l.line_id, l.invoice_id, l.charge_code, l.amount
FROM stg_invoice_lines AS l
LEFT JOIN int_invoice_shipment AS m ON m.invoice_id = l.invoice_id
WHERE m.shipment_id IS NULL
ORDER BY l.line_id
