// running window
import markdownComponents, {
  markdownPlugins,
} from "@/components/chat/chat-content-components/config";
import { GPTVis } from "@antv/gpt-vis";
import React, { memo, } from "react";
import { useState, useEffect } from "react";
import { combineMarkdownString } from "@/utils/parse-vis";

// export function useDetailPanel(chatList: any[]) {
//   const [runningWindowMarkdown, setRunningWindowMarkdown] =
//     useState<string>("");
//   useEffect(() => {
//     const newRunningMarkdown = chatList.reduce((pre: string, cur: any) => {
//       try {
//         const curRunningWindow = JSON.parse(cur.context).running_window || "";
//         if (!pre) return curRunningWindow || "";
//         return combineMarkdownString(pre, curRunningWindow);
//       } catch {
//         console.error("fail to parse vis-running-window");
//         return pre || "";
//       }
//     }, "");
//     setRunningWindowMarkdown(newRunningMarkdown || "");
//   }, [chatList]);

//   return {
//     runningWindowMarkdown,
//   };
// }

export function useDetailPanel(chatList: any[]) {
  const [runningWindowMarkdown, setRunningWindowMarkdown] = useState<string>("");

  useEffect(() => {
    if (!Array.isArray(chatList)) {
      setRunningWindowMarkdown("");
      return;
    }
    let markdownContent:any = "";

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
        
        // 获取running_window内容（支持多种可能的字段名）
        const visualContent = context.running_window || "";

        if (visualContent && typeof visualContent === 'string') {
          markdownContent = markdownContent 
            ? combineMarkdownString(markdownContent, visualContent || "") 
            : (visualContent || "");
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

    setRunningWindowMarkdown(markdownContent);
  }, [chatList]);

  return { runningWindowMarkdown };
}

const ChatDetailContent: React.FC<{
  content: string
}> = ({ content }) => {

  return (
    <>
      <div className="flex flex-col border-dashed border-r0 flex-1 h-full">
        {/* @ts-ignore */}
        <GPTVis
          components={{
            ...markdownComponents,
          }}
          {...markdownPlugins}
        >
          {content}
        </GPTVis>
      </div> 
    </>
    
  );
};

export default memo(ChatDetailContent);
