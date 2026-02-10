# Telecom Scene - Telecom Database System Specification

## Scene Overview

This is a **telecom database system** with microservices architecture for processing telecom service requests and database operations.

## Possible Root Cause Reasons
- CPU fault
- Network delay
- Network loss
- DB connection limit
- DB close

## Possible Root Cause Components

### Node Level (OS infrastructure)
- os_001, os_002, os_003, os_004, os_005, os_006
- os_007, os_008, os_009, os_010, os_011, os_012
- os_013, os_014, os_015, os_016, os_017, os_018
- os_019, os_020, os_021, os_022

### Container/Pod Level (Docker containers)
- docker_001, docker_002, docker_003, docker_004
- docker_005, docker_006, docker_007, docker_008

### Service Level (Database instances)
- db_001, db_002, db_003, db_004
- db_005, db_006, db_007, db_008
- db_009, db_010, db_011, db_012, db_013

## Telemetry Directory Structure

```
{DATASETS_DIR}/Telecom/telemetry/
└── 2020_04_11/           (Date-specific directory)
    ├── metric/
    │   ├── metric_app.csv
    │   ├── metric_container.csv
    │   ├── metric_middleware.csv
    │   ├── metric_node.csv
    │   └── metric_service.csv
    └── trace/
        └── trace_span.csv
```

**Note**: This system does not have log files.

## Data Schema

### Metric Files

**metric_app.csv** - Application-level metrics
```csv
serviceName,startTime,avg_time,num,succee_num,succee_rate
osb_001,1586534400000,0.333,1,1,1.0
```
- `serviceName`: Service identifier
- `startTime`: Unix timestamp (milliseconds)
- `avg_time`: Average processing time
- `num`: Total number of requests
- `succee_num`: Number of successful requests
- `succee_rate`: Success rate

**metric_container.csv** - Container-level metrics
```csv
itemid,name,bomc_id,timestamp,value,cmdb_id
999999996381330,container_mem_used,ZJ-004-060,1586534423000,59.0,docker_008
```
- `itemid`: Metric item identifier
- `name`: KPI name
- `bomc_id`: Business/operation management center ID
- `timestamp`: Unix timestamp (milliseconds)
- `value`: Metric value
- `cmdb_id`: Container name (e.g., `docker_008`)

**metric_middleware.csv** - Middleware metrics (e.g., Redis)
```csv
itemid,name,bomc_id,timestamp,value,cmdb_id
999999996508323,connected_clients,ZJ-005-024,1586534672000,25,redis_003
```
- Similar structure to `metric_container.csv`
- Includes middleware-specific KPIs (e.g., Redis connections)

**metric_node.csv** - Node-level metrics
```csv
itemid,name,bomc_id,timestamp,value,cmdb_id
999999996487783,CPU_iowait_time,ZJ-001-010,1586534683000,0.022954,os_017
```
- Similar structure to `metric_container.csv`
- `cmdb_id`: OS node name (e.g., `os_017`)

**metric_service.csv** - Database service metrics
```csv
itemid,name,bomc_id,timestamp,value,cmdb_id
999999998650974,MEM_Total,ZJ-002-055,1586534694000,381.902264,db_003
```
- Similar structure to `metric_container.csv`
- `cmdb_id`: Database instance name (e.g., `db_003`)
- Contains database-specific KPIs (memory, connections, etc.)

### Trace Files

**trace_span.csv** - Distributed tracing data
```csv
callType,startTime,elapsedTime,success,traceId,id,pid,cmdb_id,dsName,serviceName
JDBC,1586534400335,2.0,True,01df517164d1c0365586,407d617164d1c14f2613,6e02217164d1c14b2607,docker_006,db_003,
LOCAL,1586534400331,6.0,True,01df517164d1c0365586,6e02217164d1c14b2607,8432217164d1c1442597,docker_006,db_003,local_method_017
RemoteProcess,1586534400324,55.0,True,01df517164d1c0365586,8432217164d1c1442597,b755e17164d1c13f5066,docker_006,,csf_005
FlyRemote,1586534400149,7.0,TRUE,fa1e817164d1c0375444,da74117164d1c0955052,b959f17164d1c08c5050,docker_003,,fly_remote_001
OSB,1586534660846,376.0,True,d9c4817164d5baee6924,77d1117164d5baee6925,None,os_021,,osb_001
```
- `callType`: Type of call (JDBC, LOCAL, RemoteProcess, FlyRemote, OSB)
- `startTime`: Unix timestamp (milliseconds)
- `elapsedTime`: Call duration
- `success`: Success status (True/False)
- `traceId`: Trace identifier
- `id`: Span ID
- `pid`: Parent span ID
- `cmdb_id`: Component name (container/node name)
- `dsName`: Data source name (e.g., `db_003`)
- `serviceName`: Service name (e.g., `osb_001`, `csf_005`)

**Call Types**:
- `JDBC`: Database calls
- `LOCAL`: Local method calls
- `RemoteProcess`: Remote process calls
- `FlyRemote`: Fly remote calls
- `OSB`: Oracle Service Bus calls

## Important Notes

1. **Architecture**:
   - Three-level component hierarchy: Nodes → Docker containers → Database instances
   - Requests flow from OSB service through containers to database instances

2. **Time units**:
   - Metric: milliseconds for ALL metrics (e.g., 1586534423000)
   - Trace: milliseconds (e.g., 1586534400335)

3. **Consistent timestamp format**:
   - Unlike other scenes, all telemetry files use consistent millisecond timestamps

4. **No log files**:
   - This system does not have log telemetry data
   - Rely on metrics and traces for root cause analysis

5. **Time zone**: All timestamps use **UTC+8** (China/Hong Kong/Singapore)

6. **KPI naming**:
   - Use `name` field in metric files (not `kpi_name`)
   - Each file type contains different KPI categories relevant to its scope

7. **Root cause patterns**:
   - Node-level issues (CPU, network) affect containers and services
   - Container-level issues affect the applications and database access
   - Database-level issues (connection limits, DB close) directly impact service success rates