# Market Scene - E-commerce Platform Specification

## Scene Overview

This is an **E-commerce platform microservice system** with a cloud-native architecture using Kubernetes. It includes a **failover mechanism** with each service deployed across multiple pods (typically 4 replicas) on different nodes.

## Possible Root Cause Components

### Node Level (infrastructure failure)
- node-1, node-2, node-3, node-4, node-5, node-6

### Pod/Container Level (individual container failure)
- frontend-0, frontend-1, frontend-2, frontend2-0
- shippingservice-0, shippingservice-1, shippingservice-2, shippingservice2-0
- checkoutservice-0, checkoutservice-1, checkoutservice-2, checkoutservice2-0
- currencyservice-0, currencyservice-1, currencyservice-2, currencyservice2-0
- adservice-0, adservice-1, adservice-2, adservice2-0
- emailservice-0, emailservice-1, emailservice-2, emailservice2-0
- cartservice-0, cartservice-1, cartservice-2, cartservice2-0
- productcatalogservice-0, productcatalogservice-1, productcatalogservice-2, productcatalogservice2-0
- recommendationservice-0, recommendationservice-1, recommendationservice-2, recommendationservice2-0
- paymentservice-0, paymentservice-1, paymentservice-2, paymentservice2-0

### Service Level (all pods of a service faulty)
- frontend, shippingservice, checkoutservice
- currencyservice, adservice, emailservice
- cartservice, productcatalogservice, recommendationservice, paymentservice

## Possible Root Cause Reasons

Container-level causes:
- Container CPU load
- Container memory load
- Container network packet retransmission
- Container network packet corruption
- Container network latency
- Container packet loss
- Container process termination
- Container read I/O load
- Container write I/O load

Node-level causes:
- Node CPU load
- Node CPU spike
- Node memory consumption
- Node disk read I/O consumption
- Node disk write I/O consumption
- Node disk space consumption

## Telemetry Directory Structure

```
{DATASETS_DIR}/Market/
├── cloudbed-1/telemetry/
│   └── 2022_03_20/
│       ├── metric/
│       │   ├── metric_container.csv
│       │   ├── metric_mesh.csv
│       │   ├── metric_node.csv
│       │   ├── metric_runtime.csv
│       │   └── metric_service.csv
│       ├── trace/
│       │   └── trace_span.csv
│       └── log/
│           ├── log_proxy.csv
│           └── log_service.csv
└── cloudbed-2/telemetry/
    └── 2022_03_20/
        └── (same structure as cloudbed-1)
```

## Data Schema

### Metric Files

**metric_container.csv** - Container-level metrics
```csv
timestamp,cmdb_id,kpi_name,value
1647781200,node-6.adservice2-0,container_fs_writes_MB./dev/vda,0.0
```
- `cmdb_id` format: `node-<N>.<service>-<M>` (e.g., `node-1.adservice-0`)

**metric_mesh.csv** - Service mesh metrics
```csv
timestamp,cmdb_id,kpi_name,value
1647790380,cartservice-1.source.cartservice.redis-cart,istio_tcp_sent_bytes.-,1255.0
```
- `cmdb_id` format: `source-destination` in mesh

**metric_node.csv** - Node-level metrics
```csv
timestamp,cmdb_id,kpi_name,value
1647705600,node-1,system.cpu.iowait,0.31
```
- `cmdb_id` format: `node-<N>` (e.g., `node-1`)

**metric_runtime.csv** - Application runtime metrics
```csv
timestamp,cmdb_id,kpi_name,value
1647730800,adservice.ts:8088,java_nio_BufferPool_TotalCapacity.direct,57343.0
```
- `cmdb_id` format: `<service>:<port>` (e.g., `adservice.ts:8088`)

**metric_service.csv** - Service-level metrics
```csv
service,timestamp,rr,sr,mrt,count
adservice-grpc,1647716400,100.0,100.0,2.429508196728182,61
```
- `service` format: `<service>-<protocol>` (e.g., `adservice-grpc`)
- Only contains 4 KPIs: rr (request rate), sr (success rate), mrt (mean response time), count

### Trace Files

**trace_span.csv** - Distributed tracing data
```csv
timestamp,cmdb_id,span_id,trace_id,duration,type,status_code,operation_name,parent_span
1647705600361,frontend-0,a652d4d10e9478fc,9451fd8fdf746a80687451dae4c4e984,49877,rpc,0,hipstershop.CheckoutService/PlaceOrder,952754a738a11675
```
- `timestamp`: Unix timestamp (milliseconds)
- `cmdb_id`: Pod name (e.g., `frontend-0`)
- `type`: Call type (rpc, http, etc.)
- `status_code`: Response status (0=success)

### Log Files

**log_proxy.csv** - Proxy logs
```csv
log_id,timestamp,cmdb_id,log_name,value
KN43pn8BmS57GQLkQUdP,1647761110,cartservice-1,log_cartservice-service_application,etCartAsync called with userId=3af80013-c2c1-4ae6-86d0-1d9d308e6f5b
```
- `cmdb_id`: Pod name (e.g., `cartservice-1`)

**log_service.csv** - Service logs
```csv
log_id,timestamp,cmdb_id,log_name,value
GIvpon8BDiVcQfZwJ5a9,1647705660,currencyservice-0,log_currencyservice-service_application,"severity: info, message: Getting supported currencies..."
```
- `cmdb_id`: Pod name (e.g., `currencyservice-0`)

## Important Notes

1. **Failover Mechanism**:
   - Each service has 4 pods (e.g., `adservice-0`, `adservice-1`, `adservice-2`, `adservice2-0`)
   - Single pod failure may not significantly impact service metrics
   - Service-level failure means ALL pods of that service are faulty

2. **cmdb_id formats vary by metric type**:
   - **Container metrics**: `node-<N>.<service>-<M>`
   - **Node metrics**: `node-<N>`
   - **Service metrics**: `<service>-grpc`
   - **Runtime metrics**: `<service>:<port>`
   - **Traces**: `<service>-<M>` (pod name)
   - **Logs**: `<service>-<M>` (pod name)

3. **Root cause propagation**:
   - Service-level faults propagate through call chain to downstream services
   - Use trace analysis to identify the most downstream faulty service/component

4. **Time units**:
   - Metric: seconds (e.g., 1647781200)
   - Trace: milliseconds (e.g., 1647705600361)
   - Log: seconds (e.g., 1647705660)

5. **Time zone**: All timestamps use **UTC+8** (China/Hong Kong/Singapore)

6. **Pod = Container**: In this system, pods and containers are equivalent terms