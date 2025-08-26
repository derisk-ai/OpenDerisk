import React from "react";
import { Space } from 'antd';
import { VisPlanCardWrap } from './style';
import Avatar from '../../avatar';
import { GPTVisLite } from '@antv/gpt-vis';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
import { markdownComponents } from '../../config';
interface IProps {
  data: any;
}

const VisPlanCard = ({ data }: IProps) => {

  return (
    <VisPlanCardWrap className="planCard">
      {
        data?.tasks?.map((planItem: any, index: number) => (
          <div className='planItem' key={index}>
            <Space>
              <div>
                <span> {planItem?.task_id || '-'} </span>
                <span> {planItem?.task_name || '-'} </span>
              </div>
              <Space
                style={{ cursor: 'pointer', background: '#1b62ff1a', borderRadius: '6px', padding: '2px 8px', margin: '8px 0' }}
                onClick={() => window.open(planItem?.task_link)}
              >
                <span>@</span>
                {planItem?.agent_link && <Avatar src={planItem?.agent_link}></Avatar>}
                <span>{planItem?.agent_name || '-'}</span>
              </Space>
            </Space>
          </div>
        ))
      }
      {
        data?.markdown && (
          <GPTVisLite
            components={markdownComponents}
            rehypePlugins={[rehypeRaw]}
            remarkPlugins={[remarkGfm]}
          >
            {data?.markdown || '-'}
          </GPTVisLite>
        )
      }
    </VisPlanCardWrap>
  )
};

export default VisPlanCard;
