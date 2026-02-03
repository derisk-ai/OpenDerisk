import React, { useMemo } from 'react';
import { VisTodoListWrap } from './style';
import { Avatar, Tooltip } from 'antd';
import {
  CheckCircleOutlined,
  LoadingOutlined,
  PauseCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';

/**
 * Todo状态图标映射
 */
const TodoStatusIconMap: Record<string, React.ReactNode> = {
  pending: <PauseCircleOutlined style={{ color: '#9ca3af', fontSize: 14 }} />,
  working: <LoadingOutlined style={{ color: '#1677ff', fontSize: 14 }} spin />,
  completed: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 14 }} />,
  failed: <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 14 }} />,
};

/**
 * Todo状态文本映射
 */
const TodoStatusTextMap: Record<string, string> = {
  pending: '待完成',
  working: '进行中',
  completed: '已完成',
  failed: '失败',
};

/**
 * Todo状态颜色映射
 */
const TodoStatusColorMap: Record<string, string> = {
  pending: '#9ca3af',
  working: '#1677ff',
  completed: '#52c41a',
  failed: '#ff4d4f',
};

/**
 * Todo项数据接口
 */
interface TodoItemData {
  id: string;
  title: string;
  description?: string;
  status: 'pending' | 'working' | 'completed' | 'failed';
  index: number;
}

/**
 * Todo组件数据接口
 */
interface ITodoListData {
  uid?: string;
  type?: string;
  agent_name?: string;
  agent_avatar?: string;
  mission?: string;
  items?: TodoItemData[];
  current_index?: number;
  expand?: boolean;
}

interface IProps {
  otherComponents?: any;
  data: ITodoListData;
}

/**
 * VisTodoList - Todo列表可视化组件
 * 用于在planning_window区域展示Agent的看板stage进度
 */
const VisTodoList: React.FC<IProps> = ({ data }) => {
  const items: TodoItemData[] = data.items || [];
  const currentIndex: number = data.current_index ?? 0;
  const agentName = data.agent_name || 'Agent';
  const agentAvatar = data.agent_avatar;
  const mission = data.mission || '';

  /**
   * 计算完成进度
   */
  const progress = useMemo(() => {
    if (items.length === 0) return { completed: 0, total: 0, percentage: 0 };
    const completed = items.filter((item) => item.status === 'completed').length;
    const total = items.length;
    const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
    return { completed, total, percentage };
  }, [items]);

  /**
   * 获取状态图标
   */
  const getStatusIcon = (status: string) => {
    return TodoStatusIconMap[status] || TodoStatusIconMap.pending;
  };

  /**
   * 获取状态文本
   */
  const getStatusText = (status: string) => {
    return TodoStatusTextMap[status] || status;
  };

  /**
   * 获取状态颜色
   */
  const getStatusColor = (status: string) => {
    return TodoStatusColorMap[status] || '#9ca3af';
  };

  /**
   * 判断是否是当前项
   */
  const isCurrentItem = (index: number): boolean => {
    return index === currentIndex;
  };

  return (
    <VisTodoListWrap>
      {/* 头部：Agent信息和进度 */}
      <div className="todolist-header">
        <div className="agent-info">
          {agentName && (
            <>
              {agentAvatar && <Avatar size={24} src={agentAvatar} alt={agentName} />}
              <span className="agent-name" title={agentName}>{agentName}</span>
            </>
          )}
        </div>
        {items.length > 0 && (
          <div className="progress-info">
            <span className="progress-text">
              {progress.completed}/{progress.total}
            </span>
            <div
              className="progress-bar"
              role="progressbar"
              aria-valuenow={progress.completed}
              aria-valuemin={0}
              aria-valuemax={progress.total}
              title={`${progress.percentage}% 完成`}
            >
              <div
                className="progress-fill"
                style={{ width: `${progress.percentage}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* 任务描述 */}
      {mission && (
        <div className="todolist-mission">
          <Tooltip title={mission}>
            <span className="mission-text">{mission}</span>
          </Tooltip>
        </div>
      )}

      {/* Todo列表 */}
      <div className="todolist-items">
        {items.map((item) => (
          <div
            key={item.id}
            className={`todo-item ${item.status} ${isCurrentItem(item.index) ? 'current' : ''}`}
          >
            {/* 序号 */}
            <div className="todo-index">{item.index + 1}</div>

            {/* 状态图标 */}
            <div className="todo-status" title={getStatusText(item.status)}>
              {getStatusIcon(item.status)}
            </div>

            {/* 内容 */}
            <div className="todo-content">
              <div
                className={`todo-title ${isCurrentItem(item.index) ? 'current-title' : ''}`}
                title={item.title}
              >
                {item.title}
              </div>
              {item.description && (
                <div className="todo-description" title={item.description}>
                  {item.description}
                </div>
              )}
            </div>

            {/* 当前标记 */}
            {isCurrentItem(item.index) && (
              <div className="todo-current-badge" title="当前阶段">
                进行中
              </div>
            )}
          </div>
        ))}

        {/* 空状态 */}
        {items.length === 0 && (
          <div className="todolist-empty">
            <span className="empty-text">暂无任务</span>
          </div>
        )}
      </div>
    </VisTodoListWrap>
  );
};

export default VisTodoList;