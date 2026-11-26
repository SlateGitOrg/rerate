SELECT
    trim(approval_id) AS approval_id,
    trim(shipment_id) AS shipment_id,
    upper(trim(charge_code)) AS charge_code,
    CAST(trim(approved_on) AS DATE) AS approved_on
FROM raw_approvals
