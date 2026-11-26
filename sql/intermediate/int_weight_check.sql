-- Billed weight against the reference weight: the reweigh certificate if there is one,
-- otherwise the BOL. Over the tolerance is overbilling; at or under it the billed weight
-- is accepted for rating.
WITH certs AS (
    SELECT shipment_id, max(cert_weight_lb) AS cert_weight_lb
    FROM stg_reweigh_certs
    GROUP BY shipment_id
),
base AS (
    SELECT
        i.invoice_id,
        s.shipment_id,
        s.bol_weight_lb,
        COALESCE(i.billed_weight_lb, s.bol_weight_lb) AS billed_weight_lb,
        c.cert_weight_lb,
        COALESCE(c.cert_weight_lb, s.bol_weight_lb) AS reference_weight_lb
    FROM stg_invoices AS i
    JOIN int_invoice_shipment AS m ON m.invoice_id = i.invoice_id
    JOIN stg_shipments AS s ON s.shipment_id = m.shipment_id
    LEFT JOIN certs AS c ON c.shipment_id = s.shipment_id
    WHERE s.mode = 'LTL'
),
checked AS (
    SELECT
        b.*,
        b.billed_weight_lb > b.reference_weight_lb * (1 + p.weight_tolerance) AS over_tolerance
    FROM base AS b
    CROSS JOIN stg_audit_params AS p
)
SELECT
    invoice_id,
    shipment_id,
    bol_weight_lb,
    billed_weight_lb,
    cert_weight_lb,
    reference_weight_lb,
    over_tolerance,
    CASE
        WHEN over_tolerance THEN 'overbilled'
        WHEN cert_weight_lb IS NOT NULL THEN 'certified'
        WHEN billed_weight_lb > bol_weight_lb THEN 'within_tolerance'
        ELSE 'ok'
    END AS weight_status,
    CASE WHEN over_tolerance THEN reference_weight_lb ELSE billed_weight_lb END AS expected_weight_lb
FROM checked
ORDER BY invoice_id
