'use client';

import React, { useCallback, useMemo } from 'react';
import { Card, Input, Button, Alert, Space, Typography, Divider, List, Tag, Tabs } from 'antd';
import { PlusOutlined, ClearOutlined, CopyOutlined, DeleteOutlined, PlayCircleOutlined, EyeOutlined, CodeOutlined } from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { markdownComponents, markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';

const { TextArea } = Input;
const { Title, Text } = Typography;

interface MergeTestTabProps {
  inputText: string;
  setInputText: (text: string) => void;
  chunks: string[];
  setChunks: (chunks: string[]) => void;
  mergedResult: string;
  setMergedResult: (result: string) => void;
  error: string;
  setError: (error: string) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  tester: any;
}

// 提取 vis 内容用于渲染
// 关键更新：现在合并结果直接是 VisParser.current 的格式
function extractVisForRender(mergedResult: string): string {
  try {
    // VisParser.current 是一个 JSON 字符串，包含 planning_window 和 running_window
    const visData = JSON.parse(mergedResult);
    let content = '';
    if (visData.planning_window) {
      content += visData.planning_window + '\n';
    }
    if (visData.running_window) {
      content += visData.running_window + '\n';
    }
    return content;
  } catch {
    // ignore
  }
  return '';
}

// 提取并格式化 vis 内容
// 关键更新：适配新的合并结果格式
const extractAndFormatVis = (str: string): string => {
  try {
    // VisParser.current 直接是包含 planning_window 和 running_window 的对象
    const visData = JSON.parse(str);
    return JSON.stringify(visData, null, 2);
  } catch {
    return str;
  }
};

export default function MergeTestTab({
  inputText,
  setInputText,
  chunks,
  setChunks,
  mergedResult,
  setMergedResult,
  error,
  setError,
  activeTab,
  setActiveTab,
  tester,
}: MergeTestTabProps) {
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

      setChunks([...chunks, inputText.trim()]);
      setInputText('');
      setError('');
    } catch (e: any) {
      setError(`JSON 解析错误: ${e.message}`);
    }
  }, [inputText, chunks, setChunks, setInputText, setError]);

  // 删除指定 chunk
  const handleRemoveChunk = useCallback((index: number) => {
    setChunks(chunks.filter((_, i) => i !== index));
  }, [chunks, setChunks]);

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
  }, [chunks, tester, setError, setMergedResult]);

  // 清空所有
  const handleClear = useCallback(() => {
    setInputText('');
    setChunks([]);
    setMergedResult('');
    setError('');
  }, [setInputText, setChunks, setMergedResult, setError]);

  // 清空输入框
  const handleClearInput = useCallback(() => {
    setInputText('');
    setError('');
  }, [setInputText, setError]);

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

  // 获取用于渲染的内容
  const renderContent = useMemo(() => {
    return extractVisForRender(mergedResult);
  }, [mergedResult]);

  return (
    <div className="space-y-4 w-full" style={{ width: '100%' }}>
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
          placeholder={'请输入 VIS 数据，格式如下：\n{"vis":"{\\"planning_window\\": \\"内容\\", \\"running_window\\": \\"\\"}"}\n\n支持的数据示例：\n{"vis":"{\\"planning_window\\": \\"```d-planning-space\n{\\"uid\\":\\"test_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"```d-agent-plan\n{\\"uid\\":\\"agent_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"准备开始\\"}\n```\\"}\n```\\", \\"running_window\\": \\"\\"}"}'}
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
{'[\n  {\n    "vis": "{\\"planning_window\\": \\"```d-planning-space\n{\\"uid\\":\\"test_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"```d-agent-plan\n{\\"uid\\":\\"agent_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"准备开始\\"}\n```\\"}\n```\\", \\"running_window\\": \\"\\"}"\n  },\n  {\n    "vis": "{\\"planning_window\\": \\"```d-planning-space\n{\\"uid\\":\\"test_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"```d-agent-plan\n{\\"uid\\":\\"agent_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"执行中...\\"}\n```\\"}\n```\\", \\"running_window\\": \\"\\"}"\n  },\n  {\n    "vis": "{\\"planning_window\\": \\"```d-planning-space\n{\\"uid\\":\\"test_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"```d-agent-plan\n{\\"uid\\":\\"agent_1\\",\\"type\\":\\"incr\\",\\"markdown\\":\\"完成\\"}\n```\\"}\n```\\", \\"running_window\\": \\"\\"}"\n  }\n]'}
            </pre>
          </div>
        </div>
      </Card>
    </div>
  );
}
