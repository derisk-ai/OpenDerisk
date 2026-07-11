'use client';

import { useEffect, useMemo, useState } from 'react';
import { Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

export type TaskTabKey = 'all' | 'running' | 'awaiting' | 'done' | 'failed';

export function statusToTab(status: string | undefined): TaskTabKey {
  switch (status) {
    case 'running':
    case 'pending_trigger':
    case 'blocked':
    case 'draft':
      return 'running';
    case 'awaiting_human':
      return 'awaiting';
    case 'delivered':
    case 'closed':
      return 'done';
    case 'failed':
      return 'failed';
    default:
      return 'all';
  }
}

export function statusLabel(status: string | undefined): string {
  switch (status) {
    case 'running': return '运行中';
    case 'pending_trigger': return '等待触发';
    case 'blocked': return '阻塞';
    case 'draft': return '准备中';
    case 'awaiting_human': return '待你介入';
    case 'delivered': return '已交付';
    case 'closed': return '已关闭';
    case 'failed': return '失败';
    default: return status || '未知';
  }
}

const TAB_LABEL: Record<TaskTabKey, string> = {
  all: '全部',
  running: '运行中',
  awaiting: '待介入',
  done: '已完成',
  failed: '失败',
};

const TAB_CLASS: Record<TaskTabKey, string> = {
  all: 'ws-rail-tab--all',
  running: 'ws-rail-tab--running',
  awaiting: 'ws-rail-tab--awaiting',
  done: 'ws-rail-tab--done',
  failed: 'ws-rail-tab--failed',
};

function ElapsedTimer({ task }: { task: any }) {
  const [, force] = useState(0);
  useEffect(() => {
    if (!task?.started_at || task.status !== 'running') return;
    const t = setInterval(() => force((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [task?.started_at, task?.status]);
  if (!task?.started_at || task.status !== 'running') return <></>;
  const secs = Math.max(0, Math.floor((Date.now() - dayjs(task.started_at).valueOf()) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return <span className="ws-rail-elapsed">{`已耗时 ${m}m${String(s).padStart(2, '0')}s`}</span>;
}

export interface SceneTaskRailProps {
  tasks: any[];
  interventions: any[];
  activeTaskId?: number | null;
  disabled?: boolean;
  playbooks?: { playbook_id: number; playbook_name: string }[];
  onPreview: (item: any, kind: 'task' | 'intervention') => void;
  onEnterConversation: (taskId: number) => void;
}

export function SceneTaskRail({
  tasks,
  interventions,
  activeTaskId,
  disabled,
  playbooks,
  onPreview,
  onEnterConversation,
}: SceneTaskRailProps) {
  const [filter, setFilter] = useState('');
  const [tab, setTab] = useState<TaskTabKey>('all');

  const pbNameById = useMemo(() => {
    const m = new Map<number, string>();
    (playbooks || []).forEach((p) => m.set(p.playbook_id, p.playbook_name));
    return m;
  }, [playbooks]);

  const taskItems = useMemo(
    () => (tasks || []).map((t) => ({
      kind: 'task' as const,
      raw: t,
      updatedAt: t.gmt_modified || t.gmt_created || t.updated_at || new Date().toISOString(),
    })),
    [tasks],
  );
  const intItems = useMemo(
    () => (interventions || []).map((i) => ({
      kind: 'intervention' as const,
      raw: i,
      updatedAt: i.updated_at || i.created_at || new Date().toISOString(),
    })),
    [interventions],
  );
  const merged = useMemo(
    () => [...taskItems, ...intItems].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    ),
    [taskItems, intItems],
  );

  const counts = useMemo(() => {
    const c: Record<TaskTabKey, number> = { all: merged.length, running: 0, awaiting: 0, done: 0, failed: 0 };
    merged.forEach((it) => {
      if (it.kind === 'task') {
        if (statusToTab(it.raw.status) !== 'all') c[statusToTab(it.raw.status)] += 1;
      } else {
        c.awaiting += 1;
      }
    });
    return c;
  }, [merged]);

  const activeCount = counts.running + counts.awaiting;

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return merged.filter((it) => {
      if (it.kind === 'task') {
        if (tab !== 'all' && statusToTab(it.raw.status) !== tab) return false;
      } else {
        if (tab !== 'all' && tab !== 'awaiting') return false;
      }
      if (!q) return true;
      const t = (it.kind === 'task' ? it.raw.title : it.raw.question?.title) || `it_${it.raw.id}`;
      return t.toLowerCase().includes(q) || String(it.raw.id).includes(q);
    });
  }, [merged, tab, filter]);

  return (
    <div className="ws-scene-task-rail">
      <div className="ws-scene-task-rail__header">
        <div className="ws-rail-h-top">
          <span className="ws-rail-title">任务与介入</span>
          <span className="ws-rail-count">{`${counts.all}${activeCount ? ` · 运行中 ${activeCount}` : ''}`}</span>
        </div>
        <div className="ws-rail-tabs">
          {(Object.keys(TAB_LABEL) as TaskTabKey[]).map((k) => (
            <div
              key={k}
              className={`ws-rail-tab ${TAB_CLASS[k]}${tab === k ? ' ws-rail-tab--on' : ''}`}
              role="button"
              tabIndex={0}
              onClick={() => setTab(k)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTab(k); } }}
            >
              {TAB_LABEL[k]}
              <span className={`ws-rail-bd${counts[k] === 0 ? ' ws-rail-bd--zero' : ''}`}>{counts[k]}</span>
            </div>
          ))}
        </div>
      </div>
      <Input
        prefix={<SearchOutlined />}
        placeholder="搜索任务、介入"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="ws-scene-task-rail__search"
      />
      <div className="ws-scene-task-rail__list">
        {filtered.length === 0 && (
          <div className="ws-rail-empty">
            <div className="ws-rail-empty-t">
              {tab === 'failed' ? '没有失败的任务' : tab === 'done' ? '还没有已完成的任务' : tab === 'awaiting' ? '当前没有待介入' : '暂无任务'}
            </div>
            <div className="ws-rail-empty-h">在右侧输入发起任务,选剧本 + 写目标,Agent 会跑起来。</div>
          </div>
        )}
        {filtered.map((it) => {
          const isTask = it.kind === 'task';
          const t = it.raw;
          const pbName = isTask && t.playbook_id ? pbNameById.get(t.playbook_id) : null;
          const isActive = isTask && activeTaskId === t.id;
          return (
            <div
              key={`${it.kind}-${t.id}`}
              className={`ws-rail-card${isActive ? ' ws-rail-card--active' : ''}${!isTask ? ' ws-rail-card--int' : ''}`}
              role={disabled ? undefined : 'button'}
              tabIndex={disabled ? -1 : 0}
              aria-disabled={disabled}
              onClick={() => !disabled && onPreview(t, it.kind)}
              onKeyDown={(e) => { if (!disabled && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onPreview(t, it.kind); } }}
            >
              <div className="ws-rail-card-head">
                <span className={`ws-rail-status ws-rail-status--${t.status || (isTask ? 'draft' : 'requested')}`}>
                  <span className="ws-rail-dot" />
                  {isTask ? statusLabel(t.status) : '待响应'}
                </span>
                {pbName && <span className="ws-rail-pb">📖 {pbName}</span>}
                {isTask && <ElapsedTimer task={t} />}
              </div>
              <div className="ws-rail-ttl">{isTask ? (t.title || `task_${t.id}`) : (t.question?.title || `intervention_${t.id}`)}</div>
              <div className="ws-rail-foot">
                <span className="ws-rail-src">{isTask ? `${t.triggered_by || '手动'} · ${t.type || 'adhoc'}` : '人工 · 介入'}</span>
                <span className="ws-rail-tm">{dayjs(it.updatedAt).format('MM-DD HH:mm')}</span>
                {isTask && (
                  <span
                    className="ws-rail-enter"
                    role="button"
                    tabIndex={disabled ? -1 : 0}
                    onClick={(e) => { e.stopPropagation(); if (!disabled) onEnterConversation(t.id); }}
                    onKeyDown={(e) => { if (!disabled && e.key === 'Enter') { e.preventDefault(); onEnterConversation(t.id); } }}
                  >
                    进入对话 →
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}