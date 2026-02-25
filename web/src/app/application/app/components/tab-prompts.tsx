'use client';
import PromptEditor from '@/components/PromptEditor';
import { AppContext } from '@/contexts';
import { getAgentDefaultPrompt } from '@/client/api/app';
import { ThunderboltOutlined, UserOutlined, ReloadOutlined } from '@ant-design/icons';
import { useDebounceFn, useRequest } from 'ahooks';
import { Tabs, Button, message } from 'antd';
import { debounce } from 'lodash';
import { useContext, useMemo, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

export default function TabPrompts() {
  const { t } = useTranslation();
  const { appInfo, fetchUpdateApp } = useContext(AppContext);
  const { system_prompt_template = '', user_prompt_template = '' } = appInfo || {};
  const [localSystemPrompt, setLocalSystemPrompt] = useState('');
  const [localUserPrompt, setLocalUserPrompt] = useState('');
  const agentName = appInfo?.agent || '';

  const { run: fetchDefaultPrompts, loading: loadingDefaultPrompts } = useRequest(
    async (promptType: 'system' | 'user') => {
      if (!agentName) {
        message.warning(t('baseinfo_select_agent_type'));
        return null;
      }
      const language = appInfo?.language || 'en';
      try {
        const res = await getAgentDefaultPrompt(agentName, language);
        if (res.data?.data) return res.data.data;
        return null;
      } catch {
        message.error(t('application_update_failed'));
        return null;
      }
    },
    {
      manual: true,
      onSuccess: (data, params) => {
        const promptType = params[0];
        if (data) {
          if (promptType === 'system') {
            setLocalSystemPrompt(data.system_prompt_template);
            fetchUpdateApp({ ...appInfo, system_prompt_template: data.system_prompt_template });
            message.success(t('update_success'));
          } else {
            setLocalUserPrompt(data.user_prompt_template);
            fetchUpdateApp({ ...appInfo, user_prompt_template: data.user_prompt_template });
            message.success(t('update_success'));
          }
        }
      },
    },
  );

  useEffect(() => {
    if (system_prompt_template && !localSystemPrompt) setLocalSystemPrompt(system_prompt_template);
    if (user_prompt_template && !localUserPrompt) setLocalUserPrompt(user_prompt_template);
  }, [system_prompt_template, user_prompt_template, localSystemPrompt, localUserPrompt]);

  const { run: updateSysPrompt } = useDebounceFn(
    (template: string) => {
      setLocalSystemPrompt(template);
      fetchUpdateApp({ ...appInfo, system_prompt_template: template });
    },
    { wait: 500 },
  );

  const { run: updateUserPrompt } = useDebounceFn(
    (template: string) => {
      setLocalUserPrompt(template);
      fetchUpdateApp({ ...appInfo, user_prompt_template: template });
    },
    { wait: 500 },
  );

  const handleSysPromptChange = debounce((temp: string) => updateSysPrompt(temp), 800);
  const handleUserPromptChange = debounce((temp: string) => updateUserPrompt(temp), 800);

  const systemPrompt = useMemo(() => localSystemPrompt || system_prompt_template || '', [localSystemPrompt, system_prompt_template]);
  const userPrompt = useMemo(() => localUserPrompt || user_prompt_template || '', [localUserPrompt, user_prompt_template]);

  const items = [
    {
      key: 'system',
      label: (
        <span className="flex items-center gap-2 px-2 py-1">
          <ThunderboltOutlined className="text-amber-500" />
          <span className="font-medium">{t('character_config_system_prompt')}</span>
        </span>
      ),
      children: (
        <div className="flex flex-col h-full w-full">
          <div className="flex items-center justify-end px-4 py-2.5 border-b border-gray-100/40">
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              loading={loadingDefaultPrompts}
              onClick={() => fetchDefaultPrompts('system')}
              className="text-gray-400 hover:text-amber-600 hover:bg-amber-50/60 text-xs rounded-lg h-7 px-2.5 font-medium transition-all duration-200"
            >
              {t('Reset')}
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto">
            <PromptEditor value={systemPrompt} onChange={handleSysPromptChange} showPreview={true} />
          </div>
        </div>
      ),
    },
    {
      key: 'user',
      label: (
        <span className="flex items-center gap-2 px-2 py-1">
          <UserOutlined className="text-blue-500" />
          <span className="font-medium">{t('character_config_user_prompt')}</span>
        </span>
      ),
      children: (
        <div className="flex flex-col h-full w-full">
          <div className="flex items-center justify-end px-4 py-2.5 border-b border-gray-100/40">
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              loading={loadingDefaultPrompts}
              onClick={() => fetchDefaultPrompts('user')}
              className="text-gray-400 hover:text-blue-600 hover:bg-blue-50/60 text-xs rounded-lg h-7 px-2.5 font-medium transition-all duration-200"
            >
              {t('Reset')}
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto">
            <PromptEditor value={userPrompt} onChange={handleUserPromptChange} showPreview={true} />
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="flex-1 overflow-hidden flex flex-col h-full">
      <Tabs
        items={items}
        defaultActiveKey="system"
        type="line"
        className="h-full flex flex-col prompt-tabs [&_.ant-tabs-content]:flex-1 [&_.ant-tabs-content]:h-full [&_.ant-tabs-content]:overflow-hidden [&_.ant-tabs-nav]:mb-0 [&_.ant-tabs-nav]:px-5 [&_.ant-tabs-nav]:pt-3 [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tab]:!py-2.5 [&_.ant-tabs-tab]:!px-0 [&_.ant-tabs-tab]:!mr-6 [&_.ant-tabs-ink-bar]:!bg-gradient-to-r [&_.ant-tabs-ink-bar]:from-amber-500 [&_.ant-tabs-ink-bar]:to-orange-500 [&_.ant-tabs-ink-bar]:!h-[2.5px] [&_.ant-tabs-ink-bar]:!rounded-full"
        tabBarStyle={{ borderBottom: '1px solid rgba(0,0,0,0.04)', background: 'transparent' }}
      />
    </div>
  );
}
