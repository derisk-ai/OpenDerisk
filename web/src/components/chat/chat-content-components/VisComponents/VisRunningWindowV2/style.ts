import styled from 'styled-components';

export const WorkSpaceContainer = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: transparent;
  overflow: hidden;
`;

export const WorkSpaceHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
  flex-shrink: 0;
`;

export const WorkSpaceTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  
  .title-text {
    font-size: 13px;
    font-weight: 600;
    color: #334155;
  }
`;

export const WorkSpaceControls = styled.div`
  display: flex;
  align-items: center;
  gap: 2px;
`;

export const WorkSpaceBody = styled.div`
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: transparent;
`;

export const ExplorerPanel = styled.div<{ $visible?: boolean }>`
  width: 240px;
  min-width: 240px;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px;
  background: transparent;
  border-right: 1px solid #f1f5f9;
  flex-shrink: 0;
  display: ${(props) => (props.$visible ? 'block' : 'none')};
  
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

export const ContentPanel = styled.div<{ $explorerVisible?: boolean }>`
  flex: 1;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
`;

export const ContentHeader = styled.div`
  flex-shrink: 0;
  padding: 8px 12px;
  border-bottom: 1px solid #f1f5f9;
  background: transparent;
  
  .time-text {
    font-size: 11px;
    color: #64748b;
    font-weight: 500;
  }
`;

export const ContentBody = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px;
  background: transparent;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
  
  /* 确保 GPTVis 内容正确滚动 */
  & > div {
    max-width: 100%;
  }
`;

export const IconButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  color: #64748b;
  font-size: 13px;
  transition: all 0.15s ease;
  
  &:hover {
    background: #e2e8f0;
    color: #334155;
  }
  
  &:active {
    background: #cbd5e1;
  }
`;

export const AgentContainer = WorkSpaceContainer;
export const AgentContent = ContentBody;
export const FolderContainer = ExplorerPanel;
export const HeaderContainer = WorkSpaceHeader;