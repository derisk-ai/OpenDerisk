import styled from 'styled-components';

/* 树形目录（renderRoleTree） */
export const FolderItemContainer = styled.div`
  display: flex;
  flex-direction: column;
`;

export const RoleHeader = styled.div<{
  $isSelected: boolean;
  $hasChildren: boolean;
}>`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.375rem;
  cursor: ${(props) => (props.$hasChildren ? 'pointer' : 'default')};
  border-radius: 0.375rem;
  transition: background-color 0.2s ease;

  &:hover {
    background-color: ${(props) =>
      props.$isSelected ? 'rgba(59, 130, 246, 0.1)' : 'rgba(0, 0, 0, 0.1)'};
  }

  background-color: ${(props) =>
    props.$isSelected ? 'rgba(59, 130, 246, 0.1)' : 'transparent'};
`;

export const HeaderContent = styled.div`
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  gap: 0.25rem;
`;

export const AvatarWrapper = styled.div`
  position: relative;
  width: 1rem;
  height: 1rem;
  flex-shrink: 0;
  font-size: 0.75rem;
  text-align: center;
  line-height: 1rem;
`;

export const AvatarImage = styled.img`
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
  border: 1px solid rgba(59, 130, 246, 0.2);
`;

export const TitleText = styled.h3`
  font-size: 14px;
  color: #4f5866;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

export const ChildrenContainer = styled.div`
  margin-top: 0.125rem;
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
`;

export const IndentArea = styled.div`
  margin-left: 0.125rem;
  padding-left: 0.25rem;
`;

/* 兼容：扁平列表 / explorer 容器 */
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
