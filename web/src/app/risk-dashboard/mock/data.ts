/** Risk Dashboard Mock Data */

// Risk levels
export type RiskLevel = 'green' | 'blue' | 'yellow' | 'red';

export interface RiskLevelInfo {
  color: string;
  bgColor: string;
  text: string;
  icon: string;
}

export const riskLevelMap: Record<RiskLevel, RiskLevelInfo> = {
  green: { color: '#52c41a', bgColor: '#f6ffed', text: '正常', icon: '🟢' },
  blue: { color: '#1890ff', bgColor: '#e6f7ff', text: '关注', icon: '🔵' },
  yellow: { color: '#faad14', bgColor: '#fffbe6', text: '警告', icon: '🟡' },
  red: { color: '#ff4d4f', bgColor: '#fff2f0', text: '危险', icon: '🔴' },
};

// Entity Types
export interface EntityType {
  id: string;
  name: string;
  description?: string;
  defaultSkillCode?: string;
  icon: string;
  entityCount?: number;
}

export const mockEntityTypes: EntityType[] = [
  { id: 'app', name: '应用', icon: 'AppstoreOutlined', defaultSkillCode: 'app-health-check', description: '应用服务实体' },
  { id: 'db', name: '数据库', icon: 'DatabaseOutlined', defaultSkillCode: 'db-health-check', description: '数据库实例实体' },
  { id: 'dc', name: '机房', icon: 'CloudServerOutlined', defaultSkillCode: 'dc-health-check', description: '数据中心实体' },
  { id: 'business', name: '业务', icon: 'BranchesOutlined', defaultSkillCode: 'business-health-check', description: '业务线实体' },
  { id: 'middleware', name: '中间件', icon: 'ApiOutlined', defaultSkillCode: 'middleware-health-check', description: '中间件服务实体' },
];

// Entity
export interface Entity {
  id: string;
  typeId: string;
  typeName?: string;
  name: string;
  config?: Record<string, any>;
  extraSkills?: string[];
  source?: string;
  createdAt?: string;
  updatedAt?: string;
  riskLevel?: RiskLevel;
  riskLevelText?: string;
  lastCheckAt?: string;
  summary?: string;
  subscribed?: boolean;
}

export const mockEntities: Entity[] = [
  {
    id: '1',
    typeId: 'app',
    typeName: '应用',
    name: '订单服务',
    riskLevel: 'green',
    riskLevelText: '正常',
    lastCheckAt: '2024-03-25 09:00:00',
    subscribed: true,
    config: { appId: 'order-service', cluster: 'prod-sh' },
    summary: '各项指标正常，无风险项',
    createdAt: '2024-01-01 10:00:00',
  },
  {
    id: '2',
    typeId: 'db',
    typeName: '数据库',
    name: 'MySQL-主库',
    riskLevel: 'yellow',
    riskLevelText: '警告',
    lastCheckAt: '2024-03-25 09:00:00',
    subscribed: true,
    config: { instanceId: 'mysql-master-01', region: 'shanghai' },
    summary: 'CPU使用率85%，接近告警阈值',
    createdAt: '2024-01-01 10:00:00',
  },
  {
    id: '3',
    typeId: 'app',
    typeName: '应用',
    name: '支付服务',
    riskLevel: 'blue',
    riskLevelText: '关注',
    lastCheckAt: '2024-03-25 09:00:00',
    subscribed: true,
    config: { appId: 'payment-service', cluster: 'prod-sh' },
    summary: '有慢查询需要优化',
    createdAt: '2024-01-01 10:00:00',
  },
  {
    id: '4',
    typeId: 'dc',
    typeName: '机房',
    name: '上海机房',
    riskLevel: 'green',
    riskLevelText: '正常',
    lastCheckAt: '2024-03-25 09:00:00',
    subscribed: false,
    config: { dcId: 'sh-dc-01', location: '上海' },
    summary: '机房运行正常',
    createdAt: '2024-01-01 10:00:00',
  },
  {
    id: '5',
    typeId: 'business',
    typeName: '业务',
    name: '交易业务',
    riskLevel: 'green',
    riskLevelText: '正常',
    lastCheckAt: '2024-03-25 09:00:00',
    subscribed: false,
    config: { businessId: 'trading' },
    summary: '业务整体健康',
    createdAt: '2024-01-01 10:00:00',
  },
  {
    id: '6',
    typeId: 'db',
    typeName: '数据库',
    name: 'Redis-缓存集群',
    riskLevel: 'red',
    riskLevelText: '危险',
    lastCheckAt: '2024-03-25 09:00:00',
    subscribed: false,
    config: { instanceId: 'redis-cache-01', type: 'cluster' },
    summary: '内存使用率95%，需要立即处理',
    createdAt: '2024-01-01 10:00:00',
  },
  {
    id: '7',
    typeId: 'middleware',
    typeName: '中间件',
    name: 'Kafka-消息队列',
    riskLevel: 'green',
    riskLevelText: '正常',
    lastCheckAt: '2024-03-25 09:00:00',
    subscribed: false,
    config: { clusterId: 'kafka-prod' },
    summary: '消息队列运行正常',
    createdAt: '2024-01-01 10:00:00',
  },
  {
    id: '8',
    typeId: 'app',
    typeName: '应用',
    name: '用户服务',
    riskLevel: 'green',
    riskLevelText: '正常',
    lastCheckAt: '2024-03-25 09:00:00',
    subscribed: false,
    config: { appId: 'user-service', cluster: 'prod-sh' },
    summary: '服务运行正常',
    createdAt: '2024-01-01 10:00:00',
  },
];

// Heatmap Data
export interface HeatmapDataPoint {
  date: string;
  greenCount: number;
  blueCount: number;
  yellowCount: number;
  redCount: number;
}

// Generate heatmap data for multiple years
function generateYearHeatmapData(year: number): HeatmapDataPoint[] {
  const data: HeatmapDataPoint[] = [];
  const startDate = new Date(year, 0, 1);
  const endDate = new Date(year, 11, 31);

  const currentDate = new Date(startDate);
  while (currentDate <= endDate) {
    const dateStr = currentDate.toISOString().split('T')[0];

    // Simulate some variation in risk levels
    // Weekend days have less activity
    const dayOfWeek = currentDate.getDay();
    const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;

    const greenCount = isWeekend
      ? Math.floor(Math.random() * 3)
      : Math.floor(Math.random() * 5) + 3;
    const blueCount = isWeekend
      ? Math.floor(Math.random() * 1)
      : Math.floor(Math.random() * 2);
    const yellowCount = isWeekend
      ? Math.floor(Math.random() * 1)
      : Math.floor(Math.random() * 2);
    const redCount = Math.random() > 0.95 ? 1 : 0; // Rare red events

    data.push({
      date: dateStr,
      greenCount,
      blueCount,
      yellowCount,
      redCount,
    });

    currentDate.setDate(currentDate.getDate() + 1);
  }

  return data;
}

// Generate heatmap data for current year and past 2 years
const currentYear = new Date().getFullYear();
export const mockHeatmapData: HeatmapDataPoint[] = [
  ...generateYearHeatmapData(currentYear),
  ...generateYearHeatmapData(currentYear - 1),
  ...generateYearHeatmapData(currentYear - 2),
];

// Check History
export interface CheckRecord {
  id: string;
  entityId: string;
  convId?: string;
  riskLevel: RiskLevel;
  summary?: string;
  details?: Record<string, any>;
  suggestions?: Array<{ action: string; auto: boolean }>;
  checkedAt: string;
}

export const mockCheckHistory: CheckRecord[] = [
  {
    id: '1',
    entityId: '1',
    convId: 'conv-001',
    riskLevel: 'green',
    summary: '各项指标正常，无风险项',
    checkedAt: '2024-03-25 09:00:00',
  },
  {
    id: '2',
    entityId: '1',
    convId: 'conv-002',
    riskLevel: 'yellow',
    summary: 'CPU使用率偏高，建议关注',
    suggestions: [
      { action: '检查是否有异常流量', auto: false },
      { action: '考虑扩容', auto: false },
    ],
    checkedAt: '2024-03-24 09:00:00',
  },
  {
    id: '3',
    entityId: '1',
    convId: 'conv-003',
    riskLevel: 'green',
    summary: '各项指标正常',
    checkedAt: '2024-03-23 09:00:00',
  },
  {
    id: '4',
    entityId: '1',
    convId: 'conv-004',
    riskLevel: 'green',
    summary: '各项指标正常',
    checkedAt: '2024-03-22 09:00:00',
  },
  {
    id: '5',
    entityId: '1',
    convId: 'conv-005',
    riskLevel: 'blue',
    summary: '有少量慢查询，建议优化',
    checkedAt: '2024-03-21 09:00:00',
  },
];

// Entity Relation
export interface EntityRelation {
  id: string;
  sourceEntityId: string;
  sourceEntityName?: string;
  targetEntityId: string;
  targetEntityName?: string;
  relationType: 'depends_on' | 'contains' | 'impacts';
  strength: 'strong' | 'weak';
  createdAt?: string;
}

export const mockEntityRelations: EntityRelation[] = [
  {
    id: '1',
    sourceEntityId: '1',
    sourceEntityName: '订单服务',
    targetEntityId: '2',
    targetEntityName: 'MySQL-主库',
    relationType: 'depends_on',
    strength: 'strong',
  },
  {
    id: '2',
    sourceEntityId: '1',
    sourceEntityName: '订单服务',
    targetEntityId: '4',
    targetEntityName: '上海机房',
    relationType: 'contains',
    strength: 'weak',
  },
  {
    id: '3',
    sourceEntityId: '1',
    sourceEntityName: '订单服务',
    targetEntityId: '5',
    targetEntityName: '交易业务',
    relationType: 'impacts',
    strength: 'strong',
  },
  {
    id: '4',
    sourceEntityId: '3',
    sourceEntityName: '支付服务',
    targetEntityId: '2',
    targetEntityName: 'MySQL-主库',
    relationType: 'depends_on',
    strength: 'strong',
  },
];

// User Subscription
export interface EntitySubscription {
  id: string;
  userId: string;
  entityId: string;
  entityName?: string;
  entityTypeName?: string;
  riskLevel?: RiskLevel;
  notifyLevel: 'all' | 'yellow_plus' | 'red_only';
  notifyChannels: string[];
  createdAt?: string;
}

export const mockSubscriptions: EntitySubscription[] = [
  {
    id: '1',
    userId: 'user-001',
    entityId: '1',
    entityName: '订单服务',
    entityTypeName: '应用',
    riskLevel: 'green',
    notifyLevel: 'yellow_plus',
    notifyChannels: ['dingtalk'],
    createdAt: '2024-01-15 10:00:00',
  },
  {
    id: '2',
    userId: 'user-001',
    entityId: '2',
    entityName: 'MySQL-主库',
    entityTypeName: '数据库',
    riskLevel: 'yellow',
    notifyLevel: 'all',
    notifyChannels: ['dingtalk', 'email'],
    createdAt: '2024-01-15 10:00:00',
  },
  {
    id: '3',
    userId: 'user-001',
    entityId: '3',
    entityName: '支付服务',
    entityTypeName: '应用',
    riskLevel: 'blue',
    notifyLevel: 'red_only',
    notifyChannels: ['dingtalk'],
    createdAt: '2024-01-15 10:00:00',
  },
];

// Risk Summary
export interface RiskSummary {
  greenCount: number;
  blueCount: number;
  yellowCount: number;
  redCount: number;
  totalCount: number;
}

export const mockRiskSummary: RiskSummary = {
  greenCount: 5,
  blueCount: 1,
  yellowCount: 1,
  redCount: 1,
  totalCount: 8,
};

// SKILL types and mock data
export interface Skill {
  skill_code: string;
  name: string;
  description: string;
  type: string;
}

export const mockSkills: Skill[] = [
  { skill_code: 'app-health-check', name: '应用健康检查', description: '检查应用CPU、内存、QPS等指标', type: 'builtin' },
  { skill_code: 'db-health-check', name: '数据库健康检查', description: '检查数据库连接数、慢查询、容量等', type: 'builtin' },
  { skill_code: 'dc-health-check', name: '机房健康检查', description: '检查机房电力、网络、温度等', type: 'builtin' },
  { skill_code: 'business-health-check', name: '业务健康检查', description: '检查业务核心指标和SLA', type: 'builtin' },
  { skill_code: 'middleware-health-check', name: '中间件健康检查', description: '检查中间件运行状态', type: 'builtin' },
  { skill_code: 'log-analysis', name: '日志分析', description: '分析应用日志中的异常模式', type: 'builtin' },
  { skill_code: 'slow-query-check', name: '慢查询检查', description: '检查数据库慢查询', type: 'builtin' },
  { skill_code: 'security-scan', name: '安全扫描', description: '检查安全漏洞', type: 'custom' },
  { skill_code: 'capacity-forecast', name: '容量预测', description: '预测资源容量需求', type: 'custom' },
];

// Entity SKILL configuration
export interface EntitySkillConfig {
  id: string;
  entityId: string;
  skillCode: string;
  skillName: string;
  skillType: 'default' | 'custom';  // default: 类型默认，只能禁用; custom: 用户自定义，可删除
  enabled: boolean;
  checkParams?: Record<string, any>;
  lastCheckAt?: string;
  lastRiskLevel?: RiskLevel;
}

export const mockEntitySkillConfigs: EntitySkillConfig[] = [
  // 订单服务（应用类型）的 SKILL 配置
  {
    id: 'es-1',
    entityId: '1',
    skillCode: 'app-health-check',
    skillName: '应用健康检查',
    skillType: 'default',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'green',
  },
  {
    id: 'es-2',
    entityId: '1',
    skillCode: 'log-analysis',
    skillName: '日志分析',
    skillType: 'custom',
    enabled: true,
    checkParams: { logLevel: 'error', timeRange: '1h' },
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'green',
  },
  {
    id: 'es-3',
    entityId: '1',
    skillCode: 'security-scan',
    skillName: '安全扫描',
    skillType: 'custom',
    enabled: false,
    lastCheckAt: '2024-03-24 09:00:00',
    lastRiskLevel: 'blue',
  },
  // MySQL 主库（数据库类型）的 SKILL 配置
  {
    id: 'es-4',
    entityId: '2',
    skillCode: 'db-health-check',
    skillName: '数据库健康检查',
    skillType: 'default',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'yellow',
  },
  {
    id: 'es-5',
    entityId: '2',
    skillCode: 'slow-query-check',
    skillName: '慢查询检查',
    skillType: 'custom',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'yellow',
  },
  // 支付服务（应用类型）的 SKILL 配置
  {
    id: 'es-6',
    entityId: '3',
    skillCode: 'app-health-check',
    skillName: '应用健康检查',
    skillType: 'default',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'blue',
  },
  // 上海机房（机房类型）的 SKILL 配置
  {
    id: 'es-7',
    entityId: '4',
    skillCode: 'dc-health-check',
    skillName: '机房健康检查',
    skillType: 'default',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'green',
  },
  // 交易业务（业务类型）的 SKILL 配置
  {
    id: 'es-8',
    entityId: '5',
    skillCode: 'business-health-check',
    skillName: '业务健康检查',
    skillType: 'default',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'green',
  },
  // Redis-缓存集群（数据库类型）的 SKILL 配置
  {
    id: 'es-9',
    entityId: '6',
    skillCode: 'db-health-check',
    skillName: '数据库健康检查',
    skillType: 'default',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'red',
  },
  {
    id: 'es-10',
    entityId: '6',
    skillCode: 'capacity-forecast',
    skillName: '容量预测',
    skillType: 'custom',
    enabled: true,
    checkParams: { forecastDays: 7 },
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'red',
  },
  // Kafka-消息队列（中间件类型）的 SKILL 配置
  {
    id: 'es-11',
    entityId: '7',
    skillCode: 'middleware-health-check',
    skillName: '中间件健康检查',
    skillType: 'default',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'green',
  },
  // 用户服务（应用类型）的 SKILL 配置
  {
    id: 'es-12',
    entityId: '8',
    skillCode: 'app-health-check',
    skillName: '应用健康检查',
    skillType: 'default',
    enabled: true,
    lastCheckAt: '2024-03-25 09:00:00',
    lastRiskLevel: 'green',
  },
];