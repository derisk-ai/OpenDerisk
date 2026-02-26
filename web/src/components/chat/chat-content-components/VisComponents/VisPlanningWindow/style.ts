import styled from 'styled-components';

export const VisPWCardWrapper = styled.div`
  padding: 8px;
  background: transparent;
`;

export const PlanItemWrap = styled.div`
  width: 100%;
  background: #ffffff;
  border-radius: 8px;
  padding: 8px 12px;
  margin: 0 0 0 4px;
  border: 1px solid #e2e8f0;
  transition: all 0.15s ease;

  &:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
  }
`;

export const PlanTitle = styled.div`
  height: 22px;
  line-height: 22px;
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;

  span {
    color: #3b82f6;
    margin-left: 6px;
    font-weight: 500;
  }
`;

export const PlanDescription = styled.div`
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
`;