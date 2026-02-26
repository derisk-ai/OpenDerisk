/**
 * VisAgentFolder - 支持树形（renderRoleTree）与兼容扁平/explorer
 * 树形数据时与 UniChat 一致：单根 + addTask/clickFolder
 */
import React, { FC, useEffect, useMemo, useState } from 'react';
import {
  DownOutlined,
  FileTextOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { CheckCircleOutlined, ExclamationCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { codeComponents, markdownPlugins } from '../../config';
import { ee as workWindowEmitter } from '@/utils/event-emitter';
import {
  AvatarImage,
  AvatarWrapper,
  ChildrenContainer,
  FolderItemContainer,
  HeaderContent,
  IndentArea,
  RoleHeader,
  TitleText,
  FolderContainer,
  FolderList,
  FolderItemStyled,
  TreeContainer,
} from './style';

const iconUrlMap: Record<string, string> = {
  report: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*xaTaQ5rDghgAAAAALTAAAAgAeprcAQ/original',
  tool: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  blankaction: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  knowledge: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*P2sCQKUZoAUAAAAAOhAAAAgAeprcAQ/original',
  code: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*pPozSIZ_0u4AAAAAO7AAAAgAeprcAQ/original',
  deriskcodeaction: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*pPozSIZ_0u4AAAAAO7AAAAgAeprcAQ/original',
  monitor: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*F4pAT4italwAAAAANhAAAAgAeprcAQ/original',
  agent: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*b_vFSpByHFcAAAAAQBAAAAgAeprcAQ/original',
  plan: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*ibaHSahFSCoAAAAAQBAAAAgAeprcAQ/original',
  planningaction: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*ibaHSahFSCoAAAAAQBAAAAgAeprcAQ/original',
  llm: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*b_vFSpByHFcAAAAAQBAAAAgAeprcAQ/original',
  stage: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*ibaHSahFSCoAAAAAQBAAAAgAeprcAQ/original',
  task: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  hidden: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  default: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
};

const getTaskIcon = (taskType: string): string => {
  const normalizedType = String(taskType).toLowerCase();
  return iconUrlMap[normalizedType] || iconUrlMap.default;
};

export interface AgentFolderItem {
  uid: string;
  item_type?: 'folder' | 'file';
  dynamic?: boolean;
  agent_name?: string;
  description?: string;
  avatar?: string;
  vis?: string;
  path?: string;
  title?: string;
  status?: string;
  task_type?: string;
  start_time?: string;
  cost?: number;
  markdown?: string;
  items?: AgentFolderItem[];
}

export interface FolderItem {
  uid: string;
  type?: string;
  dynamic?: boolean;
  conv_id?: string;
  topic?: string;
  path_uid?: string;
  item_type?: string;
  title?: string;
  description?: string;
  status?: 'complete' | 'todo' | 'running' | 'waiting' | 'retrying' | 'failed';
  start_time?: string;
  cost?: number;
  markdown?: string;
}

export interface VisAgentFolderData {
  uid?: string;
  items?: AgentFolderItem[] | FolderItem[];
  dynamic?: boolean;
  running_agent?: string | string[];
  type?: string;
  agent_role?: string;
  agent_name?: string;
  description?: string;
  avatar?: string;
  explorer?: string;
}

const StatusIcon: FC<{ status?: string }> = ({ status }) => {
  switch (status) {
    case 'complete':
      return <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 12, marginRight: 6 }} />;
    case 'running':
    case 'retrying':
      return <LoadingOutlined style={{ color: '#1677ff', fontSize: 12, marginRight: 6 }} />;
    case 'failed':
      return <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 12, marginRight: 6 }} />;
    default:
      return <CheckCircleOutlined style={{ color: '#595959', fontSize: 12, marginRight: 6 }} />;
  }
};

function isTreeRoot(data: VisAgentFolderData | AgentFolderItem): data is AgentFolderItem {
  const d = data as AgentFolderItem;
  return Boolean(
    typeof d.item_type === 'string' ||
    (Array.isArray(d.items) && d.items.some((c) => c.item_type != null)),
  );
}

const VisAgentFolder: FC<{ data: VisAgentFolderData | AgentFolderItem }> = ({ data }) => {
  const [collapsedRoles, setCollapsedRoles] = useState<string[]>([]);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [tasks, setTasks] = useState<AgentFolderItem[]>([]);

  const rootItem: AgentFolderItem = useMemo(() => {
    const d = data as VisAgentFolderData & AgentFolderItem;
    if (isTreeRoot(data as AgentFolderItem)) return data as AgentFolderItem;
    if (d.items?.length) {
      return {
        uid: d.uid ?? 'root',
        item_type: 'folder',
        items: d.items as AgentFolderItem[],
        agent_name: d.agent_name,
        avatar: d.avatar,
        description: d.description,
      };
    }
    return { uid: 'root', item_type: 'folder', items: [], dynamic: false };
  }, [data]);

  const fullItems = useMemo(() => {
    const newItems = JSON.parse(JSON.stringify(rootItem)) as AgentFolderItem;
    tasks.forEach((task) => {
      if (task.path === newItems.uid) {
        newItems.items = [...(newItems.items || []), task];
        return;
      }
      const father = newItems.items?.find((item) => item.uid === task.path);
      if (father) father.items = [...(father.items || []), task];
    });
    return newItems;
  }, [rootItem, tasks]);

  useEffect(() => {
    const onAddTask = (payload: { folderItem: AgentFolderItem }) => {
      setTasks((prev) => {
        const exists = prev.some((item) => item.uid === payload.folderItem.uid);
        if (exists) return prev.map((item) => (item.uid === payload.folderItem.uid ? payload.folderItem : item));
        return [...prev, payload.folderItem];
      });
    };
    const onClickFolder = (payload: { uid: string }) => setSelectedTask(payload.uid);
    workWindowEmitter.on('addTask', onAddTask);
    workWindowEmitter.on('clickFolder', onClickFolder);
    return () => {
      workWindowEmitter.off('addTask', onAddTask);
      workWindowEmitter.off('clickFolder', onClickFolder);
    };
  }, []);

  const renderRoleTree = (item: AgentFolderItem) => {
    const isCollapsed = collapsedRoles.includes(item.uid);
    const hasChildren = item.item_type === 'folder';
    const isTask = item.item_type === 'file';

    return (
      <FolderItemContainer key={item.uid}>
        <RoleHeader
          $isSelected={Boolean(item.uid && item.uid === selectedTask)}
          $hasChildren={!!hasChildren}
          className={item.uid === selectedTask ? 'breathing-text' : ''}
          onClick={() => {
            if (hasChildren) {
              setCollapsedRoles((prev) =>
                isCollapsed ? prev.filter((id) => id !== item.uid) : [...prev, item.uid],
              );
            }
            if (isTask) {
              setSelectedTask(item.uid);
              workWindowEmitter.emit('clickFolder', { uid: item.uid });
            }
          }}
        >
          <HeaderContent>
            {hasChildren && (
              isCollapsed ? (
                <RightOutlined style={{ fontSize: '0.625rem', color: '#6b7280' }} />
              ) : (
                <DownOutlined style={{ fontSize: '0.625rem', color: '#6b7280' }} />
              )
            )}
            {item.avatar && !isTask && (
              <AvatarWrapper>
                <AvatarImage src={item.avatar} alt="" />
              </AvatarWrapper>
            )}
            {isTask && (
              <AvatarWrapper>
                {item.task_type ? (
                  <img
                    src={getTaskIcon(String(item.task_type))}
                    alt=""
                  />
                ) : (
                  <FileTextOutlined />
                )}
              </AvatarWrapper>
            )}
            <TitleText>{item.agent_name || item.title || item.uid}</TitleText>
          </HeaderContent>
        </RoleHeader>
        {!isCollapsed && item.items && item.items.length > 0 && (
          <ChildrenContainer>
            {item.items.map((child) => (
              <IndentArea key={child.uid}>{renderRoleTree(child)}</IndentArea>
            ))}
          </ChildrenContainer>
        )}
      </FolderItemContainer>
    );
  };

  const legacyData = data as VisAgentFolderData;
  const isLegacyFlat =
    legacyData.items?.length && !isTreeRoot(data as AgentFolderItem) && !legacyData.explorer;
  const flatItems = (legacyData.items ?? []) as FolderItem[];

  useEffect(() => {
    if (!isLegacyFlat) return;
    flatItems.forEach((item) => {
      workWindowEmitter.emit('addTask', { folderItem: item as unknown as AgentFolderItem });
    });
  }, [isLegacyFlat, flatItems.length]);

  if (legacyData.explorer && !isTreeRoot(data as AgentFolderItem)) {
    return (
      <FolderContainer>
        {/* @ts-expect-error GPTVis spread */}
        <GPTVis components={codeComponents} {...markdownPlugins}>
          {legacyData.explorer}
        </GPTVis>
      </FolderContainer>
    );
  }

  if (isLegacyFlat) {
    const handleClick = (uid: string) => workWindowEmitter.emit('clickFolder', { uid });
    return (
      <FolderContainer>
        <FolderList>
          {flatItems.map((item) => (
            <FolderItemStyled
              key={item.uid}
              role="button"
              tabIndex={0}
              onClick={() => handleClick(item.uid)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleClick(item.uid);
                }
              }}
            >
              <StatusIcon status={item.status} />
              <span className="title">{item.title ?? item.uid}</span>
            </FolderItemStyled>
          ))}
        </FolderList>
      </FolderContainer>
    );
  }

  return <TreeContainer>{renderRoleTree(fullItems)}</TreeContainer>;
};

export default VisAgentFolder;
