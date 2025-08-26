import { styled } from 'styled-components';

interface IProps {
  $position?: {
    top: number;
    left: number;
  };
}
/**
 * 关联知识区域样式
 */
export const MentionPanelWrapper = styled.div<IProps>`
  position: fixed;
  top: ${(props) => props.$position?.top}px;
  left: ${(props) => props.$position?.left}px;
  z-index: 100;
  width: 320px;
  height: 318px;
  border-radius: 12px;
  background-color: #fff;
  .ant-tabs-nav-wrap {
    padding: 0 20px;
    height: 40px;
  }
  .ant-tabs-nav {
    margin-bottom: 0;
  }
  .empty_content_wrapper {
    height: 262px;
    padding: 0 8px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    .empty_description {
      font-size: 14px;
      color: #000a1a78;
      line-height: 22px;
      text-align: center;
    }
  }
  .content_wrapper {
    height: 262px;
    padding: 4px 8px;
    overflow-x: hidden;
    overflow-y: auto;

    .content_item {
      padding: 7px 11px;
      cursor: pointer;
      border-radius: 10px;
      .content_item_left {
        display: flex;
        align-items: center;
        overflow: hidden;
        .content_item_icon {
          width: 24px;
          height: 24px;
          margin-right: 8px;
        }
        .content_item_title {
          font-size: 14px;
          color: #1c2533;
          line-height: 22px;
        }
      }
      .content_item_actions {
        display: none;
        color: #1b62ff;
        flex-shrink: 0;
        cursor: pointer;
      }
      .ant-typography {
        margin-bottom: 0;
      }
    }
    .content_item:hover {
      background: #f4f4f6;
      .content_item_actions {
        display: inline-flex;
      }
    }
  }
`;
