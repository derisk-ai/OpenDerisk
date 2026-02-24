import styled from 'styled-components';

export const AttachListWrap = styled.div`
  width: 100%;
  margin: 8px 0;
  background: #fafafa;
  border-radius: 8px;
  overflow: hidden;

  .attachListHeader {
    padding: 12px 16px;
    background: rgba(27, 98, 255, 0.03);
    border-bottom: 1px solid rgba(27, 98, 255, 0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;

    .folderIcon {
      font-size: 18px;
      color: #1b62ff;
    }

    .title {
      font-size: 14px;
    }
  }

  .description {
    display: block;
    padding: 8px 16px;
    font-size: 12px;
    line-height: 1.5;
  }

  .attachList {
    padding: 0;
  }
`;

export const AttachListItem = styled.div`
  padding: 10px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: background-color 0.2s;

  &:hover {
    background: rgba(27, 98, 255, 0.02);
  }

  &:last-child {
    border-bottom: none;
  }
`;

export const FileItemContent = styled.div`
  flex: 1;
  min-width: 0;

  .fileIcon {
    font-size: 20px;
    color: #1890ff;
    flex-shrink: 0;
  }

  .fileInfo {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .fileName {
    font-size: 13px;
    font-weight: 500;
    color: #262626;
  }

  .fileMeta {
    .fileSize {
      font-size: 12px;
    }

    .fileTypeTag {
      background: rgb(27 98 255 / 10%);
      border-radius: 4px;
      color: #1b62ff;
      font-size: 11px;
      padding: 0 4px;
      height: 18px;
      line-height: 18px;
    }
  }

  .fileDesc {
    font-size: 12px;
    line-height: 1.4;
    max-width: 400px;
  }
`;

export const FileItemActions = styled.div`
  flex-shrink: 0;
  padding-left: 12px;

  .ant-btn {
    color: #8c8c8c;

    &:hover {
      color: #1b62ff;
    }
  }
`;