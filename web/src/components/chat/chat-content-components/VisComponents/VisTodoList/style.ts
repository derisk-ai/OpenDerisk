import styled from 'styled-components';

/**
 * VisTodoList组件样式
 * 用于在planning_window区域展示Agent的看板stage进度
 */
export const VisTodoListWrap = styled.div`
  width: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  background-color: #fff;
  overflow: hidden;
  margin: 4px 0;

  /* 头部：Agent信息和进度 */
  .todolist-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid #f0f0f0;
    background: linear-gradient(to bottom, #fafbff, #f5f5fa);

    .agent-info {
      display: flex;
      align-items: center;
      gap: 8px;

      .ant-avatar {
        border: 1px solid #e8e8e8;
      }

      .agent-name {
        font-size: 13px;
        font-weight: 500;
        color: #262626;
        max-width: 150px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    .progress-info {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;

      .progress-text {
        font-size: 12px;
        color: #8c8c8c;
        font-weight: 500;
        min-width: 28px;
        text-align: right;
      }

      .progress-bar {
        width: 80px;
        height: 6px;
        background-color: #f5f5f5;
        border-radius: 3px;
        overflow: hidden;

        .progress-fill {
          height: 100%;
          background: linear-gradient(to right, #52c41a, #73d13d);
          border-radius: 3px;
          transition: width 0.3s ease;
        }
      }
    }
  }

  /* 任务描述 */
  .todolist-mission {
    padding: 8px 12px;
    background-color: #fafafa;
    border-bottom: 1px solid #f0f0f0;

    .mission-text {
      font-size: 12px;
      color: #595959;
      line-height: 1.5;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
  }

  /* Todo列表 */
  .todolist-items {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 0;
    max-height: 300px;
    overflow-y: auto;

    /* 自定义滚动条 */
    &::-webkit-scrollbar {
      width: 4px;
    }

    &::-webkit-scrollbar-track {
      background: #f5f5f5;
      border-radius: 2px;
    }

    &::-webkit-scrollbar-thumb {
      background: #d9d9d9;
      border-radius: 2px;

      &:hover {
        background: #b0b0b0;
      }
    }

    /* Todo项 */
    .todo-item {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 6px;
      background-color: #fafafa;
      transition: all 0.2s ease;
      position: relative;

      &:hover {
        background-color: #f0f0f0;
      }

      /* 当前进行中的项 */
      &.current {
        background: linear-gradient(to right, #e6f7ff, #f0f9ff);
        border: 1px solid #d6e4ff;

        .todo-title {
          color: #1677ff;
        }
      }

      /* 完成的项 */
      &.completed {
        opacity: 0.8;

        .todo-title {
          color: #52c41a;
          text-decoration: line-through;
        }
      }

      /* 失败的项 */
      &.failed {
        background-color: #fff2f0;
        border: 1px solid #ffccc7;

        .todo-title {
          color: #ff4d4f;
        }
      }

      /* 序号 */
      .todo-index {
        flex-shrink: 0;
        width: 20px;
        height: 20px;
        border-radius: 4px;
        background-color: #e8e8e8;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 600;
        color: #8c8c8c;
      }

      .current & .todo-index {
        background-color: #1677ff;
        color: #fff;
      }

      .completed & .todo-index {
        background-color: #52c41a;
        color: #fff;
      }

      .failed & .todo-index {
        background-color: #ff4d4f;
        color: #fff;
      }

      /* 状态图标 */
      .todo-status {
        flex-shrink: 0;
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      /* 内容 */
      .todo-content {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 2px;

        .todo-title {
          font-size: 13px;
          font-weight: 500;
          color: #262626;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          transition: color 0.2s ease;
        }

        .current-title {
          font-weight: 600;
        }

        .todo-description {
          font-size: 11px;
          color: #8c8c8c;
          line-height: 1.4;
          overflow: hidden;
          text-overflow: ellipsis;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
        }
      }

      /* 当前标记 */
      .todo-current-badge {
        flex-shrink: 0;
        padding: 2px 8px;
        border-radius: 10px;
        background: linear-gradient(135deg, #1677ff, #4096ff);
        color: #fff;
        font-size: 10px;
        font-weight: 500;
        white-space: nowrap;
        animation: pulse 1.5s ease-in-out infinite;
      }
    }

    /* 空状态 */
    .todolist-empty {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px 12px;

      .empty-text {
        font-size: 12px;
        color: #b0b0b0;
        font-style: italic;
      }
    }
  }

  /* 脉冲动画 */
  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.7;
    }
  }

  /* 响应式 */
  @media (max-width: 768px) {
    .todolist-header {
      .progress-info {
        .progress-bar {
          width: 60px;
        }
      }
    }

    .todolist-items {
      max-height: 200px;

      .todo-item {
        padding: 6px 10px;
        gap: 6px;

        .todo-index {
          width: 18px;
          height: 18px;
          font-size: 10px;
        }

        .todo-status {
          width: 18px;
          height: 18px;
        }

        .todo-content {
          .todo-title {
            font-size: 12px;
          }

          .todo-description {
            font-size: 10px;
            -webkit-line-clamp: 1;
          }
        }

        .todo-current-badge {
          font-size: 9px;
          padding: 2px 6px;
        }
      }
    }
  }
`;