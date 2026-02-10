'use client';

import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { Card, Button, Upload, Slider, Space, Typography, Tag, Progress, Alert, Badge, Row, Col, Modal, message } from 'antd';
import { UploadOutlined, PlayCircleOutlined, PauseCircleOutlined, ReloadOutlined, FileTextOutlined, BugOutlined, StepForwardOutlined, StepBackwardOutlined, EyeOutlined, CopyOutlined } from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { markdownComponents, markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content-components/config';
import { VisBaseParser } from '@/utils/parse-vis';
import type { UploadFile } from 'antd/es/upload/interface';
import 'katex/dist/katex.min.css';

const { Title, Text } = Typography;

interface DebugLog {
  id: number;
  timestamp: string;
  type: 'info' | 'warn' | 'error' | 'success';
  message: string;
  details?: Record<string, any>;
}

interface ChunkData {
  vis: string;
}

interface ParsedVisData {
  planning_window?: string;
  running_window?: string;
}

export default function ChunkReplay() {
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [chunks, setChunks] = useState<ChunkData[]>([]);
  const [error, setError] = useState<string>('');
  
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [planningContent, setPlanningContent] = useState('');
  const [runningContent, setRunningContent] = useState('');
  
  const [planningSpeed, setPlanningSpeed] = useState<number>(2);
  const [runningSpeed, setRunningSpeed] = useState<number>(20);
  
  const [debugLogs, setDebugLogs] = useState<DebugLog[]>([]);
  const [showDebugPanel, setShowDebugPanel] = useState<boolean>(false);
  const [showVisModal, setShowVisModal] = useState<boolean>(false);
  const [showPlanningModal, setShowPlanningModal] = useState<boolean>(false);
  const [showRunningModal, setShowRunningModal] = useState<boolean>(false);
  const [fileInfo, setFileInfo] = useState<{ name: string; size: string } | null>(null);
  const logIdRef = useRef<number>(0);
  
  const planningContentRef = useRef('');
  const runningContentRef = useRef('');
  const isPlayingRef = useRef(false);
  const currentIndexRef = useRef(0);
  const planningSpeedRef = useRef(planningSpeed);
  const runningSpeedRef = useRef(runningSpeed);
  
  const planningParserRef = useRef<VisBaseParser | null>(null);
  const runningParserRef = useRef<VisBaseParser | null>(null);
  
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 同步 state 到 ref，以便在 setTimeout 中获取最新值
  useEffect(() => {
    planningContentRef.current = planningContent;
    planningSpeedRef.current = planningSpeed;
  }, [planningContent, planningSpeed]);

  useEffect(() => {
    runningContentRef.current = runningContent;
    runningSpeedRef.current = runningSpeed;
  }, [runningContent, runningSpeed]);

  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  useEffect(() => {
    currentIndexRef.current = currentIndex;
  }, [currentIndex]);

  const addDebugLog = useCallback((type: DebugLog['type'], message: string, details?: Record<string, any>) => {
    const newLog: DebugLog = {
      id: ++logIdRef.current,
      timestamp: new Date().toLocaleTimeString(),
      type,
      message,
      details,
    };
    setDebugLogs(prev => [...prev.slice(-99), newLog]);
  }, []);

  const parseChunkData = useCallback((jsonStr: string): ParsedVisData | null => {
    try {
      const data = JSON.parse(jsonStr);
      if (data.vis) {
        try {
          const visData = JSON.parse(data.vis);
          return {
            planning_window: visData.planning_window,
            running_window: visData.running_window,
          };
        } catch {
          return { planning_window: data.vis };
        }
      }
      return data;
    } catch (e) {
      return null;
    }
  }, []);

  const extractThinkingInfo = useCallback((content: string): { count: number; snippets: string[] } => {
    const thinkingRegex = /```d-thinking\s*\n([\s\S]*?)```/g;
    const matches = content.matchAll(thinkingRegex);
    const snippets: string[] = [];
    let count = 0;
    
    for (const match of matches) {
      count++;
      const snippet = match[1].trim();
      if (snippet.length > 0) {
        snippets.push(snippet.substring(0, 100) + (snippet.length > 100 ? '...' : ''));
      }
    }
    
    return { count, snippets };
  }, []);

  const analyzeChunk = useCallback((chunk: ChunkData, index: number): Record<string, any> => {
    const parsed = parseChunkData(chunk.vis);
    const analysis: Record<string, any> = {
      index: index + 1,
      hasPlanningWindow: false,
      hasRunningWindow: false,
      planningLength: 0,
      runningLength: 0,
      thinkingCount: 0,
      thinkingSnippets: [] as string[],
    };

    if (parsed) {
      if (parsed.planning_window) {
        analysis.hasPlanningWindow = true;
        analysis.planningLength = parsed.planning_window.length;
        const planningThinking = extractThinkingInfo(parsed.planning_window);
        analysis.thinkingCount += planningThinking.count;
        analysis.thinkingSnippets.push(...planningThinking.snippets);
      }
      
      if (parsed.running_window) {
        analysis.hasRunningWindow = true;
        analysis.runningLength = parsed.running_window.length;
        const runningThinking = extractThinkingInfo(parsed.running_window);
        analysis.thinkingCount += runningThinking.count;
        analysis.thinkingSnippets.push(...runningThinking.snippets);
      }
    }

    return analysis;
  }, [parseChunkData, extractThinkingInfo]);

  const handleFileUpload = useCallback((file: File) => {
    const reader = new FileReader();
    const fileSizeKB = (file.size / 1024).toFixed(2);
    
    reader.onload = (e) => {
      try {
        const content = e.target?.result as string;
        const lines = content.trim().split('\n');
        const parsedChunks: ChunkData[] = [];
        
        addDebugLog('info', `开始解析文件，共 ${lines.length} 行`);
        
        lines.forEach((line, index) => {
          try {
            const parsed = JSON.parse(line);
            if (parsed.vis) {
              parsedChunks.push(parsed);
            }
          } catch (err) {
            addDebugLog('warn', `第 ${index + 1} 行解析失败`);
          }
        });
        
        if (parsedChunks.length === 0) {
          setError('未找到有效的chunk数据');
          addDebugLog('error', '未找到有效的chunk数据');
          return;
        }
        
        setChunks(parsedChunks);
        setFileInfo({ name: file.name, size: fileSizeKB });
        setError('');
        
        const chunkAnalyses = parsedChunks.map((chunk, idx) => analyzeChunk(chunk, idx));
        
        addDebugLog('success', `成功加载 ${parsedChunks.length} 个chunk`);
        
        setCurrentIndex(0);
        setPlanningContent('');
        setRunningContent('');
        setIsPlaying(false);
        currentIndexRef.current = 0;
        planningContentRef.current = '';
        runningContentRef.current = '';
        
        planningParserRef.current = new VisBaseParser();
        runningParserRef.current = new VisBaseParser();
        
      } catch (err: any) {
        setError(`文件解析错误: ${err.message}`);
        addDebugLog('error', `文件解析失败`);
      }
    };
    
    reader.readAsText(file);
    return false;
  }, [addDebugLog, analyzeChunk]);

  const playNextChunk = useCallback(() => {
    const index = currentIndexRef.current;
    
    if (index >= chunks.length) {
      setIsPlaying(false);
      isPlayingRef.current = false;
      addDebugLog('success', '回放完成');
      return;
    }

    const chunk = chunks[index];
    const parsed = parseChunkData(chunk.vis);
    
    if (!parsed) {
      addDebugLog('warn', `Chunk ${index + 1} 解析失败，跳过`);
      setCurrentIndex(index + 1);
      currentIndexRef.current = index + 1;
      
      if (isPlayingRef.current) {
        timeoutRef.current = setTimeout(playNextChunk, 100);
      }
      return;
    }

    // 关键修复：使用 ref 中的最新速度值，而不是闭包中的旧值
    const hasBoth = parsed.planning_window && parsed.running_window;
    const currentPlanningSpeed = planningSpeedRef.current;
    const currentRunningSpeed = runningSpeedRef.current;
    const delay = hasBoth ? currentPlanningSpeed * 1000 : 
                  (parsed.planning_window ? currentPlanningSpeed * 1000 : currentRunningSpeed);

    if (parsed.planning_window && planningParserRef.current) {
      const newContent = planningParserRef.current.updateCurrentMarkdown(parsed.planning_window);
      setPlanningContent(newContent);
      planningContentRef.current = newContent;
    }

    if (parsed.running_window && runningParserRef.current) {
      const newContent = runningParserRef.current.updateCurrentMarkdown(parsed.running_window);
      setRunningContent(newContent);
      runningContentRef.current = newContent;
    }

    setCurrentIndex(index + 1);
    currentIndexRef.current = index + 1;

    addDebugLog('info', `播放 Chunk ${index + 1}/${chunks.length}`, {
      hasPlanning: !!parsed.planning_window,
      hasRunning: !!parsed.running_window,
      planningLen: parsed.planning_window?.length || 0,
      runningLen: parsed.running_window?.length || 0,
      delay,
    });

    if (isPlayingRef.current && index + 1 < chunks.length) {
      timeoutRef.current = setTimeout(playNextChunk, delay);
    } else if (index + 1 >= chunks.length) {
      setIsPlaying(false);
      isPlayingRef.current = false;
      addDebugLog('success', '回放完成');
    }
  }, [chunks, parseChunkData, addDebugLog]);

  const startReplay = useCallback(() => {
    if (chunks.length === 0) {
      setError('请先上传jsonl文件');
      return;
    }

    if (currentIndexRef.current >= chunks.length) {
      resetReplay();
    }

    setIsPlaying(true);
    isPlayingRef.current = true;
    addDebugLog('info', '开始回放');
    
    playNextChunk();
  }, [chunks.length, playNextChunk, addDebugLog]);

  const pauseReplay = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setIsPlaying(false);
    isPlayingRef.current = false;
    addDebugLog('info', '暂停回放');
  }, [addDebugLog]);

  const resetReplay = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setIsPlaying(false);
    isPlayingRef.current = false;
    setCurrentIndex(0);
    currentIndexRef.current = 0;
    setPlanningContent('');
    planningContentRef.current = '';
    setRunningContent('');
    runningContentRef.current = '';
    planningParserRef.current = new VisBaseParser();
    runningParserRef.current = new VisBaseParser();
    addDebugLog('info', '重置回放');
  }, [addDebugLog]);

  const stepForward = useCallback(() => {
    if (currentIndex < chunks.length) {
      const chunk = chunks[currentIndex];
      const parsed = parseChunkData(chunk.vis);
      
      if (parsed?.planning_window && planningParserRef.current) {
        const newContent = planningParserRef.current.updateCurrentMarkdown(parsed.planning_window);
        setPlanningContent(newContent);
      }
      
      if (parsed?.running_window && runningParserRef.current) {
        const newContent = runningParserRef.current.updateCurrentMarkdown(parsed.running_window);
        setRunningContent(newContent);
      }
      
      setCurrentIndex(prev => prev + 1);
      currentIndexRef.current = currentIndex + 1;
    }
  }, [currentIndex, chunks, parseChunkData]);

  const stepBackward = useCallback(() => {
    if (currentIndex > 0) {
      const newIndex = currentIndex - 1;
      planningParserRef.current = new VisBaseParser();
      runningParserRef.current = new VisBaseParser();
      
      let planning = '';
      let running = '';
      
      for (let i = 0; i < newIndex; i++) {
        const chunk = chunks[i];
        const parsed = parseChunkData(chunk.vis);
        if (parsed?.planning_window && planningParserRef.current) {
          planning = planningParserRef.current.updateCurrentMarkdown(parsed.planning_window);
        }
        if (parsed?.running_window && runningParserRef.current) {
          running = runningParserRef.current.updateCurrentMarkdown(parsed.running_window);
        }
      }
      
      setPlanningContent(planning);
      planningContentRef.current = planning;
      setRunningContent(running);
      runningContentRef.current = running;
      setCurrentIndex(newIndex);
      currentIndexRef.current = newIndex;
    }
  }, [currentIndex, chunks, parseChunkData]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const progressPercent = useMemo(() => {
    if (chunks.length === 0) return 0;
    return Math.round((currentIndex / chunks.length) * 100);
  }, [currentIndex, chunks.length]);

  const stats = useMemo(() => {
    return {
      planningChars: planningContent.length,
      runningChars: runningContent.length,
      totalChunks: chunks.length,
      currentChunk: currentIndex,
    };
  }, [planningContent.length, runningContent.length, chunks.length, currentIndex]);

  const currentVisData = useMemo(() => {
    const visObj: any = {};
    if (planningContent) visObj.planning_window = planningContent;
    if (runningContent) visObj.running_window = runningContent;
    return JSON.stringify({ vis: JSON.stringify(visObj) }, null, 2);
  }, [planningContent, runningContent]);

  const copyVisData = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(currentVisData);
      message.success('已复制到剪贴板');
    } catch (err) {
      message.error('复制失败');
    }
  }, [currentVisData]);

  const copyPlanningContent = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(planningContent);
      message.success('已复制到剪贴板');
    } catch (err) {
      message.error('复制失败');
    }
  }, [planningContent]);

  const copyRunningContent = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(runningContent);
      message.success('已复制到剪贴板');
    } catch (err) {
      message.error('复制失败');
    }
  }, [runningContent]);

  return (
    <div style={{ width: '100%', display: 'block' }}>
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden mb-6 w-full">
        <div className="px-6 py-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-gray-100">
          <Row gutter={[24, 16]} align="middle" style={{ width: '100%' }}>
            <Col xs={24} md={6} lg={4}>
              <div className="flex flex-col gap-2">
                <Upload
                  accept=".jsonl"
                  fileList={fileList}
                  beforeUpload={handleFileUpload}
                  onChange={({ fileList }) => setFileList(fileList)}
                  maxCount={1}
                  showUploadList={false}
                >
                  <Button 
                    type="primary" 
                    icon={<UploadOutlined />} 
                    size="large"
                    className="shadow-sm"
                  >
                    上传 JSONL
                  </Button>
                </Upload>
                {fileInfo && (
                  <div className="text-xs text-gray-600">
                    <div className="truncate" title={fileInfo.name}>
                      {fileInfo.name}
                    </div>
                    <div className="flex items-center gap-2">
                      <span>{fileInfo.size}KB</span>
                      <span>•</span>
                      <span>{chunks.length} chunks</span>
                    </div>
                  </div>
                )}
              </div>
            </Col>
            
            <Col xs={24} md={12} lg={14}>
              {chunks.length > 0 ? (
                <Space size="middle" wrap>
                  {!isPlaying ? (
                    <Button
                      type="primary"
                      icon={<PlayCircleOutlined />}
                      onClick={startReplay}
                      disabled={currentIndex >= chunks.length}
                      size="large"
                      className="shadow-sm"
                    >
                      {currentIndex === 0 ? '开始回放' : '继续'}
                    </Button>
                  ) : (
                    <Button
                      icon={<PauseCircleOutlined />}
                      onClick={pauseReplay}
                      size="large"
                    >
                      暂停
                    </Button>
                  )}
                  
                  <Button.Group>
                    <Button
                      icon={<StepBackwardOutlined />}
                      onClick={stepBackward}
                      disabled={currentIndex === 0 || isPlaying}
                    >
                      上一步
                    </Button>
                    <Button
                      icon={<StepForwardOutlined />}
                      onClick={stepForward}
                      disabled={currentIndex >= chunks.length || isPlaying}
                    >
                      下一步
                    </Button>
                  </Button.Group>
                  
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={resetReplay}
                    disabled={currentIndex === 0}
                  >
                    重置
                  </Button>
                  
                  <Button
                    type="dashed"
                    icon={<EyeOutlined />}
                    onClick={() => setShowVisModal(true)}
                    disabled={currentIndex === 0}
                  >
                    查看Vis
                  </Button>
                </Space>
              ) : null}
            </Col>
            
            <Col xs={24} md={6} lg={6}>
              {chunks.length > 0 ? (
                <div className="flex items-center gap-3">
                  <Progress
                    percent={progressPercent}
                    status={isPlaying ? 'active' : 'normal'}
                    format={() => `${currentIndex} / ${chunks.length}`}
                    strokeColor={{ from: '#1890ff', to: '#52c41a' }}
                    className="flex-1"
                  />
                  <Badge 
                    status={isPlaying ? 'processing' : currentIndex === chunks.length ? 'success' : 'default'} 
                    text={isPlaying ? '播放中' : currentIndex === chunks.length ? '已完成' : '已暂停'}
                  />
                </div>
              ) : null}
            </Col>
          </Row>
        </div>
        
        {chunks.length > 0 && (
          <div className="px-6 py-3 bg-gray-50/50">
            <Row gutter={[48, 8]} align="middle">
              <Col xs={24} md={8}>
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                  <Text type="secondary" className="text-xs whitespace-nowrap">Planning</Text>
                  <Slider
                    className="flex-1 mx-2"
                    min={1}
                    max={5}
                    step={1}
                    value={planningSpeed}
                    onChange={setPlanningSpeed}
                    disabled={isPlaying}
                    tooltip={{ formatter: (v) => `${v}秒` }}
                  />
                  <Tag color="blue" className="text-xs">{planningSpeed}s</Tag>
                </div>
              </Col>
              <Col xs={24} md={8}>
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-green-500"></div>
                  <Text type="secondary" className="text-xs whitespace-nowrap">Running</Text>
                  <Slider
                    className="flex-1 mx-2"
                    min={5}
                    max={50}
                    step={5}
                    value={runningSpeed}
                    onChange={setRunningSpeed}
                    disabled={isPlaying}
                    tooltip={{ formatter: (v) => `${v}ms` }}
                  />
                  <Tag color="green" className="text-xs">{runningSpeed}ms</Tag>
                </div>
              </Col>
              <Col xs={24} md={8}>
                <div className="flex items-center justify-end gap-6">
                  <div className="text-right">
                    <Text type="secondary" className="text-xs block">Planning</Text>
                    <Text strong className="text-blue-600">{stats.planningChars}</Text>
                    <Text type="secondary" className="text-xs"> 字符</Text>
                  </div>
                  <div className="text-right">
                    <Text type="secondary" className="text-xs block">Running</Text>
                    <Text strong className="text-green-600">{stats.runningChars}</Text>
                    <Text type="secondary" className="text-xs"> 字符</Text>
                  </div>
                  <div className="text-right">
                    <Text type="secondary" className="text-xs block">进度</Text>
                    <Text strong>{stats.currentChunk}</Text>
                    <Text type="secondary" className="text-xs"> / {stats.totalChunks}</Text>
                  </div>
                </div>
              </Col>
            </Row>
          </div>
        )}
      </div>

      {error && (
        <Alert
          message={error}
          type="error"
          showIcon
          closable
          onClose={() => setError('')}
          className="mb-6 rounded-lg"
        />
      )}

      {chunks.length > 0 ? (
        <div className="grid grid-cols-12 gap-6 mb-6">
          <div className="col-span-12 lg:col-span-5">
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden h-full">
              <div className="px-4 py-3 bg-gradient-to-r from-blue-50 to-blue-100/50 border-b border-blue-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-blue-500 shadow-sm shadow-blue-500/30"></div>
                  <span className="font-medium text-gray-800">Planning Window</span>
                </div>
                <div className="flex items-center gap-2">
                  <Tag color="blue" className="border-0 bg-blue-100 text-blue-700">
                    {planningContent.length.toLocaleString()} 字符
                  </Tag>
                  <Button
                    type="text"
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => setShowPlanningModal(true)}
                    disabled={!planningContent}
                  >
                    查看
                  </Button>
                </div>
              </div>
              <div className="p-4 bg-gray-50/50">
                <div className="bg-white rounded-lg border border-gray-200 p-4 min-h-[400px] max-h-[500px] overflow-auto">
                  {planningContent ? (
                    <GPTVis components={markdownComponents} {...markdownPlugins}>
                      {preprocessLaTeX(planningContent)}
                    </GPTVis>
                  ) : (
                    <div className="h-full flex items-center justify-center text-gray-400 min-h-[300px]">
                      <Text>等待播放...</Text>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="col-span-12 lg:col-span-7">
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden h-full">
              <div className="px-4 py-3 bg-gradient-to-r from-green-50 to-green-100/50 border-b border-green-100 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-green-500 shadow-sm shadow-green-500/30"></div>
                  <span className="font-medium text-gray-800">Running Window</span>
                </div>
                <div className="flex items-center gap-2">
                  <Tag color="green" className="border-0 bg-green-100 text-green-700">
                    {runningContent.length.toLocaleString()} 字符
                  </Tag>
                  <Button
                    type="text"
                    size="small"
                    icon={<EyeOutlined />}
                    onClick={() => setShowRunningModal(true)}
                    disabled={!runningContent}
                  >
                    查看
                  </Button>
                </div>
              </div>
              <div className="p-4 bg-gray-50/50">
                <div className="bg-white rounded-lg border border-gray-200 p-4 min-h-[400px] max-h-[500px] overflow-auto">
                  {runningContent ? (
                    <GPTVis components={markdownComponents} {...markdownPlugins}>
                      {preprocessLaTeX(runningContent)}
                    </GPTVis>
                  ) : (
                    <div className="h-full flex items-center justify-center text-gray-400 min-h-[300px]">
                      <Text>等待播放...</Text>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="w-full max-w-full">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 py-16 mb-6 w-full">
            <div className="text-center px-4 w-full">
              <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-blue-50 mb-6">
                <FileTextOutlined style={{ fontSize: 40, color: '#1890ff' }} />
              </div>
              <Title level={4} className="mb-3">Chunk 回放工具</Title>
              <Text type="secondary" className="block mx-auto leading-relaxed mb-6 px-4">
                上传 JSONL 格式的对话过程文件，可视化查看 Planning Window 和 Running Window 的合并过程
              </Text>
              <div className="text-left bg-gray-50 rounded-xl p-6 border border-gray-100 mx-auto" style={{ maxWidth: '800px' }}>
                <Text strong className="block mb-3 text-gray-700">文件格式示例：</Text>
                <pre className="bg-white p-4 rounded-lg text-xs text-gray-600 border border-gray-200 overflow-auto text-left">
{`{"vis": "{\\"planning_window\\": \"...\", \\"running_window\\": \"...\"}"}
{"vis": "{\\"planning_window\\": \"...\", \\"running_window\\": \"...\"}"`}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}

      {chunks.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div 
            className="px-4 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between cursor-pointer hover:bg-gray-100/50 transition-colors"
            onClick={() => setShowDebugPanel(!showDebugPanel)}
          >
            <div className="flex items-center gap-2">
              <BugOutlined className="text-gray-500" />
              <span className="font-medium text-gray-700">调试日志</span>
              <Badge count={debugLogs.length} style={{ backgroundColor: '#1890ff' }} />
            </div>
            <Space>
              <Button 
                size="small" 
                onClick={(e) => { e.stopPropagation(); setDebugLogs([]); }}
              >
                清空
              </Button>
              <Button 
                size="small" 
                type={showDebugPanel ? 'primary' : 'default'}
                onClick={(e) => { e.stopPropagation(); setShowDebugPanel(!showDebugPanel); }}
              >
                {showDebugPanel ? '收起' : '展开'}
              </Button>
            </Space>
          </div>
          
          {showDebugPanel && (
            <div className="p-0 bg-gray-900">
              <div className="max-h-64 overflow-auto font-mono text-xs p-4">
                {debugLogs.length === 0 ? (
                  <div className="text-gray-500 py-4">// 暂无日志</div>
                ) : (
                  debugLogs.map((log) => (
                    <div key={log.id} className="mb-1">
                      <span className="text-gray-500">[{log.timestamp}]</span>
                      <span className={`ml-2 font-bold ${
                        log.type === 'error' ? 'text-red-400' :
                        log.type === 'warn' ? 'text-yellow-400' :
                        log.type === 'success' ? 'text-green-400' :
                        'text-blue-400'
                      }`}>
                        {log.type.toUpperCase()}
                      </span>
                      <span className="ml-2 text-gray-200">{log.message}</span>
                      {log.details && (
                        <div className="ml-0 mt-1 pl-4 border-l-2 border-gray-700 text-gray-400">
                          {JSON.stringify(log.details, null, 2).split('\n').map((line, idx) => (
                            <div key={idx} className="whitespace-pre">{line}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}
      
      <Modal
        title="当前Vis数据"
        open={showVisModal}
        onCancel={() => setShowVisModal(false)}
        width={800}
        footer={[
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={copyVisData}>
            复制到剪贴板
          </Button>,
          <Button key="close" onClick={() => setShowVisModal(false)}>
            关闭
          </Button>,
        ]}
      >
        <div className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-[500px]">
          <pre className="text-green-400 font-mono text-sm whitespace-pre-wrap">
            {currentVisData}
          </pre>
        </div>
        <div className="mt-4 text-gray-500 text-sm">
          <p>当前进度：{currentIndex} / {chunks.length} chunks</p>
          <p>Planning：{planningContent.length} 字符 | Running：{runningContent.length} 字符</p>
        </div>
      </Modal>
      
      <Modal
        title="Planning Window 内容"
        open={showPlanningModal}
        onCancel={() => setShowPlanningModal(false)}
        width={1000}
        footer={[
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={copyPlanningContent}>
            复制到剪贴板
          </Button>,
          <Button key="close" onClick={() => setShowPlanningModal(false)}>
            关闭
          </Button>,
        ]}
      >
        <div className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-[600px]">
          <pre className="text-green-400 font-mono text-sm whitespace-pre-wrap">
            {planningContent}
          </pre>
        </div>
        <div className="mt-4 text-gray-500 text-sm">
          <p>当前进度：{currentIndex} / {chunks.length} chunks</p>
          <p>Planning：{planningContent.length.toLocaleString()} 字符</p>
        </div>
      </Modal>
      
      <Modal
        title="Running Window 内容"
        open={showRunningModal}
        onCancel={() => setShowRunningModal(false)}
        width={1000}
        footer={[
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={copyRunningContent}>
            复制到剪贴板
          </Button>,
          <Button key="close" onClick={() => setShowRunningModal(false)}>
            关闭
          </Button>,
        ]}
      >
        <div className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-[600px]">
          <pre className="text-green-400 font-mono text-sm whitespace-pre-wrap">
            {runningContent}
          </pre>
        </div>
        <div className="mt-4 text-gray-500 text-sm">
          <p>当前进度：{currentIndex} / {chunks.length} chunks</p>
          <p>Running：{runningContent.length.toLocaleString()} 字符</p>
        </div>
      </Modal>
    </div>
  );
}