-- One row per invoice: what was billed, what the contract says it should have been, and the
-- variance. A duplicate invoice is owed nothing, so its expected total is zero.
WITH billed AS (
    SELECT
        invoice_id,
        sum(amount) AS billed_total,
        COALESCE(sum(amount) FILTER (WHERE charge_code = 'LINEHAUL'), 0) AS billed_linehaul,
        COALESCE(sum(amount) FILTER (WHERE charge_code = 'STOPOFF'), 0) AS billed_stopoff,
        COALESCE(sum(amount) FILTER (WHERE charge_code = 'FUEL'), 0) AS billed_fuel
    FROM stg_invoice_lines
    GROUP BY invoice_id
),
rated AS (
    SELECT invoice_id, 'LTL' AS mode, expected_linehaul, expected_stopoff, expected_fuel, fsc_rate
    FROM int_ltl_rated
    UNION ALL
    SELECT invoice_id, 'TL', expected_linehaul, expected_stopoff, expected_fuel, fsc_rate
    FROM int_tl_rated
),
acc_billed AS (
    SELECT invoice_id, charge_code, sum(amount) AS billed_amount
    FROM stg_invoice_lines
    WHERE charge_code NOT IN ('LINEHAUL', 'STOPOFF', 'FUEL')
    GROUP BY invoice_id, charge_code
),
acc_expected AS (
    SELECT m.invoice_id, a.charge_code, a.expected_amount
    FROM int_accessorial_expected AS a
    JOIN int_invoice_shipment AS m ON m.shipment_id = a.shipment_id
),
acc_pairs AS (
    SELECT
        COALESCE(b.invoice_id, e.invoice_id) AS invoice_id,
        COALESCE(b.charge_code, e.charge_code) AS charge_code,
        COALESCE(b.billed_amount, 0) AS billed_amount,
        COALESCE(e.expected_amount, 0) AS expected_amount
    FROM acc_billed AS b
    FULL JOIN acc_expected AS e
        ON b.invoice_id = e.invoice_id AND b.charge_code = e.charge_code
),
acc AS (
    SELECT
        p.invoice_id,
        sum(p.billed_amount) AS billed_accessorial,
        sum(p.expected_amount) AS expected_accessorial,
        sum(GREATEST(p.billed_amount - p.expected_amount, 0)) AS accessorial_overbilled,
        string_agg(p.charge_code || ' ' || printf('%.2f', p.billed_amount), ', ' ORDER BY p.charge_code)
            FILTER (WHERE p.billed_amount - p.expected_amount > t.money_tolerance_usd) AS overbilled_codes
    FROM acc_pairs AS p
    CROSS JOIN stg_audit_params AS t
    GROUP BY p.invoice_id
)
SELECT
    i.invoice_id,
    i.invoice_number,
    i.carrier_id,
    m.shipment_id,
    r.mode,
    s.ship_date,
    i.invoice_date,
    b.billed_total,
    b.billed_linehaul,
    b.billed_stopoff,
    b.billed_fuel,
    COALESCE(a.billed_accessorial, 0) AS billed_accessorial,
    r.expected_linehaul,
    r.expected_stopoff,
    r.expected_fuel,
    COALESCE(a.expected_accessorial, 0) AS expected_accessorial,
    r.fsc_rate AS expected_fsc_rate,
    COALESCE(a.accessorial_overbilled, 0) AS accessorial_overbilled,
    a.overbilled_codes,
    d.invoice_id IS NOT NULL AS is_duplicate,
    d.original_invoice_id,
    CASE
        WHEN d.invoice_id IS NOT NULL THEN CAST(0 AS DECIMAL(12, 2))
        ELSE r.expected_linehaul + r.expected_stopoff + r.expected_fuel + COALESCE(a.expected_accessorial, 0)
    END AS expected_total,
    b.billed_total - CASE
        WHEN d.invoice_id IS NOT NULL THEN CAST(0 AS DECIMAL(12, 2))
        ELSE r.expected_linehaul + r.expected_stopoff + r.expected_fuel + COALESCE(a.expected_accessorial, 0)
    END AS variance
FROM stg_invoices AS i
JOIN int_invoice_shipment AS m ON m.invoice_id = i.invoice_id
JOIN stg_shipments AS s ON s.shipment_id = m.shipment_id
JOIN billed AS b ON b.invoice_id = i.invoice_id
JOIN rated AS r ON r.invoice_id = i.invoice_id
LEFT JOIN acc AS a ON a.invoice_id = i.invoice_id
LEFT JOIN int_duplicates AS d ON d.invoice_id = i.invoice_id
ORDER BY i.invoice_id
