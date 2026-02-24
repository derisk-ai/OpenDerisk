import PromptEditor from '@/components/PromptEditor';
import { AppContext } from '@/contexts';
import { getAgentDefaultPrompt } from '@/client/api/app';
import { CaretLeftOutlined, ThunderboltOutlined, UserOutlined, CodeOutlined, ReloadOutlined } from '@ant-design/icons';
import { useDebounceFn, useRequest } from 'ahooks';
import { Tabs, Button, message } from 'antd';
import { debounce } from 'lodash';
import { useContext, useMemo, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

function CharacterConfig() {
  const { t } = useTranslation();
  const { collapsed, setCollapsed, appInfo, fetchUpdateApp } = useContext(AppContext);

  const { system_prompt_template = '', user_prompt_template = '' } = appInfo || {};

  const [localSystemPrompt, setLocalSystemPrompt] = useState('');
  const [localUserPrompt, setLocalUserPrompt] = useState('');

  const agentName = appInfo?.agent || '';

  // 获取Agent的默认提示词
  const { run: fetchDefaultPrompts, loading: loadingDefaultPrompts } = useRequest(
    async (promptType: 'system' | 'user') => {
      if (!agentName) {
        message.warning('请先选择Agent');
        return null;
      }
      const language = appInfo?.language || 'en';
      try {
        const res = await getAgentDefaultPrompt(agentName, language);
        if (res.data?.data) {
          return res.data.data;
        }
        return null;
      } catch (error) {
        message.error(`获取默认${promptType === 'system' ? '系统' : '用户'}提示词失败`);
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
            fetchUpdateApp({
              ...appInfo,
              system_prompt_template: data.system_prompt_template,
            });
            message.success('已恢复默认系统提示词');
          } else {
            setLocalUserPrompt(data.user_prompt_template);
            fetchUpdateApp({
              ...appInfo,
              user_prompt_template: data.user_prompt_template,
            });
            message.success('已恢复默认用户提示词');
          }
        }
      },
    }
  );

  useEffect(() => {
    if (system_prompt_template && !localSystemPrompt) {
      setLocalSystemPrompt(system_prompt_template);
    }
    if (user_prompt_template && !localUserPrompt) {
      setLocalUserPrompt(user_prompt_template);
    }
  }, [system_prompt_template, user_prompt_template, localSystemPrompt, localUserPrompt]);

  const { run: updateSysPrompt } = useDebounceFn(
    template => {
      setLocalSystemPrompt(template);
      fetchUpdateApp({
        ...appInfo,
        system_prompt_template: template,
      });
    },
    {
      wait: 500,
    },
  );

  const { run: updateUserPrompt } = useDebounceFn(
    template => {
      setLocalUserPrompt(template);
      fetchUpdateApp({
        ...appInfo,
        user_prompt_template: template,
      });
    },
    {
      wait: 500,
    },
  );

  const handleSysPromptChange = debounce((temp) => {
    updateSysPrompt(temp);
  }, 800);

  const handleUserPromptChange = debounce((temp) => {
    updateUserPrompt(temp);
  }, 800);

  const systemPrompt = useMemo(() => {
    return localSystemPrompt || system_prompt_template || '';
  }, [localSystemPrompt, system_prompt_template]);

  const userPrompt = useMemo(() => {
    return localUserPrompt || user_prompt_template || '';
  }, [localUserPrompt, user_prompt_template]);

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
          <div className="flex items-center justify-end px-3 py-2 border-b border-gray-100">
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              loading={loadingDefaultPrompts}
              onClick={() => fetchDefaultPrompts('system')}
              className="text-blue-500 hover:text-blue-600 hover:bg-blue-50"
            >
              恢复默认
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto">
            <PromptEditor
                value={systemPrompt}
                onChange={handleSysPromptChange}
                showPreview={true}
            />
          </div>
        </div>
      )
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
          <div className="flex items-center justify-end px-3 py-2 border-b border-gray-100">
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              loading={loadingDefaultPrompts}
              onClick={() => fetchDefaultPrompts('user')}
              className="text-blue-500 hover:text-blue-600 hover:bg-blue-50"
            >
              恢复默认
            </Button>
          </div>
          <div className="flex-1 overflow-y-auto">
            <PromptEditor
                value={userPrompt}
                onChange={handleUserPromptChange}
                showPreview={true}
            />
          </div>
        </div>
      )
    },
  ];

  return (
    <div className='flex flex-col h-full bg-white relative'>
      <div className='px-4 py-3 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-white to-gray-50'>
        <div className='flex items-center gap-2'>
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center">
            <CodeOutlined className='text-white text-sm' />
          </div>
          <h2 className='font-semibold text-base text-gray-800'>{t('character_config_title')}</h2>
        </div>
      </div>
      
      <div className='flex-1 overflow-hidden flex flex-col'>
        <Tabs
          items={items}
          defaultActiveKey="system"
          type="line"
          className="h-full flex flex-col prompt-tabs [&_.ant-tabs-content]:flex-1 [&_.ant-tabs-content]:h-full [&_.ant-tabs-content]:overflow-hidden [&_.ant-tabs-nav]:mb-0 [&_.ant-tabs-nav]:px-4 [&_.ant-tabs-nav]:pt-3 [&_.ant-tabs-tabpane]:h-full [&_.ant-tabs-tab]:!py-2 [&_.ant-tabs-tab]:!px-0 [&_.ant-tabs-tab]:!mr-6 [&_.ant-tabs-ink-bar]:!bg-gradient-to-r [&_.ant-tabs-ink-bar]:from-amber-500 [&_.ant-tabs-ink-bar]:to-orange-500 [&_.ant-tabs-ink-bar]:!h-[3px] [&_.ant-tabs-ink-bar]:!rounded-full"
          tabBarStyle={{ borderBottom: '1px solid #f0f0f0', background: 'linear-gradient(to bottom, #fafafa, #ffffff)' }}
        />
      </div>

      <button
        onClick={() => setCollapsed(!collapsed)}
        className='absolute top-1/2 -right-3 bg-white transform -translate-y-1/2 w-6 h-12 rounded-r-lg border border-l-0 border-gray-200 shadow-sm flex items-center justify-center text-gray-400 hover:text-blue-500 hover:bg-blue-50 transition-all z-10'
      >
        <CaretLeftOutlined className={`text-xs transition-transform duration-200 ${collapsed ? 'rotate-180' : ''}`} />
      </button>
    </div>
  );
}

export default CharacterConfig;
