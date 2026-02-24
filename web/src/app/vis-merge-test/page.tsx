'use client';

import React, { useState, useMemo } from 'react';
import { Typography, Tabs } from 'antd';
import { PlusOutlined, RedoOutlined } from '@ant-design/icons';
import ChunkReplay from '@/components/vis-merge/ChunkReplay';
import MergeTestTab from '@/components/vis-merge/MergeTestTab';
import { VisBaseParser } from '@/utils/parse-vis';
import 'katex/dist/katex.min.css';

const { Title, Text } = Typography;

// VIS 数据合并测试器
class VisMergeTester {
  // 提取 JSON 中的 vis 文本
  extractVisContent(jsonStr: string): { planning_window?: string; running_window?: string } | null {
    try {
      const data = JSON.parse(jsonStr);
      if (data.vis) {
        return JSON.parse(data.vis);
      }
      return data;
    } catch (e) {
      return null;
    }
  }

  // 合并 VIS 数据
  mergeVis(baseVis: string, incrVis: string): string {
    if (!baseVis) return incrVis;
    if (!incrVis) return baseVis;

    const baseData = this.extractVisContent(baseVis);
    const incrData = this.extractVisContent(incrVis);

    if (!baseData || !incrData) {
      return incrVis;
    }

    const result: any = {};

    // 合并 planning_window - 为每次合并创建新的 parser 实例
    if (incrData.planning_window !== undefined) {
      if (incrData.planning_window === null) {
        result.planning_window = null;
      } else if (baseData.planning_window && incrData.planning_window) {
        const parser = new VisBaseParser();
        parser.currentVis = baseData.planning_window;
        result.planning_window = parser.updateCurrentMarkdown(incrData.planning_window);
      } else {
        result.planning_window = incrData.planning_window;
      }
    } else {
      result.planning_window = baseData.planning_window;
    }

    // 合并 running_window - 为每次合并创建新的 parser 实例
    if (incrData.running_window !== undefined) {
      if (incrData.running_window === null) {
        result.running_window = null;
      } else if (baseData.running_window && incrData.running_window) {
        const parser = new VisBaseParser();
        parser.currentVis = baseData.running_window;
        result.running_window = parser.updateCurrentMarkdown(incrData.running_window);
      } else {
        result.running_window = incrData.running_window;
      }
    } else {
      result.running_window = baseData.running_window;
    }

    return JSON.stringify({ vis: JSON.stringify(result) });
  }

  // 逐个合并 chunk
  mergeChunks(chunks: string[]): string {
    let result = '';
    for (const chunk of chunks) {
      if (!result) {
        result = chunk;
      } else {
        result = this.mergeVis(result, chunk);
      }
    }
    return result;
  }
}

export default function VisMergeTestPage() {
  const [inputText, setInputText] = useState<string>('');
  const [chunks, setChunks] = useState<string[]>([]);
  const [mergedResult, setMergedResult] = useState<string>('');
  const [error, setError] = useState<string>('');
  // 主页面tab状态
  const [mainTab, setMainTab] = useState<string>('replay');
  // 合并结果展示tab状态
  const [activeTab, setActiveTab] = useState<string>('visual');

  const tester = useMemo(() => new VisMergeTester(), []);

  const tabItems = [
    {
      key: 'replay',
      label: (
        <span>
          <RedoOutlined /> Chunk 回放
        </span>
      ),
      children: <ChunkReplay />,
    },
    {
      key: 'merge',
      label: (
        <span>
          <PlusOutlined /> 合并测试
        </span>
      ),
      children: (
        <MergeTestTab
          inputText={inputText}
          setInputText={setInputText}
          chunks={chunks}
          setChunks={setChunks}
          mergedResult={mergedResult}
          setMergedResult={setMergedResult}
          error={error}
          setError={setError}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          tester={tester}
        />
      ),
    },
  ];

  return (
    <div className="p-6 max-w-full w-full h-full overflow-y-auto">
      <Title level={2}>DeRisk-GUI</Title>
      <Text type="secondary" className="mb-6 block">
        DeRisk GUI智能生成预览, 支持手动输入合并和 JSONL 文件回放两种模式
      </Text>

      <div className="w-full">
        <Tabs
          activeKey={mainTab}
          onChange={setMainTab}
          type="card"
          className="w-full"
          items={tabItems}
        />
      </div>
    </div>
  );
}
