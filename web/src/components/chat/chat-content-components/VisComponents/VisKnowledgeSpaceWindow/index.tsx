import React, { useEffect, useRef } from 'react';
import { GPTVis } from '@antv/gpt-vis';
import { CloseOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import { AgentContainer, AgentContent } from './style';
import { codeComponents, type MarkdownComponent, markdownPlugins } from '../../config';
import { useElementHeight } from '../hooks/useElementHeight';
import { ee as workWindowEmitter } from '../../../../../utils/event-emitter';

const CloseButton = styled.div`
  position: absolute;
  top: 8px;
  right: 8px;
  cursor: pointer;
  z-index: 10;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background-color: #ffffff;
  box-shadow: 0 2px 8px 0 rgba(0, 0, 0, 0.08);
  &:hover {
    background-color: #f5f5f5;
  }
`;

interface IProps {
  otherComponents?: MarkdownComponent;
  data: {
    uid: string;
    markdown: string;
  };
  style?: React.CSSProperties;
}

export const VisKnowledgeSpaceWindow: React.FC<IProps> = ({
  otherComponents,
  data,
}) => {
  const chatListContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const chatListContainer = chatListContainerRef.current;
    if (chatListContainer) {
      const distanceToBottom =
        chatListContainer.scrollHeight -
        chatListContainer.scrollTop -
        chatListContainer.clientHeight;
      if (distanceToBottom <= 150) {
        chatListContainer.scrollTo({
          top: chatListContainer.scrollHeight,
          behavior: 'smooth',
        });
      }
    }
  }, [data]);

  const containerHeight = useElementHeight(
    `#nex-chat-detail-panel${data.uid}`,
    `#nex-chat-detail-panel`,
  );

  return (
    <AgentContainer
      style={{ height: `${containerHeight || 400}px`, position: 'relative' }}
    >
      <CloseButton
        onClick={() => {
          workWindowEmitter.emit('closePanel');
        }}
      >
        <CloseOutlined />
      </CloseButton>
      <AgentContent
        style={
          containerHeight
            ? {
                border: '1px solid #ebedf1',
                height: '100%',
              }
            : {}
        }
        className="AgentContent"
        ref={chatListContainerRef}
      >
        {/* @ts-ignore */}
        <GPTVis
          className="whitespace-normal"
          components={{ ...codeComponents, ...(otherComponents || {}) }}
          {...markdownPlugins}
        >
          {data?.markdown || '-'}
        </GPTVis>
      </AgentContent>
    </AgentContainer>
  );
};

export default VisKnowledgeSpaceWindow;
