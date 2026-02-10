# Open RCA Diagnosis - AgentSkill

基于 Open RCA 数据集的微服务故障根因分析与诊断技能。

## 技能结构

```
open-rca-diagnosis/
├── SKILL.md                      # 主技能文件：标准化的 RCA 工作流程
├── README.md                     # 本文档
├── references/                   # 场景规格（渐进式披露）
│   ├── scene_BANK_spec.md       # 银行平台场景规格
│   ├── scene_Market_spec.md     # 电商平台场景规格
│   └── scene_Telecom_spec.md    # 电信系统场景规格
└── scripts/
    └── rca_helper.py            # RCA 分析辅助函数
```

## 设计理念

### 渐进式披露

遵循 AgentSkill 的渐进式披露范式：

1. **发现阶段（Discovery）**：系统启动时仅加载 `SKILL.md` 的元数据（name 和 description），用于判断何时激活该技能

2. **激活阶段（Activation）**：当任务匹配描述时，加载完整的 `SKILL.md` 指令到上下文

3. **执行阶段（Execution）**：根据需要动态加载场景特定的规格文件：
   - Bank 场景 → 加载 `references/scene_BANK_spec.md`
   - Market 场景 → 加载 `references/scene_Market_spec.md`
   - Telecom 场景 → 加载 `references/scene_Telecom_spec.md`

### 标准化的 RCA 流程

该技能提供一套标准的微服务故障根因分析工作流程，适用于三种不同的业务场景：

```
问题分析 → 场景识别 → 预处理 → 异常检测 → 故障识别 → 根因定位
```

## 支持的场景

### 1. Bank（银行平台）
- 架构：传统 Web 应用架构
- 组件：Apache, Tomcat, MySQL, Redis, JVM
- 数据类型：metric_app, metric_container, trace_span, log_service

### 2. Market（电商平台）
- 架构：Kubernetes 云原生架构，支持故障转移
- 组件：多副本 Pod，分布式服务网格
- 数据类型：metric_container, metric_service, metric_node, metric_runtime, metric_mesh, trace_span, log_proxy, log_service

### 3. Telecom（电信数据库系统）
- 架构：三层架构（OS → Docker → DB）
- 组件：计算节点、容器、数据库实例
- 数据类型：metric_app, metric_container, metric_middleware, metric_node, metric_service, trace_span（无日志数据）

## 使用方法

### 激活条件

当用户请求以下类型的任务时激活此技能：
- 故障诊断：识别服务故障或异常的根因
- 性能分析：调查性能下降、延迟增加或成功率降低
- 故障排查：调试微服务系统问题（需要提供时间窗口）
- 根因定位：查找导致系统故障的组件

### 工作流程

1. **场景识别**：根据问题描述识别目标系统（Bank/Market/Telecom）

2. **加载场景规格**：动态加载对应的场景规格文件

3. **执行 RCA 流程**：
   - **预处理**：聚合 KPI、计算全局阈值、过滤时间窗口数据
   - **异常检测**：识别超过阈值的数据点
   - **故障识别**：定位连续异常序列
   - **根因定位**：确定根本原因组件和原因

4. **输出报告**：提供简洁的根因报告

## 关键原则

### 应该做的

- 使用 KPI 的完整序列计算全局阈值（在时间过滤之前）
- 优先进行指标分析，然后再进行追踪和日志分析
- 使用追踪分析识别多组件故障中的最下游故障组件
- 基于阈值突破百分比过滤噪声和误报
- 时区：所有分析使用 **UTC+8**

### 不应该做的

- 在按时间窗口过滤后计算阈值
- 假设未知的变量 - 确保所有数据都已加载并可用
- 使用 matplotlib/seaborn 进行可视化（仅基于文本的结果）
- 将数据保存到磁盘文件 - 缓存在内存变量中
- 错误地将健康下游服务标识为根因
- 只关注错误日志 - 信息日志包含关键操作数据

## 辅助工具

`scripts/rca_helper.py` 提供以下辅助函数：

- `calculate_global_threshold()` - 计算全局阈值
- `detect_anomalies()` - 检测异常
- `identify_faults()` - 识别故障序列
- `filter_by_time()` - 按时间窗口过滤
- `aggregate_kpi_by_component()` - 按组件聚合 KPI

## 引用来源

此技能基于以下 Open RCA 数据集场景实现：

- **Bank 微服务数据集**：银行平台故障场景
- **Market 微服务数据集**：电商平台故障场景  
- **Telecom 微服务数据集**：电信系统故障场景

原始 Agent 实现：`derisk_ext/agent/agents/open_rca/`

## 许可证

本技能遵循 DeRisk 项目的许可证条款。