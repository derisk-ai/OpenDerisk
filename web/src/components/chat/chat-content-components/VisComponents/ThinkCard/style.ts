import styled from 'styled-components';

export const ThinkCardWrap = styled.div`
  margin: 6px 0;
  margin-top: 0;
  .ant-collapse-header {
    // padding: 8px 12px !important;
    line-height: 1em !important;
    padding: 12px !important;
    align-items: center !important;

    .ant-collapse-expand-icon {
      padding-inline-end: 0 !important;
    }
  }

  .ant-collapse-content-box {
    padding: 0 12px !important;
  }
  .ant-collapse-content {
    .ant-bubble-content {
      margin: 0;
      background: none;
    }
  }
  .ant-collapse-item {
    border-radius: 16px !important;
    background: rgba(0, 0, 0, 0.06);
    display: inline-block;
  }
  .ant-collapse-item-active {
    margin-bottom: 0;
    display: block;
  }
`;
