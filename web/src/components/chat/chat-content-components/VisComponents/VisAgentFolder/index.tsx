import React, { FC, useEffect } from 'react';
import { CheckCircleOutlined, ExclamationCircleOutlined, LoadingOutlined } from '@ant-design/icons';
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
