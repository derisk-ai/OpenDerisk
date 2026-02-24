import styled from 'styled-components';

export const AgentContainer = styled.div`
  display: flex;
  width: 100%;
  height: 100%;
  flex: 1;
  min-height: 0;
  flex-direction: row;
  border-radius: 8px;
  padding: 8px;
  border: solid #ddd 1px;
  background-color: #ffffff;
`;

export const AgentContent = styled.div`
  width: 100%;
  height: 100%;
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
