import markdownComponents, {
  markdownPlugins,
  preprocessLaTeX,
} from "@/components/chat/chat-content-components/config";
import { IChatDialogueMessageSchema } from "@/types/chat";
import { STORAGE_USERINFO_KEY } from "@/utils/constants/index";
import {
  CheckOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import { GPTVis } from "@antv/gpt-vis";
import classNames from "classnames";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import React, { memo, useMemo } from "react";
import { useTranslation } from "react-i18next";

const UserIcon: React.FC = () => {
  const user = JSON.parse(localStorage.getItem(STORAGE_USERINFO_KEY) ?? "");
  const avatarUrl = user?.avatar_url || "/agents/sre.png";

  return (
    <Image
      className="rounded-full border border-gray-200 object-contain bg-white inline-block"
      width={32}
      height={32}
      src={avatarUrl}
      alt={"User Avatar"}
    />
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
  onLinkClick: () => void;
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
          console.log((e as any).message, e);
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

  // If the robot answers, the context needs to be parsed into an object, and then the left and right are rendered separately
  const robotContext = getRobotContext(context as string);
  const planning_window = (robotContext as any)?.planning_window;

  const _context = planning_window !== undefined ? planning_window : value;

  return (
    <>
      {!isRobot && (
        <div className='flex flex-1 justify-end items-start pb-4' style={{ gap: 12 }}>
          <span
            className='break-words text-right'
            style={{
              maxWidth: '100%',
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
        <div className='flex flex-col pr-2 border-dashed border-r0 flex-1'>
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
      )}
    </>
  );
};

export default memo(ChatContent);
