'use client';

import React, { useState, useCallback, useMemo } from 'react';
import { Card, Input, Button, Alert, Space, Typography, Divider, List, Tag, Tabs } from 'antd';
import { PlusOutlined, ClearOutlined, CopyOutlined, DeleteOutlined, PlayCircleOutlined, EyeOutlined, CodeOutlined } from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { VisParser } from '@/utils/parse-vis';
import { VisBaseParser } from '@/utils/parse-vis';
import { markdownComponents, markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import 'katex/dist/katex.min.css';

const { TextArea } = Input;
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

// 提取 vis 内容用于渲染
function extractVisForRender(mergedResult: string): string {
  try {
    const parsed = JSON.parse(mergedResult);
    if (parsed.vis) {
      const visData = JSON.parse(parsed.vis);
      let content = '';
      if (visData.planning_window) {
        content += visData.planning_window + '\n';
      }
      if (visData.running_window) {
        content += visData.running_window + '\n';
      }
      return content;
    }
  } catch {
    // ignore
  }
  return '';
}

export default function VisMergeTestPage() {
  const [inputText, setInputText] = useState<string>('');
  const [chunks, setChunks] = useState<string[]>([]);
  const [mergedResult, setMergedResult] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [activeTab, setActiveTab] = useState<string>('visual');

  const tester = useMemo(() => new VisMergeTester(), []);

  // 添加 chunk 到队列
  const handleAddChunk = useCallback(() => {
    if (!inputText.trim()) {
      setError('请输入 VIS 数据');
      return;
    }

    try {
      // 验证 JSON 格式
      const parsed = JSON.parse(inputText.trim());
      if (!parsed.vis) {
        setError('输入的数据必须包含 vis 字段');
        return;
      }

      setChunks(prev => [...prev, inputText.trim()]);
      setInputText('');
      setError('');
    } catch (e: any) {
      setError(`JSON 解析错误: ${e.message}`);
    }
  }, [inputText]);

  // 删除指定 chunk
  const handleRemoveChunk = useCallback((index: number) => {
    setChunks(prev => prev.filter((_, i) => i !== index));
  }, []);

  // 执行合并
  const handleMerge = useCallback(() => {
    console.log('[handleMerge] Starting merge, chunks count:', chunks.length);
    
    if (chunks.length === 0) {
      setError('请先添加 VIS 数据到队列');
      return;
    }

    try {
      setError('');
      console.log('[handleMerge] Calling mergeChunks with:', chunks);
      const result = tester.mergeChunks(chunks);
      console.log('[handleMerge] Merge result:', result);
      setMergedResult(result);
    } catch (e: any) {
      console.error('[handleMerge] Error:', e);
      setError(`合并错误: ${e.message}`);
    }
  }, [chunks, tester]);

  // 清空所有
  const handleClear = useCallback(() => {
    setInputText('');
    setChunks([]);
    setMergedResult('');
    setError('');
  }, []);

  // 清空输入框
  const handleClearInput = useCallback(() => {
    setInputText('');
    setError('');
  }, []);

  // 复制结果
  const handleCopy = useCallback(() => {
    if (mergedResult) {
      navigator.clipboard.writeText(mergedResult);
    }
  }, [mergedResult]);

  // 格式化 JSON 显示
  const formatJson = (str: string): string => {
    try {
      const parsed = JSON.parse(str);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return str;
    }
  };

  // 提取并格式化 vis 内容
  const extractAndFormatVis = (str: string): string => {
    try {
      const parsed = JSON.parse(str);
      if (parsed.vis) {
        const visData = JSON.parse(parsed.vis);
        return JSON.stringify(visData, null, 2);
      }
      return JSON.stringify(parsed, null, 2);
    } catch {
      return str;
    }
  };

  // 获取用于渲染的内容
  const renderContent = useMemo(() => {
    return extractVisForRender(mergedResult);
  }, [mergedResult]);

  return (
    <div className="p-6 max-w-7xl mx-auto h-full overflow-y-auto">
      <Title level={2}>VIS 数据合并测试</Title>
      <Text type="secondary" className="mb-6 block">
        输入 VIS chunk 数据，添加到合并队列，执行合并后查看结果。支持连续输入多次、合并多次。
      </Text>

      {error && (
        <Alert
          message="错误"
          description={error}
          type="error"
          showIcon
          className="mb-4"
          closable
          onClose={() => setError('')}
        />
      )}

      {/* 上方：输入区域 */}
      <Card title="输入 VIS 数据" className="mb-4">
        <TextArea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={'请输入 VIS 数据，格式如下：\n{"vis":"{\\"planning_window\\": \\"内容\\", \\"running_window\\": \\"\\"}"}\n\n支持的数据示例：\n{"vis":"{\\"planning_window\\": \\"```d-planning-space\\n{\\"uid\\":\\"test_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"```d-agent-plan\\n{\\"uid\\":\\"agent_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"准备开始\\"}\\n```\\"}\\n```\\", \\"running_window\\": \\"\\"}"}'}
          rows={8}
          className="font-mono text-sm mb-4"
        />
        <Space>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAddChunk}
          >
            添加到队列
          </Button>
          <Button
            icon={<ClearOutlined />}
            onClick={handleClearInput}
          >
            清空输入
          </Button>
        </Space>
      </Card>

      {/* 显示已添加的 chunk 队列 */}
      {chunks.length > 0 && (
        <Card 
          title={`合并队列 (${chunks.length} 个 chunk)`} 
          className="mb-4"
          extra={
            <Space>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleMerge}
              >
                执行合并
              </Button>
              <Button
                danger
                icon={<ClearOutlined />}
                onClick={handleClear}
              >
                清空全部
              </Button>
            </Space>
          }
        >
          <List
            size="small"
            bordered
            dataSource={chunks}
            renderItem={(item, index) => (
              <List.Item
                actions={[
                  <Button
                    key="delete"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => handleRemoveChunk(index)}
                  >
                    删除
                  </Button>
                ]}
              >
                <Space>
                  <Tag color="blue">#{index + 1}</Tag>
                  <Text code className="max-w-md truncate">
                    {item.length > 100 ? item.substring(0, 100) + '...' : item}
                  </Text>
                </Space>
              </List.Item>
            )}
          />
        </Card>
      )}

      {/* 下方：合并结果展示 */}
      <Card
        title="合并结果"
        className="mb-4"
        extra={
          mergedResult && (
            <Space>
              <Button icon={<CopyOutlined />} onClick={handleCopy}>
                复制结果
              </Button>
            </Space>
          )
        }
      >
        {!mergedResult ? (
          <div className="text-center text-gray-400 py-12">
            <Text>暂无合并结果，请先添加 chunk 到队列并点击"执行合并"</Text>
          </div>
        ) : (
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'visual',
                label: (
                  <span>
                    <EyeOutlined /> 可视化渲染
                  </span>
                ),
                children: (
                  <div className="min-h-[400px] max-h-[600px] overflow-auto border rounded p-4 bg-white">
                    {renderContent ? (
                      <GPTVis
                        components={markdownComponents}
                        {...markdownPlugins}
                      >
                        {preprocessLaTeX(renderContent)}
                      </GPTVis>
                    ) : (
                      <div className="text-center text-gray-400 py-12">
                        <Text>无可渲染内容</Text>
                      </div>
                    )}
                  </div>
                ),
              },
              {
                key: 'json',
                label: (
                  <span>
                    <CodeOutlined /> 原始 JSON
                  </span>
                ),
                children: (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Title level={5}>完整格式</Title>
                      <pre className="bg-gray-100 p-4 rounded overflow-auto text-xs font-mono h-96">
                        {formatJson(mergedResult)}
                      </pre>
                    </div>
                    <div>
                      <Title level={5}>提取的 VIS 内容</Title>
                      <pre className="bg-gray-100 p-4 rounded overflow-auto text-xs font-mono h-96">
                        {extractAndFormatVis(mergedResult)}
                      </pre>
                    </div>
                  </div>
                ),
              },
              {
                key: 'markdown',
                label: (
                  <span>
                    <CodeOutlined /> Markdown 源码
                  </span>
                ),
                children: (
                  <pre className="bg-gray-100 p-4 rounded overflow-auto text-xs font-mono h-96">
                    {renderContent || '无内容'}
                  </pre>
                ),
              },
            ]}
          />
        )}
      </Card>

      {/* 使用说明 */}
      <Card title="使用说明" className="mb-4">
        <div className="space-y-4">
          <div>
            <Title level={5}>1. 数据格式</Title>
            <Text>
              输入 VIS chunk 数据，格式为 JSON，必须包含 vis 字段：
            </Text>
            <pre className="bg-gray-100 p-3 rounded mt-2 text-sm">
{`{"vis":"{\\"planning_window\\": \\"内容\\", \\"running_window\\": \\"\\"}"}`}
            </pre>
          </div>

          <div>
            <Title level={5}>2. 使用步骤</Title>
            <ul className="list-disc list-inside space-y-1 text-gray-600">
              <li>在上方输入框中输入 VIS chunk 数据</li>
              <li>点击"添加到队列"按钮，将数据添加到合并队列</li>
              <li>可以连续输入多个 chunk，都会添加到队列中</li>
              <li>点击"执行合并"按钮，查看合并结果</li>
              <li>在"可视化渲染"标签页查看 GPTVis 渲染效果</li>
            </ul>
          </div>

          <div>
            <Title level={5}>3. 支持的组件</Title>
            <div className="flex flex-wrap gap-2 mt-2">
              {[
                'd-planning-space',
                'd-agent-plan',
                'd-work',
                'd-code',
                'd-monitor',
                'd-tool',
                'd-llm',
                'd-thinking',
                'd-attach',
                'd-agent-folder',
                'd-todo-list',
                'nex-running-window',
                'nex-planning-window',
                'drsk-content',
                'drsk-plan',
                'drsk-msg',
                'drsk-step',
                'drsk-confirm',
                'drsk-interact',
              ].map(tag => (
                <Tag key={tag} color="blue">{tag}</Tag>
              ))}
            </div>
          </div>

          <div>
            <Title level={5}>4. 示例数据</Title>
            <pre className="bg-gray-100 p-3 rounded mt-2 text-xs">
{'[\n  {\n    "vis": "{\\"planning_window\\": \\"```d-planning-space\\n{\\"uid\\":\\"test_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"```d-agent-plan\\n{\\"uid\\":\\"agent_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"准备开始\\"}\\n```\\"}\\n```\\", \\"running_window\\": \\"\\"}"\n  },\n  {\n    "vis": "{\\"planning_window\\": \\"```d-planning-space\\n{\\"uid\\":\\"test_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"```d-agent-plan\\n{\\"uid\\":\\"agent_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"执行中...\\"}\\n```\\"}\\n```\\", \\"running_window\\": \\"\\"}"\n  },\n  {\n    "vis": "{\\"planning_window\\": \\"```d-planning-space\\n{\\"uid\\":\\"test_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"```d-agent-plan\\n{\\"uid\\":\\"agent_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"完成\\"}\\n```\\"}\\n```\\", \\"running_window\\": \\"\\"}"\n  }\n]'}
            </pre>
          </div>
        </div>
      </Card>
    </div>
  );
}
