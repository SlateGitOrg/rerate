-- A finding is money owed back and must be larger than the rounding tolerance: a negative or
-- sub-tolerance overcharge means a plug or a split went wrong.
SELECT f.finding_id, f.finding_type, f.billed, f.expected, f.overcharge
FROM fct_findings AS f
CROSS JOIN stg_audit_params AS p
WHERE f.overcharge <= p.money_tolerance_usd
ORDER BY f.finding_id
