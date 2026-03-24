// running window - 渲染数据内容，不包含标题栏等UI元素
import markdownComponents, {
  markdownPlugins,
} from "@/components/chat/chat-content-components/config";
import { GPTVis } from "@antv/gpt-vis";
import React, { memo, useState, useEffect } from "react";

export interface RunningWindowData {
  running_window?: string;
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

  useEffect(() => {
    if (!Array.isArray(chatList) || chatList.length === 0) {
      setRunningWindowData({});
      setRunningWindowMarkdown("");
      return;
    }

    // 关键修复：VisParser 已经在 use-chat.ts 中完成了增量合并，
    // history 中每条 view 消息的 context 已经是完整的合并结果（包含所有累积数据）。
    // 因此这里只需要取最后一条 view 消息的 running_window，而不是跨消息累积拼接。
    // 之前的跨消息拼接会导致 VIS 协议组件重复渲染和中间输出丢失。

    let resultData: RunningWindowData = {};
    let markdownContent = "";

    // 从后往前查找最后一条包含 running_window 的 view 消息
    for (let i = chatList.length - 1; i >= 0; i--) {
      const item = chatList[i];
      try {
        if (typeof item.context !== 'string' || !item.context.trim().startsWith('{')) {
          continue;
        }

        const context = JSON.parse(item.context);
        
        let runningWindowContent = "";
        let explorerContent = "";
        let itemsData: any[] = [];

        // 情况1: 直接包含 running_window（VisParser 合并后的完整结果）
        if (context.running_window) {
          runningWindowContent = context.running_window;
          explorerContent = context.explorer || "";
          itemsData = context.items || [];
        }
        // 情况2: 包含 vis 字段
        else if (context.vis) {
          const visData = typeof context.vis === 'string' 
            ? JSON.parse(context.vis) 
            : context.vis;
          runningWindowContent = visData.running_window || "";
          explorerContent = visData.explorer || "";
          itemsData = visData.items || [];
        }

        if (runningWindowContent) {
          resultData = {
            running_window: runningWindowContent,
            explorer: explorerContent || undefined,
            items: itemsData.length > 0 ? itemsData : undefined,
          };
          markdownContent = runningWindowContent;
          break; // 找到最新的包含 running_window 的消息即可
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

    setRunningWindowData(resultData);
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
