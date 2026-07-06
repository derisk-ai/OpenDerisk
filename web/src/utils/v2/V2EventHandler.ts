/** V2事件处理器 - 解析SSE流并dispatch到解析器 */

import { V2Event } from './types';
import { V2SimplifiedVisParser } from './V2SimplifiedVisParser';

export class V2EventHandler {
  private parser: V2SimplifiedVisParser;
  private onEvent?: (event: V2Event) => void;

  constructor(parser: V2SimplifiedVisParser, onEvent?: (event: V2Event) => void) {
    this.parser = parser;
    this.onEvent = onEvent;
  }

  /** 解析SSE data行 */
  parseSSELine(line: string): V2Event | null {
    // SSE格式: data:{"event":"xxx","seq":1,"ts":123,"payload":{...}}
    if (!line.startsWith('data:')) {
      return null;
    }

    try {
      const jsonStr = line.slice(5).trim();
      const event = JSON.parse(jsonStr) as V2Event;
      return event;
    } catch (e) {
      console.error('[V2EventHandler] Failed to parse SSE line:', line, e);
      return null;
    }
  }

  /** 处理SSE data行 */
  handleSSELine(line: string): void {
    const event = this.parseSSELine(line);
    if (!event) {
      return;
    }

    // 触发事件回调
    if (this.onEvent) {
      this.onEvent(event);
    }

    // Dispatch到解析器
    this.parser.handleEvent(event);
  }

  /** 处理完整SSE流 */
  async handleSSEStream(stream: ReadableStream<string>): Promise<void> {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 按行分割处理
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // 保留未完成的行

      for (const line of lines) {
        if (line.trim()) {
          this.handleSSELine(line);
        }
      }
    }

    // 处理剩余buffer
    if (buffer.trim()) {
      this.handleSSELine(buffer);
    }
  }
}

/** 创建事件处理器 */
export function createV2EventHandler(
  parser: V2SimplifiedVisParser,
  onEvent?: (event: V2Event) => void,
): V2EventHandler {
  return new V2EventHandler(parser, onEvent);
}
