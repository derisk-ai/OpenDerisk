import Avatar from '../../avatar';
import { markdownComponents } from '../../config';
// import { windowEmitter } from '@/PortalChat';
import { DoubleRightOutlined } from '@ant-design/icons';
import { GPTVisLite } from '@antv/gpt-vis';
import { Dropdown, MenuProps, Tabs, Tooltip } from 'antd';
import { get, keyBy } from 'lodash';
import { FC, useEffect, useMemo, useRef, useState } from 'react';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
// import { PlanItem } from '../VisPlanningWindow';
import { AgentContainer, AgentContent, AgentTab, AgentTabHeader, AgentTabSmall, AgentTabsContainer } from './style';

interface RunningAgent {
  items?: any[]; // plans items
  avatar?: string; // task logo
  agent_role?: string; //agent role
  agent_name?: string; //agent name
  description?: string; //agent description
  markdown?: string; //task's content"
}

interface IProps {
  otherComponents?: any;
  data: {
    items: RunningAgent[]; //plans items
    running_agent: string | string[]; // running agent name
  };
  style?: { [key: string]: any };
}

export const VisRunningWindow: FC<IProps> = ({ otherComponents, data }) => {
  const runningAgent = useMemo(() => {
    if (Array.isArray(data.running_agent)) {
      return data.running_agent[0] || get(data.items, [0, 'agent_name'], '');
    } else {
      return data.running_agent || get(data.items, [0, 'agent_name'], '');
    }
  }, [data.running_agent]);

  const [currentAgent, setCurrentAgent] = useState<string>(runningAgent);
  const chatListContainerRef = useRef<HTMLDivElement>(null);
  const runningAgents = keyBy(data.items, 'agent_name');
  const agentsOptions: MenuProps['items'] = data.items.map((item: RunningAgent, index) => {
    return {
      key: `${index}_${item.agent_name}`,
      label: (
        <a
          onClick={() => {
            if (item.agent_name) {
              setCurrentAgent(item.agent_name);
            }
          }}
        >
          {item.agent_name === data.running_agent ? (
            <img
              src='/icons/loading.png'
              width={14}
              style={{ display: 'inline', marginRight: '4px' }}
            />
          ) : (
            <img
              src={item.avatar || '/agents/agent1.jpg'}
              width={14}
              style={{ display: 'inline', marginRight: '4px' }}
            />
          )}
          {item.agent_name}
        </a>
      ),
    };
  });

  const scrollToRunningAgent = (agentName: string) => {
    setTimeout(() => {
      const section = document.getElementById(`agentTab_${agentName}`);
      section?.scrollIntoView({ behavior: 'smooth' });
    }, 200);
  };

  useEffect(() => {
    setCurrentAgent(runningAgent);
    scrollToRunningAgent(runningAgent);
  }, [data.running_agent]);

  useEffect(() => {
    const chatListContainer = chatListContainerRef.current;
    chatListContainer?.scrollTo({
      top: chatListContainer.scrollHeight,
      behavior: 'smooth',
    });
  }, [currentAgent]);

  useEffect(() => {
    const chatListContainer = chatListContainerRef.current;
    if (chatListContainer) {
      const distanceToBottom =
        chatListContainer.scrollHeight - chatListContainer.scrollTop - chatListContainer.clientHeight;
      if (distanceToBottom <= 150) {
        chatListContainer.scrollTo({
          top: chatListContainer.scrollHeight,
          behavior: 'smooth',
        });
      }
    }
  }, [data]);

  // useEffect(() => {
  //   windowEmitter.on(
  //     'clickPlanItem',
  //     (payload: { item: PlanItem; agent: string }) => {
  //       if (payload?.item?.status === 'todo') return;
  //       if (payload?.item?.task_type === 'agent') {
  //         setCurrentAgent(payload.item.agent);
  //         scrollToRunningAgent(payload.item.agent);
  //       } else {
  //         setCurrentAgent(payload.agent);
  //         scrollToRunningAgent(payload.agent);
  //       }
  //     },
  //   );

  //   return () => {
  //     windowEmitter.removeListener('clickPlanItem');
  //   };
  // }, []);

  const containerHeight = document.querySelector('#running-window')?.getBoundingClientRect()?.height;

  const hasItems = useMemo(() => {
    const items = runningAgents?.[currentAgent].items;
    return Array.isArray(items) && items.length > 0;
  }, [runningAgents, currentAgent]);

  const [selectedItemIndex, setSelectedItemIndex] = useState<number>(0);

  useEffect(() => {
    // 只在页面第一次加载时执行
    if (hasItems) {
      const items = runningAgents?.[currentAgent]?.items;
      if (Array.isArray(items) && items.length > 0) {
        setSelectedItemIndex(items.length - 1);
      }
    }
  }, [hasItems]);

  const CoderWindow = ({ runningAgents, currentAgent, selectedItemIndex, setSelectedItemIndex }: any) => {
    return (
      // 左右布局：左侧Items Tab，右侧Markdown内容
      <div className='flex h-full'>
        {/* 左侧 Items Tab */}
        <div className='w-[150px] border-r border-gray-200 overflow-hidden [&_.ant-tabs-tab]:my-0'>
          <Tabs
            tabPosition='left'
            activeKey={String(selectedItemIndex)}
            defaultActiveKey={String(selectedItemIndex)}
            onChange={key => {
              const idx = parseInt(key);
              setSelectedItemIndex(idx);
            }}
            items={
              Array.isArray(runningAgents?.[currentAgent]?.items)
                ? runningAgents[currentAgent].items.map((item: any, index: number) => ({
                    key: index.toString(),
                    label: (
                      <Tooltip
                        title={
                          <div>
                            <div>
                              <strong>Title:</strong> {item.title || `Task ${index + 1}`}
                            </div>
                            <div>
                              <strong>Topic:</strong> {item.topic || item.description || 'No description'}
                            </div>
                            <div>
                              <strong>Status:</strong> {item.status || 'Unknown'}
                            </div>
                            <div>
                              <strong>Start Time:</strong> {item.start_time || 'Not set'}
                            </div>
                          </div>
                        }
                        placement='right'
                        styles={{ root: { maxWidth: '400px' } }}
                      >
                        <div className='w-[100px] text-left text-xs overflow-y-auto max-h-[300px] py-1'>
                          <div className='font-bold mb-1'>{item.title || `Task ${index + 1}`}</div>
                          <div className='text-gray-600 text-[11px] overflow-hidden text-ellipsis whitespace-nowrap'>
                            {item.topic || item.description || ''}
                          </div>
                          <div className='text-gray-400 text-[10px] mt-0.5'>
                            {item.status || ''} • {item.start_time || ''}
                          </div>
                        </div>
                      </Tooltip>
                    ),
                    children: null,
                  }))
                : []
            }
            style={{ overflow: 'hidden', background: '#F1F5F9 !important' }}
          />
        </div>

        {/* 右侧 Markdown 内容 */}
        <div className='flex-1 px-1 overflow-auto'>
          <GPTVisLite components={markdownComponents} rehypePlugins={[rehypeRaw]} remarkPlugins={[remarkGfm]}>
            {runningAgents[currentAgent]?.items?.[selectedItemIndex]?.markdown || '-'}
          </GPTVisLite>
        </div>
      </div>
    );
  };



  return (
    <AgentContainer style={{ height: `${containerHeight}px` }}>
      <AgentTabsContainer>
        <AgentTabHeader>
          {data.items.map(i => (
            <AgentTab
              key={i.agent_name}
              id={`agentTab_${i.agent_name}`}
              onClick={() => {
                if (i.agent_name) {
                  setCurrentAgent(i.agent_name);
                }
              }}
            >
              <AgentTabSmall
                className='tabTitle'
                style={{
                  border: currentAgent === i.agent_name ? '1px solid #1b62ff' : '1px solid #000a1a29',
                  backgroundColor: currentAgent === i.agent_name ? '#1b62ff10' : 'transparent',
                }}
              >
                {i.agent_name === data.running_agent ? (
                  <Avatar
                    src='/icons/loading.png'
                    width={25}
                  />
                ) : (
                  <Avatar
                    src={i.avatar || '/agents/default_avatar.png'}
                    width={25}
                  />
                )}
                <span style={{ marginLeft: '8px' }}>{i.agent_name}</span>
              </AgentTabSmall>
            </AgentTab>
          ))}
        </AgentTabHeader>
      </AgentTabsContainer>
      <AgentTabSmall
        style={{
          cursor: 'pointer',
          position: 'absolute',
          top: 0,
          right: 0,
        }}
      >
        <Dropdown menu={{ items: agentsOptions }}>
          <DoubleRightOutlined />
        </Dropdown>
      </AgentTabSmall>
      <AgentContent
        style={
          containerHeight
            ? {
                height: '100%',
              }
            : {}
        }
        className='AgentContent'
        ref={chatListContainerRef}
      >
        {hasItems ? <CoderWindow runningAgents={runningAgents} currentAgent={currentAgent} selectedItemIndex={selectedItemIndex} setSelectedItemIndex={setSelectedItemIndex} /> : (
          // 原逻辑：直接显示markdown内容
          <GPTVisLite components={markdownComponents} rehypePlugins={[rehypeRaw]} remarkPlugins={[remarkGfm]}>
            {runningAgents?.[currentAgent]?.markdown || '-'}
          </GPTVisLite>
        )}
      </AgentContent>
    </AgentContainer>
  );
};
