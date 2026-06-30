'use client';

import { Select, Spin } from 'antd';
import { useRequest } from 'ahooks';
import { useRouter, useSearchParams } from 'next/navigation';
import { apiInterceptors, listWorkspaces } from '@/client/api';
import { getUserId } from '@/utils/storage';

export function WorkspaceSwitcher() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data, loading } = useRequest(async () => {
    const [err, res] = await apiInterceptors(listWorkspaces({ user_id: Number(getUserId()) || 0 }));
    return err ? [] : res || [];
  });

  // 从 URL 查询参数推断当前空间（usePathname 不包含 query string）
  const currentCode = searchParams?.get('id') || '';

  const handleChange = (value: string) => {
    router.push(`/workspaces/detail?id=${value}`);
  };

  if (loading) return <Spin size="small" />;

  return (
    <Select
      value={currentCode || undefined}
      placeholder="切换空间"
      onChange={handleChange}
      style={{ width: '100%' }}
      showSearch
      optionFilterProp="label"
      options={(data || []).map((ws: any) => ({
        value: ws.workspace_code,
        label: ws.name,
      }))}
    />
  );
}
