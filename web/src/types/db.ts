import { ConfigurableParams } from '@/types/common';

export type DBOption = {
  label: string;
  value: DBType;
  disabled?: boolean;
  isFileDb?: boolean;
  icon: string;
  desc?: string;
  parameters?: ConfigurableParams[];
};

export type DBType =
  | 'mysql'
  | 'duckdb'
  | 'sqlite'
  | 'mssql'
  | 'clickhouse'
  | 'oracle'
  | 'postgresql'
  | 'vertica'
  | 'db2'
  | 'access'
  | 'mongodb'
  | 'starrocks'
  | 'hbase'
  | 'redis'
  | 'cassandra'
  | 'couchbase'
  | (string & {});

export type IChatDbSchema = {
  type: string;
  id: string;
  name: string;
  label: string;
  description: string;
  params: any[];
  parameters: any[];
  comment: string;
  db_host: string;
  db_name: string;
  db_path: string;
  db_port: number;
  db_pwd: string;
  db_type: DBType;
  db_user: string;
};

export type DbListResponse = IChatDbSchema[];
export type IChatDbSupportTypeSchema = {
  db_type: DBType;
  name: string;
  params: ConfigurableParams;
  types: any[];
  label: string;
  description: string;
  parameters: any[];
};

export type DbSupportTypeResponse = IChatDbSupportTypeSchema[];

export type PostDbParams = Partial<DbListResponse[0] & { file_path: string }>;

export type ChatFeedBackSchema = {
  conv_uid: string;
  conv_index: number;
  question: string;
  knowledge_space: string;
  score: number;
  ques_type: string;
  messages: string;
};

export type PostDbRefreshParams = {
  id: number | string;
};

// ============================================================
// Database Spec & Learning Types
// ============================================================

export type LearningTaskRequest = {
  task_type?: 'full_learn' | 'incremental' | 'single_table';
  table_name?: string;
};

export type LearningTaskResponse = {
  id: number;
  datasource_id: number;
  task_type: string;
  status: 'pending' | 'running' | 'finalizing' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  total_tables: number | null;
  processed_tables: number;
  error_message: string | null;
  trigger_type: string;
  gmt_created: string | null;
  gmt_modified: string | null;
};

export type DbSpecTableEntry = {
  table_name: string;
  summary: string;
  row_count: number | null;
  column_count: number;
  group?: string;
};

export type DbSpecResponse = {
  datasource_id: number;
  db_name: string;
  db_type: string;
  table_count: number | null;
  spec_content: DbSpecTableEntry[];
  group_config: Record<string, any> | null;
  status: 'ready' | 'generating' | 'failed';
  gmt_created: string | null;
  gmt_modified: string | null;
};

export type TableSpecSummary = {
  table_name: string;
  table_comment: string | null;
  row_count: number | null;
  column_count: number;
  group_name: string | null;
};

export type TableColumnDef = {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
  comment: string | null;
  pk: boolean;
};

export type TableIndexDef = {
  name: string;
  columns: string[];
  unique: boolean;
};

export type ForeignKeyDef = {
  constrained_columns: string[];
  referred_table: string;
  referred_columns: string[];
};

export type TableSpecDetail = {
  table_name: string;
  table_comment: string | null;
  row_count: number | null;
  columns: TableColumnDef[];
  indexes: TableIndexDef[];
  foreign_keys: ForeignKeyDef[] | null;
  create_ddl: string | null;
  group_name: string | null;
  gmt_created: string | null;
  gmt_modified: string | null;
};

export type TableDataPreview = {
  columns: string[];
  first_rows: any[][];
  last_rows: any[][];
  total: number;
};

// ============================================================
// Sensitive Column Masking Types
// ============================================================

export type SensitiveColumnConfig = {
  id?: number;
  datasource_id: number;
  table_name: string;
  column_name: string;
  sensitive_type: string;
  masking_mode: string;
  confidence: number | null;
  source: 'auto' | 'manual';
  enabled: boolean;
};

export const SENSITIVE_TYPES = [
  'phone',
  'email',
  'id_card',
  'bank_card',
  'address',
  'name',
  'password',
  'token',
  'ip_address',
  'custom',
] as const;

export const MASKING_MODES = ['mask', 'token', 'none'] as const;

// ============================================================
// Batch Masking Configuration Types
// ============================================================

export type BatchMaskingConfigRequest = {
  column_names: string[];
  sensitive_type: string;
  masking_mode: string;
  ignore_case: boolean;
};

export type BatchMaskingConfigResponse = {
  total_tables_scanned: number;
  total_columns_matched: number;
  total_configs_added: number;
  matched_columns: Array<{ table: string; column: string }>;
  errors: string[];
};

export type SensitiveTypeLabel = {
  value: string;
  label: string;
  labelEn: string;
};

// 敏感类型的中文映射
export const SENSITIVE_TYPE_OPTIONS: SensitiveTypeLabel[] = [
  { value: 'phone', label: '手机号', labelEn: 'Phone' },
  { value: 'email', label: '邮箱', labelEn: 'Email' },
  { value: 'id_card', label: '身份证', labelEn: 'ID Card' },
  { value: 'bank_card', label: '银行卡', labelEn: 'Bank Card' },
  { value: 'address', label: '地址', labelEn: 'Address' },
  { value: 'name', label: '姓名', labelEn: 'Name' },
  { value: 'password', label: '密码', labelEn: 'Password' },
  { value: 'token', label: '令牌', labelEn: 'Token' },
  { value: 'ip_address', label: 'IP 地址', labelEn: 'IP Address' },
  { value: 'custom', label: '自定义', labelEn: 'Custom' },
];

// 脱敏模式的中文映射
export const MASKING_MODE_OPTIONS = [
  { value: 'mask', label: '部分掩码', labelEn: 'Partial Mask' },
  { value: 'token', label: '标记化', labelEn: 'Tokenize' },
  { value: 'none', label: '无脱敏', labelEn: 'None' },
];
