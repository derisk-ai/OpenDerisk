import markdownComponents, { markdownPlugins, preprocessLaTeX } from '@/components/chat/chat-content/config';
import { IChatDialogueMessageSchema } from '@/types/chat';
import { STORAGE_USERINFO_KEY } from '@/utils/constants/index';
import {
  CheckOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  CodeOutlined,
  CopyOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { message } from 'antd';
import classNames from 'classnames';
import Image from 'next/image';
import { useSearchParams } from 'next/navigation';
import React, { memo, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
// import Feedback from './Feedback';
// import RobotIcon from './RobotIcon';
import ChatInputPanel from '../input/ChatInputPanel';

const UserIcon: React.FC = () => {
  const user = JSON.parse(localStorage.getItem(STORAGE_USERINFO_KEY) ?? '');

  const avatarUrl = user?.avatar_url || '/agents/sre.png';

  return (
    <Image
      className='rounded-full border border-gray-200 object-contain bg-white inline-block'
      width={32}
      height={32}
      src={avatarUrl}
      alt={'User Avatar'}
    />
  );
};

type DBGPTView = {
  name: string;
  status: 'todo' | 'runing' | 'failed' | 'completed' | (string & {});
  result?: string;
  err_msg?: string;
};

type MarkdownComponent = Parameters<typeof GPTVis>['0']['components'];

const pluginViewStatusMapper: Record<DBGPTView['status'], { bgClass: string; icon: React.ReactNode }> = {
  todo: {
    bgClass: 'bg-gray-500',
    icon: <ClockCircleOutlined className='ml-2' />,
  },
  runing: {
    bgClass: 'bg-blue-500',
    icon: <LoadingOutlined className='ml-2' />,
  },
  failed: {
    bgClass: 'bg-red-500',
    icon: <CloseOutlined className='ml-2' />,
  },
  completed: {
    bgClass: 'bg-green-500',
    icon: <CheckOutlined className='ml-2' />,
  },
};

const formatMarkdownVal = (val: string) => {
  return val
    .replaceAll('\\n', '\n')
    .replace(/<table(\w*=[^>]+)>/gi, '<table $1>')
    .replace(/<tr(\w*=[^>]+)>/gi, '<tr $1>');
};

const formatMarkdownValForAgent = (val: string) => {
  return val?.replace(/<table(\w*=[^>]+)>/gi, '<table $1>').replace(/<tr(\w*=[^>]+)>/gi, '<tr $1>');
};

function getRobotContext(context: string): { left: string; right: string } {
  try {
    const robotContext = JSON.parse(context);
    return robotContext;
  } catch (e: unknown) {
    console.log(e);
    return {
      left: '',
      right: '',
    };
  }
}

const ChatContent: React.FC<{
  content: Omit<IChatDialogueMessageSchema, 'context'> & {
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

  const searchParams = useSearchParams();
  const scene = searchParams?.get('scene') ?? '';

  const { context, model_name, role, thinking } = content;

  const isRobot = useMemo(() => role === 'view', [role]);

  const { value, cachePluginContext } = useMemo<{
    relations: string[];
    value: string;
    cachePluginContext: DBGPTView[];
  }>(() => {
    if (typeof context !== 'string') {
      return {
        relations: [],
        value: '',
        cachePluginContext: [],
      };
    }
    const [value, relation] = context.split('\trelations:');
    const relations = relation ? relation.split(',') : [];
    const cachePluginContext: DBGPTView[] = [];

    let cacheIndex = 0;
    const result = value.replace(/<dbgpt-view[^>]*>[^<]*<\/dbgpt-view>/gi, matchVal => {
      try {
        const pluginVal = matchVal.replaceAll('\n', '\\n').replace(/<[^>]*>|<\/[^>]*>/gm, '');
        const pluginContext = JSON.parse(pluginVal) as DBGPTView;
        const replacement = `<custom-view>${cacheIndex}</custom-view>`;

        cachePluginContext.push({
          ...pluginContext,
          result: formatMarkdownVal(pluginContext.result ?? ''),
        });
        cacheIndex++;

        return replacement;
      } catch (e) {
        console.log((e as any).message, e);
        return matchVal;
      }
    });
    return {
      relations,
      cachePluginContext,
      value: result,
    };
  }, [context]);

  const extraMarkdownComponents = useMemo<MarkdownComponent>(
    () => ({
      'custom-view'({ children }) {
        const index = +children.toString();
        if (!cachePluginContext[index]) {
          return children;
        }
        const { name, status, err_msg, result } = cachePluginContext[index];

        const { bgClass, icon } = pluginViewStatusMapper[status] ?? {};
        return (
          <div className='bg-white dark:bg-[#212121] rounded-lg overflow-hidden my-2 flex flex-col lg:max-w-[80%]'>
            <div className={classNames('flex px-4 md:px-6 py-2 items-center text-white text-sm', bgClass)}>
              {name}
              {icon}
            </div>
            {result ? (
              <div className='px-4 md:px-6 py-4 text-sm'>
                <GPTVis components={markdownComponents} {...markdownPlugins}>
                  {preprocessLaTeX(result ?? '')}
                </GPTVis>
              </div>
            ) : (
              <div className='px-4 md:px-6 py-4 text-sm'>{err_msg}</div>
            )}
          </div>
        );
      },
    }),
    [cachePluginContext],
  );

  // If the robot answers, the context needs to be parsed into an object, and then the left and right are rendered separately
  const robotContext = getRobotContext(context as string);
  const { left = '', right = '' } = robotContext;

  return (
    <div className='flex h-full'>
      {/* icon */}
      {/* <div className='flex flex-shrink-0 items-start'>{isRobot ? null : <UserIcon />}</div> */}
      <div className={`flex ${scene === 'chat_agent' && !thinking ? 'flex-1' : ''} overflow-hidden`}>
        {/* 用户提问 */}
        {!isRobot && false && (
          <div className='flex flex-1 relative group'>
            <div
              className='flex-1 text-sm text-[#1c2533] dark:text-white'
              style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
            >
              {typeof context === 'string' && context}
            </div>
            {typeof context === 'string' && context.trim() && (
              <div className='absolute right-0 top-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200'>
                <button
                  className='flex items-center justify-center w-8 h-8 text-[#525964] dark:text-[rgba(255,255,255,0.6)] hover:text-[#1677ff] dark:hover:text-white transition-colors'
                  onClick={() => {
                    if (typeof context === 'string') {
                      navigator.clipboard
                        .writeText(context)
                        .then(() => {
                          message.success(t('copy_to_clipboard_success'));
                        })
                        .catch(err => {
                          console.error(t('copy_to_clipboard_failed'), err);
                          message.error(t('copy_to_clipboard_failed'));
                        });
                    }
                  }}
                  title={t('copy_to_clipboard')}
                >
                  <CopyOutlined />
                </button>
              </div>
            )}
          </div>
        )}
        {/* ai回答 */}
        {isRobot && (
          <div className='flex flex-1 flex-col w-full p-2'>
            <div className='flex w-full h-full bg-white dark:bg-[rgba(255,255,255,0.16)] p-2 rounded-2xl'>
              {typeof context === 'object' && (
                <div>
                  {`[${context.template_name}]: `}
                  <span className='text-theme-primary cursor-pointer' onClick={onLinkClick}>
                    <CodeOutlined className='mr-1' />
                    {context.template_introduce || 'More Details'}
                  </span>
                </div>
              )}
              {typeof context === 'string' && scene === 'chat_agent' && (
                <div className='flex flex-row w-full'>
                  <div className='flex flex-col w-2/5 pr-2 border-dashed border-r border-gray-300'>
                    <div className='flex flex-col flex-justify-space-between h-full overflow-y-auto'>
                      <div className='flex flex-row gap-2 mb-2 text-gray-500 text-ms pt-2 pb-3 justify-end'>
                        <span className='wrap-break-word w-4/5'>{messages[0].context}</span>
                        <span className='pl-3'>
                          <UserIcon />
                        </span>
                      </div>
                      <GPTVis components={markdownComponents} {...markdownPlugins}>
                        {preprocessLaTeX(formatMarkdownValForAgent(left))}
                      </GPTVis>
                    </div>
                    <ChatInputPanel />
                  </div>
                  <div className='flex flex-col w-3/5 pl-2 h-full'>
                    <GPTVis className='h-full overflow-y-auto' components={markdownComponents} {...markdownPlugins}>
                      {preprocessLaTeX(formatMarkdownValForAgent(right))}
                    </GPTVis>
                  </div>
                </div>
              )}
              {typeof context === 'string' && scene !== 'chat_agent' && (
                <div>
                  <GPTVis
                    components={{
                      ...markdownComponents,
                      ...extraMarkdownComponents,
                    }}
                    {...markdownPlugins}
                  >
                    {preprocessLaTeX(formatMarkdownVal(value))}
                  </GPTVis>
                  {/* <VisCard content={preprocessLaTeX(formatMarkdownVal(value)) } /> */}
                </div>
              )}
              {/* 正在思考 */}
              {false && thinking && !context && (
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
            {/* 用户反馈 */}
            {/* <Feedback content={content} /> */}
          </div>
        )}
      </div>
    </div>
  );
};

export default memo(ChatContent);
