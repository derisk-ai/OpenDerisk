import styled from 'styled-components';

export const FolderContainer = styled.div`
  max-width: 320px;
  padding: 8px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fafafa;
  overflow-y: auto;
  max-height: 400px;
`;

export const FolderList = styled.ul`
  list-style: none;
  margin: 0;
  padding: 0;
`;

export const FolderItemStyled = styled.li`
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #1a1a1a;
  transition: background 0.2s;

  &:hover {
    background: #f0f0f0;
  }

  .title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
`;
