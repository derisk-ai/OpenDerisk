import Avatar from '../../avatar';
import React from 'react';
import { VisMsgCardWrap } from './style';
import { markdownComponents } from '../../config';
import { VisMsgWrapContext } from '@/contexts';
import { GPTVisLite } from '@antv/gpt-vis';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
import { Bubble } from '@ant-design/x';

interface IProps {
  data: any;
}

const VisMsgCard = ({ data }: IProps) => {

  return (
    <VisMsgWrapContext.Provider
      value={{
        visMsgData: data,
      }}
    >
      <VisMsgCardWrap>
        <Bubble 
          content={data?.markdown}
          avatar={
            <Avatar src={data?.avatar}/>
          }
          header={
            data?.name || undefined
          }
          messageRender={() => (
            <GPTVisLite
              components={markdownComponents}
              rehypePlugins={[rehypeRaw]}
              remarkPlugins={[remarkGfm]}
            >
              {data?.markdown?.replaceAll('~', '&#126;')}
            </GPTVisLite>
          )}
          style={{
            width: '100%',
          }}
          styles={{
            content: {
              background: 'transparent',
              padding: 0,
              borderRadius: '0 16px 16px 16px',
              minWidth: 100,
              whiteSpace: 'pre-wrap',
              display: 'inline-flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              alignItems: 'start',
              width: '100%',
            },
          }}
        />
      </VisMsgCardWrap>
    </VisMsgWrapContext.Provider>
  );
};

export default VisMsgCard;
