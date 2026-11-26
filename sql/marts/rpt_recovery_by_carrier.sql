-- Recovery per carrier: spend, flagged invoices, overcharge, and the overcharge by finding type.
WITH spend AS (
    SELECT carrier_id, count(*) AS invoices, sum(billed_total) AS billed_total
    FROM fct_invoice_audit
    GROUP BY carrier_id
),
rec AS (
    SELECT
        carrier_id,
        count(DISTINCT invoice_id) AS flagged_invoices,
        sum(overcharge) AS recovery,
        COALESCE(sum(overcharge) FILTER (WHERE finding_type = 'duplicate'), 0) AS duplicate,
        COALESCE(sum(overcharge) FILTER (WHERE finding_type = 'fsc_wrong_week'), 0) AS fsc_wrong_week,
        COALESCE(sum(overcharge) FILTER (WHERE finding_type = 'unapproved_accessorial'), 0)
            AS unapproved_accessorial,
        COALESCE(sum(overcharge) FILTER (WHERE finding_type = 'weight_overbill'), 0) AS weight_overbill,
        COALESCE(sum(overcharge) FILTER (WHERE finding_type = 'contract_rate'), 0) AS contract_rate
    FROM fct_findings
    GROUP BY carrier_id
)
SELECT
    c.carrier_id,
    c.carrier_name,
    c.mode,
    s.invoices,
    s.billed_total,
    COALESCE(r.flagged_invoices, 0) AS flagged_invoices,
    COALESCE(r.recovery, 0) AS recovery,
    ROUND(100 * COALESCE(r.recovery, 0) / s.billed_total, 2) AS recovery_pct_of_billed,
    COALESCE(r.duplicate, 0) AS duplicate,
    COALESCE(r.fsc_wrong_week, 0) AS fsc_wrong_week,
    COALESCE(r.unapproved_accessorial, 0) AS unapproved_accessorial,
    COALESCE(r.weight_overbill, 0) AS weight_overbill,
    COALESCE(r.contract_rate, 0) AS contract_rate
FROM stg_carriers AS c
JOIN spend AS s ON s.carrier_id = c.carrier_id
LEFT JOIN rec AS r ON r.carrier_id = c.carrier_id
ORDER BY c.carrier_id
