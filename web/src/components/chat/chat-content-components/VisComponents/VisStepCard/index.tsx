import Avatar from '../../avatar';
import {
  CheckCircleFilled,
  CloseCircleOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { ChatContext, VisMsgWrapContext, VisCardWrapContext } from '@/contexts/chat-context';
import { Space } from 'antd';
import React, { useContext } from 'react';
import renderMarkdown from '../../render-markdown';
import { VisStepCardWrap } from './style';
interface IProps {
  data: any;
}

type SetpStatus = 'EXECUTING' | 'FINISHED' | 'FAILED';

const VisStepCard = ({ data }: IProps) => {
  const { setStepParams } = useContext(ChatContext) || {};
  const { visMsgData } = useContext(VisMsgWrapContext) || {};
  const { panelAction } = useContext(VisCardWrapContext) || {};

  const renderStatusIcon = (status: SetpStatus, type: 'title' | 'tool') => {
    switch (status) {
      case 'FINISHED':
        return type === 'title' ? (
          <CheckCircleFilled style={{ color: '#52c41a' }} />
        ) : (
          <RightOutlined />
        );
      case 'FAILED':
        return <CloseCircleOutlined style={{ color: 'red' }} />;
      default:
        return type === 'title' ? (
          <img
            src="/icons/loading.png"
            style={{ width: '20px', height: '20px' }}
          />
        ) : (
          <img
            src="/icons/loading1.gif"
            style={{ width: '20px' }}
          />
        );
    }
  };

  return (
    <VisStepCardWrap className="VisStepCardWrap">
      <div
        style={{
          display: 'inline-flex',
          justifyContent: 'space-between',
          alignItems: 'start',
          padding: '12px',
          background: '#fff',
          borderRadius: '16px',
        }}
      >
        <div style={{ marginRight: '12px' }}>
          {renderStatusIcon(data?.status, 'title')}
        </div>
        <Space direction="vertical">
          <div>{renderMarkdown(data?.tool_name)}</div>
          <div
            style={{
              background: '#000a1a0a',
              borderRadius: '16px',
              padding: '6px 12px',
              width: '100%',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              cursor: 'pointer',
            }}
            onClick={() => {
              if (panelAction) {
                panelAction(data);
              } else {
                if (setStepParams) {
                  setStepParams({
                    requestUrl: data?.tool_execute_link,
                    name: data?.tool_name || 'tool',
                    avatarUrl: visMsgData?.avatar || undefined,
                  });
                }
              }
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'start',
                alignItems: 'start',
              }}
            >
              <Avatar
                src={
                  data?.chatItem?.avatarUrl ||
                  '/agents/chat_avatar_default.png'
                }
                width={20}
              />
              <div style={{ flex: 1, margin: '0 12px' }}>
                {data?.tool_name || '--'}
              </div>
            </div>
            {renderStatusIcon('FINISHED', 'tool')}
          </div>
        </Space>
      </div>
    </VisStepCardWrap>
  );
};

export default VisStepCard;
