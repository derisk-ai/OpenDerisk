import styled from 'styled-components';

export const VisCodeIdeDiv = styled.div`
  width: 100%;
  .ant-tabs-nav::before {
    display: none;
  }
  .CodePreviewClass {
      pre::-webkit-scrollbar {
        height: 8px;
        display: block;
      }
      pre::-webkit-scrollbar-track {
        background: transparent;
        border-radius: 4px;
      }
      pre::-webkit-scrollbar-thumb {
        background: #888;
        border-radius: 4px;
        &:hover {
          background: #333;
        }
      }
  }
`;

export const VisPureCode = styled.div`
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
`;
