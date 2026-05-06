"""
Simple telemetry helper for the Voice-Powered Memo Analyzer.

The main app exposes /telemetry-summary from app.py.
This file is included to document/support the telemetry portion of the project.
"""

import statistics


def build_telemetry_summary(session_log):
    if not session_log:
        return {"message": "No calls yet."}

    confidences = [entry.get("confidence", 0) for entry in session_log]

    return {
        "total_calls": len(session_log),
        "avg_confidence": round(statistics.mean(confidences), 3),
        "min_confidence": round(min(confidences), 3),
        "latest_call": session_log[-1]
    }
