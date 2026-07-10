'use client';

import {
  apiInterceptors, getWorkspaceInfo, listTasks, listInterventions,
  createConversation, getCurrentConversation, setCurrentConversation,
  linkConversation,
} from '@/client/api';
import { Button, Spin } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ThunderboltOutlined,
  FileTextOutlined,
  DeliveredProcedureOutlined,
  WarningOutlined,
  SettingOutlined,
  ClockCircleOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import { SceneWorkspaceShell } from './scene-workspace-shell';
import '../workspaces.css';

export default function WorkspaceDetailPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const { t } = useTranslation();
  const [convUid, setConvUid] = useState<string>('');
  const [convLoadError, setConvLoadError] = useState<string | null>(null);
  const [convLoadKey, setConvLoadKey] = useState(0);
  const [listsRefreshKey, setListsRefreshKey] = useState(0);

  const { data: ws, loading: wsLoading } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const workspaceId = ws?.id;
  const appCode = ws?.default_agent_app_code || 'main';

  useRequest(
    async () => {
      setConvLoadError(null);
      const [, current] = await apiInterceptors(getCurrentConversation(workspaceId));
      if (current?.conv_uid) {
        setConvUid(current.conv_uid);
        return;
      }
      const [, newConv] = await apiInterceptors(createConversation({}));
      if (!newConv?.conv_uid) {
        setConvLoadError('无法创建会话，请稍后重试');
        return;
      }
      await apiInterceptors(
        linkConversation({ workspace_id: workspaceId, conv_uid: newConv.conv_uid, user_id: undefined })
      );
      await apiInterceptors(setCurrentConversation(workspaceId, newConv.conv_uid));
      setConvUid(newConv.conv_uid);
    },
    {
      ready: !!workspaceId,
      refreshDeps: [convLoadKey],
      onError: (e: any) => {
        setConvLoadError(e?.message || '会话加载失败');
      },
    }
  );

  const { data: tasks } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listTasks({ workspace_id: workspaceId, limit: 50 }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId, listsRefreshKey] });

  const { data: interventions } = useRequest(async () => {
    if (!workspaceId) return [];
    const [err, res] = await apiInterceptors(listInterventions({
      workspace_id: workspaceId, status: 'requested', limit: 20,
    }));
    return err ? [] : res || [];
  }, { refreshDeps: [workspaceId, listsRefreshKey] });

  const retryLoadConv = useCallback(() => {
    setConvLoadKey((k) => k + 1);
  }, []);

  const handleRefreshLists = useCallback(() => {
    setListsRefreshKey((k) => k + 1);
  }, []);

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

  if (!workspaceId) {
    return null;
  }

  const scenario = ws.scenario_type || ws.type || 'scenario';
  const reviewCount = (interventions || []).length;

  return (
    <div className="ws-page">
      <div className="ws-page-bg" />
      <div
        className="ws-page-content ws-page-content--fluid"
        style={{ paddingTop: 16, paddingBottom: 16, height: 'calc(100vh - 32px)', display: 'flex', flexDirection: 'column', gap: 16 }}
      >
        <div className="ws-console-header">
          <div className="ws-console-header-left">
            <div className="ws-console-avatar"><AppstoreOutlined /></div>
            <div style={{ minWidth: 0 }}>
              <h2 className="ws-console-title">{ws.name}</h2>
              <div className="ws-console-sub">
                {ws.workspace_code} · {scenario}
              </div>
            </div>
          </div>
          <nav className="ws-console-nav" aria-label="Workspace navigation">
            <Link href={`/workspaces/detail/triggers?id=${workspaceCode}`} className="ws-console-nav-link">
              <ClockCircleOutlined />{t('workspaces.triggers') || 'Triggers'}
            </Link>
            <Link href={`/workspaces/detail/tasks?id=${workspaceCode}`} className="ws-console-nav-link">
              <ThunderboltOutlined />{t('workspaces.tasks') || 'Tasks'}
            </Link>
            <Link href={`/workspaces/detail/deliveries?id=${workspaceCode}`} className="ws-console-nav-link ws-console-nav-link--accent">
              <DeliveredProcedureOutlined />{t('workspaces.deliveries') || 'Delivery Space'}
            </Link>
            <Link href={`/workspaces/detail/artifacts?id=${workspaceCode}`} className="ws-console-nav-link">
              <FileTextOutlined />{t('workspaces.artifacts') || 'Artifacts'}
            </Link>
            <Link href={`/workspaces/detail/interventions?id=${workspaceCode}`} className={`ws-console-nav-link${reviewCount > 0 ? ' ws-console-nav-link--attention' : ''}`}>
              <WarningOutlined />{t('workspaces.interventions') || 'Interventions'}
              {reviewCount > 0 && <span style={{ fontWeight: 700 }}>{reviewCount}</span>}
            </Link>
            <Link href={`/workspaces/detail/settings?id=${workspaceCode}`} className="ws-console-nav-link">
              <SettingOutlined />{t('workspaces.settings') || 'Settings'}
            </Link>
          </nav>
        </div>

        <SceneWorkspaceShell
          workspace={ws}
          tasks={tasks || []}
          interventions={interventions || []}
          workspaceConvUid={convUid}
          appCode={appCode}
          onRefreshLists={handleRefreshLists}
          convLoadError={convLoadError}
          retryLoadConv={retryLoadConv}
        />
      </div>
    </div>
  );
}
