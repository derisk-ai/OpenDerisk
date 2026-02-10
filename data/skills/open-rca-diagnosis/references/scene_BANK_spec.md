# Bank Scene - Banking Platform Specification

## Scene Overview

This is a **banking platform microservice system** with traditional web application architecture.

## Possible Root Cause Reasons
- High CPU usage
- High memory usage
- Network latency
- Network packet loss
- High disk I/O read usage
- High disk space usage
- High JVM CPU load
- JVM Out of Memory (OOM) Heap

## Possible Root Cause Components
- apache01, apache02
- Tomcat01, Tomcat02, Tomcat03, Tomcat04
- MG01, MG02 (Message Gateway)
- IG01, IG02 (Integration Gateway)
- Mysql01, Mysql02
- Redis01, Redis02

## Telemetry Directory Structure

```
{DATASETS_DIR}/Bank/telemetry/
└── 2021_03_05/           (Date-specific directory)
    ├── metric/
    │   ├── metric_app.csv
    │   └── metric_container.csv
    ├── trace/
    │   └── trace_span.csv
    └── log/
        └── log_service.csv
```

## Data Schema

### Metric Files

**metric_app.csv** - Application-level metrics
```csv
timestamp,rr,sr,cnt,mrt,tc
1614787440,100.0,100.0,22,53.27,ServiceTest1
```
- `rr`: Request Rate
- `sr`: Success Rate
- `cnt`: Count
- `mrt`: Mean Response Time
- `tc`: Test Case/Service Name

**metric_container.csv** - Container-level metrics
```csv
timestamp,cmdb_id,kpi_name,value
1614787200,Tomcat04,OSLinux-CPU_CPU_CPUCpuUtil,26.2957
```
- `timestamp`: Unix timestamp (seconds)
- `cmdb_id`: Component name
- `kpi_name`: KPI identifier
- `value`: Metric value

### Trace Files

**trace_span.csv** - Distributed tracing data
```csv
timestamp,cmdb_id,parent_id,span_id,trace_id,duration
1614787199628,dockerA2,369-bcou-dle-way1-c514cf30-43410@0824-2f0e47a816-17492,21030300016145905763,gw0120210304000517192504,19
```
- `timestamp`: Unix timestamp (milliseconds)
- `cmdb_id`: Component ID
- `parent_id`: Parent span ID
- `span_id`: Unique span identifier
- `trace_id`: Trace identifier
- `duration`: Span duration (milliseconds)

### Log Files

**log_service.csv** - Service logs
```csv
log_id,timestamp,cmdb_id,log_name,value
8c7f5908ed126abdd0de6dbdd739715c,1614787201,Tomcat01,gc,"3748789.580: [GC (CMS Initial Mark) [1 CMS-initial-mark: 2462269K(3145728K)] 3160896K(4089472K), 0.1985754 secs]"
```
- `log_id`: Unique log identifier
- `timestamp`: Unix timestamp (seconds)
- `cmdb_id`: Component name
- `log_name`: Log category/type
- `value`: Log message content

## Important Notes

1. **Time units**:
   - Metric: seconds (e.g., 1614787440)
   - Trace: milliseconds (e.g., 1614787199628)
   - Log: seconds (e.g., 1614787201)

2. **Time zone**: All timestamps use **UTC+8** (China/Hong Kong/Singapore)

3. **Metric characteristics**:
   - `metric_app.csv`: Only contains 4 KPIs (rr, sr, cnt, mrt, tc)
   - `metric_container.csv`: Contains diverse KPIs (CPU, memory, disk, etc.)
   - Check `kpi_name` field for specific KPI identifiers

4. **Component identification**:
   - Use `cmdb_id` field to match components from "Possible Root Cause Components" list
   - Different telemetry files may have different `cmdb_id` formats