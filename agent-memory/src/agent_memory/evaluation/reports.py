"""Evaluation report generation — JSON, JUnit XML, and HTML reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


class EvaluationResult:
    """A single evaluation result for report generation."""

    def __init__(
        self,
        scenario_name: str,
        passed: bool,
        metrics: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ):
        self.scenario_name = scenario_name
        self.passed = passed
        self.metrics = metrics or {}
        self.errors = errors or []


def generate_json_report(results: list[EvaluationResult]) -> str:
    """Generate a JSON report from evaluation results."""
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "results": [],
    }

    for r in results:
        report["results"].append({
            "scenario": r.scenario_name,
            "passed": r.passed,
            "metrics": r.metrics,
            "errors": r.errors,
        })

    return json.dumps(report, indent=2, default=str)


def generate_junit_xml(results: list[EvaluationResult]) -> str:
    """Generate a JUnit XML report from evaluation results."""
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuites name="agent-memory" tests="{len(results)}" '
        f'failures="{sum(1 for r in results if not r.passed)}" '
        f'time="0">',
    ]

    for r in results:
        if r.passed:
            lines.append(
                f'  <testcase name="{r.scenario_name}" classname="agent_memory.evaluation">'
                '</testcase>'
            )
        else:
            lines.append(
                f'  <testcase name="{r.scenario_name}" classname="agent_memory.evaluation">'
            )
            for error in r.errors:
                lines.append(
                    f'    <failure message="{_escape_xml(error)}">'
                    f'{_escape_xml(r.scenario_name)}: {error}'
                    '</failure>'
                )
            lines.append('  </testcase>')

    lines.append('</testsuites>')
    return "\n".join(lines)


def generate_html_report(results: list[EvaluationResult]) -> str:
    """Generate an HTML report with Tailwind styling."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    rows_html = ""
    for r in results:
        status_class = "bg-green-100 text-green-800" if r.passed else "bg-red-100 text-red-800"
        status_text = "PASS" if r.passed else "FAIL"

        rows_html += f"""
        <tr class="hover:bg-gray-50">
            <td class="px-6 py-4 text-sm font-medium text-gray-900">{_escape_html(r.scenario_name)}</td>
            <td class="px-6 py-4">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium {status_class}">
                    {status_text}
                </span>
            </td>
            <td class="px-6 py-4 text-sm text-gray-500">
                {', '.join(_escape_html(e) for e in r.errors) if r.errors else '<span class="text-gray-400">-</span>'}
            </td>
            <td class="px-6 py-4 text-sm text-gray-500">
                {', '.join(f"{k}: {v}" for k, v in r.metrics.items()) if r.metrics else '<span class="text-gray-400">-</span>'}
            </td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Evaluation Report</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen p-8">
    <div class="max-w-6xl mx-auto">
        <h1 class="text-3xl font-bold text-gray-800 mb-2">Evaluation Report</h1>
        <p class="text-gray-600 mb-6">Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>

        <!-- Summary Cards -->
        <div class="grid grid-cols-3 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-gray-500">Total</p>
                <p class="text-3xl font-bold text-gray-800">{total}</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-green-600">Passed</p>
                <p class="text-3xl font-bold text-green-600">{passed}</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <p class="text-sm font-medium text-red-600">Failed</p>
                <p class="text-3xl font-bold text-red-600">{failed}</p>
            </div>
        </div>

        <!-- Pass Rate Bar -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <h3 class="text-lg font-semibold text-gray-800 mb-2">Pass Rate</h3>
            <div class="w-full bg-gray-200 rounded-full h-4">
                <div class="bg-green-500 h-4 rounded-full" style="width: {pass_rate:.0f}%"></div>
            </div>
            <p class="text-sm text-gray-600 mt-2">{pass_rate:.1f}%</p>
        </div>

        <!-- Results Table -->
        <div class="bg-white rounded-lg shadow overflow-hidden">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Scenario</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Errors</th>
                        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Metrics</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
{rows_html}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>"""

    return html


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
