import { updateApp } from '@/client/api';
import PromptEditor from '@/components/PromptEditor';
import { AppContext } from '@/contexts';
import { CaretLeftOutlined } from '@ant-design/icons';
import { useDebounceFn, useRequest } from 'ahooks';
import { Collapse } from 'antd';
import { debounce } from 'lodash';
import { useContext, useMemo, useState, useEffect } from 'react';

function CharacterConfig() {
  const { collapsed, setCollapsed, appInfo, refreshAppInfo, fetchUpdateApp } = useContext(AppContext);

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
      label: '系统提示词',
      children: <PromptEditor value={systemPrompt} onChange={handleSysPromptChange} />,
    },
    {
      label: '用户提示词',
      children: <PromptEditor value={userPrompt} onChange={handleUserPromptChange} />,
    },
  ];

  return (
    <div className='flex-1 border-r-1 p-4 relative border-r-[#D9D9D9] h-full flex flex-col'>
      <div className='p-4 pt-1'>
        <h2 className='font-semibold text-[18px]'>提示词设定</h2>
      </div>
      <div className='[&_.ant-collapse-header-text]:font-bold overflow-y-auto flex-1'>
        <Collapse items={items} bordered={false} collapsible='header' defaultActiveKey={['0', '1']} />
      </div>

      <button
        onClick={() => setCollapsed(!collapsed)}
        className='absolute top-1/2 right-[-10px] bg-[#f3f5f9] transform -translate-y-1/2 px-1 pr-4 rounded-[24px] 
        w-5 h-10 border-[#D9D9D9] border-[1px]'
      >
        <CaretLeftOutlined className='w-8 h-8' onClick={() => setCollapsed(!collapsed)} />
      </button>
    </div>
  );
}

export default CharacterConfig;
