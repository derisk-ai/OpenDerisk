cand = """## POSSIBLE ROOT CAUSE REASONS:
        
- high CPU usage
- high memory usage 
- network latency 
- network packet loss
- high disk I/O read usage 
- high disk space usage
- high JVM CPU load 
- JVM Out of Memory (OOM) Heap

## POSSIBLE ROOT CAUSE COMPONENTS:

- apache01
- apache02
- Tomcat01
- Tomcat02
- Tomcat04
- Tomcat03
- MG01
- MG02
- IG01
- IG02
- Mysql01
- Mysql02
- Redis01
- Redis02"""

schema = f"""## TELEMETRY DIRECTORY STRUCTURE:

- You can access the telemetry directory in our microservices system: `/Users/tuyang.yhj/Downloads/Bank/telemetry/`.

- This directory contains subdirectories organized by a date (e.g., `/Users/tuyang.yhj/Downloads/Bank/telemetry/2021_03_05/`). 

- Within each date-specific directory, you’ll find these subdirectories: `metric`, `trace`, and `log` (e.g., `/Users/tuyang.yhj/Downloads/Bank/telemetry/2021_03_05/metric/`).

- The telemetry data in those subdirectories is stored in CSV format (e.g., `/Users/tuyang.yhj/Downloads/Bank/telemetry/2021_03_05/metric/metric_container.csv`).

## DATA SCHEMA

1.  **Metric Files**:
    
    1. `metric_app.csv`:

        ```csv
        timestamp,rr,sr,cnt,mrt,tc
        1614787440,100.0,100.0,22,53.27,ServiceTest1
        ```

    2. `metric_container.csv`:

        ```csv
        timestamp,cmdb_id,kpi_name,value
        1614787200,Tomcat04,OSLinux-CPU_CPU_CPUCpuUtil,26.2957
        ```

2.  **Trace Files**:

    1. `trace_span.csv`:

        ```csv
        timestamp,cmdb_id,parent_id,span_id,trace_id,duration
        1614787199628,dockerA2,369-bcou-dle-way1-c514cf30-43410@0824-2f0e47a816-17492,21030300016145905763,gw0120210304000517192504,19
        ```

3.  **Log Files**:

    1. `log_service.csv`:

        ```csv
        log_id,timestamp,cmdb_id,log_name,value
        8c7f5908ed126abdd0de6dbdd739715c,1614787201,Tomcat01,gc,"3748789.580: [GC (CMS Initial Mark) [1 CMS-initial-mark: 2462269K(3145728K)] 3160896K(4089472K), 0.1985754 secs] [Times: user=0.59 sys=0.00, real=0.20 secs] "
        ```

{cand}

## CLARIFICATION OF TELEMETRY DATA:

1. This microservice system is a banking platform.

2. The `metric_app.csv` file only contains four KPIs: rr, sr, cnt, and mrt,. In contrast, `metric_container.csv` records a variety of KPIs, such as CPU usage and memory usage. The specific names of these KPIs can be found in the `kpi_name` field.

3. In different telemetry files, the timestamp units and cmdb_id formats may vary:

- Metric: Timestamp units are in seconds (e.g., 1614787440).

- Trace: Timestamp units are in milliseconds (e.g., 1614787199628).

- Log: Timestamp units are in seconds (e.g., 1614787201).

4. Please use the UTC+8 time zone in all analysis steps since system is deployed in China/Hong Kong/Singapore."""

