import { styled } from 'styled-components';

export const CustomPopoverWrapper = styled.div`
  max-width: 287px;
  /* padding: 4px; */
  /* background-color: #fff; */
  .custom_popover_content_name {
    font-size: 14px;
    color: #525964;
    line-height: 22px;
    font-weight: 600;
    display: flex;
    justify-content: space-between;
    align-items: center;
    .custom_popover_content_switch {
      color: #1b62ff;
      cursor: pointer;
      font-size: 14px;
      font-weight: normal;
      margin-left: 8px;
    }
  }
  .custom_popover_content_desc {
    font-size: 12px;
    color: #000a1a78;
    line-height: 22px;
  }
  .custom_popover_content_code {
    max-height: 226px;
    background: #f4f4f6;
    border-radius: 10px;
    margin-top: 8px;
    .tech-highlight-light {
      background: #f4f4f6;
    }
  }
`;

export const CustomPluginContent = styled.div`
  display: inline-flex;
  align-items: center;
  background: #e6f4ff;
  border: 1px solid #91caff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  color: #1677ff;
  line-height: 20px;
  padding: 0 6px;
  margin: 0 2px;
  vertical-align: baseline;
  transition: all 0.2s;
  
  &:hover {
    background: #bae0ff;
    border-color: #69b1ff;
  }

  img {
    margin-right: 4px;
    width: 14px !important;
    height: 14px !important;
  }
`;

export const VariableRenderWrapper = styled.span`
  .ant-popover-inner {
    background-image: linear-gradient(114deg, #3595ff 12%, #185cff 98%);
  }
  .ant-popover-arrow::before {
    background: #3595ff;
  }
  .init_popover_content {
    width: 205px;
    /* padding: 4px; */
    font-size: 14px;
    color: #ffffff;
    line-height: 24px;
    font-weight: 500;
    .ant-btn {
      color: #1b62ff;
      width: 100%;
      margin-top: 8px;
    }
  }
`;
