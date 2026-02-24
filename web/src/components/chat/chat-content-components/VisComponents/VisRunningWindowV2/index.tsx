import React, { FC, useEffect, useRef, useState, useMemo } from 'react';
import {
  CheckCircleOutlined,
  CloseOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PauseCircleOutlined,
  SyncOutlined,
  ArrowsAltOutlined,
  ShrinkOutlined,
} from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { Space, Tooltip } from 'antd';
import dayjs from 'dayjs';
import { keyBy } from 'lodash';
import {
  AgentContainer,
  AgentContent,
  FolderContainer,
  HeaderContainer,
} from './style';
import { codeComponents, type MarkdownComponent, markdownPlugins } from '../../config';
import { useElementHeight } from '../hooks/useElementHeight';
import { useElementWidth } from '../hooks/useElementWidth';
import { ee, EVENTS } from '../../../../../utils/event-emitter';

interface RunningItem {
  uid: string;
  type: string;
  dynamic: boolean;
  conv_id: string;
  topic: string;
  path_uid: string;
  item_type: string;
  title: string;
  description: string;
  status: 'complete' | 'todo' | 'running';
  start_time: string;
  cost: number;
  markdown: string;
}

interface IProps {
  otherComponents?: MarkdownComponent;
  data: {
    uid: string;
    items: RunningItem[];
    dynamic: boolean;
    running_agent: string | string[];
    type: string;
    agent_role: string;
    agent_name: string;
    description: string;
    avatar: string;
    explorer: string;
  };
  style?: React.CSSProperties;
}

const IconMap: Record<string, JSX.Element> = {
  complete: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 12 }} />,
  todo: <CheckCircleOutlined style={{ color: '#595959', fontSize: 12 }} />,
  running: <LoadingOutlined style={{ color: '#1677ff', fontSize: 12 }} />,
  waiting: <PauseCircleOutlined style={{ color: '#f5dc62', fontSize: 12 }} />,
  retrying: <SyncOutlined style={{ color: '#1677ff', fontSize: 12 }} />,
  failed: (
    <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 12 }} />
  ),
};

export const VisRunningWindowV2: FC<IProps> = ({ otherComponents, data }) => {
  const [displayUid, setDisplayUid] = useState<string>('');
  const [isFolderVisible, setIsFolderVisible] = useState<boolean>(true);
  const [isFullScreen, setIsFullScreen] = useState<boolean>(false);
  const chatListContainerRef = useRef<HTMLDivElement>(null);
  const runningContent = useMemo(() => keyBy(data.items, 'uid'), [data.items]);

  // const containerHeight = useElementHeight(
  //   `#nex-chat-detail-panel${data.uid}`,
  //   `#nex-chat-detail-panel`,
  // );
  // const containerWidth = useElementWidth('.chatContent', 'body');

  useEffect(() => {
    const onClickFolder = (payload: { uid: string }) => {
      setDisplayUid(payload.uid);
    };
    ee.on(EVENTS.CLICK_FOLDER, onClickFolder);
    return () => {
      ee.off(EVENTS.CLICK_FOLDER, onClickFolder);
    };
  }, []);

  useEffect(() => {
    data.items.forEach((item) => {
      ee.emit(EVENTS.ADD_TASK, { folderItem: item });
    });
  }, [data.items.length]);

  useEffect(() => {
    chatListContainerRef.current?.scrollTo({
      top: chatListContainerRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [
    runningContent?.[displayUid]?.markdown,
    data.items[data.items.length - 1]?.markdown,
  ]);

  const toggleFolder = () => setIsFolderVisible((prev) => !prev);

  const explorerContent = useMemo(
    () => (
      <FolderContainer
        style={{
          width: '30%',
          display: isFolderVisible ? 'block' : 'none',
        }}
      >
        {/* @ts-ignore */}
        <GPTVis
          components={{ ...codeComponents, ...(otherComponents || {}) }}
          {...markdownPlugins}
        >
          {data.explorer || '-'}
        </GPTVis>
      </FolderContainer>
    ),
    [isFolderVisible, data.explorer, otherComponents],
  );

  const mainContentMarkdown =
    runningContent[displayUid]?.markdown ||
    data.items[data.items.length - 1]?.markdown ||
    '-';

  const mainContent = useMemo(
    () => (
      <AgentContent ref={chatListContainerRef} className="AgentContent">
        {/* @ts-ignore */}
        <GPTVis
          className="whitespace-normal"
          components={{ ...codeComponents, ...(otherComponents || {}) }}
          {...markdownPlugins}
        >
          {mainContentMarkdown}
        </GPTVis>
      </AgentContent>
    ),
    [mainContentMarkdown, otherComponents],
  );

  return (
    <AgentContainer
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        // width: `${isFullScreen ? containerWidth : 0.6 * containerWidth}px`,
      }}
    >
      <HeaderContainer>
        <div className="title">
          <Tooltip title="收起/展开目录" placement="right">
            <button
              type="button"
              onClick={toggleFolder}
              style={{ marginRight: '8px' }}
            >
              {isFolderVisible ? (
                <MenuFoldOutlined />
              ) : (
                <MenuUnfoldOutlined />
              )}
            </button>
          </Tooltip>
          智能体工作空间
        </div>
        <div className="controls">
          <Tooltip
            title={isFullScreen ? '收缩工作空间' : '展开工作空间'}
          >
            <button
              type="button"
              style={{
                border: 'none',
                padding: '4px 8px',
                borderRadius: '4px',
              }}
              onClick={() => setIsFullScreen((prev) => !prev)}
            >
              {!isFullScreen ? (
                <ArrowsAltOutlined />
              ) : (
                <ShrinkOutlined />
              )}
            </button>
          </Tooltip>
          <Tooltip title="关闭工作空间" placement="right">
            <button
              type="button"
              style={{
                border: 'none',
                padding: '4px 8px',
                borderRadius: '4px',
              }}
              onClick={() => ee.emit(EVENTS.CLOSE_PANEL)}
            >
              <CloseOutlined />
            </button>
          </Tooltip>
        </div>
      </HeaderContainer>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {explorerContent}
        <div
          style={{
            flex: 1,
            height: '100%',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {runningContent[displayUid]?.start_time && (
            <div
              style={{
                color: '#aaaaaa',
                fontSize: '12px',
                borderBottom: '1px solid #dddddd',
                padding: '12px',
              }}
            >
              <Space>
                {IconMap[runningContent[displayUid]?.status]}
                {dayjs(runningContent[displayUid]?.start_time).format(
                  'YYYY-MM-DD HH:mm:ss',
                )}
              </Space>
            </div>
          )}
          {mainContent}
        </div>
      </div>
    </AgentContainer>
  );
};

export default React.memo(VisRunningWindowV2);