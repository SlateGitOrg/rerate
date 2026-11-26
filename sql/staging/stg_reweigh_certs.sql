SELECT
    trim(cert_id) AS cert_id,
    trim(shipment_id) AS shipment_id,
    CAST(trim(cert_weight_lb) AS INTEGER) AS cert_weight_lb,
    CAST(trim(cert_date) AS DATE) AS cert_date
FROM raw_reweigh_certificates
