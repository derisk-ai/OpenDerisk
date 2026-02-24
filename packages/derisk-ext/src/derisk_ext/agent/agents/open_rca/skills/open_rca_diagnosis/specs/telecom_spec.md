# Telecom Scene Specification - 电信场景规格

## 场景概述

本场景是一个电信数据库系统，用于处理电信业务的核心数据存储和查询。系统包含多个数据库实例、容器节点和物理机节点。

## 数据目录结构

```
{data_path}/telemetry/
├── 2020_04_11/                    # 按日期组织
│   ├── metric/                    # 指标数据
│   │   ├── metric_app.csv         # 应用层指标
│   │   ├── metric_container.csv   # 容器层指标
│   │   ├── metric_middleware.csv  # 中间件指标
│   │   ├── metric_node.csv        # 节点层指标
│   │   └── metric_service.csv     # 服务层指标
│   └── trace/                     # 链路追踪
│       └── trace_span.csv
```

## 数据模式定义

### 1. 应用层指标 (metric_app.csv)

| 字段名 | 类型 | 单位 | 描述 |
|--------|------|------|------|
| serviceName | string | - | 服务名称 |
| startTime | int | 毫秒 | 开始时间戳 |
| avg_time | float | ms | 平均响应时间 |
| num | int | 次数 | 请求总数 |
| succee_num | int | 次数 | 成功请求数 |
| succee_rate | float | % | 成功率 |

**示例数据：**
```csv
serviceName,startTime,avg_time,num,succee_num,succee_rate
osb_001,1586534400000,0.333,1,1,1.0
```

### 2. 容器层指标 (metric_container.csv)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| itemid | string | 指标项 ID |
| name | string | KPI 名称 |
| bomc_id | string | BOMC 标识 |
| timestamp | int | Unix 时间戳 (毫秒) |
| value | float | 指标值 |
| cmdb_id | string | 组件标识 |

**示例数据：**
```csv
itemid,name,bomc_id,timestamp,value,cmdb_id
999999996381330,container_mem_used,ZJ-004-060,1586534423000,59.000000,docker_008
```

### 3. 中间件指标 (metric_middleware.csv)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| itemid | string | 指标项 ID |
| name | string | KPI 名称 |
| bomc_id | string | BOMC 标识 |
| timestamp | int | Unix 时间戳 (毫秒) |
| value | float | 指标值 |
| cmdb_id | string | 组件标识 (如 redis_003) |

**示例数据：**
```csv
itemid,name,bomc_id,timestamp,value,cmdb_id
999999996508323,connected_clients,ZJ-005-024,1586534672000,25,redis_003
```

### 4. 节点层指标 (metric_node.csv)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| itemid | string | 指标项 ID |
| name | string | KPI 名称 |
| bomc_id | string | BOMC 标识 |
| timestamp | int | Unix 时间戳 (毫秒) |
| value | float | 指标值 |
| cmdb_id | string | 组件标识 (如 os_017) |

**示例数据：**
```csv
itemid,name,bomc_id,timestamp,value,cmdb_id
999999996487783,CPU_iowait_time,ZJ-001-010,1586534683000,0.022954,os_017
```

### 5. 服务层指标 (metric_service.csv)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| itemid | string | 指标项 ID |
| name | string | KPI 名称 |
| bomc_id | string | BOMC 标识 |
| timestamp | int | Unix 时间戳 (毫秒) |
| value | float | 指标值 |
| cmdb_id | string | 组件标识 (如 db_003) |

**示例数据：**
```csv
itemid,name,bomc_id,timestamp,value,cmdb_id
999999998650974,MEM_Total,ZJ-002-055,1586534694000,381.902264,db_003
```

### 6. 链路追踪 (trace_span.csv)

| 字段名 | 类型 | 描述 |
|--------|------|------|
| callType | string | 调用类型 (JDBC/LOCAL/RemoteProcess/FlyRemote/OSB) |
| startTime | int | Unix 时间戳 (毫秒) |
| elapsedTime | float | ms | 耗时 |
| success | string | 是否成功 (True/False) |
| traceId | string | 追踪 ID |
| id | string | Span ID |
| pid | string | 父 Span ID |
| cmdb_id | string | 组件标识 |
| dsName | string | 数据源名称 |
| serviceName | string | 服务名称 |

**示例数据：**
```csv
callType,startTime,elapsedTime,success,traceId,id,pid,cmdb_id,dsName,serviceName
JDBC,1586534400335,2.0,True,01df517164d1c0365586,407d617164d1c14f2613,6e02217164d1c14b2607,docker_006,db_003,
```

## 候选根因组件

### Node 层组件 (物理机)

| 组件 ID | 描述 |
|---------|------|
| os_001 ~ os_022 | 22 个物理机节点 |

### Container 层组件 (容器)

| 组件 ID | 描述 |
|---------|------|
| docker_001 ~ docker_008 | 8 个容器实例 |

### Service 层组件 (服务/数据库)

| 组件 ID | 描述 |
|---------|------|
| db_001 ~ db_013 | 13 个数据库/服务实例 |

## 候选根因原因

| 原因类别 | 具体原因 |
|----------|----------|
| CPU 相关 | CPU fault |
| 网络相关 | network delay, network loss |
| 数据库相关 | db connection limit, db close |

## 时间戳单位约定

| 数据类型 | 时间戳单位 | 示例 |
|----------|------------|------|
| Metric | 毫秒 | 1586534423000 |
| Trace | 毫秒 | 1586534400335 |

## 时区设置

所有问题均使用 **UTC+8** 时间。

## 系统特点

1. **多层级结构**：Node -> Container -> Service 三层
2. **复杂的调用类型**：支持 JDBC、LOCAL、RemoteProcess、FlyRemote、OSB 等多种调用
3. **中间件监控**：独立的中间件指标文件
4. **无日志数据**：此场景暂不提供日志文件
5. **组件命名规范**：
   - Node: `os_{编号}`
   - Container: `docker_{编号}`
   - Service: `db_{编号}`