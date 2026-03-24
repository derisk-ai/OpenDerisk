import React, { FC } from 'react';
import { VisConfirmResponseWrap } from './style';
import { CheckCircleOutlined } from '@ant-design/icons';
import { Typography, Tag } from 'antd';

const { Text } = Typography;

interface VisConfirmResponseData {
  confirm_type?: 'select' | 'input' | 'confirm';
  question?: string;
  header?: string;
  selected_option?: {
    label: string;
    description?: string;
  };
  input_content?: string;
  is_custom_input?: boolean;
  timestamp?: string;
}

interface IProps {
  data: VisConfirmResponseData;
}

const VisConfirmResponse: FC<IProps> = ({ data }) => {
  const {
    confirm_type = 'confirm',
    question,
    header,
    selected_option,
    input_content,
    is_custom_input,
    timestamp,
  } = data;

  const formatTime = (ts?: string) => {
    if (!ts) return '';
    try {
      const date = new Date(ts);
      return date.toLocaleTimeString();
    } catch {
      return '';
    }
  };

  return (
    <VisConfirmResponseWrap>
      <div className="response-card">
        <div className="response-header">
          <CheckCircleOutlined className="check-icon" />
          <Text strong className="response-title">
            {header || 'User Confirmed'}
          </Text>
          {timestamp && (
            <Text type="secondary" className="response-time">
              {formatTime(timestamp)}
            </Text>
          )}
        </div>

        {question && (
          <div className="response-question">
            <Text type="secondary">Q: {question}</Text>
          </div>
        )}

        <div className="response-content">
          {confirm_type === 'select' && selected_option && !is_custom_input && (
            <div className="response-selection">
              <Tag color="blue" className="selection-tag">
                {selected_option.label}
              </Tag>
              {selected_option.description && (
                <Text type="secondary" className="selection-desc">
                  {selected_option.description}
                </Text>
              )}
            </div>
          )}

          {input_content && (
            <div className="response-input">
              <Text>{is_custom_input ? 'Custom: ' : 'Notes: '}{input_content}</Text>
            </div>
          )}

          {confirm_type === 'confirm' && !selected_option && !input_content && (
            <Text type="success">Confirmed</Text>
          )}
        </div>
      </div>
    </VisConfirmResponseWrap>
  );
};

export default VisConfirmResponse;
