import { EVENTS, ee } from '@/utils/event-emitter';
import { GPTVis } from '@antv/gpt-vis';
import { Tabs } from 'antd';
import { useEffect, useState } from 'react';
import markdownComponents, { markdownPlugins, preprocessLaTeX } from './config';

export type VisTabsData = {
  name: string;
  status: string;
  num: number;
  task_id: string;
  agent: string;
  avatar: string;
  markdown: string;
};

function getLastActiveKey(data: VisTabsData[]) {
  // Get the last tab as the default active key
  return data.length > 0 ? data[data.length - 1].task_id : '';
}

/**
 * Show tabs ui for llm output.
 * This tab pane is renderred with GPT-Vis.
 */
export function VisTabs({ data }: { data: VisTabsData[] }) {
  // Currently, the last tab is active by default.
  const [activeKey, setActiveKey] = useState(getLastActiveKey(data));
  const [isUserActive, setIsUserActive] = useState(false);

  useEffect(() => {
    if (!isUserActive) {
      setActiveKey(getLastActiveKey(data));
    }
  }, [data]);

  useEffect(() => {
    ee.on(EVENTS.TASK_CLICK, (data: any) => {
      setTabActiveByUser(data.taskId);
    });
  }, []);

  /**
   * When the user clicks on a tab, we set the active key to the clicked tab.
   * If the clicked tab is the last active key, we set isUserActive to false,
   * indicating that the user is not actively switching tabs.
   * Otherwise, we set isUserActive to true.
   * This is used to determine whether to reset the active tab when new data arrives.
   */
  function setTabActiveByUser(key: string) {
    console.log('setTabActiveByUser', key, getLastActiveKey(data));
    if (key === getLastActiveKey(data)) {
      setIsUserActive(false);
    } else {
      setIsUserActive(true);
    }
    setActiveKey(key);
  }

  /**
   * Organize the data structure into the format required by the Tabs component
   */
  function getTabItems() {
    return data.map((content, index) => {
      const { agent, markdown, task_id } = content;
      return {
        key: task_id,
        label: (
          <div className='flex flex-row items-center'>
            <img
              src={`/agents/${content.avatar}`}
              className='flex-0 rounded-xl w-4 h-4 inline-block mr-2'
              alt={`${agent} avatar`}
            />
            <span className='text-xs break-all'>{agent}</span>
          </div>
        ),
        children: (
          <GPTVis components={markdownComponents} {...markdownPlugins}>
            {preprocessLaTeX(markdown)}
          </GPTVis>
        ),
      };
    });
  }

  return (
    <div className='flex pl-2'>
      <Tabs className='w-full' activeKey={activeKey} items={getTabItems()} size='small' onChange={setTabActiveByUser} />
    </div>
  );
}
