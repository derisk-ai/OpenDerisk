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
    // @ts-ignore
    const root = ReactDOM.createRoot(container);
    // @ts-ignore
    root.render(
      // @ts-ignore
      <VariableRender
        data={this.data}
        handleClickChangeVariable={this.handleClickChangeVariable}
      />,
    );
    return container;
  }

  ignoreEvent() {
    return false;
  }
}
