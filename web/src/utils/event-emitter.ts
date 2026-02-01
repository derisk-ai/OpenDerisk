import EE from '@antv/event-emitter';

/**
 * 定义全局事件
 */
export const EVENTS = {
  TASK_CLICK: 'task-click',
  CLICK_FOLDER: 'click-folder',
  ADD_TASK: 'add-task',
  CLOSE_PANEL: 'close-panel',
};

/**
 * 用于全局通信，谨慎使用
 */
export const ee = new EE();
