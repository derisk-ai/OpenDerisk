import EE from '@antv/event-emitter';

/**
 * 定义全局事件
 */
export const EVENTS = {
  TASK_CLICK: 'task-click',
};

/**
 * 用于全局通信，谨慎使用
 */
export const ee = new EE();
