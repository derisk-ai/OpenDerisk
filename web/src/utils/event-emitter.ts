import EE from '@antv/event-emitter';

/**
 * 定义全局事件
 */
export const EVENTS = {
  TASK_CLICK: 'task-click',
  CLICK_FOLDER: 'clickFolder',
  ADD_TASK: 'addTask',
  CLOSE_PANEL: 'closePanel',
  OPEN_PANEL: 'openPanel',
  SWITCH_TAB: 'switchTab',
};

const DEBUG_EMITTER = false; // 调试 folder/work 联动时打开

const rawEE = new EE();

/**
 * 用于全局通信，谨慎使用
 * 调试时包装 emit/on，打日志看是否有监听者、是否触发
 */
export const ee = DEBUG_EMITTER
  ? {
      on: (event: string, handler: (...args: any[]) => void) => {
        console.log('[ee] on', event);
        return rawEE.on(event, handler);
      },
      off: (event: string, handler?: (...args: any[]) => void) => {
        console.log('[ee] off', event);
        return rawEE.off(event, handler);
      },
      emit: (event: string, ...args: any[]) => {
        console.log('[ee] emit', event, args);
        return rawEE.emit(event, ...args);
      },
    }
  : rawEE;
