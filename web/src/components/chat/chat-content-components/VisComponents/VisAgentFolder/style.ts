import styled from 'styled-components';

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
  padding: 5px 8px;
  cursor: ${(props) => (props.$hasChildren ? 'pointer' : 'default')};
  border-radius: 6px;
  transition: background 0.15s ease;

  &:hover {
    background-color: ${(props) =>
      props.$isSelected ? '#dbeafe' : '#e8ecf1'};
  }

  background-color: ${(props) =>
    props.$isSelected ? '#eff6ff' : 'transparent'};
`;

export const HeaderContent = styled.div`
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  gap: 6px;
`;

export const AvatarWrapper = styled.div`
  position: relative;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;

  img {
    width: 100%;
    height: 100%;
    object-fit: contain;
  }
`;

export const AvatarImage = styled.img`
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
  border: 1px solid #e2e8f0;
`;

export const TitleText = styled.h3`
  font-size: 12px;
  font-weight: 500;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 0;
`;

export const ChildrenContainer = styled.div`
  margin-top: 1px;
  margin-left: 10px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding-left: 6px;
`;

export const IndentArea = styled.div`
  padding-left: 2px;
`;

export const FolderContainer = styled.div`
  width: 100%;
  height: 100%;
  padding: 8px;
  background: transparent;
  overflow-y: auto;
`;

export const FolderList = styled.ul`
  list-style: none;
  margin: 0;
  padding: 0;
`;

export const FolderItemStyled = styled.li`
  display: flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: #334155;
  transition: background 0.15s ease;

  &:hover {
    background: #e8ecf1;
  }

  .title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }
`;

export const TreeContainer = styled.div`
  width: 100%;
  height: 100%;
  padding: 4px;
  background: transparent;
  overflow-y: auto;
  
  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 2px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
`;