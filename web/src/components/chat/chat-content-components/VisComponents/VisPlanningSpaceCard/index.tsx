import React, { FC } from 'react';
import { GPTVis } from '@antv/gpt-vis';
import { markdownComponents, markdownPlugins } from '../../config';
import { PlanningSpaceWrap } from './style';

interface IProps {
  data: {
    markdown?: string;
    content?: string;
    [key: string]: unknown;
  };
}

const VisPlanningSpaceCard: FC<IProps> = ({ data }) => {
  const content = data?.markdown ?? data?.content ?? '';

  if (!content) {
    return null;
  }

  return (
    <PlanningSpaceWrap>
      {/* @ts-ignore */}
      <GPTVis components={markdownComponents} {...markdownPlugins}>
        {content}
      </GPTVis>
    </PlanningSpaceWrap>
  );
};

export default VisPlanningSpaceCard;
