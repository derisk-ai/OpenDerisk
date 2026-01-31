import styled from 'styled-components';

export const DThinkCardWrap = styled.div`
  .d-thinking-title {
    font-size: 16px;
    background: rgb(245, 245, 245);
    font-size: 14px;
    display: inline-flex;
    padding: 6px 10px;
    border-radius: 6px;
    justify-content: center;
    align-items: center;
    cursor: pointer;
    user-select: none;
  }
  .d-icon {
    transform: rotate(90deg);
    transition: all 0.3s ease;
  }
  .rotate {
    transform: rotate(0);
    transition: all 0.3s ease;
  }
`;

