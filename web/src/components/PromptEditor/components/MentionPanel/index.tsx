// 唤起的已关联技能浮层内容
import { AppContext } from '@/contexts';
import { useContext, useEffect, useRef, useState } from 'react';
import { PlusOutlined } from '@ant-design/icons';
import { Rect } from '@codemirror/view';
import { Button, Flex, Popover, Space, Tabs, Typography } from 'antd';
import React from 'react';
import { MentionPanelWrapper } from './style';

interface MentionPanelProps {
  skillList: any[]; // 已关联技能列表
  knowledgeList: any[]; // 已关联知识列表
  agentList: any[]; // 已关联Agent列表
  variableList: any[]; // 已关联变量列表
  cursorPosition: Rect | null;
  getPopPosition: any;
  setOpen: (val: boolean) => void;
  handleChangeVar: (params: {
    arg: string;
    name: string;
    mentionType?: string;
    title?: string;
  }) => void;
  teamMode?: string;
}

interface ListItemProps {
  item: any;
  actionText: string;
  onActionClick: (item: any) => void;
  iconSrc?: string;
  type: string;
  avatar?: string;
}

interface TabContentProps {
  items: any[];
  actionText: string;
  onItemClick: (item: any) => void;
  type: string;
}

interface EmptyContentProps {
  description: string;
  buttonText: string;
  onButtonClick: () => void;
  icon: React.ReactNode;
  type?: string;
}

interface TabContentWrapperProps {
  list: any[];
  actionText: string;
  onItemClick: (item: any) => void;
  emptyProps: EmptyContentProps;
  type: string;
}

const iconMap = {
  skill:
    '/icons/tool_default.svg',
  agent:
    '/agents/agent_default.svg',
  knowledge:
    '/icons/knowledge_icon.png',
  variable:
    '/icons/variable.svg',
};

const ListItem = ({ item, actionText, onActionClick, type }: ListItemProps) => {
  return (
    <Flex
      className="content_item"
      key={item.id}
      justify="space-between"
      align="center"
      gap={4}
    >
      <div className="content_item_left">
        <img
         //  @ts-ignore
          src={item?.avatar || iconMap[type]}
          className="content_item_icon"
        />
        <Typography.Text ellipsis={{ tooltip: item.title }}>
          <span className="content_item_title">
            {/* 使用字段需要根据实际数据调整 */}
            {item.title}
          </span>
        </Typography.Text>
      </div>
      <Space className="content_item_actions">
        {type === 'variable' && (
          <Popover
            content={
              <div
                style={{
                  maxHeight: '260px',
                  maxWidth: '356px',
                  overflow: 'auto',
                }}
                className="custom-choose-modal"
                onClick={(e) => {
                  e.stopPropagation();
                }}
              >
                {item?.description || ''}
              </div>
            }
          >
            <div
              onClick={(e) => {
                e.stopPropagation();
              }}
            >
              详情
            </div>
          </Popover>
        )}

        <div className="content_item_use" onClick={() => onActionClick(item)}>
          {actionText}
        </div>
      </Space>
    </Flex>
  );
};

// TabContent组件
const TabContent = ({
  items,
  actionText,
  onItemClick,
  type,
}: TabContentProps) => {
  return (
    <div className="content_wrapper">
      {items?.map((item) => (
        <ListItem
          key={item.id}
          item={item}
          actionText={actionText}
          onActionClick={onItemClick}
          type={type}
        />
      ))}
    </div>
  );
};

// 空状态组件
const EmptyContent = ({
  description,
  buttonText,
  onButtonClick,
  icon,
  type,
}: EmptyContentProps) => (
  <div className="empty_content_wrapper">
    {icon}
    <div className="empty_description">{description}</div>
    {/* <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} /> */}
    {type !== 'variable' && (
      <Button
        style={{ marginTop: '16px' }}
        onClick={onButtonClick}
        type="primary"
        icon={<PlusOutlined />}
      >
        {buttonText}
      </Button>
    )}
  </div>
);

const TabContentWrapper = ({
  list,
  actionText,
  onItemClick,
  emptyProps,
  type,
}: TabContentWrapperProps) => {
  return list?.length > 0 ? (
    <TabContent
      items={list}
      actionText={actionText}
      onItemClick={onItemClick}
      type={type}
    />
  ) : (
    <EmptyContent {...emptyProps} />
  );
};

const MentionPanel = (props: MentionPanelProps) => {
  const {
    skillList,
    knowledgeList,
    agentList,
    variableList,
    cursorPosition,
    getPopPosition,
    setOpen,
    handleChangeVar,
    teamMode,
  } = props;

  const popRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number }>();
  const {
    setAssociationAgentModalOpen,
    setAssociationKnowledgeModalOpen,
    setAssociationSkillModalOpen,
  } = useContext(AppContext);

  const updatePosition = () => {
    const pos = getPopPosition?.(popRef, cursorPosition);
    if (pos) {
      setPosition(pos);
    }
  };

  // 监听浮窗高度变化
  useEffect(() => {
    if (popRef.current) {
      const resizeObserver = new ResizeObserver(() => {
        updatePosition(); // 高度变化时重新计算位置
      });
      resizeObserver.observe(popRef.current);
      // 清理监听器
      return () => {
        resizeObserver.disconnect();
      };
    }
  }, []);
  const tabItems = [
    {
      key: 'skill',
      label: '技能',
      children: (
        <TabContentWrapper
          list={skillList}
          actionText="使用技能"
          onItemClick={(item) => {
            // 替换变量，拼接为指定格式
            handleChangeVar({ ...item, mentionType: 'skill' });
            // 关闭浮层
            setOpen(false);
          }}
          type="skill"
          emptyProps={{
            description: '您还没有关联技能，点击按钮关联技能～',
            buttonText: '关联技能',
            onButtonClick: () => {
              // @ts-ignore
              setAssociationSkillModalOpen(true);
            },
            icon: (
              <img
                style={{ height: '174px' }}
                src={
                  '/icons/bg-skill.svg'
                }
              />
            ),
          }}
        />
      ),
    },
    {
      key: 'knowledge',
      label: '知识',
      children: (
        <TabContentWrapper
          list={knowledgeList?.map((item) => ({ ...item, title: item?.name }))}
          actionText="使用知识"
          onItemClick={(item) => {
            // 替换变量，拼接为指定格式
            handleChangeVar({ ...item, mentionType: 'knowledge' });
            // 关闭浮层
            setOpen(false);
          }}
          type="knowledge"
          emptyProps={{
            description: '您还没有关联知识，点击按钮关联知识～',
            buttonText: '关联知识',
            onButtonClick: () => {
              // @ts-ignore
              setAssociationKnowledgeModalOpen(true);
            },
            icon: (
              <img
                style={{ height: '174px' }}
                src={
                  '/icons/bg-knowledge.svg'
                }
              />
            ),
          }}
        />
      ),
    },
    {
      key: 'agent',
      label: 'Agent',
      children: (
        <TabContentWrapper
          list={agentList}
          actionText="使用Agent"
          onItemClick={(item) => {
            // 替换变量，拼接为指定格式
            handleChangeVar({ ...item, mentionType: 'agent' });
            // 关闭浮层
            setOpen(false);
          }}
          type="agent"
          emptyProps={{
            description: '您还没有关联Agent，点击按钮关联Agent～',
            buttonText: '关联Agent',
            onButtonClick: () => {
              // @ts-ignore
              setAssociationAgentModalOpen(true);
            },
            icon: (
              <img
                style={{ height: '174px' }}
                src={
                  '/icons/bg-agent.svg'
                }
              />
            ),
          }}
        />
      ),
    },
    {
      key: 'variable',
      label: '变量',
      children: (
        <TabContentWrapper
          list={variableList?.map((item) => ({ ...item, title: item?.arg }))}
          actionText="使用变量"
          onItemClick={(item) => {
            // 替换变量，拼接为指定格式
            handleChangeVar({ ...item, mentionType: 'variable' });
            // 关闭浮层
            setOpen(false);
          }}
          type="variable"
          emptyProps={{
            description: '暂无变量数据～',
            buttonText: '关联变量',
            onButtonClick: () => {},
            icon: (
              <img
                style={{ height: '174px' }}
                src={
                  '/icons/bg-variable.svg'
                }
              />
            ),
          }}
        />
      ),
    },
  ];

  return (
    <MentionPanelWrapper
      ref={popRef}
      hidden={!position}
      $position={position}
      className="custom-command-modal"
    >
      <Tabs
        items={
          teamMode !== 'single_agent'
            ? tabItems
            : tabItems.filter((item) => item.key !== 'agent')
        }
      />
    </MentionPanelWrapper>
  );
};

export default MentionPanel;
