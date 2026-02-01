import React, { FC, useEffect, useRef, useState, useMemo, useCallback, memo } from 'react';
import {
  CheckCircleOutlined,
  CloseOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ArrowsAltOutlined,
  ShrinkOutlined,
  DownOutlined,
  RightOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { Space, Tooltip, Button } from 'antd';
import dayjs from 'dayjs';
import { keyBy } from 'lodash';
import {
  VariableSizeList as List,
  ListChildComponentProps,
} from 'react-window';
import {
  AgentContainer,
  AgentContent,
  FolderContainer,
  HeaderContainer,
} from './style';
import { codeComponents, type MarkdownComponent, markdownPlugins } from '../../config';
import { useElementHeight } from '../hooks/useElementHeight';
import { useElementWidth } from '../hooks/useElementWidth';
import { ee, EVENTS } from '../../../../../utils/event-emitter';

interface RunningItem {
  uid: string;
  type: string;
  dynamic: boolean;
  conv_id: string;
  topic: string;
  path_uid: string;
  item_type: string;
  title: string;
  description: string;
  status: 'complete' | 'todo' | 'running';
  start_time: string;
  cost: number;
  markdown: string;
}

interface IProps {
  otherComponents?: MarkdownComponent;
  data: {
    uid: string;
    items: RunningItem[];
    dynamic: boolean;
    running_agent: string | string[];
    type: string;
    agent_role: string;
    agent_name: string;
    description: string;
    avatar: string;
    explorer: string;
  };
  style?: React.CSSProperties;
}

// 配置常量
const CONFIG = {
  // 虚拟滚动阈值：超过这个数量使用虚拟滚动
  VIRTUAL_SCROLL_THRESHOLD: 30,

  // 内容长度阈值（字符数）：超过这个长度需要折叠
  LARGE_CONTENT_THRESHOLD: 5000,

  // 内容长度阈值（字符数）：超过这个长度需要分块懒加载
  HUGE_CONTENT_THRESHOLD: 20000,

  // 预显示的字符数（折叠时）
  PREVIEW_CHARS: 500,

  // 每块大小（分块懒加载时）
  CHUNK_SIZE: 2000,
};

const IconMap: Record<string, JSX.Element> = {
  complete: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 12 }} />,
  todo: <CheckCircleOutlined style={{ color: '#595959', fontSize: 12 }} />,
  running: <LoadingOutlined style={{ color: '#1677ff', fontSize: 12 }} />,
  waiting: <PauseCircleOutlined style={{ color: '#f5dc62', fontSize: 12 }} />,
  retrying: <LoadingOutlined style={{ color: '#1677ff', fontSize: 12 }} />,
  failed: (
    <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 12 }} />
  ),
};

/**
 * Memoized GPTVis 组件
 * 只有当 children 或 components 改变时才重新渲染
 */
const MemoizedGPTVis = memo(
  ({
    children,
    components,
    className,
    ...props
  }: {
    children: string;
    components: any;
    className?: string;
  }) => (
    // @ts-ignore
    <GPTVis
      className={className}
      components={components}
      {...props}
      {...markdownPlugins}
    >
      {children}
    </GPTVis>
  ),
  (prev, next) => prev.children === next.children && prev.components === next.components,
);
MemoizedGPTVis.displayName = 'MemoizedGPTVis';

/**
 * 大型内容折叠组件
 * 对超长内容进行折叠处理
 */
interface LongContentWrapperProps {
  content: string;
  children: React.ReactNode;
  isPreview?: boolean;
}

const LongContentWrapper: FC<LongContentWrapperProps> = ({ content, children, isPreview = false }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const contentLength = content.length;
  const shouldCollapse = contentLength > CONFIG.LARGE_CONTENT_THRESHOLD;

  if (!shouldCollapse || isExpanded) {
    return <>{children}</>;
  }

  return (
    <div className="long-content-wrapper">
      <div className="long-content-preview">
        {children}
      </div>
      <div className="long-content-footer">
        <Button
          type="link"
          size="small"
          onClick={() => setIsExpanded(true)}
          icon={<DownOutlined />}
        >
          展开全部内容（{contentLength.toLocaleString()} 字符）
        </Button>
      </div>
    </div>
  );
};

/**
 * 分块懒加载渲染器
 * 对超大内容进行分块渐进式渲染
 */
interface ChunkedRendererProps {
  content: string;
  renderChunk: (chunk: string, index: number) => React.ReactNode;
}

const ChunkedRenderer: FC<ChunkedRendererProps> = ({ content, renderChunk }) => {
  const [visibleChunks, setVisibleChunks] = useState(1);
  const chunkCount = Math.ceil(content.length / CONFIG.CHUNK_SIZE);

  // 初始加载第一块，后续通过定时器渐近加载
  useEffect(() => {
    let mounted = true;
    let chunkIndex = 1;

    const loadNextChunk = () => {
      if (!mounted || chunkIndex >= chunkCount) {
        return;
      }
      chunkIndex++;
      setVisibleChunks(chunkIndex);
      // 逐渐增加延迟，避免阻塞UI
      requestAnimationFrame(() => {
        setTimeout(loadNextChunk, 50 * Math.min(chunkIndex, 5));
      });
    };

    const timer = setTimeout(loadNextChunk, 100);
    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, [content.length, chunkCount]);

  return (
    <>
      {Array.from({ length: visibleChunks }, (_, i) => i).map(index => {
        const start = index * CONFIG.CHUNK_SIZE;
        const end = start + CONFIG.CHUNK_SIZE;
        return (
          <div key={index} className="content-chunk">
            {renderChunk(content.slice(start, end), index)}
          </div>
        );
      })}
    </>
  );
};

/**
 * Markdown内容组件
 * 结合折叠和分块来实现超长内容的高性能渲染
 */
interface MarkdownContentProps {
  markdown: string;
  components: any;
  className?: string;
  isDynamic?: boolean;
}

const MarkdownContent: FC<MarkdownContentProps> = ({
  markdown,
  components,
  className = '',
  isDynamic = false,
}) => {
  const [renderedMarkdown, setRenderedMarkdown] = useState(markdown);
  const [isProcessing, setIsProcessing] = useState(false);

  // 使用debounce来避免频繁更新
  useEffect(() => {
    if (markdown === renderedMarkdown) return;

    // 对于短内容或非动态内容，直接更新
    if (markdown.length < CONFIG.HUGE_CONTENT_THRESHOLD && !isDynamic) {
      setRenderedMarkdown(markdown);
      return;
    }

    // 对于长内容，使用防抖
    setIsProcessing(true);
    const timer = setTimeout(() => {
      setRenderedMarkdown(markdown);
      setIsProcessing(false);
    }, 300);

    return () => clearTimeout(timer);
  }, [markdown, isDynamic, renderedMarkdown]);

  const isLarge = renderedMarkdown.length > CONFIG.LARGE_CONTENT_THRESHOLD;
  const isHuge = renderedMarkdown.length > CONFIG.HUGE_CONTENT_THRESHOLD;

  const renderVis = (content: string) => (
    <MemoizedGPTVis className={className} components={components}>
      {content}
    </MemoizedGPTVis>
  );

  // 简短内容：直接渲染
  if (!isLarge) {
    return renderVis(renderedMarkdown);
  }

  // 中等内容：折叠显示
  if (!isHuge) {
    return (
      <LongContentWrapper content={renderedMarkdown}>
        {renderVis(renderedMarkdown)}
      </LongContentWrapper>
    );
  }

  // 超大内容：分块懒加载
  return (
    <LongContentWrapper content={renderedMarkdown}>
      <ChunkedRenderer
        content={renderedMarkdown}
        renderChunk={(chunk, index) => renderVis(chunk)}
      />
    </LongContentWrapper>
  );
};

/**
 * Markdown行组件 - 用于虚拟滚动
 * 使用IntersectionObserver实现可见区域检测，减少不可见区域的渲染开销
 */
const MarkdownRow: FC<{ index: number; style: React.CSSProperties; data: any }> = memo(
  ({ index, style, data }) => {
    const { mergedComponents, currentItem, isVisible } = data;
    const rowRef = useRef<HTMLDivElement>(null);
    const [shouldRenderDetailed, setShouldRenderDetailed] = useState(false);

    // 使用IntersectionObserver优化：只有行可见时才渲染完整内容
    useEffect(() => {
      const element = rowRef.current;
      if (!element) return;

      const observer = new IntersectionObserver(
        (entries) => {
          const entry = entries[0];
          if (entry.isIntersecting) {
            setShouldRenderDetailed(true);
          } else {
            // 当行不可见时，可以考虑放入休眠状态
            // 这里我们保持渲染状态以避免闪烁，但可以进一步优化
          }
        },
        {
          root: null,
          rootMargin: '200px 0px 200px 0px', // 提前200px开始渲染
          threshold: 0,
        }
      );

      observer.observe(element);
      return () => observer.disconnect();
    }, [index]);

    // 对于可见区域或大内容，渲染完整内容
    // 对于不可见区域的小内容，可以简化渲染
    const contentLength = (currentItem.markdown || '').length;
    const useSimplifiedRender = !shouldRenderDetailed && contentLength < CONFIG.LARGE_CONTENT_THRESHOLD;

    return (
      <div ref={rowRef} style={style} className="vis-running-window-row">
        {currentItem.status === 'complete' && currentItem.start_time && (
          <div
            className="vis-running-window-row-header"
            style={{
              color: '#aaaaaa',
              fontSize: '12px',
              borderBottom: '1px solid #dddddd',
              padding: '4px 12px',
            }}
          >
            <Space size={4}>
              {IconMap[currentItem.status]}
              <span>{dayjs(currentItem.start_time).format('HH:mm:ss')}</span>
            </Space>
          </div>
        )}
        <div className="vis-running-window-row-content">
          {useSimplifiedRender ? (
            // 简化渲染：只显示纯文本预览
            <div className="simplified-render">
              {currentItem.status === 'running' ? (
                <LoadingOutlined style={{ color: '#1677ff', marginRight: 8 }} />
              ) : null}
              <span className="markdown-preview">
                {currentItem.markdown?.slice(0, 100) || '-'}
                {contentLength > 100 ? '...' : ''}
              </span>
              {contentLength > CONFIG.LARGE_CONTENT_THRESHOLD && (
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0, marginLeft: 8 }}
                  onClick={() => setShouldRenderDetailed(true)}
                >
                  查看完整内容 ({(contentLength / 1000).toFixed(1)}k字符)
                </Button>
              )}
            </div>
          ) : (
            // 完整渲染
            <MarkdownContent
              markdown={currentItem.markdown || '-'}
              components={mergedComponents}
              isDynamic={currentItem.status === 'running'}
            />
          )}
        </div>
      </div>
    );
  },
  (prev, next) => {
    // 根据item内容和可见状态决定是否需要重新渲染
    const prevItem = prev.data.currentItem;
    const nextItem = next.data.currentItem;
    const prevVisible = prev.data.isVisible;
    const nextVisible = next.data.isVisible;

    // 内容相同且可见状态未变化时，跳过渲染
    if (prevItem === nextItem && prevVisible === nextVisible) {
      return true;
    }

    // 状态变化时需要重新渲染
    if (prevItem?.status !== nextItem?.status) {
      return false;
    }

    return false;
  },
);

MarkdownRow.displayName = 'MarkdownRow';

/**
 * 扁平化items列表
 */
const flattenItems = (items: RunningItem[]): RunningItem[] => {
  return items.slice(); // 创建浅拷贝
};

/**
 * 估算文本行数的高度
 */
const estimateRowHeight = (markdown: string, isHeader: boolean = false): number => {
  if (!markdown) {
    return isHeader ? 24 : 20;
  }

  const contentLength = markdown.length;

  // 快速估算：假设每100字符约等于1行（22px）高度
  const estimatedLines = Math.ceil(contentLength / 80);
  const contentHeight = Math.max(20, estimatedLines * 18);

  // 代码块额外高度
  const codeBlockMatches = markdown.match(/```[\s\S]*?```/g);
  const codeBlockHeight = codeBlockMatches
    ? codeBlockMatches.reduce((sum, block) => {
        const lines = block.split('\n').length;
        return sum + Math.max(60, lines * 16);
      }, 0)
    : 0;

  // 大内容折叠后的高度
  const isLarge = contentLength > CONFIG.LARGE_CONTENT_THRESHOLD;
  if (isLarge) {
    // 折叠后只显示预览高度
    return Math.min(contentHeight, 200) + 40; // 40是展开按钮高度
  }

  return (isHeader ? 24 : 0) + Math.min(contentHeight, 2000) + codeBlockHeight;
};

/**
 * VisRunningWindowV2 主组件
 * 使用虚拟滚动 + 内容折叠 + 分块懒加载 来优化大量内容的性能
 */
export const VisRunningWindowV2: FC<IProps> = ({ otherComponents, data }) => {
  const [displayUid, setDisplayUid] = useState<string>('');
  const [isFolderVisible, setIsFolderVisible] = useState<boolean>(true);
  const [isFullScreen, setIsFullScreen] = useState<boolean>(false);
  const listRef = useRef<any>(null);
  const processedItemsCount = useRef<number>(0);
  const heightMapRef = useRef<Map<string, number>>(new Map());
  const visibleRangeRef = useRef({ start: 0, end: 0 });

  // 扁平化items用于虚拟滚动
  const flatItems = useMemo(() => {
    if (displayUid && data.items.find((item) => item.uid === displayUid)) {
      return [data.items.find((item) => item.uid === displayUid)!];
    }
    return flattenItems(data.items);
  }, [data.items, displayUid]);

  const runningContent = useMemo(() => keyBy(data.items, 'uid'), [data.items]);

  const mergedComponents = useMemo(
    () => ({ ...codeComponents, ...(otherComponents || {}) }),
    [otherComponents],
  );

  const containerHeight = useElementHeight(
    `#nex-chat-detail-panel${data.uid}`,
    `#nex-chat-detail-panel`,
  );
  const containerWidth = useElementWidth('.chatContent', 'body');

  // 初始化高度缓存
  useEffect(() => {
    flatItems.forEach((item) => {
      if (!heightMapRef.current.has(item.uid)) {
        heightMapRef.current.set(item.uid, estimateRowHeight(item.markdown, item.status === 'complete'));
      }
    });
  }, [flatItems]);

  useEffect(() => {
    const onClickFolder = (payload: { uid: string }) => {
      setDisplayUid(payload.uid);
    };
    ee.on(EVENTS.CLICK_FOLDER, onClickFolder);
    return () => {
      ee.off(EVENTS.CLICK_FOLDER, onClickFolder);
    };
  }, []);

  useEffect(() => {
    if (data.items.length < processedItemsCount.current) {
      processedItemsCount.current = data.items.length;
    }

    const newItems = data.items.slice(processedItemsCount.current);
    if (newItems.length > 0) {
      newItems.forEach((item) => {
        ee.emit(EVENTS.ADD_TASK, { folderItem: item });
      });
      processedItemsCount.current = data.items.length;
    }
  }, [data.items]);

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    if (listRef.current && flatItems.length > 0) {
      listRef.current.scrollToItem(flatItems.length - 1, 'end');
    }
  }, [flatItems.length]);

  useEffect(() => {
    scrollToBottom();
  }, [
    scrollToBottom,
    runningContent?.[displayUid]?.markdown,
    data.items[data.items.length - 1]?.markdown,
  ]);

  // 计算行高度
  const getItemHeight = useCallback(
    (index: number) => {
      const item = flatItems[index];
      const existingHeight = heightMapRef.current.get(item.uid);

      if (existingHeight) {
        return existingHeight;
      }

      const estimatedHeight = estimateRowHeight(item.markdown, item.status === 'complete');
      heightMapRef.current.set(item.uid, estimatedHeight);
      return estimatedHeight;
    },
    [flatItems],
  );

  // 可见范围变化回调：优化可见范围内的渲染
  const onItemsRendered = useCallback(
    ({ visibleStartIndex, visibleStopIndex }: { visibleStartIndex: number; visibleStopIndex: number }) => {
      const { start, end } = visibleRangeRef.current;

      // 只有当可见范围有显著变化时才更新
      if (Math.abs(visibleStartIndex - start) > 2 || Math.abs(visibleStopIndex - end) > 2) {
        visibleRangeRef.current = { start: visibleStartIndex, end: visibleStopIndex };
      }
    },
    [],
  );

  // 动态高度的行渲染器
  const RowRenderer = useCallback(
    ({ index, style }: ListChildComponentProps) => {
      const { start, end } = visibleRangeRef.current;
      const isVisible = index >= start - 2 && index <= end + 2; // 稍微扩大可见范围
      const item = flatItems[index];

      return (
        <MarkdownRow
          index={index}
          style={style}
          data={{
            mergedComponents,
            currentItem: item,
            isVisible,
          }}
        />
      );
    },
    [flatItems, mergedComponents],
  );

  const toggleFolder = () => setIsFolderVisible((prev) => !prev);

  const useVirtualScroll = flatItems.length > CONFIG.VIRTUAL_SCROLL_THRESHOLD;

  return (
    <AgentContainer
      style={{
        height: `${containerHeight || 400}px`,
        display: 'flex',
        flexDirection: 'column',
        width: `${isFullScreen ? containerWidth : 0.6 * containerWidth}px`,
      }}
    >
      <HeaderContainer>
        <div className="title">
          <Tooltip title="收起/展开目录" placement="right">
            <button
              type="button"
              onClick={toggleFolder}
              style={{ marginRight: '8px' }}
            >
              {isFolderVisible ? (
                <MenuFoldOutlined />
              ) : (
                <MenuUnfoldOutlined />
              )}
            </button>
          </Tooltip>
          智能体工作空间
          <span style={{ marginLeft: '8px', fontSize: '12px', color: '#999', fontWeight: 'normal' }}>
            ({flatItems.length} 条记录)
          </span>
        </div>
        <div className="controls">
          <Tooltip
            title={isFullScreen ? '收缩工作空间' : '展开工作空间'}
          >
            <button
              type="button"
              style={{
                border: 'none',
                padding: '4px 8px',
                borderRadius: '4px',
              }}
              onClick={() => setIsFullScreen((prev) => !prev)}
            >
              {!isFullScreen ? (
                <ArrowsAltOutlined />
              ) : (
                <ShrinkOutlined />
              )}
            </button>
          </Tooltip>
          <Tooltip title="关闭工作空间" placement="right">
            <button
              type="button"
              style={{
                border: 'none',
                padding: '4px 8px',
                borderRadius: '4px',
              }}
              onClick={() => ee.emit(EVENTS.CLOSE_PANEL)}
            >
              <CloseOutlined />
            </button>
          </Tooltip>
        </div>
      </HeaderContainer>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <FolderContainer
          style={{
            width: '30%',
            display: isFolderVisible ? 'block' : 'none',
          }}
        >
          <MemoizedGPTVis components={mergedComponents}>
            {data.explorer || '-'}
          </MemoizedGPTVis>
        </FolderContainer>
        <div
          style={{
            flex: 1,
            height: '100%',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {useVirtualScroll ? (
            // 虚拟滚动模式
            <AgentContent>
              <List
                ref={listRef}
                height={containerHeight || 400 - 50}
                itemCount={flatItems.length}
                itemSize={getItemHeight}
                width="100%"
                onItemsRendered={onItemsRendered}
                className="vis-running-window-list"
              >
                {RowRenderer}
              </List>
            </AgentContent>
          ) : (
            // 普通滚动模式
            <>
              {flatItems.map((item, index) => (
                <div key={item.uid} className="vis-running-window-row">
                  {item.status === 'complete' && item.start_time && (
                    <div
                      className="vis-running-window-row-header"
                      style={{
                        color: '#aaaaaa',
                        fontSize: '12px',
                        borderBottom: '1px solid #dddddd',
                        padding: '4px 12px',
                      }}
                    >
                      <Space size={4}>
                        {IconMap[item.status]}
                        <span>{dayjs(item.start_time).format('HH:mm:ss')}</span>{' '}
                        {item.markdown?.length > CONFIG.LARGE_CONTENT_THRESHOLD && (
                          <span style={{ marginLeft: 12, color: '#ff9800' }}>
                            ({(item.markdown!.length / 1000).toFixed(1)}k字符)
                          </span>
                        )}
                      </Space>
                    </div>
                  )}
                  <div className="vis-running-window-row-content">
                    <MarkdownContent
                      markdown={item.markdown || '-'}
                      components={mergedComponents}
                      isDynamic={item.status === 'running'}
                    />
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </AgentContainer>
  );
};

export default VisRunningWindowV2;