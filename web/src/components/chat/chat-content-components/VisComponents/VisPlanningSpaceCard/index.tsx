import React, { FC } from 'react';
import { GPTVis } from '@antv/gpt-vis';
import { markdownComponents, markdownPlugins, preprocessLaTeX } from '../../config';
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

  const gptVisProps: any = {
    components: markdownComponents,
    ...markdownPlugins,
  };

  return (
    <PlanningSpaceWrap>
      {content && <GPTVis {...gptVisProps}>{preprocessLaTeX(content)}</GPTVis>}
    </PlanningSpaceWrap>
  );
};

export default VisPlanningSpaceCard;