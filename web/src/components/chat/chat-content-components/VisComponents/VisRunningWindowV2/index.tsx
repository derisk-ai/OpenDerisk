import React, { FC, useEffect, useRef, useState, useMemo, useCallback } from 'react';
import {
  CheckCircleOutlined,
  CloseOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PauseCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { Space } from 'antd';
import dayjs from 'dayjs';
import { keyBy } from 'lodash';
import {
  WorkSpaceContainer,
  WorkSpaceHeader,
  WorkSpaceTitle,
  WorkSpaceControls,
  WorkSpaceBody,
  ExplorerPanel,
  ContentPanel,
  ContentHeader,
  ContentBody,
  IconButton,
} from './style';
import { codeComponents, type MarkdownComponent, markdownPlugins } from '../../config';
import { ee, EVENTS } from '@/utils/event-emitter';

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

const IconMap: Record<string, React.ReactNode> = {
  complete: <CheckCircleOutlined style={{ color: '#10b981', fontSize: 14 }} />,
  todo: <CheckCircleOutlined style={{ color: '#9ca3af', fontSize: 14 }} />,
  running: <LoadingOutlined style={{ color: '#3b82f6', fontSize: 14 }} />,
  waiting: <PauseCircleOutlined style={{ color: '#f59e0b', fontSize: 14 }} />,
  retrying: <SyncOutlined style={{ color: '#3b82f6', fontSize: 14 }} />,
  failed: <ExclamationCircleOutlined style={{ color: '#ef4444', fontSize: 14 }} />,
};

export const VisRunningWindowV2: FC<IProps> = ({ otherComponents, data }) => {
  const [displayUid, setDisplayUid] = useState<string>('');
  const [isExplorerVisible, setIsExplorerVisible] = useState<boolean>(true);
  const contentRef = useRef<HTMLDivElement>(null);
  const runningContent = useMemo(() => keyBy(data.items, 'uid'), [data.items]);

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
  }, [data.items]);

  const lastItemMarkdown = data.items[data.items.length - 1]?.markdown;

  useEffect(() => {
    contentRef.current?.scrollTo({
      top: contentRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [runningContent?.[displayUid]?.markdown, lastItemMarkdown]);

  const handleClose = useCallback(() => {
    ee.emit(EVENTS.CLOSE_PANEL);
  }, []);

  const toggleExplorer = useCallback(() => {
    setIsExplorerVisible((prev) => !prev);
  }, []);

  const explorerContent = useMemo(
    () => (
      <ExplorerPanel $visible={isExplorerVisible}>
        {/* @ts-expect-error GPTVis components */}
        <GPTVis
          components={{ ...codeComponents, ...(otherComponents || {}) }}
          {...markdownPlugins}
        >
          {data.explorer || '-'}
        </GPTVis>
      </ExplorerPanel>
    ),
    [isExplorerVisible, data.explorer, otherComponents],
  );

  const mainContentMarkdown =
    runningContent[displayUid]?.markdown ||
    data.items[data.items.length - 1]?.markdown ||
    '-';

  const mainContent = useMemo(
    () => (
      <ContentBody ref={contentRef}>
        {/* @ts-expect-error GPTVis components */}
        <GPTVis
          className="prose prose-sm max-w-none"
          components={{ ...codeComponents, ...(otherComponents || {}) }}
          {...markdownPlugins}
        >
          {mainContentMarkdown}
        </GPTVis>
      </ContentBody>
    ),
    [mainContentMarkdown, otherComponents],
  );

  const currentItem = runningContent[displayUid];

  return (
    <WorkSpaceContainer>
      <WorkSpaceHeader>
        <WorkSpaceTitle>
          <IconButton onClick={toggleExplorer} title={isExplorerVisible ? '收起目录' : '展开目录'}>
            {isExplorerVisible ? <MenuFoldOutlined /> : <MenuUnfoldOutlined />}
          </IconButton>
          <span className="title-text">工作空间</span>
        </WorkSpaceTitle>
        <WorkSpaceControls>
          <IconButton onClick={handleClose} title="关闭工作空间">
            <CloseOutlined />
          </IconButton>
        </WorkSpaceControls>
      </WorkSpaceHeader>

      <WorkSpaceBody>
        {explorerContent}
        <ContentPanel $explorerVisible={isExplorerVisible}>
          {currentItem?.start_time && (
            <ContentHeader>
              <Space size={8}>
                {IconMap[currentItem.status] || IconMap.running}
                <span className="time-text">
                  {dayjs(currentItem.start_time).format('HH:mm:ss')}
                </span>
              </Space>
            </ContentHeader>
          )}
          {mainContent}
        </ContentPanel>
      </WorkSpaceBody>
    </WorkSpaceContainer>
  );
};

export default React.memo(VisRunningWindowV2);