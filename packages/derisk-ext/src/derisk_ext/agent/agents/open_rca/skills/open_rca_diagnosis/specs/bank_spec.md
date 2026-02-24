# Bank Scene Specification - 银行场景规格

## 场景概述

本场景是一个银行微服务平台系统，用于处理银行业务流程。系统采用典型三层架构，包含 Web 层、应用层和数据层。

## 数据目录结构

```
{data_path}/telemetry/
├── 2021_03_05/                    # 按日期组织
│   ├── metric/                    # 指标数据
│   │   ├── metric_app.csv         # 应用层指标
│   │   └── metric_container.csv   # 容器层指标
│   ├── trace/                     # 链路追踪
│   │   └── trace_span.csv
│   └── log/                       # 日志数据
│       └── log_service.csv
```

## 数据模式定义

### 1. 应用层指标 (metric_app.csv)

业务级 KPI 指标，反映服务整体健康状态。

| 字段名 | 类型 | 单位 | 描述 |
|--------|------|------|------|
| timestamp | int | 秒 | Unix 时间戳 |
| rr | float | % | 请求成功率 |
| sr | float | % | 服务成功率 |
| cnt | int | 次数 | 请求计数 |
| mrt | float | ms | 平均响应时间 |
| tc | string | - | 服务名称 |

**示例数据：**
```csv
timestamp,rr,sr,cnt,mrt,tc
1614787440,100.0,100.0,22,53.27,ServiceTest1
```

### 2. 容器层指标 (metric_container.csv)

基础设施层 KPI 指标，反映容器资源使用情况。

| 字段名 | 类型 | 单位 | 描述 |
|--------|------|------|------|
| timestamp | int | 秒 | Unix 时间戳 |
| cmdb_id | string | - | 组件标识 (容器名) |
| kpi_name | string | - | KPI 名称 |
| value | float | - | 指标值 |

**示例数据：**
```csv
timestamp,cmdb_id,kpi_name,value
1614787200,Tomcat04,OSLinux-CPU_CPU_CPUCpuUtil,26.2957
```

### 3. 链路追踪 (trace_span.csv)

服务调用链路信息。

| 字段名 | 类型 | 单位 | 描述 |
|--------|------|------|------|
| timestamp | int | 毫秒 | Unix 时间戳 (毫秒) |
| cmdb_id | string | - | 组件标识 |
| parent_id | string | - | 父 Span ID |
| span_id | string | - | 当前 Span ID |
| trace_id | string | - | 追踪 ID |
| duration | int | ms | 调用耗时 |

**示例数据：**
```csv
timestamp,cmdb_id,parent_id,span_id,trace_id,duration
1614787199628,dockerA2,369-bcou-dle-way1-c514cf30-43410@0824-2f0e47a816-17492,21030300016145905763,gw0120210304000517192504,19
```

### 4. 服务日志 (log_service.csv)

服务运行日志信息。

| 字段名 | 类型 | 描述 |
|--------|------|------|
| log_id | string | 日志唯一标识 |
| timestamp | int | Unix 时间戳 (秒) |
| cmdb_id | string | 组件标识 |
| log_name | string | 日志类型 |
| value | string | 日志内容 |

**示例数据：**
```csv
log_id,timestamp,cmdb_id,log_name,value
8c7f5908ed126abdd0de6dbdd739715c,1614787201,Tomcat01,gc,"3748789.580: [GC (CMS Initial Mark) [1 CMS-initial-mark: 2462269K(3145728K)] 3160896K(4089472K), 0.1985754 secs]"
```

## 候选根因组件

### 组件层级结构

```
Node 层（物理机/虚拟机）
└── Container 层（容器）
    └── Service 层（服务实例）
```

### 候选组件列表

| 层级 | 组件列表 |
|------|----------|
| Web 服务器 | apache01, apache02 |
| 应用服务器 | Tomcat01, Tomcat02, Tomcat03, Tomcat04 |
| 网关 | MG01, MG02, IG01, IG02 |
| 数据库 | Mysql01, Mysql02 |
| 缓存 | Redis01, Redis02 |

## 候选根因原因

| 原因类别 | 具体原因 |
|----------|----------|
| CPU 相关 | high CPU usage, high JVM CPU load |
| 内存相关 | high memory usage, JVM Out of Memory (OOM) Heap |
| 网络相关 | network latency, network packet loss |
| 磁盘相关 | high disk I/O read usage, high disk space usage |

## 时间戳单位约定

| 数据类型 | 时间戳单位 | 示例 |
|----------|------------|------|
| Metric | 秒 | 1614787440 |
| Trace | 毫秒 | 1614787199628 |
| Log | 秒 | 1614787201 |

## 时区设置

所有问题均使用 **UTC+8** 时间。分析时需显式设置时区：
```python
import pytz
tz = pytz.timezone('Asia/Shanghai')
```

## 系统特点

1. **三层架构**：Web -> App -> DB，故障可逐层传播
2. **单一故障点**：问题通常描述单个故障
3. **组件命名规范**：`{ServiceType}{序号}`，如 Tomcat01
4. **KPI 命名约定**：`{系统}-{类型}_{资源}_{指标}`，如 `OSLinux-CPU_CPU_CPUCpuUtil`