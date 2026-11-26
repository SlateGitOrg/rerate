-- Every shipment resolves to exactly one diesel-index week and one FSC band.
SELECT shipment_id, ship_date, count(*) AS rows_found, count(fsc_rate) AS bands_found
FROM int_fuel_week
GROUP BY shipment_id, ship_date
HAVING count(*) <> 1 OR count(fsc_rate) <> 1
ORDER BY shipment_id
