'use client';

import { useMemo, useState } from 'react';
import { Button, Input, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

export interface SceneTaskRailProps {
  tasks: any[];
  interventions: any[];
  activeTaskId?: number | null;
  disabled?: boolean;
  onPreview: (item: any, kind: 'task' | 'intervention') => void;
  onEnterConversation: (taskId: number) => void;
}

interface MixedItem {
  id: number;
  kind: 'task' | 'intervention';
  title: string;
  status: string;
  updatedAt: string;
  raw: any;
}

const STATUS_COLORS: Record<string, string> = {
  running: 'blue',
  awaiting_human: 'orange',
  delivered: 'green',
  failed: 'red',
  pending_trigger: 'default',
  closed: 'default',
};

export function SceneTaskRail({
  tasks,
  interventions,
  activeTaskId,
  disabled,
  onPreview,
  onEnterConversation,
}: SceneTaskRailProps) {
  const [filter, setFilter] = useState('');

  const items = useMemo<MixedItem[]>(() => {
    const mappedTasks: MixedItem[] = (tasks || []).map((t) => ({
      id: t.id,
      kind: 'task',
      title: t.title || `task_${t.id}`,
      status: t.status || 'unknown',
      updatedAt: t.updated_at || t.created_at || new Date().toISOString(),
      raw: t,
    }));
    const mappedInterventions: MixedItem[] = (interventions || []).map((i) => ({
      id: i.id,
      kind: 'intervention',
      title: i.question?.title || `intervention_${i.id}`,
      status: i.status || 'requested',
      updatedAt: i.updated_at || i.created_at || new Date().toISOString(),
      raw: i,
    }));
    return [...mappedTasks, ...mappedInterventions].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    );
  }, [tasks, interventions]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => i.title.toLowerCase().includes(q) || String(i.id).includes(q));
  }, [items, filter]);

  return (
    <div className="ws-scene-task-rail">
      <div className="ws-scene-task-rail__header">任务与介入</div>
      <Input
        prefix={<SearchOutlined />}
        placeholder="搜索任务、介入"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="ws-scene-task-rail__search"
      />
      <div className="ws-scene-task-rail__list">
        {filtered.length === 0 && <div className="ws-scene-task-rail__empty">暂无任务或介入请求</div>}
        {filtered.map((item) => (
          <div
            key={`${item.kind}-${item.id}`}
            className={`ws-scene-task-rail__item${activeTaskId === item.id && item.kind === 'task' ? ' ws-scene-task-rail__item--active' : ''}`}
            role={disabled ? undefined : 'button'}
            tabIndex={disabled ? -1 : 0}
            aria-disabled={disabled}
            onClick={() => !disabled && onPreview(item.raw, item.kind)}
            onKeyDown={(e) => {
              if (disabled) return;
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onPreview(item.raw, item.kind);
              }
            }}
          >
            <div className="ws-scene-task-rail__item-top">
              <Tag color={STATUS_COLORS[item.status] || 'default'}>{item.status}</Tag>
              <span className="ws-scene-task-rail__time">{dayjs(item.updatedAt).format('MM-DD HH:mm')}</span>
            </div>
            <div className="ws-scene-task-rail__title">{item.title}</div>
            {item.kind === 'task' && (
              <Button
                size="small"
                type="link"
                className="ws-scene-task-rail__enter"
                disabled={disabled}
                onClick={(e) => {
                  e.stopPropagation();
                  onEnterConversation(item.id);
                }}
              >
                进入对话
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
