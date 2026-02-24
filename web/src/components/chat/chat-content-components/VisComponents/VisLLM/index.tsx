import { codeComponents, markdownPlugins } from '../../config';
import {
  RobotOutlined,
} from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { Avatar, Descriptions, Flex } from 'antd';
import { isEqual } from 'lodash';
import React, { useState } from 'react';
import { VisLLMDiv } from './style';
import ThinkInput from './ThinkInput';

interface IProps {
  footer?: string | React.ReactNode;
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
    link_url,
  } = data || {};
  const [showModelInput, setShowModelInput] = useState(false);

  return (
    <VisLLMDiv className="vis-llm">
      <Descriptions
        title={
          <Flex flex={0} align="center" gap={10}>
            <Avatar onClick={() => setShowModelInput(!showModelInput)} src={llm_avatar}>
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
      {showModelInput && <ThinkInput url={link_url} />}
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

export default React.memo(VisLLM, isEqual);
