import styled from 'styled-components';

export const AgentContainer = styled.div`
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background-color: #ffffff73;
`;

export const AgentContent = styled.div`
  width: 100%;
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  .VisContentCardClass {
    background-color: transparent;
    padding: 0;
    .VisStepCardWrap {
      background-color: transparent;
    }
  }
  .thinkLinkBtn {
    display: none;
  }
`;
