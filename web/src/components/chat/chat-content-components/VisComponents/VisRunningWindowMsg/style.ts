import styled from 'styled-components';

export const VisRWMsgCardWrap = styled.div`
  width: 100%;
  height: 100%;
  min-width: 100px;
  white-space: normal;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: start;
  margin: 0px 0;
  border: 2px solid #f5f7fa !important;
  background-color: #ffffff;
  overflow-x: auto;
  border-radius: 12px;

  .ant-divider-horizontal {
    margin: 0;
  }
`;

export const VisRWMsgCardHeader = styled.div`
  width: 100%;
  line-height: 32px;
  font-size: 12px;
  padding: 4px 12px;
  background-color: #f5f7fa;
`;
