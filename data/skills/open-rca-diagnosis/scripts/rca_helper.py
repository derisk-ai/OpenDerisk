#!/usr/bin/env python3
"""RCA Helper for Open RCA Diagnosis

This script provides utilities for root cause analysis.
All functions work with file paths since the agent can only provide paths.
"""

import pandas as pd
import os
from typing import List, Tuple


def load_csv(file_path: str) -> pd.DataFrame:
    """Load a CSV file into DataFrame."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    return pd.read_csv(file_path)


def list_available_kpis(
    metric_df: pd.DataFrame, kpi_col: str = "kpi_name"
) -> List[str]:
    """List all unique KPI names in the metric file."""
    if kpi_col not in metric_df.columns:
        # Try alternative column names
        alternatives = ["name", "KPI", "metric_name"]
        for alt in alternatives:
            if alt in metric_df.columns:
                kpi_col = alt
                break
    return metric_df[kpi_col].unique().tolist()


def list_available_components(
    metric_df: pd.DataFrame, component_col: str = "cmdb_id"
) -> List[str]:
    """List all unique component names in the metric file."""
    if component_col not in metric_df.columns:
        # Try alternative column names
        alternatives = ["cmdb_id", "container_id", "pod", "service"]
        for alt in alternatives:
            if alt in metric_df.columns:
                component_col = alt
                break
    return metric_df[component_col].unique().tolist()


def calculate_percentile_threshold(
    values: List[float], percentile: float = 95.0
) -> float:
    """Calculate percentile threshold for a list of values."""
    import numpy as np

    return float(np.percentile(values, percentile))


def detect_anomalies(
    values: List[float], threshold: float, direction: str = "above"
) -> List[bool]:
    """Detect anomalies based on threshold."""
    if direction == "above":
        return [v > threshold for v in values]
    return [v < threshold for v in values]


def find_consecutive_faults(
    anomaly_flags: List[bool], min_length: int = 3
) -> List[Tuple[int, int]]:
    """Find consecutive anomaly sequences (faults)."""
    faults = []
    start = None

    for i, is_anomaly in enumerate(anomaly_flags):
        if is_anomaly and start is None:
            start = i
        elif not is_anomaly and start is not None:
            if i - start >= min_length:
                faults.append((start, i))
            start = None

    # Handle case where fault extends to end
    if start is not None and len(anomaly_flags) - start >= min_length:
        faults.append((start, len(anomaly_flags)))

    return faults


def convert_timestamp(ts: float, unit: str = "seconds") -> str:
    """Convert timestamp to readable datetime string (UTC+8)."""
    from datetime import datetime
    import pytz

    tz = pytz.timezone("Asia/Shanghai")

    if unit == "milliseconds":
        ts = ts / 1000.0

    dt = datetime.fromtimestamp(ts, tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def filter_data_by_time(
    df: pd.DataFrame, timestamp_col: str, start_ts: float, end_ts: float
) -> pd.DataFrame:
    """Filter DataFrame by time range."""
    mask = (df[timestamp_col] >= start_ts) & (df[timestamp_col] <= end_ts)
    result = df.loc[mask].copy()
    return pd.DataFrame(result)


def get_metric_by_component_kpi(
    df: pd.DataFrame,
    component: str,
    kpi: str,
    component_col: str = "cmdb_id",
    kpi_col: str = "kpi_name",
) -> pd.DataFrame:
    """Get metrics for a specific component and KPI."""
    # Handle alternative column names
    if component_col not in df.columns:
        for alt in ["cmdb_id", "container_id", "pod", "serviceName"]:
            if alt in df.columns:
                component_col = alt
                break

    if kpi_col not in df.columns:
        for alt in ["kpi_name", "name", "KPI"]:
            if alt in df.columns:
                kpi_col = alt
                break

    mask = (df[component_col] == component) & (df[kpi_col] == kpi)
    result = df.loc[mask].copy()
    return pd.DataFrame(result)


def analyze_trace_call_chain(trace_df: pd.DataFrame, trace_id: str):
    """Analyze call chain for a specific trace."""
    trace_data = trace_df[trace_df["trace_id"] == trace_id].copy()

    # Sort by timestamp if available
    if "startTime" in trace_data.columns:
        trace_data = trace_data.sort_values("startTime")
    elif "timestamp" in trace_data.columns:
        trace_data = trace_data.sort_values("timestamp")

    return trace_data


if __name__ == "__main__":
    print("Open RCA Diagnosis - Helper Functions")
    print("=" * 50)
    print("\nAvailable functions:")
    print("  - load_csv(file_path)")
    print("  - list_available_kpis(metric_df)")
    print("  - list_available_components(metric_df)")
    print("  - calculate_percentile_threshold(values, percentile)")
    print("  - detect_anomalies(values, threshold, direction)")
    print("  - find_consecutive_faults(anomaly_flags, min_length)")
    print("  - convert_timestamp(ts, unit)")
    print("  - filter_data_by_time(df, timestamp_col, start_ts, end_ts)")
    print("  - get_metric_by_component_kpi(df, component, kpi)")
    print("  - analyze_trace_call_chain(trace_df, trace_id)")
    print("\nUsage example:")
    print('  df = load_csv("/path/to/metric_container.csv")')
    print("  kpis = list_available_kpis(df)")
    print("  print(kpis)")
