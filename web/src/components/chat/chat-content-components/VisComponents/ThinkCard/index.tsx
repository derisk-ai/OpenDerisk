import { DownOutlined, UpOutlined } from '@ant-design/icons';
import { Collapse } from 'antd';
import React, { useContext, useState } from 'react';
import { ThinkCardWrap } from './style';
import {
  ChatContext,
  VisCardWrapContext,
  VisMsgWrapContext,
} from '@/contexts';
import { Bubble } from '@ant-design/x';
import { markdownComponents, markdownPlugins } from '../../config';
import { GPTVisLite } from '@antv/gpt-vis';

interface IProps {
  data: any;
}

const ThinkCard = ({ data }: IProps) => {
  const [active, setActive] = useState<string[]>(['1']);
  const { setStepParams } = useContext(ChatContext) || {};
  const { visMsgData } = useContext(VisMsgWrapContext) || {};
  const { panelAction } = useContext(VisCardWrapContext) || {};
  
  return (
    <ThinkCardWrap style={{ background: 'transparent' }}>
      <Collapse
        defaultActiveKey={['1']}
        activeKey={active}
        ghost
        onChange={(values) => setActive(values)}
        items={[
          {
            key: '1',
            label: (
              <div
                style={{
                  display: 'inline-flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  width: '100%',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'flex-start',
                    alignItems: 'center',
                  }}
                >
                  <img
                    src="/icons/thinking.svg"
                    style={{ width: '17px' }}
                  />
                  <span style={{ margin: '0 8px' }}>深度思考过程</span>
                  {active?.length > 0 ? <UpOutlined /> : <DownOutlined />}
                </div>
                {/* 外源 组件不展示规划详情 */}
                {/* {data?.think_link && active?.length > 0 && (
                  <div
                    style={{
                      marginLeft: 12,
                      color: '#1b62ff',
                      cursor: 'pointer',
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (panelAction) {
                        panelAction(data);
                      } else {
                        if (setStepParams) {
                          setStepParams({
                            requestUrl: data?.think_link,
                            name: '规划详情',
                            avatarUrl: visMsgData?.avatar || undefined,
                          });
                        }
                      }
                    }}
                  >
                    <img
                      src=""
                      style={{
                        display: 'inline-block',
                        width: 16,
                        height: 16,
                        margin: '0px 6px 2px 0px',
                      }}
                    />
                    <span>规划详情</span>
                  </div>
                )} */}
              </div>
            ),
            children: (
              <Bubble
                placement="start"
                messageRender={() => {
                  if (data?.markdown) {
                    return (
                      // @ts-ignore
                      <GPTVisLite
                        className="whitespace-normal"
                        components={markdownComponents}
                        {...markdownPlugins}
                      >
                        {data?.markdown || '-'}
                      </GPTVisLite>
                    );
                  }
                }}
                style={{
                  width: '100%',
                  // marginInlineEnd: 'auto',
                  borderTop: '1px solid #ccc',
                }}
                styles={{
                  content: {
                    width: '100%',
                    borderRadius: '0 16px 16px 16px',
                    minWidth: 100,
                    whiteSpace: 'pre-wrap',
                    padding: '12px 0',
                    color: '#6A7380',
                  },
                  footer: {
                    alignSelf: 'stretch',
                  },
                }}
              />
            ),
          },
        ]}
      />
    </ThinkCardWrap>
  );
};

export default ThinkCard;
