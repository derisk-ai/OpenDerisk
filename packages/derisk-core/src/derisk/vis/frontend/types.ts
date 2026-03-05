/**
 * Part类型定义 - 自动生成
 * 
 * 与后端Python Pydantic模型保持同步
 * 运行: npm run generate-types 自动生成
 */

// Part状态枚举
export enum PartStatus {
  PENDING = 'pending',
  STREAMING = 'streaming',
  COMPLETED = 'completed',
  ERROR = 'error',
}

// Part类型枚举
export enum PartType {
  TEXT = 'text',
  CODE = 'code',
  TOOL_USE = 'tool_use',
  THINKING = 'thinking',
  PLAN = 'plan',
  IMAGE = 'image',
  FILE = 'file',
  INTERACTION = 'interaction',
  ERROR = 'error',
}

// 基础Part接口
export interface VisPart {
  type: PartType;
  status: PartStatus;
  uid: string;
  content: string;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  parent_uid?: string;
}

// 文本Part
export interface TextPart extends VisPart {
  type: PartType.TEXT;
  format?: 'markdown' | 'plain' | 'html';
}

// 代码Part
export interface CodePart extends VisPart {
  type: PartType.CODE;
  language?: string;
  filename?: string;
  line_numbers?: boolean;
}

// 工具使用Part
export interface ToolUsePart extends VisPart {
  type: PartType.TOOL_USE;
  tool_name: string;
  tool_args?: Record<string, any>;
  tool_result?: string;
  tool_error?: string;
  execution_time?: number;
}

// 思考Part
export interface ThinkingPart extends VisPart {
  type: PartType.THINKING;
  expand?: boolean;
  think_link?: string;
}

// 计划Part
export interface PlanPart extends VisPart {
  type: PartType.PLAN;
  title?: string;
  items?: PlanItem[];
  current_index?: number;
}

export interface PlanItem {
  task?: string;
  status?: 'pending' | 'working' | 'completed' | 'failed';
}

// 图片Part
export interface ImagePart extends VisPart {
  type: PartType.IMAGE;
  url: string;
  alt?: string;
  width?: number;
  height?: number;
}

// 文件Part
export interface FilePart extends VisPart {
  type: PartType.FILE;
  filename: string;
  size?: number;
  file_type?: string;
  url?: string;
}

// 交互Part
export interface InteractionPart extends VisPart {
  type: PartType.INTERACTION;
  interaction_type: 'confirm' | 'select' | 'input';
  message: string;
  options?: string[];
  default_choice?: string;
  response?: string;
}

// 错误Part
export interface ErrorPart extends VisPart {
  type: PartType.ERROR;
  error_type: string;
  stack_trace?: string;
}

// 联合类型
export type Part = 
  | TextPart 
  | CodePart 
  | ToolUsePart 
  | ThinkingPart 
  | PlanPart 
  | ImagePart 
  | FilePart 
  | InteractionPart 
  | ErrorPart;

// Part容器
export interface PartContainer {
  parts: Part[];
}

// WebSocket消息
export interface WSMessage {
  type: 'part_update' | 'event';
  conv_id: string;
  timestamp: string;
  data: Part | EventData;
}

export interface EventData {
  event_type: string;
  [key: string]: any;
}

// VIS协议数据
export interface VisData {
  uid: string;
  type: 'incr' | 'all';
  status?: PartStatus;
  content?: string;
  metadata?: Record<string, any>;
}