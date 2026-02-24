import React from "react";
import { VisContentCardWrap } from './style';
import { GPTVis } from '@antv/gpt-vis';
import 'katex/dist/katex.min.css';
import { markdownPlugins, basicComponents, markdownComponents } from '../../config';

interface IProps {
  data: any;
}

const VisContentCard = ({ data }: IProps) => {

  return (
    <VisContentCardWrap className="VisContentCardClass">
      {/* @ts-ignore */}
      <GPTVis components={markdownComponents} {...markdownPlugins}>
        {data?.markdown || '-'}
      </GPTVis>
    </VisContentCardWrap>
  )
};

export default VisContentCard;
