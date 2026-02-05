import React, { FC, useEffect } from 'react';
import { CheckCircleOutlined, ExclamationCircleOutlined, LoadingOutlined, FolderOutlined, FileOutlined } from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { codeComponents, markdownPlugins } from '../../config';
import { ee as workWindowEmitter } from '../../../../../utils/event-emitter';
import { FolderList, FolderItemStyled, FolderContainer } from './style';

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
  items?: FolderItem[];
  avatar?: string;
}

export interface VisAgentFolderData {
  uid?: string;
  items?: FolderItem[];
  dynamic?: boolean;
  running_agent?: string | string[];
  type?: string;
  agent_role?: string;
  agent_name?: string;
  description?: string;
  avatar?: string;
  explorer?: string;
}

interface AgentFolderNodeProps {
  data: FolderItem;
  onItemClick: (uid: string) => void;
  level?: number;
}

const StatusIcon: FC<{ status?: FolderItem['status'] }> = ({ status }) => {
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

// 递归渲染 Folder 节点
const AgentFolderNode: FC<AgentFolderNodeProps> = ({ data, onItemClick, level = 0 }) => {
  const isFolder = data.item_type === 'folder' || (data.items && data.items.length > 0);
  
  return (
    <div style={{ marginLeft: level * 16 }}>
      <FolderItemStyled
        key={data.uid}
        role="button"
        tabIndex={0}
        onClick={() => onItemClick(data.uid)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onItemClick(data.uid);
          }
        }}
      >
        {isFolder ? (
          <FolderOutlined style={{ marginRight: 6, color: '#1677ff' }} />
        ) : (
          <StatusIcon status={data.status} />
        )}
        <span className="title">{data.title ?? data.uid}</span>
      </FolderItemStyled>
      
      {/* 递归渲染子 items */}
      {data.items && data.items.map((item) => (
        <AgentFolderNode 
          key={item.uid} 
          data={item} 
          onItemClick={onItemClick} 
          level={level + 1}
        />
      ))}
    </div>
  );
};

const VisAgentFolder: FC<{ data: VisAgentFolderData }> = ({ data }) => {
  const items = data?.items ?? [];
  const explorer = data?.explorer;

  useEffect(() => {
    items.forEach((item) => {
      workWindowEmitter.emit('addTask', { folderItem: item });
    });
  }, [items.length]);

  const handleClick = (uid: string) => {
    workWindowEmitter.emit('clickFolder', { uid });
  };

  if (explorer) {
    // 直接解析 explorer markdown 中的 JSON 数据
    // explorer 格式: ```d-agent-folder\n{json}\n```
    try {
      const jsonMatch = explorer.match(/```d-agent-folder\n([\s\S]*?)\n```/);
      if (jsonMatch) {
        const folderData = JSON.parse(jsonMatch[1]) as FolderItem;
        // 递归渲染 folder 结构
        return (
          <FolderContainer>
            <AgentFolderNode data={folderData} onItemClick={handleClick} />
          </FolderContainer>
        );
      }
    } catch (e) {
      console.error('Failed to parse explorer:', e);
    }
    // 解析失败时回退到 GPTVis
    return (
      <FolderContainer>
        {/* @ts-ignore */}
        <GPTVis components={codeComponents} {...markdownPlugins}>
          {explorer}
        </GPTVis>
      </FolderContainer>
    );
  }

  return (
    <FolderContainer>
      <FolderList>
        {items.map((item) => (
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
};

export default VisAgentFolder;
