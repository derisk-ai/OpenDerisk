import styled from 'styled-components';

export const VisAuthorizationCardWrap = styled.div`
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
    background-image: linear-gradient(174deg, #fff8f0 4%, #ffffff4d 42%, #ffffff00 87%);
    background-color: #ffffff;
    padding: 16px;
    box-shadow: 0px 2px 6px 0px #000a1a08;
    border-radius: 12px;
    border: 1px solid #ffd591;

    .auth-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
      
      .auth-icon {
        font-size: 18px;
        color: #fa8c16;
      }
      
      .auth-title {
        font-size: 14px;
        color: #000a1ae3;
        line-height: 24px;
        font-weight: 500;
      }
    }
    
    .tool-info {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
      
      .tool-name {
        font-weight: 600;
        font-size: 14px;
        color: #1890ff;
      }
    }
    
    .risk-factors {
      margin: 8px 0;
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
    
    .arguments-section {
      width: 100%;
      margin: 8px 0;
      
      .arguments-content {
        max-height: 200px;
        overflow: auto;
        background-color: #f5f5f5;
        padding: 12px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 12px;
        
        .arg-item {
          margin-bottom: 8px;
          
          .arg-key {
            color: #8c8c8c;
          }
          
          .arg-value {
            margin: 4px 0 0 16px;
            white-space: pre-wrap;
            word-break: break-all;
          }
        }
      }
    }
    
    .session-grant-option {
      margin: 12px 0;
    }

    .auth-footer {
      height: 32px;
      width: 100%;
      font-size: 14px;
      line-height: 32px;
      color: #000a1a78;
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      
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
