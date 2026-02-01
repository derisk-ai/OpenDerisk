import styled from 'styled-components';

export const AgentContainer = styled.div`
  display: flex;
  width: 100%;
  height: 100%;
  flex-direction: row;
  border-radius: 8px;
  padding: 8px;
  border: solid #ddd 1px;
  background-color: #ffffff;
`;

export const AgentContent = styled.div`
  width: 100%;
  height: 100%;

  /* 为虚拟滚动列表重置样式 */
  & .vis-running-window-list {
    overflow-x: hidden !important;

    /* 确保react-window列表正常显示 */
    > div {
      outline: none;
      overflow-x: hidden;
      width: 100%;
      overflow-y: hidden;
    }

    /* 行样式 */
    .vis-running-window-row {
      width: 100%;
      border-bottom: 1px solid #f0f0f0;
      background: #fff;

      &:last-child {
        border-bottom: none;
      }

      &-header {
        flex-shrink: 0;
      }

      &-content {
        padding: 12px;
        min-height: 20px;
        overflow-x: hidden;
      }
    }
  }

  /* 简化渲染样式 */
  .simplified-render {
    display: flex;
    align-items: flex-start;
    padding: 12px;
    color: #666;
    font-size: 14px;
    line-height: 1.5;

    .markdown-preview {
      flex: 1;
      word-break: break-all;
      white-space: pre-wrap;
    }
  }

  /* 普通滚动模式 */
  padding: 12px;
  overflow-y: auto;
  scrollbar-width: none;
  ::-webkit-scrollbar {
    display: none;
  }
`;

export const FolderContainer = styled.div`
  max-width: 250px;
  width: 30%;
  height: 100%;
  overflow-y: auto;
  padding: 8px 4px;
  border-right: solid #ddd 1px;
  overflow-y: scroll;
  scrollbar-width: none;
  ::-webkit-scrollbar {
    display: none;
  }
`;

export const HeaderContainer = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 0 8px 0;
  border-bottom: 1px solid #d9d9d9;
  font-weight: 600;
  color: #1a1a1a;
  font-size: 14px;
  .controls button {
    padding: 4px 8px;
    font-size: 12px;
    cursor: pointer;
    border-radius: 4px;
    border: 1px solid #ccc;
    background: #fff;
    transition: all 0.2s;
    &:hover {
      background-color: #f5f5f5;
    }
  }
`;