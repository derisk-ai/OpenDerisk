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
    padding: 2px 8px;
    display: inline-flex;
    align-items: center;

    .attachIcon {
      font-size: 14px;
      margin-right: 2px;
    }
  }
`;

export const AttachItemWrap = styled.div`
  background: rgb(27 98 255 / 6%);
  border: 1px solid rgb(27 98 255 / 20%);
  border-radius: 6px;
  padding: 4px 10px;
  display: inline-flex;
  align-items: center;
  transition: background-color 0.2s, border-color 0.2s;

  &:hover {
    background: rgb(27 98 255 / 10%);
    border-color: rgb(27 98 255 / 30%);
  }

  .attachIcon {
    font-size: 15px;
    color: #1b62ff;
  }

  .attachName {
    font-size: 13px;
    color: #262626;
  }

  .attachSize {
    font-size: 12px;
  }

  .attachAction {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 4px;
    color: #8c8c8c;
    cursor: pointer;
    transition: color 0.2s, background-color 0.2s;
    margin-left: 4px;

    &:hover {
      color: #1b62ff;
      background: rgb(27 98 255 / 10%);
    }
  }
`;