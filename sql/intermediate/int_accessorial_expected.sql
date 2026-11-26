-- Accessorials the contract allows for a shipment: those with an approval, or those whose
-- schedule rule is met (consignee flags for liftgate and residential). Detention is
-- approval-only and is priced from gate timestamps: per started hour after the free time.
WITH approved AS (
    SELECT DISTINCT shipment_id, charge_code FROM stg_approvals
),
candidates AS (
    SELECT
        s.shipment_id,
        s.carrier_id,
        sch.charge_code,
        sch.rate,
        sch.unit,
        sch.rule,
        sch.free_minutes,
        sch.increment_minutes,
        a.shipment_id IS NOT NULL AS has_approval,
        CASE sch.charge_code
            WHEN 'LIFTGATE' THEN c.needs_liftgate
            WHEN 'RESIDENTIAL' THEN c.is_residential
            ELSE FALSE
        END AS rule_met,
        date_diff('minute', s.gate_in, s.gate_out) AS dwell_minutes
    FROM stg_shipments AS s
    JOIN stg_accessorial_schedule AS sch ON sch.carrier_id = s.carrier_id
    JOIN stg_consignees AS c ON c.consignee_id = s.consignee_id
    LEFT JOIN approved AS a
        ON a.shipment_id = s.shipment_id AND a.charge_code = sch.charge_code
),
allowed AS (
    SELECT
        *,
        CASE
            WHEN unit = 'hour' THEN
                CAST(ceil(GREATEST(dwell_minutes - free_minutes, 0)::DOUBLE / increment_minutes) AS INTEGER)
            ELSE 1
        END AS quantity
    FROM candidates
    WHERE has_approval OR (rule = 'consignee_flag' AND rule_met)
)
SELECT
    shipment_id,
    carrier_id,
    charge_code,
    CASE
        WHEN has_approval AND rule_met THEN 'approval+schedule'
        WHEN has_approval THEN 'approval'
        ELSE 'schedule'
    END AS basis,
    quantity,
    rate,
    CAST(rate * quantity AS DECIMAL(12, 2)) AS expected_amount,
    dwell_minutes
FROM allowed
ORDER BY shipment_id, charge_code
