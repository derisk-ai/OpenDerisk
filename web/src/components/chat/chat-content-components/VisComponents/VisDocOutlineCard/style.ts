import styled from 'styled-components';

export const VisDocOutlinedWrap: any = styled.div`
  .reload-text {
    color: #1890ff;
    pointer-events: none;
    opacity: 0.5;
    cursor: not-allowed;
    img {
      height: 15px;
      margin-right: 4px;
      display: inline-block;
      vertical-align: -2px;
    }
  }
  .footer-btn {
    display: flex;
    gap: 16px;
  }
  .footer-text {
    color: #1b62ff;
    font-size: 14px;
    margin-bottom: 12px;
    span {
      margin-right: 6px;
    }
  }
  .article-title-container {
    text-align: center;
    margin-bottom: 16px;
    padding: 8px 0;
  }
  .article-title {
    font-size: 18px;
    color: #000a1a;
    font-weight: 600;
    margin-bottom: 0;
  }
  .document-outline-card {
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    border: none;
    padding: 4px 0;
    background-image: url('https://mdn.alipayobjects.com/huamei_5qayww/afts/img/A*AnNuRJzJj3MAAAAAQlAAAAgAeprcAQ/original'),
      linear-gradient(180deg, #ffffff 0%, #ffffff00 100%);
    background-repeat: no-repeat;
    background-position: top center;
    background-size: 100% auto;
    .ant-card-body {
      padding: 8px;
    }
    .ant-card-head {
      font-weight: 600;
      padding: 12px;
      min-height: 20px;
      font-size: 18px;
      color: #000a1a;
      text-align: center;
    }
    .card-header {
      display: flex;
      gap: 8px;
      align-items: center;
      .header-icon {
        color: #1890ff;
        margin-right: 4px;
        display: inline-block;
      }
    }
    .outline-collapse {
      background-color: #fafafa;
      .outline-panel {
        border-bottom: 1px solid #f0f0f0;
        &:last-child {
          border-bottom: none;
        }
      }
      .panel-header {
        display: flex;
        align-items: center;
        padding: 12px 0;
        cursor: pointer;
        .panel-icon {
          color: #bfbfbf;
          margin-right: 8px;
          font-size: 12px;
        }
        .panel-title {
          flex: 1;
          font-weight: 500;
          color: #666;
          transition: color 0.3s;
          &:hover {
            color: #1890ff;
          }
          &.active {
            color: #1890ff;
            font-weight: 600;
          }
        }
      }
      .panel-content {
        padding: 8px 0 16px 20px;
        border-left: 2px solid #e8e8e8;
        margin-left: 6px;
        p {
          margin-bottom: 0;
          font-size: 13px;
          line-height: 1.6;
        }
      }
    }
  }
  .outline-item {
    position: relative;
  }
  .outline-card {
    position: relative;
    z-index: 1;
    border: none !important;
    cursor: pointer;
    .outline-summary {
      max-height: 80px;
      overflow-y: auto;
    }
  }
`;
