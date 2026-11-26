-- Audit constants in one row, so no rule hides a literal in a downstream model.
SELECT
    CAST(0.05 AS DECIMAL(6, 2)) AS money_tolerance_usd,      -- cent rounding on a line is not a finding
    CAST(0.02 AS DECIMAL(5, 3)) AS weight_tolerance,         -- billed weight may exceed the reference by 2%
    CAST(1.00 AS DECIMAL(6, 2)) AS duplicate_total_window_usd,
    8 AS min_lane_shipments,                                 -- finding-free shipments for a lane to be scored
    CAST(1.12 AS DOUBLE) AS lane_flag_index,                 -- lane index at or above this is flagged
    CAST(1.15 AS DOUBLE) AS lane_refit_drop_index            -- lanes above this are dropped before the refit
