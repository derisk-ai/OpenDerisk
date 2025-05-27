cand = """## POSSIBLE ROOT CAUSE COMPONENTS:

(if the root cause is at the node level, i.e., the root cause is a specific node)
- node-1
- node-2
- node-3
- node-4
- node-5
- node-6

(if the root cause is at the pod level, i.e., the root cause is a specific container)

- frontend-0
- frontend-1
- frontend-2
- frontend2-0
- shippingservice-0
- shippingservice-1
- shippingservice-2
- shippingservice2-0
- checkoutservice-0
- checkoutservice-1
- checkoutservice-2
- checkoutservice2-0
- currencyservice-0
- currencyservice-1
- currencyservice-2
- currencyservice2-0
- adservice-0
- adservice-1
- adservice-2
- adservice2-0
- emailservice-0
- emailservice-1
- emailservice-2
- emailservice2-0
- cartservice-0
- cartservice-1
- cartservice-2
- cartservice2-0
- productcatalogservice-0
- productcatalogservice-1
- productcatalogservice-2
- productcatalogservice2-0
- recommendationservice-0
- recommendationservice-1
- recommendationservice-2
- recommendationservice2-0
- paymentservice-0
- paymentservice-1
- paymentservice-2
- paymentservice2-0

(if the root cause is at the service level, i.e., if all pods of a specific service are faulty, the root cause is the service itself)

- frontend
- shippingservice
- checkoutservice
- currencyservice
- adservice
- emailservice
- cartservice
- productcatalogservice
- recommendationservice
- paymentservice

## POSSIBLE ROOT CAUSE REASONS:

- container CPU load
- container memory load
- container network packet retransmission 
- container network packet corruption
- container network latency 
- container packet loss 
- container process termination
- container read I/O load
- container write I/O load
- node CPU load
- node CPU spike
- node memory consumption
- node disk read I/O consumption 
- node disk write I/O consumption 
- node disk space consumption"""

schema = f"""## TELEMETRY DIRECTORY STRUCTURE:

- You can access the telemetry directories of two cloudbed (i.e., `cloudbed-1` and `cloudbed-2`) in our microservices system: `dataset/Market/cloudbed-1/telemetry/` and `dataset/Market/cloudbed-2/telemetry/`.

- This directory contains subdirectories organized by a date (e.g., `dataset/Market/cloudbed-1/telemetry/2022_03_20/`). 

- Within each date-specific directory, you’ll find these subdirectories: `metric`, `trace`, and `log` (e.g., `dataset/Market/cloudbed-1/telemetry/2022_03_20/metric/`).

- The telemetry data in those subdirectories is stored in CSV format (e.g., `dataset/Market/cloudbed-1/telemetry/2022_03_20/metric/metric_container.csv`).

## DATA SCHEMA

1.  **Metric Files**:
    
    1. `metric_container.csv`:

        ```csv
        timestamp,cmdb_id,kpi_name,value
        1647781200,node-6.adservice2-0,container_fs_writes_MB./dev/vda,0.0
        ```

    2. `metric_mesh.csv`:

        ```csv
        timestamp,cmdb_id,kpi_name,value
        1647790380,cartservice-1.source.cartservice.redis-cart,istio_tcp_sent_bytes.-,1255.0
        ```

    3. `metric_node.csv`:

        ```csv
        timestamp,cmdb_id,kpi_name,value
        1647705600,node-1,system.cpu.iowait,0.31
        ```

    4. `metric_runtime.csv`:

        ```csv
        timestamp,cmdb_id,kpi_name,value
        1647730800,adservice.ts:8088,java_nio_BufferPool_TotalCapacity.direct,57343.0
        ```

    5. `metric_service.csv`:

        ```csv
        service,timestamp,rr,sr,mrt,count
        adservice-grpc,1647716400,100.0,100.0,2.429508196728182,61
        ```

2.  **Trace Files**:

    1. `trace_span.csv`:

        ```csv
        timestamp,cmdb_id,span_id,trace_id,duration,type,status_code,operation_name,parent_span
        1647705600361,frontend-0,a652d4d10e9478fc,9451fd8fdf746a80687451dae4c4e984,49877,rpc,0,hipstershop.CheckoutService/PlaceOrder,952754a738a11675
        ```

3.  **Log Files**:

    1. `log_proxy.csv`:

        ```csv
        log_id,timestamp,cmdb_id,log_name,value
        KN43pn8BmS57GQLkQUdP,1647761110,cartservice-1,log_cartservice-service_application,etCartAsync called with userId=3af80013-c2c1-4ae6-86d0-1d9d308e6f5b
        ```

    2. `log_service.csv`:

        ```csv
        log_id,timestamp,cmdb_id,log_name,value
        GIvpon8BDiVcQfZwJ5a9,1647705660,currencyservice-0,log_currencyservice-service_application,"severity: info, message: Getting supported currencies..."
        ```

{cand}

## CLARIFICATION OF TELEMETRY DATA:

1. This microservice system is a E-commerce platform which includes a failover mechanism, with each service deployed across four pods. In this system, a container (pod) can be deployed in different nodes. If the root cause component is a single pod of a specific service (e.g., node-1.adservice-0), the failure may not significantly impact the corresponding service metrics. In contrast, if the root cause component is a service itself (e.g., adservice), which means all pods of this service are faulty, the corresponding service metrics will be significantly impacted. Moreover, such fault could be propagate through the call chain, resulting in other service's metrics faulty. Note that `Pod` equals to `Container` in this system.

2. The `metric_service.csv` file only contains four KPIs: rr, sr, mrt, and count. In contrast, other metric files record a variety of KPIs, such as CPU usage and memory usage. The specific names of these KPIs can be found in the `kpi_name` field.

3. Note that the `cmdb_id` is the name of specific components, including nodes, pods, services, etc.

-  Metrics:
    -  Runtime: The application name and port, e.g., `adservice.ts:8088`
    -  Service: The service name and protocol, e.g., `adservic-grpc`
    -  Container: The pod name combined with a node name, e.g., `node-1.adservice-0`
    -  Node: The node name, e.g., `node-1`
    -  Mesh: The service-to-service connection identifier within the mesh, e.g.,`cartservice-1.source.cartservice.redis-cart`

-  Traces: The pod name, e.g., `adservice-0`

-  Logs: The pod name, e.g., `adservice-0`

4. In different telemetry files, the timestamp units and cmdb_id formats may vary:

- Metric: Timestamp units are in seconds (e.g., 1647781200). cmdb_id varies by metric file:
    - In container metrics: `<node>-x.<service>-x` (e.g., `node-1.adservice-0`)
    - In node metrics: `<node>-x` (e.g., `node-1`)
    - In service metrics: `<service>-grpc` (e.g., `adservice-grpc`)

- Trace: Timestamp units are in milliseconds (e.g., 1647705600361). cmdb_id is consistently `<service>-x` (e.g., frontend-0).

- Log: Timestamp units are in seconds (e.g., 1647705660). cmdb_id is consistently `<service>-x` (e.g., currencyservice-0).

5. Please use the UTC+8 time zone in all analysis steps since system is deployed in China/Hong Kong/Singapore."""
