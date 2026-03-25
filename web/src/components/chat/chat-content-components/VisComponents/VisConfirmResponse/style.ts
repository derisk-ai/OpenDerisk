import styled from 'styled-components';

export const VisConfirmResponseWrap = styled.div`
  width: 100%;
  padding: 4px 6px;

  .response-card {
    background: #f6ffed;
    border: 1px solid #b7eb8f;
    border-radius: 8px;
    padding: 12px 16px;

    .response-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;

      .check-icon {
        color: #52c41a;
        font-size: 16px;
      }

      .response-title {
        font-size: 14px;
        color: #237804;
      }

      .response-time {
        margin-left: auto;
        font-size: 12px;
      }
    }

    .response-question {
      margin-bottom: 8px;
      font-size: 13px;
    }

    .response-content {
      .response-selection {
        display: flex;
        align-items: center;
        gap: 8px;

        .selection-tag {
          font-size: 13px;
        }

        .selection-desc {
          font-size: 12px;
        }
      }

      .response-input {
        margin-top: 4px;
        font-size: 13px;
        color: #333;
      }
    }
  }
`;
