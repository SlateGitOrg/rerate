-- One row per finding. Linehaul variance goes to the weight finding when the billed weight is
-- over tolerance, otherwise to the contract-rate finding; the fuel that follows a linehaul
-- change (LTL fuel is a percentage of linehaul) travels with it. Whatever fuel variance is left
-- is the fuel-week finding. What the split leaves over (the residual) is bounded: up to the money
-- tolerance it is rounding and goes to the largest finding; a larger positive residual becomes an
-- explicit 'unexplained_variance' finding; a larger negative one (under-billing) is left alone
-- and fails the data tests. A duplicate takes the whole invoice and suppresses every other
-- finding on it.
WITH t AS (SELECT money_tolerance_usd AS tol FROM stg_audit_params),
base AS (
    SELECT
        a.*,
        w.weight_status,
        w.billed_weight_lb,
        w.bol_weight_lb,
        w.reference_weight_lb,
        f.diesel_price,
        f.index_effective_date,
        a.billed_linehaul - a.expected_linehaul AS d_linehaul,
        a.billed_stopoff - a.expected_stopoff AS d_stopoff,
        a.billed_fuel - a.expected_fuel AS d_fuel
    FROM fct_invoice_audit AS a
    LEFT JOIN int_weight_check AS w ON w.invoice_id = a.invoice_id
    LEFT JOIN int_fuel_week AS f ON f.shipment_id = a.shipment_id
    WHERE NOT a.is_duplicate
),
knock AS (
    SELECT
        b.*,
        -- LTL fuel follows linehaul, so fuel on a linehaul variance belongs to that variance.
        CASE
            WHEN b.mode = 'LTL' AND b.d_linehaul > t.tol THEN ROUND(b.d_linehaul * b.expected_fsc_rate, 2)
            ELSE CAST(0 AS DECIMAL(12, 2))
        END AS knock_on_fuel,
        COALESCE(b.weight_status = 'overbilled', FALSE) AS weight_over
    FROM base AS b
    CROSS JOIN t
),
parts AS (
    SELECT
        k.*,
        CASE WHEN k.weight_over AND k.d_linehaul + k.knock_on_fuel > t.tol
             THEN k.d_linehaul + k.knock_on_fuel ELSE 0 END AS amt_weight,
        (CASE WHEN NOT k.weight_over AND k.d_linehaul > t.tol THEN k.d_linehaul + k.knock_on_fuel ELSE 0 END)
          + (CASE WHEN k.d_stopoff > t.tol THEN k.d_stopoff ELSE 0 END) AS amt_rate,
        CASE WHEN k.d_fuel - k.knock_on_fuel > t.tol THEN k.d_fuel - k.knock_on_fuel ELSE 0 END AS amt_fsc,
        CASE WHEN k.accessorial_overbilled > t.tol THEN k.accessorial_overbilled ELSE 0 END AS amt_acc
    FROM knock AS k
    CROSS JOIN t
),
found AS (
    SELECT invoice_id, 'weight_overbill' AS finding_type, amt_weight AS amount,
           billed_linehaul + billed_fuel AS billed,
           printf('billed %d lb against %d lb %s', billed_weight_lb, reference_weight_lb,
                  CASE WHEN reference_weight_lb = bol_weight_lb THEN 'on the BOL' ELSE 'on the reweigh certificate' END)
               AS evidence
    FROM parts WHERE amt_weight > 0
    UNION ALL
    SELECT invoice_id, 'contract_rate', amt_rate,
           billed_linehaul + billed_stopoff + CASE WHEN knock_on_fuel > 0 THEN billed_fuel ELSE 0 END,
           printf('linehaul billed %.2f, contract in force on %s gives %.2f',
                  billed_linehaul, ship_date, expected_linehaul)
    FROM parts WHERE amt_rate > 0
    UNION ALL
    SELECT invoice_id, 'fsc_wrong_week', amt_fsc, billed_fuel,
           printf('fuel billed %.2f, expected %.2f at index %.3f effective %s (ship date %s, invoiced %s)',
                  billed_fuel, expected_fuel, diesel_price, index_effective_date, ship_date, invoice_date)
    FROM parts WHERE amt_fsc > 0
    UNION ALL
    SELECT invoice_id, 'unapproved_accessorial', amt_acc, billed_accessorial,
           printf('%s billed with no approval or schedule rule covering it', overbilled_codes)
    FROM parts WHERE amt_acc > 0
),
ranked AS (
    SELECT
        f.*,
        row_number() OVER (PARTITION BY f.invoice_id ORDER BY f.amount DESC, f.finding_type) AS rn,
        p.variance - sum(f.amount) OVER (PARTITION BY f.invoice_id) AS residual,
        p.shipment_id,
        p.carrier_id
    FROM found AS f
    JOIN parts AS p ON p.invoice_id = f.invoice_id
),
residuals AS (
    SELECT
        p.invoice_id,
        p.shipment_id,
        p.carrier_id,
        p.billed_total,
        p.variance - COALESCE(s.typed, 0) AS residual
    FROM parts AS p
    LEFT JOIN (SELECT invoice_id, sum(amount) AS typed FROM found GROUP BY invoice_id) AS s
        ON s.invoice_id = p.invoice_id
),
unexplained AS (
    SELECT
        r.invoice_id,
        'unexplained_variance' AS finding_type,
        r.shipment_id,
        r.carrier_id,
        r.billed_total AS billed,
        r.billed_total - r.residual AS expected,
        r.residual AS overcharge,
        printf('%.2f over the contract that no modelled cause accounts for', r.residual) AS evidence
    FROM residuals AS r
    CROSS JOIN t
    WHERE r.residual > t.tol
),
duplicates AS (
    SELECT
        a.invoice_id,
        'duplicate' AS finding_type,
        a.shipment_id,
        a.carrier_id,
        a.billed_total AS billed,
        CAST(0 AS DECIMAL(12, 2)) AS expected,
        a.billed_total AS overcharge,
        CASE d.matched_on
            WHEN 'pro' THEN printf('same normalised PRO as %s, billed earlier', d.original_invoice_id)
            WHEN 'bol_total' THEN printf('same BOL and a total within $1 of %s, billed earlier', d.original_invoice_id)
            ELSE printf('same PRO and BOL and a near-identical total as %s, billed earlier', d.original_invoice_id)
        END AS evidence
    FROM fct_invoice_audit AS a
    JOIN int_duplicates AS d ON d.invoice_id = a.invoice_id
),
single AS (
    SELECT
        invoice_id,
        finding_type,
        shipment_id,
        carrier_id,
        billed,
        billed - (amount + CASE WHEN rn = 1 AND abs(residual) <= tol THEN residual ELSE 0 END)
            AS expected,
        amount + CASE WHEN rn = 1 AND abs(residual) <= tol THEN residual ELSE 0 END AS overcharge,
        evidence
    FROM ranked
    CROSS JOIN t
)
SELECT invoice_id || ':' || finding_type AS finding_id, *
FROM (
    SELECT * FROM single
    UNION ALL
    SELECT * FROM unexplained
    UNION ALL
    SELECT * FROM duplicates
)
ORDER BY invoice_id, finding_type
