import Avatar from '../../avatar';
import React from 'react';
import { VisMsgCardWrap } from './style';
import { markdownComponents, markdownPlugins } from '../../config';
import { VisMsgWrapContext } from '@/contexts';
import { GPTVis } from '@antv/gpt-vis';
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
            // @ts-ignore
            <GPTVis
              components={markdownComponents}
              {...markdownPlugins}
            >
              {data?.markdown?.replaceAll('~', '&#126;')}
            </GPTVis>
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
