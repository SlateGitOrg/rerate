-- Range join: the contract version in force on the ship date. Two rows for one
-- shipment means overlapping versions; no version shows as a NULL contract_version_id.
SELECT
    s.shipment_id,
    s.carrier_id,
    s.ship_date,
    v.contract_version_id,
    v.version_label,
    v.effective_from,
    v.effective_to,
    v.ltl_discount,
    v.ltl_min_charge,
    v.tl_rate_multiplier,
    v.tl_min_charge,
    v.tl_stop_charge
FROM stg_shipments AS s
LEFT JOIN stg_contract_versions AS v
    ON v.carrier_id = s.carrier_id
   AND s.ship_date BETWEEN v.effective_from AND v.effective_to
ORDER BY s.shipment_id, v.effective_from
