import markdownComponents, {
  markdownPlugins,
  preprocessLaTeX,
} from "@/components/chat/chat-content-components/config";
import { ChatContentContext } from "@/contexts";
import { IChatDialogueMessageSchema } from "@/types/chat";
import { STORAGE_USERINFO_KEY } from "@/utils/constants/storage";
import {
  CheckOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import { GPTVis } from "@antv/gpt-vis";
import { Avatar } from "antd";
import classNames from "classnames";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import React, { memo, useContext, useMemo } from "react";
import { useTranslation } from "react-i18next";

const UserIcon: React.FC = () => {
  let user: any = {};
  try {
    user = JSON.parse(localStorage.getItem(STORAGE_USERINFO_KEY) ?? "{}");
  } catch (e) {
    console.error(e);
  }

  return (
    <Avatar
      src={user?.avatar_url}
      className="bg-gradient-to-tr from-[#31afff] to-[#1677ff] cursor-pointer shrink-0"
      size={32}
    >
      {user?.nick_name}
    </Avatar>
  );
};

const AgentIcon: React.FC = () => {
  const { appInfo } = useContext(ChatContentContext);
  
  return (
    <Avatar
      src={appInfo?.icon}
      className="bg-gradient-to-tr from-[#52c41a] to-[#389e0d] cursor-pointer shrink-0"
      size={32}
    >
      {appInfo?.app_name?.charAt(0) || 'A'}
    </Avatar>
  );
};

type DBGPTView = {
  name: string;
  status: "todo" | "runing" | "failed" | "completed" | (string & {});
  result?: string;
  err_msg?: string;
};

type MarkdownComponent = Parameters<typeof GPTVis>["0"]["components"];

const pluginViewStatusMapper: Record<
  DBGPTView["status"],
  { bgClass: string; icon: React.ReactNode }
> = {
  todo: {
    bgClass: "bg-gray-500",
    icon: <ClockCircleOutlined className="ml-2" />,
  },
  runing: {
    bgClass: "bg-blue-500",
    icon: <LoadingOutlined className="ml-2" />,
  },
  failed: {
    bgClass: "bg-red-500",
    icon: <CloseOutlined className="ml-2" />,
  },
  completed: {
    bgClass: "bg-green-500",
    icon: <CheckOutlined className="ml-2" />,
  },
};

const formatMarkdownVal = (val: string) => {
  return val
    .replaceAll("\\n", "\n")
    .replace(/<table(\w*=[^>]+)>/gi, "<table $1>")
    .replace(/<tr(\w*=[^>]+)>/gi, "<tr $1>");
};

const formatMarkdownValForAgent = (val: string) => {
  return val
    ?.replace(/<table(\w*=[^>]+)>/gi, "<table $1>")
    .replace(/<tr(\w*=[^>]+)>/gi, "<tr $1>");
};

function getRobotContext(context: string): { left: string; right: string } {
  try {
    const robotContext = JSON.parse(context);
    return robotContext;
  } catch (e: unknown) {
    // console.log(e);
    return {
      left: "",
      right: "",
    };
  }
}

const ChatContent: React.FC<{
  content: Omit<IChatDialogueMessageSchema, "context"> & {
    context:
      | string
      | {
          template_name: string;
          template_introduce: string;
        };
  };
  onLinkClick?: () => void;
  messages: any[];
}> = ({ content, onLinkClick, messages }) => {
  const { t } = useTranslation();
  const { context, role, thinking } = content;
  const isRobot = useMemo(() => role === "view", [role]);

  const { value, cachePluginContext } = useMemo<{
    relations: string[];
    value: string;
    cachePluginContext: DBGPTView[];
  }>(() => {
    if (typeof context !== "string") {
      return {
        relations: [],
        value: "",
        cachePluginContext: [],
      };
    }
    const [value, relation] = context.split("\trelations:");
    const relations = relation ? relation.split(",") : [];
    const cachePluginContext: DBGPTView[] = [];

    let cacheIndex = 0;
    const result = value.replace(
      /<dbgpt-view[^>]*>[^<]*<\/dbgpt-view>/gi,
      (matchVal) => {
        try {
          const pluginVal = matchVal
            .replaceAll("\n", "\\n")
            .replace(/<[^>]*>|<\/[^>]*>/gm, "");
          const pluginContext = JSON.parse(pluginVal) as DBGPTView;
          const replacement = `<custom-view>${cacheIndex}</custom-view>`;

          cachePluginContext.push({
            ...pluginContext,
            result: formatMarkdownVal(pluginContext.result ?? ""),
          });
          cacheIndex++;

          return replacement;
        } catch (e) {
          console.error(e);
          return matchVal;
        }
      }
    );
    return {
      relations,
      cachePluginContext,
      value: result,
    };
  }, [context]);

  const extraMarkdownComponents = useMemo<MarkdownComponent>(
    () => ({
      "custom-view"({ children }) {
        const index = +children.toString();
        if (!cachePluginContext[index]) {
          return children;
        }
        const { name, status, err_msg, result } = cachePluginContext[index];

        const { bgClass, icon } = pluginViewStatusMapper[status] ?? {};
        return (
          <div className="bg-white dark:bg-[#212121] rounded-lg overflow-hidden my-2 flex flex-col lg:max-w-[80%]">
            <div
              className={classNames(
                "flex px-4 md:px-6 py-2 items-center text-white text-sm",
                bgClass
              )}
            >
              {name}
              {icon}
            </div>
            {result ? (
              <div className="px-4 md:px-6 py-4 text-sm">
                {/* @ts-ignore */}
                <GPTVis components={markdownComponents} {...markdownPlugins}>
                  {preprocessLaTeX(result ?? "")}
                </GPTVis>
              </div>
            ) : (
              <div className="px-4 md:px-6 py-4 text-sm">{err_msg}</div>
            )}
          </div>
        );
      },
    }),
    [cachePluginContext]
  );

  const MAX_CONTEXT_PARSE_SIZE = 10_000_000; // 10MB limit for JSON parsing

  const _context = useMemo(() => {
    if (typeof value === 'string' && value.trim().startsWith('{')) {
      // Size check: skip parsing if context is too large
      if (value.length > MAX_CONTEXT_PARSE_SIZE) {
        console.warn(`[ChatContent] Context too large (${value.length} chars), returning raw value`);
        return value;
      }
      try {
        const parsed = JSON.parse(value);
        // 检查 planning_window 字段是否存在（即使为空字符串也应该使用它，
        // 因为这意味着这是一个多窗口布局的数据格式）
        if ('planning_window' in parsed) {
          let pw = parsed.planning_window || '';
          // Strip trailing plain text after the last VIS tag block to avoid
          // duplicate rendering (vis_final may append a conclusion that already
          // appears in the structured VIS component or right-panel summary).
          if (pw.includes('```manus-left-panel') || pw.includes('```manus-right-panel')) {
            const lastVisClose = pw.lastIndexOf('\n```');
            if (lastVisClose > 0) {
              const afterClose = lastVisClose + 4; // length of '\n```'
              const trailing = pw.substring(afterClose).trim();
              if (trailing) {
                pw = pw.substring(0, afterClose);
              }
            }
          }
          return pw;
        }
        if (parsed?.vis) {
          const visData = typeof parsed.vis === 'string' ? JSON.parse(parsed.vis) : parsed.vis;
          if ('planning_window' in visData) {
            return visData.planning_window || '';
          }
        }
      } catch {
      }
    }
    return value;
  }, [value]);

  return (
    <>
      {!isRobot && (
        <div className='flex flex-1 justify-end items-start pb-4 pt-6' style={{ gap: 12 }}>
          <span
            className='break-words min-w-0'
            style={{
              maxWidth: '95%',
              minWidth: 0,
            }}
          >
            {typeof context === 'string' ? (
              <div
                className='flex-1 text-sm text-[#1c2533] dark:text-white'
                style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
              >
                {typeof context === 'string' && (
                  <div>
                    {/* @ts-ignore */}
                    <GPTVis
                      components={{
                        ...markdownComponents,
                        // @ts-ignore
                        img: ({ src, alt, ...props }) => (
                          <img
                            src={src}
                            alt={alt || 'image'}
                            className='max-w-full md:max-w-[80%] lg:max-w-[70%] object-contain'
                            style={{ maxHeight: '200px' }}
                            {...props}
                          />
                        ),
                        
                      }}
                      {...markdownPlugins}
                    >
                      {preprocessLaTeX(formatMarkdownVal(value))}
                    </GPTVis>
                  </div>
                )}
              </div>
            ) : (
              context?.template_introduce || ''
            )}
          </span>
          <UserIcon />
        </div>
      )}
      {isRobot && (
        <div className='flex flex-1 justify-start items-start pb-4 pt-6' style={{ gap: 12 }}>
          <AgentIcon />
          <div className='flex flex-col flex-1 min-w-0 border-dashed border-r0 overflow-x-auto'>
            {/* @ts-ignore */}
            <GPTVis
              components={{
                ...markdownComponents,
                ...extraMarkdownComponents,
              }}
              {...markdownPlugins}
            >
              {preprocessLaTeX(formatMarkdownValForAgent(_context))}
            </GPTVis>
            {thinking && !context && (
              <div className='flex items-center gap-2'>
                <span className='flex text-sm text-[#1c2533] dark:text-white'>{t('thinking')}</span>
                <div className='flex'>
                  <div className='w-1 h-1 rounded-full mx-1 animate-pulse1'></div>
                  <div className='w-1 h-1 rounded-full mx-1 animate-pulse2'></div>
                  <div className='w-1 h-1 rounded-full mx-1 animate-pulse3'></div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default memo(ChatContent);
