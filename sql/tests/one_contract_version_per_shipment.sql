-- Every shipment falls in exactly one contract version (none, or two overlapping, is a violation).
SELECT shipment_id, carrier_id, ship_date, count(contract_version_id) AS versions_in_force
FROM int_contract_version
GROUP BY shipment_id, carrier_id, ship_date
HAVING count(contract_version_id) <> 1
ORDER BY shipment_id
