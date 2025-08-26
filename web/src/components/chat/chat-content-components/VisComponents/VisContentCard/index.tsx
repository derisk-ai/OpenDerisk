import React from "react";
import { VisContentCardWrap } from './style';
import { GPTVisLite } from '@antv/gpt-vis';
import 'katex/dist/katex.min.css';
import { markdownPlugins, basicComponents, markdownComponents } from '../../config';
import rehypeRaw from "rehype-raw";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

interface IProps {
  data: any;
}

const VisContentCard = ({ data }: IProps) => {

  return (
    <VisContentCardWrap className="VisContentCardClass">
      <GPTVisLite
        components={markdownComponents}
        rehypePlugins={[rehypeRaw, [rehypeKatex, { output: 'htmlAndMathml' }]]}
        remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: true }]]}
      >
        {data?.markdown || '-'}
      </GPTVisLite>
    </VisContentCardWrap>
  )
};

export default VisContentCard;
