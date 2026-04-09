import styled from 'styled-components';

export const VisAgentPlanCardWrap = styled.div`
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 3px 0;

  &.selected {
    .header-plan {
      background: #eff6ff;
      border-color: #bfdbfe;
    }
  }

  .header {
    width: 100%;
    border-radius: 8px;
    padding: 8px 10px;
    color: #334155;
    background: transparent;
    transition: background 0.15s ease;
  }

  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;

    .content-header {
      display: flex;
      justify-content: flex-start;
      align-items: center;
      width: 100%;
      gap: 6px;

      .task-icon {
        width: 14px;
        height: 14px;
        flex-shrink: 0;
      }
    }

    .result {
      display: flex;
      flex-direction: column;
      width: 100%;
      border-radius: 6px;
    }
  }

  .title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
    color: #1e293b;
  }

  .description {
    font-size: 12px;
    color: #64748b;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .status {
    color: #475569;
    margin-left: 8px;
    border-radius: 10px;
    padding: 2px 8px;
    background: #f1f5f9;
    font-size: 11px;
    font-weight: 500;
  }

  .expand-btn {
    padding: 0;
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s ease;
    font-size: 12px;
    color: #94a3b8;
    border-radius: 4px;

    &:hover {
      color: #475569;
      background: #f1f5f9;
    }

    &.collapsed {
      transform: rotate(-90deg);
    }

    &.expanded {
      transform: rotate(0deg);
    }
  }

  .divider {
    margin: 0;
    border-color: #f1f5f9;
  }

  .markdown-content {
    width: 100%;
    animation: fadeIn 0.2s ease;
  }

  .markdown-content-wrap {
    width: 100%;
    background: transparent;
    padding: 6px 0 0 0;
  }

  .markdown-content-wrap-stage {
    border-left: 2px solid #e2e8f0;
    padding-left: 12px;
    margin-left: 6px;
  }

  .stage-icon-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    background: #eff6ff;
    border-radius: 50%;
    width: 18px;
    height: 18px;
  }

  .title-text {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
  }

  .result-title {
    display: flex;
    justify-content: space-between;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
    transition: background 0.15s ease;
    cursor: pointer;
    border-radius: 6px;
    padding: 2px 4px;

    &:hover {
      background: #f8fafc;
    }
  }

  .result-icon {
    width: 14px;
    height: 14px;
    margin-right: 4px;
  }

  .result-content {
    font-size: 12px;
    max-height: 200px;
    overflow: auto;
  }

  .time-info {
    display: flex;
    flex: 1;
    justify-content: flex-end;
    color: #94a3b8;
    font-size: 11px;
    gap: 8px;
  }

  .content-wrapper {
    width: 100%;
  }

  .time-cost {
    font-weight: 500;
    color: #64748b;
  }

  .task-description {
    color: #64748b;
    margin-top: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
    font-size: 12px;
  }

  .task-description-level-0 {
    font-size: 13px;
  }

  .task-description-level-other {
    font-size: 12px;
  }

  .agent_name {
    display: flex;
    align-items: center;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .agent_name-badge {
    background: #f1f5f9;
    padding: 2px 8px;
    margin: 0 4px 0 2px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 500;
    color: #475569;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .header-plan {
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(226, 232, 240, 0.6);
    border-radius: 10px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);

    &:hover {
      background: rgba(255, 255, 255, 0.85);
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
  }

  .header-task {
    width: fit-content;
    max-width: 85%;
    background: rgba(255, 255, 255, 0.6);
    border: 1px solid rgba(226, 232, 240, 0.5);
    border-radius: 16px;
    padding: 5px 12px;
    transition: all 0.15s ease;
    cursor: pointer;

    &:hover {
      background: rgba(255, 255, 255, 0.8);
    }

    .task-icon {
      width: 13px;
      height: 13px;
      margin-right: 4px;
    }

    .title-task-with-markdown {
      flex: 1;
      min-width: 0;
      overflow: hidden;

      .title-text-ellipsis:first-child {
        flex-shrink: 1;
        max-width: none;
      }
    }

    .task-title-markdown-line {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 100%;
    }

    .task-title-description-line {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 100%;
      color: #64748b;
      font-size: 11px;
    }
  }

  .header-agent {
    background: rgba(255, 255, 255, 0.75);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(226, 232, 240, 0.6);
    border-radius: 10px;
    padding: 10px 12px;
    transition: all 0.15s ease;
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);

    &:hover {
      background: rgba(255, 255, 255, 0.85);
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }

    .task-icon {
      margin-right: 4px;
    }

    .agent_name-leading {
      flex: 1;
      min-width: 0;
      font-size: 14px;
      font-weight: 600;
      max-width: none;

      .avatar-shrink {
        flex-shrink: 0;
      }

      .agent_name-badge {
        font-size: 13px;
        font-weight: 500;
        padding: 2px 10px;
      }
    }
  }

  .header-stage {
    background: transparent;
    border-radius: 6px;
    padding: 6px 8px 6px 0;
    transition: background 0.15s ease;
    cursor: pointer;

    &:hover {
      background: transparent;
    }

    .content-header {
      padding-left: 0;
    }

    .task-icon {
      width: 16px;
      margin-right: 6px;
      margin-left: 0;
    }

    .title-text {
      font-size: 13px;
      font-weight: 500;
    }
  }

  .header-default {
  }

  .title-container {
    font-size: 13px;
  }

  .title-level-0 {
    font-size: 14px;
    font-weight: 600;
  }

  .title-level-1 {
    font-size: 13px;
    font-weight: 500;
  }

  .title-level-2 {
    font-size: 12px;
    font-weight: 500;
  }

  .title-text-ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
    flex: 1;
  }

  .title-flex-container {
    display: flex;
    align-items: center;
    width: 100%;
    overflow: hidden;
    justify-content: space-between;
  }

  .result-title-container {
    font-size: 13px;
  }

  .result-title-outer {
    font-size: 13px;
  }

  .result-title-inner {
    font-size: 12px;
  }

  .result-title-flex {
    display: flex;
    overflow: hidden;
    align-items: flex-start;
  }

  .result-icon-style {
    flex-shrink: 0;
  }

  .result-icon-outer {
    margin-top: 2px;
  }

  .avatar-shrink {
    flex-shrink: 0;
  }

  .button-shrink {
    flex-shrink: 0;
  }

  .status-badge {
    background: #f1f5f9;
    font-size: 11px;
    flex-shrink: 0;
    font-weight: 500;
    border-radius: 10px;
    padding: 2px 8px;
  }

  .flex-container {
    display: flex;
    width: 100%;
    justify-content: space-between;
    align-items: center;
  }

  .task-description-container {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;