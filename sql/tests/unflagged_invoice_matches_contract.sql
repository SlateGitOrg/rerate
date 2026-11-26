-- An invoice with no finding agrees with the contract to within the rounding tolerance. This is
-- what catches variance the findings do not explain, such as under-billing.
SELECT a.invoice_id, a.billed_total, a.expected_total, a.variance
FROM fct_invoice_audit AS a
CROSS JOIN stg_audit_params AS p
WHERE NOT EXISTS (SELECT 1 FROM fct_findings AS f WHERE f.invoice_id = a.invoice_id)
  AND abs(a.variance) > p.money_tolerance_usd
ORDER BY a.invoice_id
