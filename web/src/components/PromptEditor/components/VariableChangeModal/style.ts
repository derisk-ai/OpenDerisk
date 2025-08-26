import { styled } from 'styled-components';
import { Modal } from 'antd';

export const VariableChangeModalWrapper = styled(Modal)`
  .descriptions {
    font-size: 12px;
    color: #000a1a78;
    line-height: 22px;
  }

  .ant-modal-content {
    width: 480px;
    max-height: 640px;
    display: flex;
    flex-direction: column;
  }

  .ant-modal-content,
  .ant-modal-title {
    background: #eceff6;
  }

  .ant-modal-header {
    margin-bottom: 16px;
  }

  .ant-modal-body {
    overflow-y: auto;
  }

  .ant-collapse-item {
    background: #fff;
    border-radius: 10px !important;
    border-bottom: none;
    margin-bottom: 12px;
  }

  .ant-collapse-header {
    padding: 12px !important;
  }

  .ant-collapse-header-text {
    overflow-x: hidden;
  }

  .ant-popover .ant-popover-content {
    position: relative;
    right: 40px;
  }

  .ant-popover-inner {
    padding: 0 !important;
  }

  .ant-btn-primary {
    width: 40px;
    height: 24px;
    border-radius: 6px;

    span {
      font-size: 12px;
      color: #ffffff;
      line-height: 20px;
      text-align: center;
      font-weight: 500;
      letter-spacing: -1px;
    }
  }

  .hover-button {
    display: none;
  }

  .ant-collapse-item:hover .hover-button {
    display: inline-flex;
    height: 22px;
  }
`;
