---
name: open-rca-diagnosis
description: "Systematically diagnose and root cause analysis of microservice failures using telemetry data (metrics, traces, logs). Apply the RCA workflow when users report service anomalies, performance degradation, or system failures with time windows."
---

# Open RCA Diagnosis - Microservice Root Cause Analysis

## When to use this skill

Activate this skill when a user requests:
- **Failure diagnosis**: Identifying root causes of service failures or anomalies
- **Performance analysis**: Investigating performance degradation, increased latency, or reduced success rates
- **Troubleshooting**: Debugging microservice system issues with specified time ranges
- **Root cause localization**: Finding the component responsible for system failures

**Prerequisites**: The user must provide a time window (start time and end time) for the analysis.

## Overview

This skill implements a systematic **Root Cause Analysis (RCA)** workflow for microservice systems using telemetry data. The workflow follows a proven pattern:

```
问题分析 → 场景识别 → 预处理 → 异常检测 → 故障识别 → 根因定位
```

Based on the system architecture, dynamically load the appropriate scene specification for accurate diagnosis.

## Diagnosis Workflow

### Step 1: Scene Identification

Before analysis, identify the target system scene:

1. **Bank** - Banking platform microservices
   - Typical components: Apache, Tomcat, MySQL, Redis
   - Data structure: `metric`, `trace`, `log`

2. **Market** - E-commerce platform with failover mechanism
   - Typical components: Multiple pods per service across nodes
   - Data structure: `metric_container`, `metric_service`, `metric_node`, `trace_span`, `log_proxy`

3. **Telecom** - Telecom database system
   - Typical components: Nodes, Docker containers, Database instances
   - Data structure: `metric_app`, `metric_container`, `metric_middleware`, `metric_node`, `trace_span`

**Action**: Load the corresponding scene specification file:
- For Bank: Read `scene_BANK_spec.md`
- For Market: Read `scene_Market_spec.md`
- For Telecom: Read `scene_Telecom_spec.md`

### Step 2: Standard RCA Workflow

Follow this systematic process after loading the scene specification:

#### 2.1 Preprocessing
1. Aggregate KPIs for each possible root cause component to create time series (e.g., `service_A-cpu_usage_pct`)
2. Calculate global thresholds for each KPI (use entire metric file, not filtered data):
   - Typical thresholds: P95, P90, P5, P15
   - For traffic/business KPIs: use lower thresholds (<=P95, <=P15, <=P5)
3. Filter data within the failure time window

#### 2.2 Anomaly Detection
- Identify data points exceeding global thresholds
- For success/flow metrics: look for values BELOW thresholds (indicates packet loss or network issues)
- If no anomalies found: loosen thresholds (e.g., P95 → P90, or lower for drop scenarios)

#### 2.3 Fault Identification
- A "fault" is a consecutive sub-series of anomalies in a component-KPI time series
- Filter isolated noise spikes (consider threshold breach percentage)
- If max/min value only slightly exceeds/falls below threshold (≤50%), likely false positive
- Identify: fault components, resource types, and occurrence timestamps

#### 2.4 Root Cause Localization

**Critical Principles**:

1. **Single fault scenario**: Root cause level determined by fault with most significant threshold deviation (>> 50%)

2. **Multiple service-level faults**: Root cause is the **last (most downstream)** faulty component in the trace call chain

3. **Multiple container-level faults**: Root cause is the **last (most downstream)** faulty container in traces

4. **Multiple node-level faults**:
   - Single failure scenario: Node with most faults is root cause
   - Multiple failures: Each node may be separate root cause

5. **Use traces & logs when**:
   - Multiple faulty components at same level exist
   - Identifying which resource/kpi is root cause among multiple faults
   - Validating hypothesis from metric analysis

### Step 3: Analysis Order

**Strictly follow this sequence**:
1. Threshold calculation → 2. Data extraction → 3. Metric analysis → 4. Trace analysis → 5. Log analysis

**Rationale**:
- Metrics are fastest for narrowing down search space
- Traces help pinpoint root cause among multiple same-level faulty components
- Logs identify the specific resource/kpi and provide operational context

## Key Principles

### DO:
- Use entire KPI series for global threshold calculation (before time filtering)
- Prioritize metric analysis before traces/logs
- Use traces to identify the most downstream fault during multi-component failures
- Filter noise and false positives based on threshold breach percentage
- Timezone: Always use **UTC+8** for all analysis

### DO NOT:
- Calculate thresholds AFTER filtering by time window
- Assume unknown variables - ensure all data is loaded and available
- Use matplotlib/seaborn for visualization (text-based results only)
- Save data to disk files - cache in memory variables only
- Misidentify healthy downstream services as root cause
- Focus only on error logs - info logs contain critical operational data

## Output Format

Provide a concise root cause report including:
- **Root cause component**: Name of the component causing the issue
- **Root cause reason**: The specific resource/KPI and type of failure
- **Occurrence time**: When the fault started
- **Evidence chain**: Brief explanation of how the root cause was identified through the RCA workflow

## Troubleshooting Common Issues

### No anomalies found
- Loosen global thresholds step by step (P95 → P90 → P85)
- Check if using correct threshold direction for the KPI type

### Empty retrieval results
- Verify component names, KPI names, trace IDs, log IDs from schema
- Ensure time zone is set to UTC+8

### Multiple potential root causes
- Use trace analysis to call chain dependency
- Check which fault has the largest threshold deviation
- Use logs to confirm operational timeline