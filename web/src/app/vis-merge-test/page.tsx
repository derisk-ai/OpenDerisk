'use client';

import React, { useState, useMemo } from 'react';
import { Typography, Tabs } from 'antd';
import { PlusOutlined, RedoOutlined } from '@ant-design/icons';
import ChunkReplay from '@/components/vis-merge/ChunkReplay';
import MergeTestTab from '@/components/vis-merge/MergeTestTab';
import { VisParser } from '@/utils/parse-vis';
import 'katex/dist/katex.min.css';

const { Title, Text } = Typography;

// VIS 数据合并测试器 - 与正式对话完全一致
class VisMergeTester {
  private visParser: VisParser;

  constructor() {
    this.visParser = new VisParser();
  }

  // 重置解析器状态（模拟新的对话）
  reset() {
    this.visParser.destroy();
    this.visParser = new VisParser();
  }

  // 合并单个 chunk - 与正式对话的 parseChunkData 完全一致
  // chunk 格式: {"vis": "{\"planning_window\": \"...\", \"running_window\": \"...\"}"}
  mergeChunk(chunk: string): string {
    try {
      const data = JSON.parse(chunk);
      // 正式对话中：parseChunkData 接收 data.vis（即包含 planning_window 和 running_window 的 JSON 字符串）
      // 然后调用 visParser.update(answer) 其中 answer = data.vis
      const visContent = data.vis || chunk;
      return this.visParser.update(visContent);
    } catch (e) {
      console.error('Failed to merge chunk:', e);
      return chunk;
    }
  }

  // 逐个合并 chunks - 保持状态累积
  mergeChunks(chunks: string[]): string {
    let lastResult = '';
    for (const chunk of chunks) {
      lastResult = this.mergeChunk(chunk);
    }
    return lastResult;
  }

  // 获取当前合并结果（与正式对话的 midMsgObject.text 一致）
  getCurrentResult(): string {
    return this.visParser.current;
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
      <Title level={2}>VIS 数据合并测试</Title>
      <Text type="secondary" className="mb-6 block">
        测试 VIS chunk 数据的合并效果，支持手动输入合并和 JSONL 文件回放两种模式。
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
