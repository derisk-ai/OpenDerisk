import styled from 'styled-components';

export const VisConfirmCardWrap = styled.div`
  width: 100%;
  min-width: 100px;
  padding: 6px;
  background: transparent;

  .card-content {
    width: 100%;
    min-width: 100px;
    white-space: pre-wrap;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: start;
    background-image: linear-gradient(174deg, #ffffff 4%, #ffffff4d 42%, #ffffff00 87%);
    background-color: #ffffff;
    padding: 16px;
    box-shadow: 0px 2px 6px 0px #000a1a08;
    border-radius: 12px;

    .confirm-title {
      font-size: 14px;
      color: #000a1ae3;
      line-height: 24px;
      font-weight: 500;
    }
    .confirm-footer {
      height: 32px;
      width: 100%;
      font-size: 14px;
      line-height: 32px;
      color: #000a1a78;
      display: flex;
      justify-content: space-between;
      flex-direction: row-reverse;
      button {
        border-radius: 8px;
        padding: 8px;
        height: 32px;
      }
    }
    .whitespace-normal {
      width: 100%;
    }
  }
`;
