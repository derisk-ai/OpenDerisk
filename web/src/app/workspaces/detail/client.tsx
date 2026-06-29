'use client';

import {
  apiInterceptors, getWorkspaceInfo, listTasks, listArtifacts,
  listAssets, listInterventions, listTriggers, listPlaybooks,
  createConversation,
} from '@/client/api';
import { Button, Spin } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Lobby } from './lobby';
import { Workbench } from './workbench';
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ThunderboltOutlined,
  FileTextOutlined,
  DeliveredProcedureOutlined,
  WarningOutlined,
  TeamOutlined,
  SettingOutlined,
  ClockCircleOutlined,
  AppstoreOutlined,
  PlayCircleOutlined,
  FlagOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import '../workspaces.css';

function workspaceConvKey(workspaceCode: string) {
  return `ws_conv_${workspaceCode}`;
}

interface SignalChainProps {
  workspaceCode: string;
  triggerCount: number;
  playbookCount: number;
  reviewCount: number;
  taskCount: number;
  deliveredCount: number;
}

function SignalChain({
  workspaceCode,
  triggerCount,
  playbookCount,
  reviewCount,
  taskCount,
  deliveredCount,
}: SignalChainProps) {
  const { t } = useTranslation();
  const nodes = [
    {
      key: 'triggers',
      icon: <FlagOutlined />,
      label: t('workspaces.signal_trigger') || '触发源',
      count: triggerCount,
      href: `/workspaces/detail/triggers?id=${workspaceCode}`,
    },
    {
      key: 'playbooks',
      icon: <PlayCircleOutlined />,
      label: t('workspaces.signal_playbook') || '剧本',
      count: playbookCount,
      href: `/workspaces/detail/playbooks?id=${workspaceCode}`,
    },
    {
      key: 'interventions',
      icon: <WarningOutlined />,
      label: t('workspaces.signal_intervention') || '介入',
      count: reviewCount,
      href: `/workspaces/detail/interventions?id=${workspaceCode}`,
      attention: reviewCount > 0,
    },
    {
      key: 'tasks',
      icon: <ThunderboltOutlined />,
      label: t('workspaces.signal_task') || '任务',
      count: taskCount,
      href: `/workspaces/detail/tasks?id=${workspaceCode}`,
    },
    {
      key: 'delivery',
      icon: <DeliveredProcedureOutlined />,
      label: t('workspaces.signal_delivery') || '产出/交付',
      count: deliveredCount,
      href: `/workspaces/detail/deliveries?id=${workspaceCode}`,
    },
  ];

  return (
    <div className="ws-signal-chain" aria-label="Workspace signal chain">
      <span className="ws-signal-chain-label">{t('workspaces.signal_chain') || 'Signal Chain'}</span>
      {nodes.map((node, idx) => (
        <>
          <Link
            key={node.key}
            href={node.href}
            className={`ws-signal-node${node.attention ? ' ws-signal-node--attention' : ''}`}
          >
            <span className="ws-signal-node-icon">{node.icon}</span>
            <span className="ws-signal-node-label">{node.label}</span>
            <span className="ws-signal-node-count">{node.count}</span>
          </Link>
          {idx < nodes.length - 1 && (
            <span className="ws-signal-arrow"><ArrowRightOutlined /></span>
          )}
        </>
      ))}
    </div>
  );
}

interface TaskItem {
  id: number;
  title: string;
  status: string;
  type?: string;
}

interface ArtifactItem {
  id: number;
  title: string;
  type: string;
  task_id: number;
}

interface AssetItem {
  id: number;
  name: string;
  type: string;
}

interface InterventionItem {
  id: number;
  task_id: number;
  requested_by: string;
  type?: string;
  question?: any;
}

const STATUS_VARIANT: Record<string, string> = {
  pending_trigger: 'attention',
  running: 'running',
  awaiting_human: 'attention',
  delivered: 'success',
  blocked: 'danger',
  failed: 'danger',
  draft: 'neutral',
  closed: 'neutral',
  archived: 'neutral',
};

function statusVariant(s: string) {
  return STATUS_VARIANT[s] || 'neutral';
}

function statusLabel(s: string) {
  return (s || '').replace(/_/g, ' ');
}

export default function WorkspaceDetailPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();
  const [convUid, setConvUid] = useState<string>('');
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);

  const { data: ws, loading: wsLoading } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const workspaceId = ws?.id;
  const appCode = ws?.default_agent_app_code || 'chat_normal';

  useEffect(() => {
    if (!workspaceCode || !workspaceId) return;
    const stored = typeof window !== 'undefined' ? localStorage.getItem(workspaceConvKey(workspaceCode)) : '';
    if (stored) {
      setConvUid(stored);
      return;
    }
    createConversation({ workspace_id: workspaceId, app_code: appCode }).then((res: { data?: { data?: { conv_uid?: string } } }) => {
      const data = res?.data?.data;
      const uid = data?.conv_uid;
      if (uid) {
        localStorage.setItem(workspaceConvKey(workspaceCode), uid);
        setConvUid(uid);
      }
    }).catch(() => {
      const uid = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem(workspaceConvKey(workspaceCode), uid);
      setConvUid(uid);
    });
  }, [workspaceCode, workspaceId, appCode]);

  const { data: tasks } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listTasks({ workspace_id: workspaceId, limit: 50 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: artifacts } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listArtifacts({ workspace_id: workspaceId, limit: 5 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: assets } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listAssets({ workspace_id: workspaceId, limit: 5 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: interventions } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listInterventions({
      workspace_id: workspaceId, status: 'requested', limit: 20,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: triggers } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listTriggers({
      workspace_id: workspaceId, limit: 100,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const { data: playbooks } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listPlaybooks({
      workspace_id: workspaceId, limit: 100,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId] });

  const activeTasks = (tasks || []).filter((item: TaskItem) =>
    ['pending_trigger', 'running', 'awaiting_human', 'delivered'].includes(item.status)
  );
  const runningCount = (tasks || []).filter((i: TaskItem) => i.status === 'running').length;
  const pendingTriggerCount = (tasks || []).filter((i: TaskItem) => i.status === 'pending_trigger').length;
  const reviewCount = (interventions || []).length;
  const deliveredCount = (artifacts || []).length;
  const memoryCount = (assets || []).length;
  const triggerCount = (triggers || []).length;
  const playbookCount = (playbooks || []).length;

  if (!searchParams || wsLoading) {
    return (
      <div className="ws-page">
        <div className="ws-page-bg" />
        <div className="ws-page-content ws-page-content--fluid" style={{ display: 'flex', justifyContent: 'center', padding: '120px 24px' }}>
          <Spin size="large" />
        </div>
      </div>
    );
  }

  if (!ws) {
    return (
      <div className="ws-page">
        <div className="ws-page-bg" />
        <div className="ws-page-content ws-page-content--fluid">
          <div className="ws-empty">
            <div className="ws-empty-icon"><AppstoreOutlined /></div>
            <p className="ws-empty-title">Workspace not found</p>
            <p className="ws-empty-desc">This workspace may have been archived or you lack access.</p>
            <Link href="/workspaces"><Button>Back to workspaces</Button></Link>
          </div>
        </div>
      </div>
    );
  }

  const scenario = ws.scenario_type || ws.type || 'scenario';

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div className="ws-page-content ws-page-content--fluid" style={{ paddingTop: 16, paddingBottom: 16 }}>
        {/* Console header */}
        <div className="ws-console-header">
          <div className="ws-console-header-left">
            <div className="ws-console-avatar"><TeamOutlined /></div>
            <div style={{ minWidth: 0 }}>
              <h2 className="ws-console-title">{ws.name}</h2>
              <div className="ws-console-sub">
                {ws.workspace_code} · {scenario}
              </div>
            </div>
          </div>
          <nav className="ws-console-nav" aria-label="Workspace navigation">
            <Link
              href={`/workspaces/detail/triggers?id=${workspaceCode}`}
              className="ws-console-nav-link"
            >
              <ClockCircleOutlined />
              {t('workspaces.triggers') || 'Triggers'}
            </Link>
            <Link
              href={`/workspaces/detail/tasks?id=${workspaceCode}`}
              className="ws-console-nav-link"
            >
              <ThunderboltOutlined />
              {t('workspaces.tasks') || 'Tasks'}
            </Link>
            <Link
              href={`/workspaces/detail/deliveries?id=${workspaceCode}`}
              className="ws-console-nav-link ws-console-nav-link--accent"
            >
              <DeliveredProcedureOutlined />
              {t('workspaces.deliveries') || 'Delivery Space'}
            </Link>
            <Link
              href={`/workspaces/detail/artifacts?id=${workspaceCode}`}
              className="ws-console-nav-link"
            >
              <FileTextOutlined />
              {t('workspaces.artifacts') || 'Artifacts'}
            </Link>
            <Link
              href={`/workspaces/detail/interventions?id=${workspaceCode}`}
              className={`ws-console-nav-link${reviewCount > 0 ? ' ws-console-nav-link--attention' : ''}`}
            >
              <WarningOutlined />
              {t('workspaces.interventions') || 'Interventions'}
              {reviewCount > 0 && <span style={{ fontWeight: 700 }}>{reviewCount}</span>}
            </Link>
            <Link
              href={`/workspaces/detail/settings?id=${workspaceCode}`}
              className="ws-console-nav-link"
            >
              <SettingOutlined />
              {t('workspaces.settings') || 'Settings'}
            </Link>
          </nav>
        </div>

        {/* Signal chain — workspace pipeline */}
        <SignalChain
          workspaceCode={workspaceCode}
          triggerCount={triggerCount}
          playbookCount={playbookCount}
          reviewCount={reviewCount}
          taskCount={(tasks || []).length}
          deliveredCount={deliveredCount}
        />

        {/* Loop strip — signature */}
        <div className="ws-loop" role="status" aria-label="Workspace operational state">
          <span className="ws-loop-label">Loop</span>
          <div className={`ws-loop-stage ${pendingTriggerCount > 0 ? 'ws-loop-stage--info' : 'ws-loop-stage--muted'}`}>
            <span className="ws-loop-stage-dot" />
            <span className="ws-loop-stage-count">{pendingTriggerCount}</span>
            <span className="ws-loop-stage-label">queued</span>
          </div>
          <div className={`ws-loop-stage ${runningCount > 0 ? 'ws-loop-stage--info' : 'ws-loop-stage--muted'}`}>
            <span className="ws-loop-stage-dot" />
            <span className="ws-loop-stage-count">{runningCount}</span>
            <span className="ws-loop-stage-label">running</span>
          </div>
          <div className={`ws-loop-stage ${reviewCount > 0 ? 'ws-loop-stage--attention' : 'ws-loop-stage--muted'}`}>
            <span className="ws-loop-stage-dot" />
            <span className="ws-loop-stage-count">{reviewCount}</span>
            <span className="ws-loop-stage-label">needs review</span>
          </div>
          <div className={`ws-loop-stage ${deliveredCount > 0 ? 'ws-loop-stage--success' : 'ws-loop-stage--muted'}`}>
            <span className="ws-loop-stage-dot" />
            <span className="ws-loop-stage-count">{deliveredCount}</span>
            <span className="ws-loop-stage-label">delivered</span>
          </div>
          <div className={`ws-loop-stage ${memoryCount > 0 ? 'ws-loop-stage--success' : 'ws-loop-stage--muted'}`}>
            <span className="ws-loop-stage-dot" />
            <span className="ws-loop-stage-count">{memoryCount}</span>
            <span className="ws-loop-stage-label">in memory</span>
          </div>
        </div>

        {/* Console: lobby / workbench */}
        <div className="ws-console">
          {selectedTaskId === null ? (
            <Lobby
              workspaceId={Number(workspaceId)}
              onSelectTask={(tid) => setSelectedTaskId(tid)}
              onQuickStart={(pid) => {
                // P0 简化：跳转到 triggers 页或调 createTask
                router.push(`/workspaces/detail?id=${workspaceCode}&trigger=${pid}`);
              }}
            />
          ) : (
            <Workbench
              taskId={selectedTaskId}
              workspaceId={Number(workspaceId)}
              appCode={appCode}
              convUid={convUid || ''}
              onBack={() => setSelectedTaskId(null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}
