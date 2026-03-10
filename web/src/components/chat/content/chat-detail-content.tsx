// running window - 渲染数据内容，不包含标题栏等UI元素
import markdownComponents, {
  markdownPlugins,
} from "@/components/chat/chat-content-components/config";
import { GPTVis } from "@antv/gpt-vis";
import React, { memo, useState, useEffect, useRef } from "react";
import { VisBaseParser } from "@/utils/parse-vis";

export interface RunningWindowData {
  running_window?: string;
  planning_window?: string;
  explorer?: string;
  items?: any[];
  [key: string]: any;
}

export function useDetailPanel(chatList: any[]): { 
  runningWindowData: RunningWindowData;
  runningWindowMarkdown: string;
} {
  const [runningWindowData, setRunningWindowData] = useState<RunningWindowData>({});
  const [runningWindowMarkdown, setRunningWindowMarkdown] = useState<string>("");
  
  // 使用 ref 持久化 VisBaseParser 实例，避免每次渲染重建
  const runningWindowParserRef = useRef<VisBaseParser | null>(null);
  const planningWindowParserRef = useRef<VisBaseParser | null>(null);
  const explorerParserRef = useRef<VisBaseParser | null>(null);
  
  // 初始化解析器
  useEffect(() => {
    runningWindowParserRef.current = new VisBaseParser();
    planningWindowParserRef.current = new VisBaseParser();
    explorerParserRef.current = new VisBaseParser();
    
    return () => {
      runningWindowParserRef.current?.destroy();
      planningWindowParserRef.current?.destroy();
      explorerParserRef.current?.destroy();
    };
  }, []);

  useEffect(() => {
    if (!Array.isArray(chatList)) {
      setRunningWindowData({});
      setRunningWindowMarkdown("");
      // 重置解析器
      runningWindowParserRef.current = new VisBaseParser();
      planningWindowParserRef.current = new VisBaseParser();
      explorerParserRef.current = new VisBaseParser();
      return;
    }

    let mergedData: RunningWindowData = {};
    let markdownContent = "";

    for (const item of chatList) {
      try {
        // 情况1：context是纯字符串（如"你好"）
        if (typeof item.context === 'string' && !item.context.trim().startsWith('{')) {
          continue; // 跳过非JSON内容
        }

        // 情况2：context是JSON字符串
        const context = typeof item.context === 'string' 
          ? JSON.parse(item.context) 
          : item.context;
        
        // 尝试从多个可能的位置获取数据
        let runningWindowContent = "";
        let planningWindowContent = "";
        let explorerContent = "";
        let itemsData = [];
        
        // 情况2a: 直接包含数据字段
        if (context.running_window) {
          runningWindowContent = context.running_window;
        }
        if (context.planning_window) {
          planningWindowContent = context.planning_window;
        }
        
        // 情况2b: 包含 vis 字段
        if (context.vis) {
          const visData = typeof context.vis === 'string' 
            ? JSON.parse(context.vis) 
            : context.vis;
          
          // 使用 VisBaseParser 处理 running_window
          if (visData.running_window && runningWindowParserRef.current) {
            runningWindowContent = runningWindowParserRef.current.updateCurrentMarkdown(visData.running_window);
          }
          
          // 使用 VisBaseParser 处理 planning_window
          if (visData.planning_window && planningWindowParserRef.current) {
            planningWindowContent = planningWindowParserRef.current.updateCurrentMarkdown(visData.planning_window);
          }
          
          // 处理 explorer
          if (visData.explorer && explorerParserRef.current) {
            explorerContent = explorerParserRef.current.updateCurrentMarkdown(visData.explorer);
          } else if (visData.explorer) {
            explorerContent = visData.explorer;
          }
          
          itemsData = visData.items || [];
        }

        // 合并数据
        if (runningWindowContent) {
          mergedData.running_window = runningWindowContent;
          markdownContent = runningWindowContent;
        }
        
        if (planningWindowContent) {
          mergedData.planning_window = planningWindowContent;
        }
        
        if (explorerContent) {
          mergedData.explorer = explorerContent;
        }
        
        if (itemsData.length > 0) {
          mergedData.items = itemsData;
        }
        
      } catch (error) {
        console.debug("Skipping invalid chat item context:", {
          error: error instanceof Error ? error.message : String(error),
          itemId: item?.id || item?.order,
          contextSample: typeof item?.context === 'string' 
            ? item.context.substring(0, 50) 
            : '[non-string context]'
        });
      }
    }

    setRunningWindowData(mergedData);
    setRunningWindowMarkdown(markdownContent);
  }, [chatList]);

  return { 
    runningWindowData,
    runningWindowMarkdown 
  };
}

// 纯内容渲染组件 - 不包含标题、关闭按钮等UI元素
// 这些UI元素应该在父组件中处理
const ChatDetailContent: React.FC<{
  content?: string;
  data?: RunningWindowData;
}> = ({ content, data }) => {
  // 如果有完整数据对象，直接渲染 RunningWindow
  if (data?.running_window) {
    // 解析 d-work 组件
    const workMatch = data.running_window.match(/```d-work\n([\s\S]*?)\n```/);
    if (workMatch) {
      try {
        const workData = JSON.parse(workMatch[1]);
        // 合并 explorer 和 items
        const mergedData = {
          ...workData,
          explorer: data.explorer || workData.explorer,
          items: data.items || workData.items,
        };
        return (
          <div className="h-full w-full flex flex-col [&_.gpt-vis]:h-full [&_.gpt-vis]:flex-grow [&_.gpt-vis_pre]:flex-grow [&_.gpt-vis_pre]:h-full [&_.gpt-vis_pre]:m-0 [&_.gpt-vis_pre]:p-0 [&_.gpt-vis_pre]:bg-transparent [&_.gpt-vis_pre]:border-0 [&_.gpt-vis_pre]:flex [&_.gpt-vis_pre]:flex-col">
            {/* @ts-ignore */}
            <GPTVis
              components={{
                ...markdownComponents,
              }}
              {...markdownPlugins}
            >
              {`\`\`\`d-work\n${JSON.stringify(mergedData)}\n\`\`\``}
            </GPTVis>
          </div>
        );
      } catch (e) {
        console.error('Failed to parse running window data:', e);
      }
    }
  }

  // 回退到原来的渲染方式
  return (
    <div className="h-full w-full flex flex-col [&_.gpt-vis]:h-full [&_.gpt-vis]:flex-grow [&_.gpt-vis_pre]:flex-grow [&_.gpt-vis_pre]:h-full [&_.gpt-vis_pre]:m-0 [&_.gpt-vis_pre]:p-0 [&_.gpt-vis_pre]:bg-transparent [&_.gpt-vis_pre]:border-0 [&_.gpt-vis_pre]:flex [&_.gpt-vis_pre]:flex-col">
      {/* @ts-ignore */}
      <GPTVis
        components={{
          ...markdownComponents,
        }}
        {...markdownPlugins}
      >
        {content || data?.running_window || ''}
      </GPTVis>
    </div>
  );
};

export default memo(ChatDetailContent);
