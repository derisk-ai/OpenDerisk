/** V2简化VIS解析器 - 无嵌套，原子操作。

设计文档 §5.2。
*/
import { V2Event, SimplifiedVisComponent, VisComponentState, VisOperationType } from './types';
import { UID_SEPARATOR } from './constants';

export class V2SimplifiedVisParser {
  private components: Map<string, VisComponentState> = new Map();
  private currentStepId: string = '';
  private listeners: Array<(components: Map<string, VisComponentState>) => void> = [];

  /** 处理V2事件 */
  handleEvent(event: V2Event): void {
    switch (event.event) {
      case 'step_start':
        this.currentStepId = (event.payload.step_id as string) || '';
        break;

      case 'vis_update':
        this.handleVisUpdate(event.payload as SimplifiedVisComponent);
        break;

      // 其他事件类型暂不处理VIS更新，可扩展
      default:
        break;
    }
  }

  /** 处理VIS组件更新 */
  handleVisUpdate(component: SimplifiedVisComponent): void {
    const { type, uid, tag, content, meta } = component;

    switch (type) {
      case 'incr':
        // 增量追加
        const existing = this.components.get(uid);
        if (existing) {
          existing.content += content;
          if (meta) {
            existing.meta = { ...existing.meta, ...meta };
          }
        } else {
          // 新组件
          this.components.set(uid, { uid, tag, content, meta });
        }
        break;

      case 'replace':
        // 全量替换
        this.components.set(uid, { uid, tag, content, meta });
        break;

      case 'delete':
        // 删除组件
        this.components.delete(uid);
        break;
    }

    // 触发渲染更新
    this.notifyListeners();
  }

  /** 按step ID聚合组件 */
  groupByStep(): Map<string, VisComponentState[]> {
    const groups = new Map<string, VisComponentState[]>();

    for (const [uid, component] of this.components) {
      // UID格式: {step_id}-{component_type}-{index}
      const stepId = uid.split(UID_SEPARATOR)[0];

      if (!groups.has(stepId)) {
        groups.set(stepId, []);
      }
      groups.get(stepId)?.push(component);
    }

    return groups;
  }

  /** 获取当前所有组件 */
  getComponents(): Map<string, VisComponentState> {
    return this.components;
  }

  /** 清空所有组件 */
  clear(): void {
    this.components.clear();
    this.currentStepId = '';
    this.notifyListeners();
  }

  /** 添加渲染监听器 */
  addListener(listener: (components: Map<string, VisComponentState>) => void): void {
    this.listeners.push(listener);
  }

  /** 移除渲染监听器 */
  removeListener(listener: (components: Map<string, VisComponentState>) => void): void {
    const index = this.listeners.indexOf(listener);
    if (index > -1) {
      this.listeners.splice(index, 1);
    }
  }

  /** 通知监听器 */
  private notifyListeners(): void {
    for (const listener of this.listeners) {
      listener(this.components);
    }
  }
}

/** 创建解析器实例 */
export function createV2Parser(): V2SimplifiedVisParser {
  return new V2SimplifiedVisParser();
}
