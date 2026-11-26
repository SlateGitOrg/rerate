# Freight audit report

4,024 invoices shipped 2025-07-01 to 2026-06-30, $4,439,870.01 billed. 174 findings on 174 invoices recover $29,904.27 (0.67% of billed).

## Recovery by finding type

| Finding type | Invoices | Overcharge ($) |
| --- | ---: | ---: |
| duplicate | 24 | 22,916.54 |
| unapproved_accessorial | 40 | 3,255.00 |
| contract_rate | 20 | 2,672.22 |
| weight_overbill | 30 | 774.21 |
| fsc_wrong_week | 60 | 286.30 |
| **total** | **174** | **29,904.27** |

## Recovery by carrier

| Carrier | Mode | Invoices | Billed ($) | Flagged | Recovery ($) | % of billed |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| TL1 | TL | 888 | 1,973,032.05 | 35 | 13,541.99 | 0.69 |
| TL2 | TL | 721 | 1,724,342.03 | 41 | 8,692.65 | 0.50 |
| LTL1 | LTL | 973 | 302,228.35 | 45 | 4,589.69 | 1.52 |
| LTL3 | LTL | 588 | 182,726.81 | 28 | 2,206.76 | 1.21 |
| LTL2 | LTL | 854 | 257,540.77 | 25 | 873.18 | 0.34 |

## Truckload lanes: raw cost per mile against lane index

Expected linehaul = $289.73 + $2.0543 x miles, refitted on 27 of 30 lanes after dropping 3 with a first-pass index above 1.15.

| Rank | By raw $/mile: lane | Miles | $/mile | Index | By lane index: lane | Miles | Index | $/mile |
| ---: | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 1 | P1>C001 | 80 | 6.00 | 1.06 | P3>C003 | 640 | 1.22 | 3.06 |
| 2 | P2>C002 | 110 | 4.79 | 1.02 | P1>C004 | 900 | 1.21 | 2.87 |
| 3 | P3>C006 | 174 | 3.47 | 0.93 | P2>C005 | 1,250 | 1.20 | 2.73 |
| 4 | P2>C008 | 291 | 3.14 | 1.03 | P1>C001 | 80 | 1.06 | 6.00 |
| 5 | P1>C007 | 243 | 3.08 | 0.95 | P1>C016 | 700 | 1.06 | 2.61 |

Flagged lanes (index at or above 1.12, at least 8 finding-free shipments):

| Lane | Carrier | Miles | Shipments | Index |
| --- | --- | ---: | ---: | ---: |
| P3>C003 | TL1 | 640 | 52 | 1.22 |
| P1>C004 | TL1 | 900 | 46 | 1.21 |
| P2>C005 | TL1 | 1,250 | 96 | 1.20 |
