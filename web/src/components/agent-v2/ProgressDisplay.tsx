/**
 * 进度显示组件
 * 
 * 展示超长任务的执行进度
 */

import React from 'react';
import { Progress, Card, Tag, Typography, Space, Statistic, Row, Col } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  PauseCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import type { ProgressPhase, LongTaskStatus } from '@/types/v2';

const { Text, Title } = Typography;

interface ProgressDisplayProps {
  progress: {
    phase: ProgressPhase;
    current_step: number;
    total_steps: number;
    progress_percent: number;
    status: LongTaskStatus;
    elapsed_time: number;
    estimated_remaining: number;
    current_goal: string;
    completed_goals: number;
    total_goals: number;
    checkpoint_count: number;
  };
  compact?: boolean;
}

const phaseLabels: Record<ProgressPhase, string> = {
  initialization: '初始化',
  planning: '规划中',
  execution: '执行中',
  verification: '验证中',
  completion: '完成',
};

const statusConfig: Record<LongTaskStatus, { color: string; icon: React.ReactNode; text: string }> = {
  pending: { color: 'default', icon: <ClockCircleOutlined />, text: '等待中' },
  running: { color: 'processing', icon: <SyncOutlined spin />, text: '运行中' },
  paused: { color: 'warning', icon: <PauseCircleOutlined />, text: '已暂停' },
  completed: { color: 'success', icon: <CheckCircleOutlined />, text: '已完成' },
  failed: { color: 'error', icon: <CloseCircleOutlined />, text: '失败' },
  cancelled: { color: 'default', icon: <CloseCircleOutlined />, text: '已取消' },
};

export const ProgressDisplay: React.FC<ProgressDisplayProps> = ({ progress, compact = false }) => {
  const status = statusConfig[progress.status] || statusConfig.pending;
  
  const formatTime = (seconds: number): string => {
    if (seconds < 60) return `${Math.round(seconds)}秒`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`;
    return `${Math.round(seconds / 3600)}小时`;
  };

  return (
    <Card size="small" style={{ marginBottom: 16 }}>
      <Row gutter={[16, 16]} align="middle">
        <Col flex="auto">
          <Space size={4} align="start">
            {status.icon}
            <div>
              <Text strong>{phaseLabels[progress.phase]}</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {progress.current_goal}
              </Text>
            </div>
          </Space>
        </Col>
        <Col>
          <Tag color={status.color}>{status.text}</Tag>
        </Col>
      </Row>

      <div style={{ marginTop: 16 }}>
        <Progress 
          percent={progress.progress_percent} 
          status={progress.status === 'failed' ? 'exception' : 'active'}
          strokeColor={{
            '0%': '#108ee9',
            '100%': '#87d068',
          }}
        />
      </div>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Statistic title="当前步骤" value={`${progress.current_step}/${progress.total_steps}`} />
        </Col>
        <Col span={6}>
          <Statistic title="已用时间" value={formatTime(progress.elapsed_time)} />
        </Col>
        <Col span={6}>
          <Statistic title="预计剩余" value={formatTime(progress.estimated_remaining)} />
        </Col>
        <Col span={6}>
          <Statistic title="检查点" value={progress.checkpoint_count} />
        </Col>
      </Row>

      {!compact && (
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={12}>
            <Statistic title="目标进度" value={`${progress.completed_goals}/${progress.total_goals}`} />
          </Col>
        </Row>
      )}
    </Card>
  );
};

export default ProgressDisplay;