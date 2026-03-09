/**
 * 上下文压缩监控类型定义
 * 
 * 用于三层压缩机制的实时监控
 */

/**
 * 压缩层级枚举
 */
export type CompressionLayer = 'truncation' | 'pruning' | 'compaction';

/**
 * Layer 1: 截断指标
 */
export interface TruncationMetrics {
  total_count: number;
  total_bytes_truncated: number;
  total_bytes_original: number;
  total_lines_truncated: number;
  total_files_archived: number;
  last_tool_name: string;
  last_original_size: number;
  last_truncated_size: number;
  last_file_key: string | null;
  last_timestamp: number;
  tool_stats: Record<string, { count: number; bytes: number }>;
}

/**
 * Layer 2: 修剪指标
 */
export interface PruningMetrics {
  total_count: number;
  total_messages_pruned: number;
  total_tokens_saved: number;
  last_messages_count: number;
  last_tokens_saved: number;
  last_trigger_reason: string;
  last_usage_ratio: number;
  last_timestamp: number;
  usage_history: Array<{
    timestamp: number;
    usage_ratio: number;
    tokens: number;
    message_count: number;
  }>;
}

/**
 * Layer 3: 压缩归档指标
 */
export interface CompactionMetrics {
  total_count: number;
  total_messages_archived: number;
  total_tokens_saved: number;
  total_chapters_created: number;
  current_chapters: number;
  current_chapter_index: number;
  last_messages_archived: number;
  last_tokens_saved: number;
  last_chapter_index: number;
  last_summary_length: number;
  last_timestamp: number;
  chapter_stats: Array<{
    index: number;
    messages: number;
    tokens_saved: number;
    summary_length: number;
    key_tools: string[];
    timestamp: number;
  }>;
}

/**
 * 上下文压缩总指标
 */
export interface ContextMetrics {
  conv_id: string;
  session_id: string;
  current_tokens: number;
  context_window: number;
  usage_ratio: number;
  usage_percent: string;
  message_count: number;
  round_counter: number;
  config: Record<string, unknown>;
  truncation: TruncationMetrics;
  pruning: PruningMetrics;
  compaction: CompactionMetrics;
  created_at: number;
  updated_at: number;
  duration_seconds: number;
}

/**
 * WebSocket 推送事件类型
 */
export interface ContextMetricsEvent {
  type: 'event';
  event_type: 'context_metrics_update' | 'context_metrics_full';
  conv_id: string;
  timestamp: string;
  data: ContextMetrics;
}

/**
 * 格式化 token 数量
 */
export function formatTokens(tokens: number): string {
  if (tokens >= 1000000) {
    return `${(tokens / 1000000).toFixed(1)}M`;
  } else if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}K`;
  }
  return tokens.toString();
}

/**
 * 获取使用率等级
 */
export function getUsageLevel(usageRatio: number): 'low' | 'medium' | 'high' | 'critical' {
  if (usageRatio < 0.5) return 'low';
  if (usageRatio < 0.7) return 'medium';
  if (usageRatio < 0.85) return 'high';
  return 'critical';
}

/**
 * 获取使用率颜色
 */
export function getUsageColor(level: 'low' | 'medium' | 'high' | 'critical'): string {
  const colors = {
    low: '#52c41a',
    medium: '#faad14',
    high: '#fa8c16',
    critical: '#ff4d4f',
  };
  return colors[level];
}