import styled from '@emotion/styled';

export const VisStatusNotificationWrap = styled.div`
  margin: 8px 0;
  animation: slideIn 0.3s ease-out;
  
  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  .ant-progress {
    margin: 0;
  }
  
  .ant-progress-text {
    font-size: 12px;
  }
`;