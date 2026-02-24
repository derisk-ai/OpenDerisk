import styled from 'styled-components';

export const VisDocCardWrap = styled.div`
  width: 100%;
  background: #ffffff73;
  box-shadow: inset 1px 0px 0 0px #000a1a12;

  .blue-double-ring {
    width: 16px;
    height: 16px;
    border: 2px solid #3498db;
    border-radius: 50%;
    background-color: white;
    position: relative;
    margin-right: 8px;
  }
  .blue-double-ring::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 8px;
    height: 8px;
    border: 2px solid #3498db;
    border-radius: 50%;
    background-color: white;
  }
  .doc-title {
    font-size: 20px;
    color: #000a1a;
    line-height: 32px;
    text-align: center;
    font-weight: 600;
    border-bottom: 2px solid #000a1a12;
    padding-bottom: 16px;
  }
  .doc-subtitle {
    font-size: 18px;
    color: #000a1a;
    line-height: 26px;
    font-weight: 600;
    margin: 24px 0;
  }
  .doc-section {
    margin-top: 16px;
    font-size: 14px;
    color: #000a1a;
    line-height: 20px;
    font-weight: 600;
    display: flex;
    align-items: center;
  }
  .doc-paragraph {
    font-size: 1rem;
    line-height: 1.6;
    margin-bottom: 1rem;
    color: #34495e;
  }
  .titleActionWrap {
    width: 100%;
    height: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 15px;
    font-weight: 666;
  }
  .reGenerate-button {
    font-size: 14px;
    color: #000a1a;
    font-weight: normal;
  }
  .title-bottom-divider {
    width: 80px;
    height: 5px;
    background: #1b62ff;
    margin: 0 auto;
    position: absolute;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
  }
`;
