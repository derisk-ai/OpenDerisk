import styled from 'styled-components';

export const VisAgentPlanCardWrap = styled.div`
  height: 100%;
  border-radius:16px;
  min-width: 100px;
  white-space: pre-wrap;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: start;
  padding: 4px 0;
  white-space: normal;


  .selected {
    background-color: #f5f5f5;
  }

  .header {
    width: 100%;
    border-radius: 6px;
    padding: 6px;
    color: #4f5866 ;
  }

  .header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;

    .content-header{
      display: flex;
      justify-content: flex-start;
      align-items: center;
      width: 100%;

      .task-icon{
        width:16px;
        margin-right: 2px;
      }
    }

    .result{
      display: flex;
      flex-direction: column;
      width: 100%;
      border-radius: 6px;
    }
  }

  .title{
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .description{
    font-size:12px;
    color: rgba(0, 0, 0, 0.65);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }

  .status {
    align-self: center;
    color:#000000cc;
    margin-left: 12px;
    border-radius: 6px;
    padding: 0px 8px
  }

  .expand-btn {
    padding: 0;
    width: 26px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s;
    font-size: 12px;

    &:hover {
      color: rgba(0, 0, 0, 0.65);
    }

    &.collapsed {
      transform: rotate(-90deg);
    }

    &.expanded {
      transform: rotate(0deg);
    }
  }

  .divider{
      margin: 0;
      border-width: 1px;
      border-color: rgba(0, 0, 0, 0.03);
  }

  .markdown-content {
    width: 100%;
    animation: fadeIn 0.3s ease-in-out;
  }

  .title-text {
    display:flex;
    align-items:center;
    justify-content: space-between;
  }

  .result-title {
    display: flex;
    justify-content: space-between;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
    transition: background-color 0.2s ease;
    cursor: pointer;

    &:hover {
      background-color: #f5f5f5;
      border-radius: 6px;
    }
  }

  .result-icon {
    width: 16px;
    height: 16px;
    margin-right: 4px;
    margin-top: 2px;
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
    color: #00000073;
    font-size: 12px;
  }

  .content-wrapper {
    width: 100%;
  }

  .time-cost {
    margin-left: 12px;
  }

  .task-description {
    color: rgba(0, 0, 0, 0.45);
    margin-bottom: 0px !important;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }

  .task-description-level-0 {
    font-size: 14px;
  }

  .task-description-level-other {
    font-size: 13px;
  }

  .agent_name {
    display: flex;
    align-items: center;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .agent_name-badge {
    background-color: #0000001c;
    padding: 0 6px;
    margin:0 4px 0 2px;
    border-radius: 6px;
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .header-plan {
    border: 1px solid #f0f0f0;
  }

  .header-task {
    transition: background-color 0.2s ease;
    cursor: pointer;

    &:hover {
      background-color: #f5f5f5;
    }
  }

  .header-default {
  }

  .title-container {
    font-size: 14px;
  }

  .title-level-0 {
    font-size: 14px;
  }

  .title-level-1 {
    font-size: 13px;
  }

  .title-level-2 {
    font-size: 12px;
  }

  .title-text-ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width:80%
  }

  .title-flex-container {
    display: flex;
    align-items: center;
    width: 100%;
    overflow: hidden;
    justify-content: space-between;
  }

  .result-title-container {
    font-size: 14px;
  }

  .result-title-outer {
    font-size: 14px;
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
    margin-top: 2px;
    flex-shrink: 0;
  }

  .result-icon-outer {
    margin-top: 4px;
  }

  .avatar-shrink {
    flex-shrink: 0;
  }

  .button-shrink {
    flex-shrink: 0;
  }

  .status-badge {
    background-color: #f0f0f0;
    font-size: 12px;
    flex-shrink: 0;
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
    max-width: 80%;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;
