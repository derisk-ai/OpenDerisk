import { WidgetType } from '@codemirror/view';
import React from 'react';
import ReactDOM from 'react-dom/client';
import CustomContentRender from './CustomContentRender';

interface PluginData {
  name: string;
  description?: string;
  type: 'knowledge' | 'agent' | 'skill';
}

export class CommonPluginWidget extends WidgetType {
  static instance: CommonPluginWidget;
  data: PluginData;
  handleClickChangeVariable?: () => void;
  constructor(data: PluginData, handleClickChangeVariable?: () => void) {
    super();
    this.data = data;
    this.handleClickChangeVariable = handleClickChangeVariable;
  }

  eq(widget: WidgetType & { data: PluginData }) {
    return (
      JSON.stringify(this.data || {}) === JSON.stringify(widget.data || {})
    );
  }

  toDOM() {
    const container = document.createElement('span'); // 创建一个临时容器
    // 使用 ReactDOM.createRoot 渲染 Ant Design 的 Tag 组件
    const root = ReactDOM.createRoot(container);
    root.render(<CustomContentRender data={this.data} />);
    // container.addEventListener('click', (event) => {
    //   // 调用外部传入的点击事件处理器
    //   if (this.onClick) {
    //     this.onClick(
    //       event,
    //       this.data?.name || this.data?.renderName,
    //     );
    //   }
    //   event.stopPropagation();
    // });
    return container;
  }

  ignoreEvent() {
    return false;
  }
}
