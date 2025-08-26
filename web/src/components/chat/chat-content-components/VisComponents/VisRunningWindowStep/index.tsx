import { ChatContext, VisCardWrapContext, VisMsgWrapContext } from '@/contexts/chat-context';
import { CheckCircleFilled, CloseCircleOutlined, DownOutlined, UpOutlined } from '@ant-design/icons';
import React, { useContext } from 'react';
import Markdown from 'react-markdown';
import Avatar from '../../avatar';
import { VisStepCardWrap } from './style';
interface IProps {
  data: any;
}

type SetpStatus = 'EXECUTING' | 'FINISHED' | 'FAILED';

const VisRunningWindowStepCard = ({ data }: IProps) => {
  const { setStepParams } = useContext(ChatContext) || {};
  const { visMsgData } = useContext(VisMsgWrapContext) || {};
  const { panelAction } = useContext(VisCardWrapContext) || {};
  const [showDetail, setShowDetail] = React.useState<boolean>(false);

  const renderStatusIcon = (status: SetpStatus, type: 'title' | 'tool') => {
    switch (status) {
      case 'FINISHED':
        return type === 'title' ? <CheckCircleFilled style={{ color: '#52c41a' }} /> : (!showDetail ? <DownOutlined /> : <UpOutlined />);
      case 'FAILED':
        return <CloseCircleOutlined style={{ color: 'red' }} />;
      default:
        return type === 'title' ? (
          <img
            src='/icons/loading.png'
            style={{ width: '20px', height: '20px' }}
          />
        ) : (
          <img
            src='/icons/loading1.gif'
            style={{ width: '20px' }}
          />
        );
    }
  };

  return (
    <VisStepCardWrap className='VisStepCardWrap'>
      <div
        style={{
          display: 'inline-flex',
          justifyContent: 'space-between',
          alignItems: 'start',
          // padding: '12px 16px',
          padding: '12px',
          background: '#fff',
          borderRadius: '16px',
        }}
      >
        <div
          style={{
            background: '#000a1a0a',
            borderRadius: '16px',
            padding: '6px 12px',
            width: '100%',
            display: 'flex',
            flexDirection: 'column',
            cursor: 'pointer',
          }}
          onClick={() => {
            setShowDetail(prev => !prev);
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              width: '100%',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'start',
                alignItems: 'start',
              }}
            >
              <div style={{ marginRight: '12px' }}>{renderStatusIcon(data?.status, 'title')}</div>
              <Avatar
                src={
                  data?.chatItem?.avatarUrl ||
                  '/agents/chat_avatar_default.png'
                }
                width={20}
              />
              <div style={{ flex: 1, margin: '0 12px' }}>{data?.tool_name || '--'}</div>
            </div>
            {renderStatusIcon('FINISHED', 'tool')}
          </div>
          {showDetail && (
            <div style={{ marginTop: 12, width: '100%' }}>
              <div style={{ marginBottom: 8, color: '#888' }}>请求参数：</div>
              <div style={{ background: '#f6f8fa', borderRadius: 8, padding: 8 }}>
                <pre style={{ margin: 0, fontSize: 13 }}>{data?.tool_args}</pre>
              </div>
              <div style={{ margin: '12px 0 8px', color: '#888' }}>返回结果：</div>
              <div style={{ background: '#f6f8fa', borderRadius: 8, padding: 8 }}>
                <Markdown>{data?.tool_result || '无结果'}</Markdown>
              </div>
            </div>
          )}
        </div>
      </div>
    </VisStepCardWrap>
  );
};

export default VisRunningWindowStepCard;
