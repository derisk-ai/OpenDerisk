'use client';

import React from 'react';
import { Progress, Tooltip, Badge, Space, Drawer, Button, Typography, Tag, Descriptions, Statistic, Row, Col } from 'antd';
import {
  CloudServerOutlined,
  DatabaseOutlined,
  ScissorOutlined,
  CompressOutlined,
  InfoCircleOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import type {
  ContextMetrics,
  TruncationMetrics,
  PruningMetrics,
  CompactionMetrics,
} from '@/types/context-metrics';
import { formatTokens, getUsageLevel, getUsageColor } from '@/types/context-metrics';

const { Text, Title } = Typography;

interface ContextMetricsDisplayProps {
  metrics: ContextMetrics | null;
  compact?: boolean;
  showDetails?: boolean;
}

/**
 * 上下文指标展示组件
 * 
 * 显示三层压缩的实时监控数据
 */
export const ContextMetricsDisplay: React.FC<ContextMetricsDisplayProps> = ({
  metrics,
  compact = true,
  showDetails = true,
}) => {
  const [drawerVisible, setDrawerVisible] = React.useState(false);

  if (!metrics) {
    return null;
  }

  const usageLevel = getUsageLevel(metrics.usage_ratio);
  const usageColor = getUsageColor(usageLevel);

  const renderCompactView = () => (
    <div 
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-800 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
      onClick={() => showDetails && setDrawerVisible(true)}
    >
      <CloudServerOutlined style={{ color: usageColor }} />
      <Tooltip title={`上下文使用率: ${metrics.usage_percent}`}>
        <Progress 
          percent={Math.round(metrics.usage_ratio * 100)} 
          size="small" 
          style={{ width: 60 }}
          strokeColor={usageColor}
          showInfo={false}
        />
      </Tooltip>
      <Text type="secondary" className="text-xs">
        {formatTokens(metrics.current_tokens)}/{formatTokens(metrics.context_window)}
      </Text>
      {metrics.truncation.total_count > 0 && (
        <Badge count={metrics.truncation.total_count} size="small" title="截断次数">
          <ScissorOutlined className="text-gray-400" />
        </Badge>
      )}
      {metrics.compression.total_count > 0 && (
        <Badge count={metrics.compression.total_count} size="small" title="压缩次数">
          <CompressOutlined className="text-gray-400" />
        </Badge>
      )}
      {showDetails && (
        <Button type="text" size="small" icon={<InfoCircleOutlined />} />
      )}
    </div>
  );

  const renderDetailedView = () => (
    <Drawer
      title={
        <Space>
          <BarChartOutlined />
          上下文压缩监控
        </Space>
      }
      placement="right"
      width={480}
      onClose={() => setDrawerVisible(false)}
      open={drawerVisible}
    >
      {/* 总览 */}
      <div className="mb-6">
        <Title level={5}>当前状态</Title>
        <Row gutter={16}>
          <Col span={12}>
            <Statistic
              title="上下文使用"
              value={Math.round(metrics.usage_ratio * 100)}
              suffix="%"
              valueStyle={{ color: usageColor }}
            />
          </Col>
          <Col span={12}>
            <Statistic
              title="Token 数"
              value={formatTokens(metrics.current_tokens)}
              suffix={`/ ${formatTokens(metrics.context_window)}`}
            />
          </Col>
        </Row>
        <Progress 
          percent={Math.round(metrics.usage_ratio * 100)} 
          strokeColor={usageColor}
          className="mt-2"
        />
        <Row gutter={16} className="mt-4">
          <Col span={8}>
            <Statistic title="消息数" value={metrics.message_count} />
          </Col>
          <Col span={8}>
            <Statistic title="轮次" value={metrics.round_counter} />
          </Col>
          <Col span={8}>
            <Statistic 
              title="章节" 
              value={metrics.compression.current_chapters} 
            />
          </Col>
        </Row>
      </div>

      {/* Layer 1: 截断 */}
      <div className="mb-6">
        <Title level={5}>
          <Space>
            <Tag color="blue">Layer 1</Tag>
            <ScissorOutlined />
            截断 (Truncation)
          </Space>
        </Title>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="总次数">{metrics.truncation.total_count}</Descriptions.Item>
          <Descriptions.Item label="归档文件">{metrics.truncation.total_files_archived}</Descriptions.Item>
          <Descriptions.Item label="截断字节">{formatBytes(metrics.truncation.total_bytes_truncated)}</Descriptions.Item>
          <Descriptions.Item label="截断行数">{metrics.truncation.total_lines_truncated}</Descriptions.Item>
        </Descriptions>
        {metrics.truncation.last_tool_name && (
          <Text type="secondary" className="text-xs">
            最近: {metrics.truncation.last_tool_name} ({formatBytes(metrics.truncation.last_original_size)} → {formatBytes(metrics.truncation.last_truncated_size)})
          </Text>
        )}
      </div>

      {/* Layer 2: 修剪 */}
      <div className="mb-6">
        <Title level={5}>
          <Space>
            <Tag color="orange">Layer 2</Tag>
            <DatabaseOutlined />
            修剪 (Pruning)
          </Space>
        </Title>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="总次数">{metrics.pruning.total_count}</Descriptions.Item>
          <Descriptions.Item label="修剪消息">{metrics.pruning.total_messages_pruned}</Descriptions.Item>
          <Descriptions.Item label="节省 Tokens">{formatTokens(metrics.pruning.total_tokens_saved)}</Descriptions.Item>
          <Descriptions.Item label="最近触发">{metrics.pruning.last_trigger_reason || '-'}</Descriptions.Item>
        </Descriptions>
      </div>

      {/* Layer 3: 压缩 */}
      <div className="mb-6">
        <Title level={5}>
          <Space>
            <Tag color="green">Layer 3</Tag>
            <CompressOutlined />
            压缩归档 (Compaction)
          </Space>
        </Title>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="总次数">{metrics.compression.total_count}</Descriptions.Item>
          <Descriptions.Item label="归档消息">{metrics.compression.total_messages_archived}</Descriptions.Item>
          <Descriptions.Item label="节省 Tokens">{formatTokens(metrics.compression.total_tokens_saved)}</Descriptions.Item>
          <Descriptions.Item label="创建章节">{metrics.compression.total_chapters_created}</Descriptions.Item>
        </Descriptions>
        
        {metrics.compression.chapter_stats.length > 0 && (
          <div className="mt-4">
            <Text type="secondary" className="text-xs">最近章节:</Text>
            {metrics.compression.chapter_stats.slice(-3).map((chapter) => (
              <div key={chapter.index} className="text-xs mt-1 p-2 bg-gray-50 dark:bg-gray-800 rounded">
                章节 {chapter.index}: {chapter.messages} 消息, 节省 {formatTokens(chapter.tokens_saved)} tokens
              </div>
            ))}
          </div>
        )}
      </div>
    </Drawer>
  );

  return (
    <>
      {compact ? renderCompactView() : renderDetailedView()}
      {showDetails && renderDetailedView()}
    </>
  );
};

/**
 * 格式化字节数
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export default ContextMetricsDisplay;