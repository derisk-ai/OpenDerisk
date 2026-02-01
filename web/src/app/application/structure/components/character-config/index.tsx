import PromptEditor from '@/components/PromptEditor';
import { AppContext } from '@/contexts';
import { CaretLeftOutlined, ThunderboltOutlined, UserOutlined } from '@ant-design/icons';
import { useDebounceFn } from 'ahooks';
import { Tabs } from 'antd';
import { debounce } from 'lodash';
import { useContext, useMemo, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

function CharacterConfig() {
  const { t } = useTranslation();
  const { collapsed, setCollapsed, appInfo, fetchUpdateApp } = useContext(AppContext);

  const { system_prompt_template = '', user_prompt_template = '' } = appInfo || {};

  // 本地状态管理用户输入，避免接口返回数据覆盖导致的闪动
  const [localSystemPrompt, setLocalSystemPrompt] = useState('');
  const [localUserPrompt, setLocalUserPrompt] = useState('');

  // 初始化本地状态
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
      setLocalSystemPrompt(template); // 立即更新本地状态
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
      setLocalUserPrompt(template); // 立即更新本地状态
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
        <span className="flex items-center gap-2">
          <ThunderboltOutlined />
          {t('character_config_system_prompt')}
        </span>
      ),
      children: (
        <div className="flex h-full w-full overflow-hidden">
            <PromptEditor 
                value={systemPrompt} 
                onChange={handleSysPromptChange} 
                showPreview={true}
            />
        </div>
      )
    },
    {
      key: 'user',
      label: (
        <span className="flex items-center gap-2">
          <UserOutlined />
          {t('character_config_user_prompt')}
        </span>
      ),
      children: (
        <div className="flex h-full w-full overflow-hidden">
             <PromptEditor 
                value={userPrompt} 
                onChange={handleUserPromptChange} 
                showPreview={true}
            />
        </div>
      )
    },
  ];

  return (
    <div className='flex flex-col h-full bg-white relative'>
      <div className='p-4 border-b border-gray-100 flex items-center justify-between'>
        <h2 className='font-semibold text-lg text-gray-800'>{t('character_config_title')}</h2>
      </div>
      
      <div className='flex-1 overflow-hidden flex flex-col'>
        <Tabs 
          items={items} 
          defaultActiveKey="system" 
          type="card"
          className="h-full flex flex-col [&_.ant-tabs-content]:flex-1 [&_.ant-tabs-content]:h-full [&_.ant-tabs-nav]:mb-0 [&_.ant-tabs-nav]:px-4 [&_.ant-tabs-nav]:pt-4"
          tabBarStyle={{ borderBottom: '1px solid #f0f0f0' }}
        />
      </div>

      <button
        onClick={() => setCollapsed(!collapsed)}
        className='absolute top-1/2 right-[-14px] bg-white transform -translate-y-1/2 w-7 h-14 rounded-r-xl border border-l-0 border-gray-200 shadow-sm flex items-center justify-center text-gray-400 hover:text-blue-500 hover:bg-gray-50 transition-all z-10'
      >
        <CaretLeftOutlined />
      </button>
    </div>
  );
}

export default CharacterConfig;
