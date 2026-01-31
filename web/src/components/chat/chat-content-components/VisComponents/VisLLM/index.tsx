import { RobotOutlined } from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { Avatar, Descriptions, Flex } from 'antd';
import React, { useState } from 'react';
import { VisLLMDiv } from './style';
import { codeComponents, markdownPlugins } from '../../config';

interface IProps {
  data: {
    llm_avatar?: string;
    token_use?: number | string;
    cost?: number;
    token_speed?: number | string;
    markdown?: string;
    link_url?: string;
    llm_model?: string;
  };
}

const VisLLM = ({ data }: IProps) => {
  const {
    llm_avatar,
    token_use,
    cost,
    token_speed,
    markdown,
  } = data || {};
  const [showModelInput] = useState(false);

  return (
    <VisLLMDiv className="vis-llm">
      <Descriptions
        title={
          <Flex flex={0} align="center" gap={10}>
            <Avatar src={llm_avatar}>
              <RobotOutlined />
            </Avatar>
            <div>{data?.llm_model || '模型输出'}</div>
          </Flex>
        }
        rootClassName=""
        layout="vertical"
        column={3}
        size="small"
        items={[
          { label: '推理耗时', children: cost ? `${cost}s` : '-' },
          { label: '输出token', children: token_use ?? '-' },
          {
            label: '速度',
            children: token_speed
              ? `${token_speed} tokens/s`
              : '-',
          },
        ]}
      />
      {showModelInput && <div />}
      <div>
        {markdown && (
          // @ts-ignore 
          <GPTVis
            className="whitespace-normal"
            components={{ ...codeComponents }}
            {...markdownPlugins}
          >
            {markdown.replaceAll('~', '&#126;')}
          </GPTVis>
        )}
      </div>
    </VisLLMDiv>
  );
};

export default React.memo(VisLLM);
