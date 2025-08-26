import { Bubble } from '@ant-design/x';
import React from 'react';
import renderMarkdown from '../../render-markdown';

interface IProps {
  content: string;
  isLoading?: boolean;
  isTyping?: boolean;
}

const MarkdownCard = ({
  content,
  isLoading = false,
  isTyping = false,
}: IProps) => {
  return (
    <Bubble
      placement="start"
      content={content}
      messageRender={(content) => renderMarkdown(content)}
      typing={isTyping}
      style={{
        width: '100%',
        marginInlineEnd: 'auto',
      }}
      styles={{
        content: {
          background: '#fff',
          borderRadius: '0 16px 16px 16px',
          minWidth: 100,
          whiteSpace: 'pre-wrap',
        },
        footer: {
          alignSelf: 'stretch',
        },
      }}
      loading={isLoading}
    />
  );
};

export default MarkdownCard;
