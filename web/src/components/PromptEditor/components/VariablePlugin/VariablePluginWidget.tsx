import { WidgetType } from '@codemirror/view';
import React from 'react';
import ReactDOM from 'react-dom/client';
import VariableRender from './VariableRender';

interface PluginData {
  name: string;
  description?: string;
  script: string;
  renderName: string;
  // 是否为文本中第一个符合规则的
  isFirst?: boolean;
  matchPos: number;
  readonly?: boolean;
}

export class VariablePluginWidget extends WidgetType {
  static instance: VariablePluginWidget;
  data: PluginData;
  handleClickChangeVariable?: () => void;
  constructor(data: PluginData, handleClickChangeVariable?: () => void) {
    super();
    this.data = data;
    this.handleClickChangeVariable = handleClickChangeVariable;
  }

  eq(widget: WidgetType & { data: PluginData }) {
    // return widget.data.name === this.data.name && widget.data.description === this.data.description;
    return (
      JSON.stringify(this.data || {}) === JSON.stringify(widget.data || {})
    );
  }

  toDOM() {
    const container = document.createElement('span'); // 创建一个临时容器
    // 使用 ReactDOM.createRoot 渲染 Ant Design 的 Tag 组件
    const root = ReactDOM.createRoot(container);
    root.render(
      <VariableRender
        data={this.data}
        handleClickChangeVariable={this.handleClickChangeVariable}
      />,
    );
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
