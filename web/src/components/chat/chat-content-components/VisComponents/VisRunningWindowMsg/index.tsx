import React from 'react';
import { VisRWMsgCardHeader, VisRWMsgCardWrap } from './style';
import { markdownComponents } from '../../config';
import { GPTVisLite } from '@antv/gpt-vis';
import Avatar from '../../avatar';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
import { createContext } from 'react';
import { Space } from 'antd';
interface IProps {
  data: any;
}

export const VisMsgWrapContext = createContext<any>(null);

const VisRunningWindowMsgCard = ({ data }: IProps) => {
  return (
    <VisMsgWrapContext.Provider
      value={{
        visMsgData: data,
      }}
    >
      <VisRWMsgCardWrap>
        <VisRWMsgCardHeader>
          <Space>
            <Avatar
              src={data?.avatar}
              width={26}
            />
            {data?.name}
          </Space>
        </VisRWMsgCardHeader>
        <div style={{ padding: '8px 12px' }}>
          <GPTVisLite
            className="whitespace-normal"
            components={markdownComponents}
            rehypePlugins={[rehypeRaw]}
            remarkPlugins={[remarkGfm]}
          >
            {data?.markdown?.replaceAll('~', '&#126;')}
          </GPTVisLite>
        </div>
      </VisRWMsgCardWrap>
    </VisMsgWrapContext.Provider>
  );
};

export default VisRunningWindowMsgCard;
