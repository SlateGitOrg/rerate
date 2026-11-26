-- Resolve each invoice to its shipment through carrier + BOL. An invoice that finds no
-- shipment keeps a NULL shipment_id so the sql/tests join check can print it.
SELECT
    i.invoice_id,
    s.shipment_id,
    i.carrier_id,
    i.bol_number
FROM stg_invoices AS i
LEFT JOIN stg_shipments AS s
    ON s.bol_number = i.bol_number
   AND s.carrier_id = i.carrier_id
ORDER BY i.invoice_id
