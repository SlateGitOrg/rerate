SELECT
    trim(contract_version_id) AS contract_version_id,
    trim(carrier_id) AS carrier_id,
    trim(version_label) AS version_label,
    CAST(trim(effective_from) AS DATE) AS effective_from,
    CAST(trim(effective_to) AS DATE) AS effective_to,
    CAST(NULLIF(trim(ltl_discount), '') AS DECIMAL(5, 4)) AS ltl_discount,
    CAST(NULLIF(trim(ltl_min_charge), '') AS DECIMAL(8, 2)) AS ltl_min_charge,
    CAST(NULLIF(trim(tl_rate_multiplier), '') AS DECIMAL(6, 4)) AS tl_rate_multiplier,
    CAST(NULLIF(trim(tl_min_charge), '') AS DECIMAL(8, 2)) AS tl_min_charge,
    CAST(NULLIF(trim(tl_stop_charge), '') AS DECIMAL(8, 2)) AS tl_stop_charge
FROM raw_contract_versions
