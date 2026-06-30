'use client';

import { apiInterceptors, listWorkspaces, listInterventions } from '@/client/api';
import { Card, Empty, Spin, Tag, List } from 'antd';
import { useRequest } from 'ahooks';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import { getUserId } from '@/utils/storage';

export default function MyViewPage() {
  const router = useRouter();
  const { t } = useTranslation();

  const { data: workspaces, loading } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listWorkspaces({ user_id: Number(getUserId()) || 0 }));
    return err ? [] : res || [];
  });

  // Aggregate requested interventions across all workspaces
  const { data: myInterventions } = useRequest(async () => {
    if (!workspaces || workspaces.length === 0) return [];
    const all: any[] = [];
    for (const ws of workspaces) {
      const [err, res] = await apiInterceptors(listInterventions({
        workspace_id: ws.id, status: 'requested', limit: 20,
      }));
      if (!err && res) {
        for (const iv of res) {
          all.push({ ...iv, workspace_code: ws.workspace_code, workspace_name: ws.name });
        }
      }
    }
    return all;
  }, { refreshDeps: [workspaces?.length] });

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-semibold">{t('me.title') || 'My View'}</h1>

      <Card title={t('me.pending_reviews') || 'Pending Reviews (Across Workspaces)'} >
        {loading ? <div className="flex justify-center py-8"><Spin /></div> : (
          <List
            size="small"
            dataSource={myInterventions || []}
            locale={{ emptyText: <Empty description="No pending reviews" /> }}
            renderItem={(item: any) => (
              <List.Item>
                <Link href={`/workspaces/detail/interventions?id=${item.workspace_code}`} className="block w-full">
                  <div className="flex items-center gap-3">
                    <Tag color="orange">review</Tag>
                    <span className="font-medium">Task #{item.task_id}</span>
                    <span className="text-gray-400 text-xs">in {item.workspace_name}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Requested by: {item.requested_by} · {item.requested_at}
                  </div>
                </Link>
              </List.Item>
            )}
          />
        )}
      </Card>

      <Card title={t('me.my_workspaces') || 'My Workspaces'}>
        {loading ? <div className="flex justify-center py-8"><Spin /></div> : (
          <List
            size="small"
            dataSource={workspaces || []}
            locale={{ emptyText: <Empty description="No workspaces" /> }}
            renderItem={(ws: any) => (
              <List.Item>
                <Link href={`/workspaces/detail?id=${ws.workspace_code}`} className="block w-full">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-medium">{ws.name}</span>
                      <Tag className="ml-2" color="blue">{ws.scenario_type || ws.type}</Tag>
                    </div>
                    <span className="text-xs text-gray-400">{ws.member_count} members</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{ws.description}</div>
                </Link>
              </List.Item>
            )}
          />
        )}
      </Card>
    </div>
  );
}
