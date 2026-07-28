"""Generates a self-contained static HTML report summarizing the audit log.

No server, no external assets - `triage report` writes one HTML file that can be opened
directly in a browser or attached to a PR/README as a snapshot of agent activity.
"""

from __future__ import annotations

import html
from collections import Counter
from pathlib import Path

from triage_agent.models import TriageRecord

_CATEGORY_COLORS = {
    "flake": "#f5a524",
    "regression": "#e5484d",
    "infra_issue": "#8e4ec6",
    "new_bug": "#3b82f6",
}
_DEFAULT_BAR_COLOR = "#6b7280"
_MAX_TABLE_ROWS = 50


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _category_counts(records: list[TriageRecord]) -> Counter[str]:
    return Counter(r.classification.category.value for r in records)


def _render_bar_chart_svg(counts: Counter[str], bar_height: int = 28, width: int = 420) -> str:
    if not counts:
        return "<p><em>No triage records yet.</em></p>"

    max_count = max(counts.values())
    label_width = 110
    chart_width = width - label_width
    row_gap = 8
    rows = []
    for i, (category, count) in enumerate(sorted(counts.items(), key=lambda kv: -kv[1])):
        y = i * (bar_height + row_gap)
        bar_len = max(2, int((count / max_count) * chart_width))
        color = _CATEGORY_COLORS.get(category, _DEFAULT_BAR_COLOR)
        rows.append(
            f'<text x="0" y="{y + bar_height * 0.7:.0f}" font-size="13" fill="currentColor">'
            f"{_escape(category)}</text>"
            f'<rect x="{label_width}" y="{y}" width="{bar_len}" height="{bar_height}" '
            f'rx="3" fill="{color}"/>'
            f'<text x="{label_width + bar_len + 8}" y="{y + bar_height * 0.7:.0f}" '
            f'font-size="13" fill="currentColor">{count}</text>'
        )
    svg_height = len(counts) * (bar_height + row_gap)
    return (
        f'<svg viewBox="0 0 {width} {svg_height}" width="100%" '
        f'style="max-width:{width}px" role="img" aria-label="Category breakdown">'
        + "".join(rows)
        + "</svg>"
    )


def _summary_stats(records: list[TriageRecord]) -> dict[str, str]:
    total = len(records)
    if total == 0:
        return {
            "Total triaged": "0",
            "Issues filed": "0",
            "Avg. confidence": "n/a",
            "Avg. triage time": "n/a",
        }
    filed = sum(1 for r in records if r.issue_url is not None)
    avg_confidence = sum(r.classification.confidence for r in records) / total
    avg_duration = sum(r.total_duration_seconds for r in records) / total
    return {
        "Total triaged": str(total),
        "Issues filed": f"{filed} ({filed / total:.0%})",
        "Avg. confidence": f"{avg_confidence:.0%}",
        "Avg. triage time": f"{avg_duration:.1f}s",
    }


def _render_table_rows(records: list[TriageRecord]) -> str:
    rows = []
    for record in records[:_MAX_TABLE_ROWS]:
        issue_cell = (
            f'<a href="{_escape(record.issue_url)}">issue</a>' if record.issue_url else "—"
        )
        rows.append(
            "<tr>"
            f"<td>{_escape(record.triaged_at.isoformat(timespec='seconds'))}</td>"
            f"<td>{_escape(record.run.repo)}</td>"
            f"<td>{_escape(record.run.workflow_name)} / {_escape(record.run.job_name)}</td>"
            f"<td>{_escape(record.classification.category.value)}</td>"
            f"<td>{record.classification.confidence:.0%}</td>"
            f"<td>{issue_cell}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_report(records: list[TriageRecord]) -> str:
    """Renders the full HTML report for a list of triage records (most recent first)."""
    stats = _summary_stats(records)
    stat_cards = "".join(
        f'<div class="card"><div class="value">{_escape(v)}</div>'
        f'<div class="label">{_escape(k)}</div></div>'
        for k, v in stats.items()
    )
    chart = _render_bar_chart_svg(_category_counts(records))
    table_rows = _render_table_rows(records)
    truncation_note = (
        f"<p><em>Showing the {_MAX_TABLE_ROWS} most recent of {len(records)} records.</em></p>"
        if len(records) > _MAX_TABLE_ROWS
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CI Failure Triage Report</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 900px; margin: 2rem auto; padding: 0 1rem;
    color: #111827; background: #ffffff;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e5e7eb; background: #111827; }}
    table {{ border-color: #374151; }}
    th, td {{ border-color: #374151 !important; }}
  }}
  h1 {{ font-size: 1.5rem; }}
  .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }}
  .card {{
    border: 1px solid #d1d5db; border-radius: 8px; padding: 0.75rem 1rem; min-width: 140px;
  }}
  .card .value {{ font-size: 1.5rem; font-weight: 600; }}
  .card .label {{ font-size: 0.85rem; opacity: 0.7; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 0.5rem; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e5e7eb; }}
  th {{ font-size: 0.85rem; text-transform: uppercase; opacity: 0.7; }}
  td {{ font-size: 0.9rem; }}
  section {{ margin-bottom: 2rem; }}
</style>
</head>
<body>
<h1>CI Failure Triage Report</h1>
<section class="cards">{stat_cards}</section>
<section>
<h2>By category</h2>
{chart}
</section>
<section>
<h2>Recent triage records</h2>
{truncation_note}
<table>
<thead><tr><th>Triaged at</th><th>Repo</th><th>Workflow / Job</th><th>Category</th>
<th>Confidence</th><th>Issue</th></tr></thead>
<tbody>{table_rows}</tbody>
</table>
</section>
</body>
</html>
"""


def write_report(records: list[TriageRecord], output_path: str | Path) -> None:
    Path(output_path).write_text(render_report(records))
