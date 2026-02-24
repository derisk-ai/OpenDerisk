import styled from 'styled-components';

export const VisLLMDiv = styled.div`
  .ant-descriptions {
    table {
      display: table !important;
    }
    .ant-descriptions-header {
      margin-bottom: 8px;
    }
    .ant-descriptions-item {
      padding-inline-end: 8px;
      padding-bottom: 2px;
    }
  }

  .vis-llm-coll-header {
    padding-left: 0 !important;
    align-items: center !important;
    display: none !important;
  }

  .vis-llm-col-content{
    .ant-collapse-content-box{
      // padding: 0 !important;
      max-height: 70vh;
      margin-top: 8px;
      margin-bottom: 8px;
      background: #fafafa;
      overflow: auto;
      pre {
        margin-top: 0 !important;
      }
    }
  }
`;
