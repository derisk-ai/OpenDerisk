import { Popover, Typography } from 'antd';
import React from 'react';
import {
  CustomContentRenderWrapper,
  CustomPluginContent,
  CustomPopoverWrapper,
} from './style';

const typeIconMap = {
  knowledge:
    '/icons/knowledge_blue.png',
  skill:
    '/icons/skill_blue.svg',
  agent:
    '/icons/agent_blue.svg',
};

interface IProps {
  data: { name: string; description?: string; type: keyof typeof typeIconMap };
}

export const CustomContentRender = (props: IProps) => {
  const { data } = props;
  return (
    <CustomContentRenderWrapper>
      <Popover
        placement="bottom"
        content={
          <CustomPopoverWrapper>
            <div className="custom_popover_content_name">{data?.name}</div>
            <div>
              {data?.description && (
                <Typography.Text
                  className="custom_popover_content_desc"
                  ellipsis={{
                    tooltip: data?.description,
                  }}
                >
                  {data?.description || ''}
                </Typography.Text>
              )}
            </div>
          </CustomPopoverWrapper>
        }
      >
        <CustomPluginContent>
          {data?.type && typeIconMap[data.type] && (
            <img style={{ width: '16px' }} src={typeIconMap[data.type]} />
          )}
          <span>{data?.name}</span>
        </CustomPluginContent>
      </Popover>
    </CustomContentRenderWrapper>
  );
};

export default CustomContentRender;
