import styled from 'styled-components';

export const VisUitilDiv = styled.div`
  .vis-utils-markdown {
    position: relative;
    display: flex;
    flex-direction: column;
    .code-copy-btn {
      align-self: flex-end;
      position: absolute;
      top: 0;
      right: 0;
      background: #fff;
      visibility: hidden;
      font-size: 18px;
      .ant-typography-copy {
        color: gray !important;
      }
    }
    .inner-chat-gpt-vis {
      overflow: auto;
    }
    &:hover {
      .code-copy-btn {
        visibility: visible;
      }
    }
  }
  .ant-collapse-content-box {
    padding-top: 0px !important;
  }
`;
