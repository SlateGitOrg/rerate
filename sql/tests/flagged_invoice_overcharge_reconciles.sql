-- For each flagged invoice the overcharges add up to billed minus expected, within a cent. The
-- findings bound their own residual, so a variance they cannot explain shows up here.
SELECT
    a.invoice_id,
    a.billed_total,
    a.expected_total,
    sum(f.overcharge) AS sum_overcharge
FROM fct_invoice_audit AS a
JOIN fct_findings AS f ON f.invoice_id = a.invoice_id
GROUP BY a.invoice_id, a.billed_total, a.expected_total
HAVING abs(sum(f.overcharge) - (a.billed_total - a.expected_total)) > 0.01
ORDER BY a.invoice_id
