import styled from 'styled-components';

export const AgentContainer = styled.div`
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  background-color: #ffffff73;
  position: relative;
  .ant-tabs-nav {
    margin: 0;
    background-color: #F1F5F9;
    border-radius: 4px;
    .ant-tabs-tab {
      border: 1px solid #F1F5F9;
    }
  }
  .ant-tabs {
    height: 100%;
  }
  .ant-tabs-content {
    height: 100%;
  }
  .ant-tabs-tabpane {
    height: 100%;
  }
`;

export const AgentTabsContainer = styled.div`
  width: 100%;
  overflow-x: auto;
  
  &::-webkit-scrollbar {
    display: none;
  }

  /* -webkit-mask-image: linear-gradient(to right, 
      rgba(0, 0, 0, 0), 
      rgba(0, 0, 0, 0) 150px, 
      rgba(0, 0, 0, 1) 170px, 
      rgba(0, 0, 0, 1) 80%, 
      rgba(0, 0, 0, 0));
  mask-image: linear-gradient(to right,
      rgba(0, 0, 0, 0),
      rgba(0, 0, 0, 0) 150px, 
      rgba(0, 0, 0, 1) 170px,
      rgba(0, 0, 0, 1) 80%,
      rgba(0, 0, 0, 0)); */
  -webkit-mask-image: linear-gradient(to right, 
      rgba(0, 0, 0, 1), 
      rgba(0, 0, 0, 1) 90%, 
      rgba(0, 0, 0, 0) 95%,
      rgba(0, 0, 0, 0)) ;
  mask-image: linear-gradient(to right,
      rgba(0, 0, 0, 1),
      rgba(0, 0, 0, 1) 90%,
      rgba(0, 0, 0, 0) 95%,
      rgba(0, 0, 0, 0)) ;
`

export const AgentTabHeader = styled.div`
  display: flex;
  flex-direction: row;
  align-items: center;
  min-width: max-content;
 // margin-left: 150px;
`

export const AgentTab = styled.div`
  color: #000a1ae3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;

  img {
    display: inline-flex;
    width: 25px;
    max-width: 25px;
    height: 25px;
  }
`;

export const AgentTabSmall = styled.div`
  max-width: 200px;
  height: 36px;
  font-size: 14px;
  line-height: 22px;
  vertical-align: middle;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
  display: flex;
  justify-content: start;
  align-items: center;

  background: #ffffff00;
  border: 1px solid #000a1a29;
  border-radius: 8px;
  padding: 8px;
  margin: 16px 8px;
`;

export const RunningImage = styled.div`
  display: inline-block;
  width: 25px;
  height: 25px;
  border-radius: 12px;
  padding: 3px;
  margin-right: 4px;
  margin-bottom: 2px;

  img {
    display: inline-flex;
    width: 25px;
    height: 25px;
  }
`;

export const AgentContent = styled.div`
  width: 100%;
  flex: 1;
  /* padding: 12px; */
  overflow-y: auto;

  .VisContentCardClass {
    background-color: transparent;
    padding: 0;

    .VisStepCardWrap {
      background-color: transparent;
    }
  }
  .thinkLinkBtn {
    display: none;
  }
`;

export const WorkSpaceTitle = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  width: 150px;
  height: 64px;
  font-size: 18px;
  line-height: 64px;
  padding-left: 16px;
  font-size: 18px;

  img {
    display: inline;
    margin-right: 10px;
  }
`
