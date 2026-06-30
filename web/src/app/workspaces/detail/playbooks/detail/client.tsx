'use client';

import { apiInterceptors, getPlaybookInfo, updatePlaybook, validatePlaybook, listPlaybookVersions, fireTrigger, createTrigger, getWorkspaceInfo } from '@/client/api';
import { Button, Card, Input, message, Spin, Tabs, Tag } from 'antd';
import { useRequest } from 'ahooks';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

const { TextArea } = Input;

export default function PlaybookEditorPage() {
  const searchParams = useSearchParams();
  const workspaceCode = searchParams?.get('id') || '';
  const playbookId = Number(searchParams?.get('playbook_id'));
  const { t } = useTranslation();
  const [dsl, setDsl] = useState('');
  const [saving, setSaving] = useState(false);
  const [firing, setFiring] = useState(false);

  const { data: ws } = useRequest(async () => {
    if (!workspaceCode) return null;
    const [err, res] = await apiInterceptors(getWorkspaceInfo(workspaceCode));
    return err ? null : res;
  }, { refreshDeps: [workspaceCode] });

  const { data: playbook, loading } = useRequest(async () => {
    if (!playbookId) return null;
    const [err, res] = await apiInterceptors(getPlaybookInfo(playbookId));
    return err ? null : res;
  }, { refreshDeps: [playbookId] });

  useEffect(() => {
    if (playbook?.declaration) {
      setDsl(JSON.stringify(playbook.declaration, null, 2));
    }
  }, [playbook]);

  const { data: versions } = useRequest(async () => {
    if (!playbookId) return [];
    const [err, res] = await apiInterceptors(listPlaybookVersions(playbookId));
    return err ? [] : res || [];
  }, { refreshDeps: [playbookId] });

  const handleSave = async () => {
    try {
      const parsed = JSON.parse(dsl);
      setSaving(true);
      const [err] = await apiInterceptors(updatePlaybook({
        id: playbookId,
        workspace_id: playbook?.workspace_id,
        name: playbook?.name,
        scenario_type: playbook?.scenario_type,
        task_type: playbook?.task_type,
        trigger: playbook?.trigger,
        declaration: parsed,
        is_active: playbook?.is_active,
      }));
      setSaving(false);
      if (err) { message.error(err.message); return; }
      message.success('Saved');
    } catch (e) {
      message.error('Invalid JSON');
    }
  };

  const handleValidate = async () => {
    try {
      const parsed = JSON.parse(dsl);
      const [err, res] = await apiInterceptors(validatePlaybook({ declaration: parsed }));
      if (err) { message.error(err.message); return; }
      message.success('Valid');
    } catch (e) {
      message.error('Invalid JSON');
    }
  };

  const handleFire = async () => {
    if (!ws?.id) return;
    setFiring(true);
    // Create a manual trigger for this playbook + fire it
    const [err1, trigRes] = await apiInterceptors(createTrigger({
      workspace_id: ws.id,
      type: 'manual',
      name: `Manual fire ${new Date().toISOString()}`,
      config: {},
      target_playbook_id: playbookId,
      is_active: true,
    }));
    if (err1 || !trigRes?.id) {
      setFiring(false);
      message.error(err1?.message || 'Failed to create trigger');
      return;
    }
    const [err2, fireRes] = await apiInterceptors(fireTrigger({
      workspace_id: ws.id,
      trigger_id: trigRes.id,
      payload: { fired_from: 'playbook_editor' },
    }));
    setFiring(false);
    if (err2) { message.error(err2.message); return; }
    message.success(`Task #${fireRes?.task_id} created`);
  };

  if (loading) return <div className="flex justify-center py-20"><Spin /></div>;
  if (!playbook) return <div className="p-6">Playbook not found</div>;

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <div>
          <Link href={`/workspaces/detail/playbooks?id=${workspaceCode}`}>
            <Button size="small">← Back</Button>
          </Link>
          <h1 className="text-xl font-semibold mt-2">{playbook.name}</h1>
          <Tag color="blue">{playbook.scenario_type}</Tag>
          <Tag>{playbook.task_type}</Tag>
          <Tag>v{playbook.current_version}</Tag>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleValidate}>{t('playbooks.validate') || 'Validate'}</Button>
          <Button type="primary" loading={saving} onClick={handleSave}>{t('save') || 'Save'}</Button>
          <Button loading={firing} onClick={handleFire}>{t('playbooks.fire') || 'Fire Task'}</Button>
        </div>
      </div>

      <Tabs
        items={[
          {
            key: 'editor',
            label: t('playbooks.editor') || 'Declaration DSL (JSON)',
            children: (
              <Card>
                <TextArea
                  className="font-mono text-xs"
                  value={dsl}
                  onChange={(e) => setDsl(e.target.value)}
                  autoSize={{ minRows: 24, maxRows: 40 }}
                />
              </Card>
            ),
          },
          {
            key: 'versions',
            label: t('playbooks.versions') || 'Versions',
            children: (
              <Card>
                <pre className="text-xs bg-gray-50 p-3 max-h-96 overflow-auto">
                  {JSON.stringify(versions || [], null, 2)}
                </pre>
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
