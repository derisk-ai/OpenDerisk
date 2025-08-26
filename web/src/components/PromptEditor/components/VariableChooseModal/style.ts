import { styled } from 'styled-components';
interface IProps {
  $position?: {
    top: number;
    left: number;
  };
}

export const VariableChooseModalStyle = styled.div<IProps>`
  position: fixed;
  top: ${(props) => props.$position?.top}px;
  left: ${(props) => props.$position?.left}px;
  z-index: 1000;
  max-height: 220px;
  overflow-y: auto;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0px 9px 28px 8px #0000000d, 0px 6px 16px 0px #00000014,
    0px 3px 6px -4px #0000001f;
  overflow-x: hidden;
  .variable_choose_wrapper {
    width: 380px;
    padding: 8px;
    .variable_choose_item {
      height: 40px;
      padding: 0 12px;
      border-radius: 10px;
      margin-bottom: 4px;
      cursor: pointer;
      .variable_choose_item_title {
        font-size: 14px;
        color: #525964;
        line-height: 22px;
        font-weight: 600;
        flex-shrink: 0;
      }
      .variable_choose_item_desc {
        font-size: 12px;
        color: #000a1a78;
        line-height: 22px;
      }
      .variable_choose_item_action {
        display: none;
        color: #1b62ff;
        flex-shrink: 0;
      }
      .ant-typography {
        margin-bottom: 0;
      }
    }
    .variable_choose_item:hover {
      background: #f4f4f6;
      .variable_choose_item_action {
        display: block;
      }
    }
  }
`;
