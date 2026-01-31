import React, { useEffect, useState } from 'react';
import { VisAgentPlanCardWrap } from './style';
import { GPTVis } from '@antv/gpt-vis';
import 'katex/dist/katex.min.css';
import {
  codeComponents,
  type MarkdownComponent,
  markdownPlugins,
} from '../../config';
import {
  CheckCircleOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  PauseCircleOutlined,
  SyncOutlined,
  UpOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Tooltip } from 'antd';
import { ee as workWindowEmitter } from '@/utils/event-emitter';

const StatusMap: Record<string, string> = {
  todo: '待执行',
  running: '执行中',
  waiting: '等待中',
  retrying: '重试中',
  failed: '失败',
  complete: '成功',
};

const getStatusText = (status: string): string =>
  StatusMap[status] ?? status ?? '成功';

const iconUrlMap: Record<string, string> = {
  report:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*xaTaQ5rDghgAAAAALTAAAAgAeprcAQ/original',
  tool: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  blankaction:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*WC8ARKan1WEAAAAAQBAAAAgAeprcAQ/original',
  knowledge:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*P2sCQKUZoAUAAAAAOhAAAAgAeprcAQ/original',
  code: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*pPozSIZ_0u4AAAAAO7AAAAgAeprcAQ/original',
  deriskcodeaction:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*pPozSIZ_0u4AAAAAO7AAAAgAeprcAQ/original',
  monitor:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*F4pAT4italwAAAAANhAAAAgAeprcAQ/original',
  agent: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*b_vFSpByHFcAAAAAQBAAAAgAeprcAQ/original',
  plan: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*ibaHSahFSCoAAAAAQBAAAAgAeprcAQ/original',
  planningaction:
    'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*ibaHSahFSCoAAAAAQBAAAAgAeprcAQ/original',
  llm: 'https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*b_vFSpByHFcAAAAAQBAAAAgAeprcAQ/original',
};

interface IProps {
  otherComponents?: MarkdownComponent;
  data: Record<string, unknown>;
}

const IconMap = {
  complete: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 12 }} />,
  todo: <CheckCircleOutlined style={{ color: '#595959', fontSize: 12 }} />,
  running: <LoadingOutlined style={{ color: '#1677ff', fontSize: 12 }} />,
  waiting: <PauseCircleOutlined style={{ color: '#f5dc62', fontSize: 12 }} />,
  retrying: <SyncOutlined style={{ color: '#1677ff', fontSize: 12 }} />,
  failed: (
    <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 12 }} />
  ),
};

const VisAgentPlanCard: React.FC<IProps> = ({ otherComponents, data }) => {
  const [expanded, setExpanded] = useState((data.expand as boolean) ?? true);
  const [isSelected, setIsSelected] = useState(false);
  const [dynamicCost, setDynamicCost] = useState(
    (data?.cost as number) ?? 0,
  );

  const toggleExpand = () => {
    setExpanded((prev) => !prev);
  };

  const formatTime = (timeStr: string) => {
    if (!timeStr) return '';
    try {
      const date = new Date(timeStr);
      if (Number.isNaN(date.getTime())) return timeStr;
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      const seconds = String(date.getSeconds()).padStart(2, '0');
      return `${hours}:${minutes}:${seconds}`;
    } catch {
      return timeStr;
    }
  };

  useEffect(() => {
    if (data.expand !== undefined) {
      setExpanded(Boolean(data.expand));
    }
  }, [data.expand]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;
    if (
      (data?.cost as number) === 0 &&
      (data?.status as string) === 'running'
    ) {
      setDynamicCost(0);
      interval = setInterval(() => {
        setDynamicCost((prev) => prev + 1);
      }, 1000);
    } else {
      setDynamicCost((data?.cost as number) ?? 0);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [data?.cost, data?.status]);

  useEffect(() => {
    const handler = (payload: { uid?: string }) => {
      if (payload?.uid === (data?.uid as string)) setIsSelected(true);
      else setIsSelected(false);
    };
    workWindowEmitter.on('clickFolder', handler);
    return () => {
      workWindowEmitter.off('clickFolder', handler);
    };
  }, [data?.uid]);

  const hasChildren =
    data?.markdown ||
    (Array.isArray(data?.children) && (data.children as unknown[]).length > 0);
  const isReport = data?.task_type === 'report';
  const isPlan = data?.item_type === 'plan';
  const isTask = data?.item_type === 'task';
  const layerCount = (data?.layer_count as number) ?? 0;

  return (
    <VisAgentPlanCardWrap
      onClick={(e: React.MouseEvent) => {
        e.stopPropagation();
        const callback = () =>
          setTimeout(() => {
            workWindowEmitter.emit('clickFolder', {
              uid: data.uid as string,
            });
          }, 500);
        workWindowEmitter.emit('openPanel', { callback });
      }}
      className={`VisAgentPlanCardClass level-${layerCount} ${isSelected && isPlan ? 'selected' : ''}`}
    >
      <div
        className={`header ${isPlan ? 'header-plan' : ''} ${data?.item_type === 'task' ? 'header-task' : 'header-default'}`}
        onClick={toggleExpand}
      >
        <div className="content-wrapper">
          <div className="header-row">
            <div className="content-header">
              {Boolean(data?.agent_name) && (
                <div className="agent_name" title={String(data.agent_name)}>
                  {isPlan && (
                    <Avatar
                      size={20}
                      src={data.agent_avatar as string}
                      className="avatar-shrink"
                    />
                  )}
                  <div className="agent_name-badge">
                    <Tooltip title={String(data.agent_name)}>
                      {String(data.agent_name)}
                    </Tooltip>
                  </div>
                </div>
              )}
              {isTask && (
                <img
                  className="task-icon"
                  src={
                    iconUrlMap[
                      (String(data?.task_type).toLowerCase() as keyof typeof iconUrlMap) || 'tool'
                    ]
                  }
                  alt=""
                />
              )}
              <div
                className={`title title-text title-level-${layerCount}`}
              >
                <div className="title-flex-container">
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      width: '80%',
                    }}
                  >
                    <span className="title-text-ellipsis">
                      <Tooltip title={String(data?.title ?? '未命名任务')}>
                        {String(data?.title ?? '未命名任务')}
                      </Tooltip>
                    </span>
                    {hasChildren && !isReport && (
                      <Button
                        type="text"
                        size="small"
                        icon={expanded ? <UpOutlined /> : <DownOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleExpand();
                        }}
                        className={`expand-btn ${expanded ? 'expanded' : 'collapsed'} button-shrink`}
                      />
                    )}
                  </div>
                  {isTask ? (
                    <span
                      className="button-shrink"
                      style={{ marginLeft: 8 }}
                    >
                      {
                        IconMap[
                          (data?.status as keyof typeof IconMap) ?? 'running'
                        ]
                      }
                    </span>
                  ) : (
                    <span className="status status-badge">
                      {getStatusText((data?.status as string) ?? '')}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
          <div className="flex-container">
            {Boolean(data?.description) && layerCount < 2 && (
              <div
                className={`task-description ${layerCount === 0 ? 'task-description-level-0' : 'task-description-level-other'} task-description-container`}
              >
                <Tooltip title={String(data.description)}>
                  {String(data.description)}
                </Tooltip>
              </div>
            )}
            {isPlan && (
              <div className="time-info">
                <div>{formatTime((data?.start_time as string) ?? '')}</div>
                <div className="time-cost">{dynamicCost} s</div>
              </div>
            )}
          </div>
        </div>
      </div>
      {expanded && data?.markdown ? (
        // @ts-expect-error GPTVis + markdownPlugins spread
        <GPTVis
          components={{ ...codeComponents, ...(otherComponents ?? {}) }}
          {...markdownPlugins}
        >
          {String(data.markdown)}
        </GPTVis>
      ) : null}
    </VisAgentPlanCardWrap>
  );
};

export default VisAgentPlanCard;
