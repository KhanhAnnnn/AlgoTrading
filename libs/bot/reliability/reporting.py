"""
libs/bot/reliability/reporting.py — Reliability & Soak Report Generator (GĐ39)
Formats structured human-readable markdown and JSON evidence files for acceptance.
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import json
import logging

logger = logging.getLogger("reliability-reporting")


class ReliabilityReportGenerator:
    """
    Compiles soak test runs, benchmark latencies, and reconciliation audits into final reports.
    """

    @staticmethod
    def generate_soak_report(soak_data: Dict[str, Any]) -> str:
        """Generates comprehensive markdown text for a soak test run."""
        lines = [
            f"# SOAK RUN REPORT: {soak_data.get('soak_run_id', 'UNKNOWN')}",
            f"- **Level**: {soak_data.get('level', 'N/A')}",
            f"- **Target Duration**: {soak_data.get('target_duration_seconds', 0)}s",
            f"- **Observed Elapsed**: {soak_data.get('observed_elapsed_seconds', 0):.2f}s",
            f"- **Uninterrupted Duration**: {soak_data.get('uninterrupted_duration_seconds', 0):.2f}s",
            f"- **Bot Count**: {soak_data.get('bot_count', 0)}",
            f"- **Events Processed**: {soak_data.get('events_processed', 0)}",
            f"- **Orders Created**: {soak_data.get('orders_created', 0)}",
            f"- **Fills Created**: {soak_data.get('fills_created', 0)}",
            f"- **Queue Overflows**: {soak_data.get('queue_overflows', 0)}",
            f"- **Recovered Gaps**: {soak_data.get('recovered_gaps', 0)}",
            f"- **Broker Write Calls**: {soak_data.get('broker_write_calls', 0)} (Must be 0)",
            f"- **Financial Reconciliation**: {soak_data.get('reconciliation_status', 'UNKNOWN')}",
            f"- **Final Status**: {soak_data.get('final_status', 'UNKNOWN')}",
            "",
            "## Latencies (E2E ms)",
        ]
        lat = soak_data.get("latencies_ms", {}).get("e2e", {})
        lines.append(f"- p50: {lat.get('p50', 0.0)} ms")
        lines.append(f"- p95: {lat.get('p95', 0.0)} ms")
        lines.append(f"- p99: {lat.get('p99', 0.0)} ms")
        return "\n".join(lines)
