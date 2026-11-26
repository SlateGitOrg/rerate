"""Markdown report and CSV export, both read straight from the mart tables."""

from __future__ import annotations

from pathlib import Path

import duckdb

MARTS = ["fct_invoice_audit", "fct_findings", "rpt_recovery_by_carrier", "fct_lane_benchmark"]


def money(x: float | None) -> str:
    return f"{float(x or 0):,.2f}"


def table(header: list[str], rows: list[list[str]], right: set[int] | None = None) -> str:
    """A Markdown table; columns in `right` are right-aligned (default: all but the first)."""
    right = set(range(1, len(header))) if right is None else right
    sep = ["---:" if i in right else "---" for i in range(len(header))]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def build_report(con: duckdb.DuckDBPyConnection, top_n: int = 5) -> str:
    inv, billed, flagged, findings, recovery = con.execute(
        """
        SELECT
            (SELECT count(*) FROM fct_invoice_audit),
            (SELECT sum(billed_total) FROM fct_invoice_audit),
            (SELECT count(DISTINCT invoice_id) FROM fct_findings),
            (SELECT count(*) FROM fct_findings),
            (SELECT COALESCE(sum(overcharge), 0) FROM fct_findings)
        """
    ).fetchone()
    first, last = con.execute(
        "SELECT min(ship_date), max(ship_date) FROM fct_invoice_audit"
    ).fetchone()

    out = ["# Freight audit report", ""]
    out.append(
        f"{inv:,} invoices shipped {first} to {last}, ${money(billed)} billed. "
        f"{findings:,} findings on {flagged:,} invoices recover ${money(recovery)} "
        f"({100 * float(recovery) / float(billed):.2f}% of billed)."
    )

    out += ["", "## Recovery by finding type", ""]
    rows = con.execute(
        """
        SELECT finding_type, count(DISTINCT invoice_id), sum(overcharge)
        FROM fct_findings GROUP BY finding_type ORDER BY sum(overcharge) DESC, finding_type
        """
    ).fetchall()
    body = [[t, f"{n:,}", money(a)] for t, n, a in rows]
    body.append(["**total**", f"**{flagged:,}**", f"**{money(recovery)}**"])
    out.append(table(["Finding type", "Invoices", "Overcharge ($)"], body))

    out += ["", "## Recovery by carrier", ""]
    rows = con.execute(
        """
        SELECT carrier_id, mode, invoices, billed_total, flagged_invoices, recovery,
               recovery_pct_of_billed
        FROM rpt_recovery_by_carrier ORDER BY recovery DESC, carrier_id
        """
    ).fetchall()
    body = [
        [c, m, f"{n:,}", money(b), f"{f:,}", money(r), f"{p:.2f}"] for c, m, n, b, f, r, p in rows
    ]
    out.append(
        table(
            ["Carrier", "Mode", "Invoices", "Billed ($)", "Flagged", "Recovery ($)", "% of billed"],
            body,
            right={2, 3, 4, 5, 6},
        )
    )

    out += ["", "## Truckload lanes: raw cost per mile against lane index", ""]
    drop_at, flag_at, min_shipments = con.execute(
        "SELECT lane_refit_drop_index, lane_flag_index, min_lane_shipments FROM stg_audit_params"
    ).fetchone()
    fit = con.execute(
        """
        SELECT any_value(fit_intercept), any_value(fit_slope), count(*),
               count(*) FILTER (WHERE dropped_from_refit)
        FROM fct_lane_benchmark
        """
    ).fetchone()
    if fit[2]:
        out.append(
            f"Expected linehaul = ${fit[0]:,.2f} + ${fit[1]:.4f} x miles, refitted on "
            f"{fit[2] - fit[3]} of {fit[2]} lanes after dropping {fit[3]} with a first-pass "
            f"index above {drop_at:.2f}."
        )
        out.append("")
        by_cpm = con.execute(
            "SELECT lane_id, miles, raw_cost_per_mile, lane_index FROM fct_lane_benchmark "
            "ORDER BY raw_cost_per_mile_rank, lane_id LIMIT ?",
            [top_n],
        ).fetchall()
        by_idx = con.execute(
            "SELECT lane_id, miles, lane_index, raw_cost_per_mile FROM fct_lane_benchmark "
            "ORDER BY lane_index_rank, lane_id LIMIT ?",
            [top_n],
        ).fetchall()
        body = []
        for k, (a, b) in enumerate(zip(by_cpm, by_idx, strict=False), start=1):
            body.append(
                [
                    str(k),
                    a[0],
                    f"{a[1]:,.0f}",
                    f"{a[2]:.2f}",
                    f"{a[3]:.2f}",
                    b[0],
                    f"{b[1]:,.0f}",
                    f"{b[2]:.2f}",
                    f"{b[3]:.2f}",
                ]
            )
        out.append(
            table(
                [
                    "Rank",
                    "By raw $/mile: lane",
                    "Miles",
                    "$/mile",
                    "Index",
                    "By lane index: lane",
                    "Miles",
                    "Index",
                    "$/mile",
                ],
                body,
                right={0, 2, 3, 4, 6, 7, 8},
            )
        )
        flagged_lanes = con.execute(
            "SELECT lane_id, carrier_id, miles, shipments, lane_index FROM fct_lane_benchmark "
            "WHERE flagged ORDER BY lane_index DESC"
        ).fetchall()
        out += [
            "",
            f"Flagged lanes (index at or above {flag_at:.2f}, "
            f"at least {min_shipments} finding-free shipments):",
            "",
        ]
        if flagged_lanes:
            out.append(
                table(
                    ["Lane", "Carrier", "Miles", "Shipments", "Index"],
                    [[a, b, f"{c:,.0f}", f"{d:,}", f"{e:.2f}"] for a, b, c, d, e in flagged_lanes],
                    right={2, 3, 4},
                )
            )
        else:
            out.append("None.")
    else:
        out.append("No truckload lane has enough finding-free shipments to benchmark.")
    return "\n".join(out) + "\n"


def write_report(db_path: Path, out_path: Path, top_n: int = 5) -> str:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        text = build_report(con, top_n)
    finally:
        con.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return text


def export_marts(db_path: Path, out_dir: Path) -> list[Path]:
    """Write each mart as CSV, ordered by every column so the files are reproducible."""
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=True)
    written = []
    try:
        for name in MARTS:
            path = out_dir / f"{name}.csv"
            con.execute(
                f"COPY (SELECT * FROM {name} ORDER BY ALL) TO '{path}' (HEADER, DELIMITER ',')"
            )
            written.append(path)
    finally:
        con.close()
    return written
