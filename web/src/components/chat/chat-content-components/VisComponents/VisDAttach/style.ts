import styled from 'styled-components';

export const AttachWrap = styled.div`
  width: 100%;
  margin-top: 8px;
  padding: 8px 0;

  .attachItem {
    background: rgb(27 98 255 / 10%);
    border-radius: 4px;
    color: #1b62ff;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;

    &:hover {
      background: rgb(27 98 255 / 20%);
    }

    .fileSize {
      font-size: 10px;
      opacity: 0.7;
    }
  }

  /* 列表模式样式 */
  .attachList {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 400px;
    overflow-y: auto;
  }
`;

export const AttachListItem = styled.div`
  display: flex;
  align-items: center;
  padding: 12px;
  background: #f5f5f5;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: #e8e8e8;
    transform: translateX(4px);
  }

  .fileInfo {
    flex: 1;
    min-width: 0;
    margin-left: 12px;
  }

  .fileName {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }

  .nameText {
    font-weight: 500;
    color: #262626;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .mimeType {
    font-size: 10px;
    color: #8c8c8c;
    background: #e6f7ff;
    padding: 2px 6px;
    border-radius: 4px;
  }

  .fileSize {
    font-size: 12px;
    color: #8c8c8c;
  }

  .fileActions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .actionIcon {
    font-size: 16px;
    color: #595959;
    cursor: pointer;
    padding: 4px;
    transition: color 0.2s ease;

    &:hover {
      color: #1b62ff;
    }
  }
`;

export const FileIconWrapper = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: white;
  border-radius: 8px;
  flex-shrink: 0;

  .anticon {
    font-size: 24px;
    color: #1b62ff;
  }
`;