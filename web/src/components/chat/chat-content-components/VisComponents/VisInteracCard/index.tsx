import React from 'react';
import { VisConfirmCardWrap } from '../VisConfirmCard/style';
import {
  codeComponents,
  type MarkdownComponent,
  markdownPlugins,
} from '../../config';
import { GPTVis } from '@antv/gpt-vis';
import { Divider } from 'antd';

interface VisInteracCardIProps {
  data: {
    title?: string;
    markdown?: string;
  };
  otherComponents?: MarkdownComponent;
}

const VisInteracCard: React.FC<VisInteracCardIProps> = ({
  data,
  otherComponents,
}) => {
  return (
    <VisConfirmCardWrap className="VisConfirmCardClass">
      <div className="card-content">
        <span className="confirm-title">🎯{data.title ?? '交互'}</span>
        <Divider
          style={{
            margin: '8px 0px 8px 0px',
            borderWidth: '1px',
            borderColor: 'rgba(0, 0, 0, 0.03)',
          }}
        />
        <div className="whitespace-normal">
          {/* @ts-ignore */}
          <GPTVis
            className="whitespace-normal"
            components={{ ...codeComponents, ...(otherComponents || {}) }}
            {...markdownPlugins}
          >
            {data?.markdown || '-'}
          </GPTVis>
        </div>
        <Divider
          style={{
            margin: '8px 0px 8px 0px',
            borderWidth: '1px',
            borderColor: 'rgba(0, 0, 0, 0.03)',
          }}
        />
      </div>
    </VisConfirmCardWrap>
  );
};

export default VisInteracCard;
