import {
  CheckCircleTwoTone,
  ClockCircleTwoTone,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { Flex, Space, Timeline } from 'antd';
import Avatar from '../../avatar';
import React, { FC } from 'react';
import {
  PlanDescription,
  PlanItemWrap,
  PlanTitle,
  VisPWCardWrapper,
} from './style';
interface PlanningWindow {
  data: {
    items: Plan[];
  };
}

interface Plan {
  title?: string;
  description?: string;
  items: PlanItem[];
  model?: string;
  agent?: string;
  avatar?: string;
}

interface PlanItem {
  title: string;
  task_id: string;
  status?: 'running' | 'todo' | 'complete' | 'failed'; // 待确认
  description: string;
  avatar?: string;
  model?: string;
  agent: string;
  task_type: string; //待确认
}

export const VisPlanningWindow: FC<PlanningWindow> = ({ data }) => {

  const renderIcon = (type: string) => {
    const iconMap: Record<string, string> = {
      knowledge_pack: '/icons/package.png',
      knowledge: '/icons/package.png',
      tool: '/icons/tool.png',
      code: '/icons/code.png',
      report: '/icons/report.png',
      monitor: '/icons/monitor.png',
      agent: '/icons/agent.png',
      plan: '/icons/plan.png',
      llm: '/icons/llm.png',
      stage: '/icons/stage.png',
      task: '/icons/task.png',
      default: '/icons/tool_default.svg',
    };
    const normalizedType = String(type).toLowerCase();
    return iconMap[normalizedType] || iconMap.default;
  }

  const PlanItems = (plan: Plan) => {
    return plan.items?.map((planItem: PlanItem, index) => {
      return ({
        dot: (
          <Space>
            <div>
              {planItem.status === 'running' && <LoadingOutlined />}
              {planItem.status === 'complete' && (
                <CheckCircleTwoTone twoToneColor="#52c41a" />
              )}
              {planItem.status === 'todo' && <ClockCircleTwoTone />}
              {planItem.status === 'failed' && <CloseCircleOutlined className='text-red-500' />}
            </div>
          </Space>
        ),
        children: (
          <PlanItemWrap key={`${index}-${planItem.task_id}`}>
            <Space direction='vertical' style={{ width: '100%' }}>
              <span> {planItem.title || '-'}</span>
              <Space>
                <Avatar
                  src={
                    planItem?.avatar ||
                    renderIcon(planItem?.task_type)
                  }
                  width={18}
                />
                <span> {planItem.agent || '-'} </span>
              </Space>
            </Space>
          </PlanItemWrap>
        ),
      })
    });
  };


  return (
    <VisPWCardWrapper>
      <Timeline
        items={data.items?.map((plan: Plan) => {
          return {
            dot:(
              <Avatar
                src={
                  plan.avatar ||
                  '/agents/robot.png'
                }
              />
            ),
            children: (
              <Flex vertical gap={16}>
                <Flex>
                  <PlanTitle>
                    {plan.title}
                    <span>@{plan?.agent || '-'}</span>
                  </PlanTitle>
                </Flex>
                <PlanDescription>{plan.description}</PlanDescription>
                <Timeline items={PlanItems(plan)} />
              </Flex>
            ),
          };
        })}
      ></Timeline>
    </VisPWCardWrapper>
  );
};
