'use client';
import { apiInterceptors, delDialogue, getAppList, getDialogueListBByFilter, newDialogue } from '@/client/api';
import { ChatContext } from '@/contexts';
import { IApp } from '@/types/app';
import { STORAGE_LANG_KEY, STORAGE_THEME_KEY } from '@/utils/constants/index';
import Icon, {
  ApiOutlined,
  ClockCircleOutlined,
  ConsoleSqlOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  GlobalOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PartitionOutlined,
  SettingOutlined,
  ShareAltOutlined,
  AppstoreOutlined,
  SearchOutlined,
  RobotOutlined,
  ExperimentOutlined,
  SafetyOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { authService } from '@/services/auth';
import { App, Flex, Input, Popover, Spin, Tooltip, Typography } from 'antd';
import cls from 'classnames';
import moment from 'moment';
import 'moment/locale/zh-cn';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ReactNode, useCallback, useContext, useEffect, useMemo, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import ModelSvg from '../icons/model-svg';
import ChatIcon from '../icons/chat-icon';
import MenuList from './menlist';
import UserBar from './user-bar';
import copy from 'copy-to-clipboard';

type SettingItem = {
  key: string;
  name: string;
  icon: ReactNode;
  noDropdownItem?: boolean;
  onClick?: () => void;
  items?: any[];
  onSelect?: (p: { key: string }) => void;
  defaultSelectedKeys?: string[];
  placement?: 'top' | 'topLeft';
  disable?: boolean;
};

export type RouteItem = {
  key: string;
  name: string;
  icon?: ReactNode;
  path?: string;
  isActive?: boolean;
  children?: RouteItem[];
  hideInMenu?: boolean;
};

interface Dialogue {
  chat_mode: string;
  conv_uid: string;
  user_input?: string;
  select_param?: string;
  app_code?: string;
  user_name?: string;
  gmt_created?: string;
  gmt_modified?: string;
}

interface DialogueListItem {
  key: string;
  name: string | undefined;
  path: string;
  dialogue: Dialogue;
}

interface GroupedDialogues {
  [key: string]: DialogueListItem[];
}

function smallMenuItemStyle(active?: boolean) {
  return `flex items-center justify-center mx-auto rounded w-14 h-14 text-xl hover:bg-[#F1F5F9] dark:hover:bg-theme-dark transition-colors cursor-pointer ${
    active ? 'bg-[#F1F5F9] dark:bg-theme-dark' : ''
  }`;
}

const MenuItem: React.FC<{
  item: any;
  refresh?: any;
  order: React.MutableRefObject<number>;
  historyLoading?: boolean;
  loading?: boolean;
}> = ({ item, refresh, historyLoading, loading }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const chatId = searchParams?.get('conv_uid') ?? '';
  const appCode = searchParams?.get('app_code') ?? '';
  const { modal, message } = App.useApp();
  const { refreshDialogList } = useContext(ChatContext);

  const handleDelChat = () => {
    modal.confirm({
      title: t('delete_chat'),
      content: t('delete_chat_confirm'),
      centered: true,
      onOk: async () => {
        const [err] = await apiInterceptors(delDialogue(item.conv_uid));
        if (err) {
          return;
        }
        refreshDialogList && (await refreshDialogList());
        router.push(`/chat`);
      },
    });
  };

  if (loading) {
    return (
      <Flex align='center' className='w-full h-10 px-3 rounded-lg mb-1'>
        <div className='flex items-center justify-center w-6 h-6 rounded-lg mr-3'>
          <Spin size='small' />
        </div>
        <div className='flex-1 min-w-0'>
          <div className='h-4 bg-gray-200 rounded animate-pulse'></div>
        </div>
      </Flex>
    );
  }
  const isActive = chatId === item.conv_uid && appCode === item.app_code;

  return (
    <Flex
      align='center'
      className={cls(`group/item w-full cursor-pointer relative max-w-full my-0.5`)}
      onClick={() => {
        if (historyLoading) {
          return;
        }
        router.push(`/chat/?conv_uid=${item.conv_uid}&app_code=${item.app_code}`);
      }}
    >
      <div className={cls('flex-1 flex flex-row min-w-0 overflow-hidden hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg px-3 py-2 transition-colors duration-200', {
        'bg-gray-100 dark:bg-gray-800': isActive,
      })}>
        <div className='mr-3 flex-shrink-0'>
          <ChatIcon className="w-5 h-5 text-gray-500 dark:text-gray-400" />
        </div>
        <div className='flex-1 min-w-0 overflow-hidden'>
          <Typography.Text
            ellipsis={{
              tooltip: true,
            }}
            className={cls('block text-sm font-normal', isActive ? 'text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-400')}
          >
            {item.label}
          </Typography.Text>
        </div>
        <div className='flex gap-1 ml-1 flex-shrink-0 items-center'>
          <div
            className='group-hover/item:opacity-100 cursor-pointer opacity-0 transition-opacity'
            onClick={e => {
              e.stopPropagation();
            }}
          >
            <ShareAltOutlined
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
              style={{ fontSize: 14 }}
              onClick={() => {
                const success = copy(`${location.origin}/chat?scene=${item.chat_mode}&id=${item.conv_uid}`);
                message[success ? 'success' : 'error'](success ? t('copy_success') : t('copy_failed'));
              }}
            />
          </div>
          <div
            className='group-hover/item:opacity-100 cursor-pointer opacity-0 transition-opacity'
            onClick={e => {
              e.stopPropagation();
              handleDelChat();
            }}
          >
            <DeleteOutlined className="text-gray-400 hover:text-red-500" style={{ fontSize: 14 }} />
          </div>
        </div>
      </div>
    </Flex>
  );
};

function SideBar() {
  const { isMenuExpand, setIsMenuExpand, mode, setMode, dialogueList } = useContext(ChatContext);
  const pathname = usePathname();
  const { t, i18n } = useTranslation();
  const [logo, setLogo] = useState<string>('/logo_zh_latest.png');
  const [appList, setAppList] = useState<IApp[]>([]);
  const [dialogueLists, setDialogueLists] = useState<DialogueListItem[]>([]);
  const [searchValue, setSearchValue] = useState<string>('');
  const [oauthEnabled, setOauthEnabled] = useState(false);

  useEffect(() => {
    authService.getOAuthStatus().then((s) => setOauthEnabled(s.enabled));
  }, []);

  const handleToggleMenu = useCallback(() => {
    setIsMenuExpand(!isMenuExpand);
  }, [isMenuExpand, setIsMenuExpand]);

  const handleToggleTheme = useCallback(() => {
    const theme = mode === 'light' ? 'dark' : 'light';
    setMode(theme);
    localStorage.setItem(STORAGE_THEME_KEY, theme);
  }, [mode, setMode]);

  const {
    run: fetchDialogueList,
    loading: listLoading,
  } = useRequest(async (name: string) => {
    return await apiInterceptors(getDialogueListBByFilter(name));
  },
   {
      manual: true,
      onSuccess: data => {
        if (data && data[1]) {
          const di = (data[1] as unknown as Dialogue[]).map(
            (dialogue: Dialogue): DialogueListItem => ({
              key: dialogue?.conv_uid,
              name: dialogue.user_input || dialogue.select_param,
              path: '/',
              dialogue: dialogue,
            }),
          );
          setDialogueLists(di);
        } else {
          setDialogueLists([]);
        }
      },
    },
 );

  useEffect(() => {
    fetchAppList();
  }, []);

  const { run: fetchAppList, loading: appListLoading } = useRequest(
    async () => {
      const [_, data] = await apiInterceptors(
        getAppList({
          page: 1,
          page_size: 10,
          published: true,
        }),
      );
      return data;
    },
    {
      manual: true,
      onSuccess: data => {
        if (data) {
          setAppList(data.app_list || []);
        }
      },
    },
  );
  // 暂时注释，后续完善中英文
  const handleChangeLang = useCallback(() => {
    const language = i18n.language === 'en' ? 'zh' : 'en';
    i18n.changeLanguage(language);
    if (language === 'zh') moment.locale('zh-cn');
    if (language === 'en') moment.locale('en');
    localStorage.setItem(STORAGE_LANG_KEY, language);
  }, [i18n]);
  const settings = useMemo(() => {
    const items: SettingItem[] = [
      {
        key: 'language',
        name: t('language'),
        icon: <GlobalOutlined />,
        items: [
          {
            key: 'en',
            label: (
              <div className='py-1 flex justify-between gap-8 '>
                <span className='flex gap-2'>
                  <Image src='/icons/english.png' alt='english' width={21} height={21}></Image>
                  <span>English</span>
                </span>
                <span
                  className={cls({
                    block: i18n.language === 'en',
                    hidden: i18n.language !== 'en',
                  })}
                >
                  ✓
                </span>
              </div>
            ),
          },
          {
            key: 'zh',
            label: (
              <div className='py-1 flex justify-between gap-8 '>
                <span className='flex gap-2'>
                  <Image src='/icons/zh.png' alt='english' width={21} height={21}></Image>
                  <span>简体中文</span>
                </span>
                <span
                  className={cls({
                    block: i18n.language === 'zh',
                    hidden: i18n.language !== 'zh',
                  })}
                >
                  ✓
                </span>
              </div>
            ),
          },
        ],
        onSelect: ({ key }: { key: string }) => {
          if (i18n.language === key) return;
          i18n.changeLanguage(key);
          if (key === 'zh') moment.locale('zh-cn');
          if (key === 'en') moment.locale('en');
          localStorage.setItem(STORAGE_LANG_KEY, key);
        },
        onClick: handleChangeLang,
        defaultSelectedKeys: [i18n.language],
      },
      {
        key: 'fold',
        name: t(isMenuExpand ? 'Close_Sidebar' : 'Show_Sidebar'),
        icon: isMenuExpand ? <MenuFoldOutlined /> : <MenuUnfoldOutlined />,
        onClick: handleToggleMenu,
        noDropdownItem: true,
      },
    ];
    return items;
  }, [t, mode, handleToggleTheme, i18n, handleChangeLang, isMenuExpand, handleToggleMenu, setMode]);

  const handleChat = async (app: IApp) => {
    const [, res] = await apiInterceptors(newDialogue({ app_code: app.app_code }));
    if (res) {
      window.open(`/chat/?app_code=${app.app_code}&conv_uid=${res.conv_uid}&isNew=true`, '_blank');
    }
  };

  const searchParams = useSearchParams();
  const appLists = useMemo(() => {
    const currentAppCode = searchParams?.get('app_code');
    const isNew = Boolean(searchParams?.get('isNew'));
    return appList.map(app => ({
      key: app.app_code,
      name: app.app_name,
      icon: (
        <Image
          key='image_chat'
          src={app.icon || '/pictures/chat.png'}
          alt='chat_image'
          width={24}
          height={24}
          className='rounded-md'
        />
      ),
      path: '/',
      app: app,
      isActive: pathname.startsWith('/chat') && (currentAppCode === app.app_code) && isNew,
    }));
  }, [appList, pathname, searchParams]);

  /**
   * Extract readable user text from user_input.
   * user_input may be a plain string or a JSON stringified object
   * like {"type":"human","data":{"content":"...",...}} from V2 conversations.
   */
  const extractUserText = (raw: string | undefined): string => {
    if (!raw) return '';
    // If it starts with '{', try to parse as JSON and extract the text content
    if (raw.startsWith('{')) {
      try {
        const obj = JSON.parse(raw);
        if (obj.data?.content) return obj.data.content;
        if (obj.content) return obj.content;
        return raw;
      } catch {
        return raw;
      }
    }
    return raw;
  };

  useEffect(() => {
     if (dialogueList && dialogueList[1]) {
      const di =  (dialogueList[1] as unknown as Dialogue[]).map(
        (dialogue: Dialogue): DialogueListItem => ({
          key: dialogue?.conv_uid,
          name: extractUserText(dialogue.user_input) || dialogue.select_param,
          path: '/',
          dialogue: dialogue,
        }),
      );
     setDialogueLists(di);
    }

  }, [dialogueList]);

  const functions = useMemo(() => {
    const currentAppCode = searchParams?.get('app_code');
    const items: RouteItem[] = [
      // Removed duplicate 'chat_online' item as it is already handled by the "New Dialogue" button
      // ...appLists, // Remove appList from menu items since we have a new way to start chats
      // Removed duplicate 'chat_online' item as it is already handled by the "New Dialogue" button
      // ...appLists, // Remove appList from menu items since we have a new way to start chats
      {
        key: 'application',
        name: t('application'),
        icon: <AppstoreOutlined className='w-5 h-5 text-gray-500' />,
        path: '/',
        children: [
          {
            key: 'explore',
            name: t('explore_agents'),
            isActive: pathname.startsWith('/application/explore'),
            icon: <SearchOutlined className='w-5 h-5 text-gray-500' />,
            path: '/application/explore',
          },
          {
            key: 'agents',
            name: t('Agents'),
            isActive: pathname.startsWith('/application/app'),
            icon: <RobotOutlined className='w-5 h-5 text-gray-500' />,
            path: '/application/app',
          },
          {
            key: 'agent_skills',
            name: t('agent_skills'),
            isActive: pathname.startsWith('/agent-skills'),
            icon: <ExperimentOutlined className='w-5 h-5 text-gray-500' />,
            path: '/agent-skills',
          },
          {
            key: 'MCP',
            name: 'MCP',
            isActive: pathname.startsWith('/mcp'),
            icon: <ConsoleSqlOutlined className='w-5 h-5 text-gray-500' />,
            path: '/mcp',
          },
          {
            key: 'database',
            name: t('Database'),
            isActive: pathname.startsWith('/database'),
            icon: <DatabaseOutlined className='w-5 h-5 text-gray-500' />,
            path: '/database',
          },
        ],
        isActive: pathname.startsWith('/application') || pathname.startsWith('/agent-skills') || pathname.startsWith('/mcp') || pathname.startsWith('/database'),
      },
      {
        key: 'configuration_management',
        name: t('configuration_management'),
        icon: <SettingOutlined />,
        path: '/',
        children: [
          {
            key: 'models',
            name: t('model_manage'),
            isActive: pathname.startsWith('/models'),
            icon: (
              <Icon component={ModelSvg} className='w-5 h-5 text-gray-500' />
            ),
            path: '/models',
          },
          {
            key: 'cron',
            name: t('cron_page_title'),
            isActive: pathname.startsWith('/cron'),
            icon: <ClockCircleOutlined className='w-5 h-5 text-gray-500' />,
            path: '/cron',
          },
          {
            key: 'channel',
            name: t('channel_page_title'),
            isActive: pathname.startsWith('/channel'),
            icon: <ApiOutlined className='w-5 h-5 text-gray-500' />,
            path: '/channel',
          },
          {
            key: 'vis_merge_test',
            name: 'GUI',
            isActive: pathname.startsWith('/vis-merge-test'),
            icon: <ExperimentOutlined className='w-5 h-5 text-gray-500' />,
            path: '/vis-merge-test',
          },
          {
            key: 'system_config',
            name: t('system_config'),
            isActive: pathname.startsWith('/settings/config'),
            icon: <SettingOutlined className='w-5 h-5 text-gray-500' />,
            path: '/settings/config',
          },
          {
            key: 'plugin_market',
            name: t('plugin_market'),
            isActive: pathname.startsWith('/settings/plugin-market'),
            icon: <AppstoreOutlined className='w-5 h-5 text-gray-500' />,
            path: '/settings/plugin-market',
          },
          {
            key: 'audit_logs',
            name: t('audit_logs_title'),
            isActive: pathname.startsWith('/audit-logs'),
            icon: <SafetyOutlined className='w-5 h-5 text-gray-500' />,
            path: '/audit-logs',
          },
          {
            key: 'monitoring',
            name: t('monitoring_page_title'),
            isActive: pathname.startsWith('/monitoring'),
            icon: <DashboardOutlined className='w-5 h-5 text-gray-500' />,
            path: '/monitoring',
          },
          ...(oauthEnabled ? [{
            key: 'user_management',
            name: '用户管理',
            isActive: pathname.startsWith('/users'),
            icon: <TeamOutlined className='w-5 h-5 text-gray-500' />,
            path: '/users',
          }] : []),
        ],
        isActive: pathname.startsWith('/models') || pathname.startsWith('/vis-merge-test') || pathname.startsWith('/cron') || pathname.startsWith('/channel') || pathname.startsWith('/settings/config') || pathname.startsWith('/settings/plugin-market') || pathname.startsWith('/audit-logs') || pathname.startsWith('/monitoring') || (oauthEnabled && pathname.startsWith('/users')),
      },
    ];
    return items;
  }, [t, pathname, appLists, oauthEnabled]);

  useEffect(() => {
    const language = i18n.language;
    if (language === 'zh') moment.locale('zh-cn');
    if (language === 'en') moment.locale('en');
  }, []);

  useEffect(() => {
    setLogo(mode === 'dark' ? '/logo_s_latest.png' : '/logo_zh_latest.png');
  }, [mode]);

  const handleSearch = (value: string) => {
    setSearchValue(value);
    if (value.trim()) {
      fetchDialogueList(value);
    } else {
      if (dialogueList && dialogueList[1]) {
        const di = (dialogueList[1] as unknown as Dialogue[]).map(
          (dialogue: Dialogue): DialogueListItem => ({
            key: dialogue?.conv_uid,
            name: extractUserText(dialogue.user_input) || dialogue.select_param,
            path: '/',
            dialogue: dialogue,
          }),
        );
        setDialogueLists(di);
      }
    }
  };

  const getWeekRange = (date: string) => {
    const m = moment(date);
    const startOfWeek = m.clone().startOf('week');
    const endOfWeek = m.clone().endOf('week');
    const now = moment();
    
    if (now.isSame(startOfWeek, 'week')) {
      return t('this_week');
    }
    if (now.clone().subtract(1, 'week').isSame(startOfWeek, 'week')) {
      return t('last_week');
    }
    
    const weeksAgo = Math.floor(now.diff(startOfWeek, 'weeks'));
    return `${weeksAgo} ${t('weeks_ago')}`;
  };

  const groupDialoguesByWeek = (dialogues: DialogueListItem[]): GroupedDialogues => {
    return dialogues.reduce((groups, item) => {
      const date = item.dialogue.gmt_created || item.dialogue.gmt_modified;
      if (date) {
        const weekRange = getWeekRange(date);
        if (!groups[weekRange]) {
          groups[weekRange] = [];
        }
        groups[weekRange].push(item);
      } else {
        if (!groups[t('unknown')]) {
          groups[t('unknown')] = [];
        }
        groups[t('unknown')].push(item);
      }
      return groups;
    }, {} as GroupedDialogues);
  };

  // Sort items within each group by created time descending
  const sortGroupedDialogues = (grouped: GroupedDialogues): GroupedDialogues => {
    const sorted: GroupedDialogues = {};
    for (const [key, items] of Object.entries(grouped)) {
      sorted[key] = [...items].sort((a, b) => {
        const aTime = a.dialogue.gmt_created || a.dialogue.gmt_modified || '';
        const bTime = b.dialogue.gmt_created || b.dialogue.gmt_modified || '';
        return bTime.localeCompare(aTime);
      });
    }
    return sorted;
  };

  const renderGroupedDialogues = (dialogues: DialogueListItem[]) => {
    const grouped = groupDialoguesByWeek(dialogues);
    const sorted = sortGroupedDialogues(grouped);
    const sortedGroups = Object.entries(sorted).sort((a, b) => {
      const order = [t('this_week'), t('last_week'), t('weeks_ago'), t('unknown')];
      const aIndex = order.findIndex(k => a[0].startsWith(k));
      const bIndex = order.findIndex(k => b[0].startsWith(k));
      return (aIndex === -1 ? 999 : aIndex) - (bIndex === -1 ? 999 : bIndex);
    });

    return sortedGroups.map(([week, items], index) => (
      <div key={`group-${index}`} className="mb-4">
        <div className="flex items-center px-3 mb-2">
          <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">
            {week}
          </span>
        </div>
        {items.map((item) => (
          <MenuItem
            key={item.key}
            item={{
              label: item.name || 'Untitled',
              app_code: item.dialogue.app_code || '',
              ...item.dialogue,
              default: false,
            }}
            order={{ current: 0 }}
          />
        ))}
      </div>
    ));
  };

  // if (pathname === '/') return null;

  if (!isMenuExpand) {
    return (
      <div className='flex flex-col justify-between pt-3 h-screen bg-[#F9FAFB] dark:bg-[#111] border-r border-gray-100 dark:border-gray-800 animate-fade animate-duration-300 '>
        <div>
          <Link href='/' className='flex justify-center items-center pb-2'>
            <Image src={isMenuExpand ? logo : '/LOGO_SMALL.png'} alt='DB-GPT' width={40} height={40} />
          </Link>
          <div className='flex flex-col gap-3 items-center px-2'>
            {functions.map(item => {
              if (item?.children) {
                return (
                  <div className='w-10 h-10 flex items-center justify-center cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors' onClick={() => setIsMenuExpand(true)}>{item.icon}</div>
                )
              }
              if ((item as any).app) {
                return (
                  <div className='h-10 w-10 flex items-center justify-center cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors' onClick={() => handleChat((item as any).app)} key={item.key + Date.now()}>
                    <div className='w-6 h-6 flex items-center justify-center'>{item.icon}</div>
                  </div>
                );
              }

              return (
                <Link key={item.key} className='h-10 w-10 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors' href={item.path || '#'}>
                  <div className='w-5 h-5 flex items-center justify-center'>{item.icon}</div>
                </Link>
              );
            })}
          </div>
        </div>
        <div className='py-4 flex flex-col items-center gap-2'>
          <UserBar onlyAvatar />
          {settings
            .filter(item => item.noDropdownItem)
            .map(item => (
              <Tooltip key={item.key} title={item.name} placement='right'>
                <div className='w-10 h-10 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg cursor-pointer transition-colors' onClick={item.onClick}>
                  {item.icon}
                </div>
              </Tooltip>
            ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cls(
        'flex flex-col justify-between flex-1 pt-3 overflow-hidden h-screen',
        'bg-[#F9FAFB] dark:bg-[#111] border-r border-gray-100 dark:border-gray-800',
        'animate-fade animate-duration-300 max-w-[260px] w-[260px]',
      )}
    >
      <div className='flex flex-col w-full px-4'>
        {/* LOGO */}
        <Link href='/' className='flex flex-row justify-between items-center mb-2 pl-1'>
          <Image src={isMenuExpand ? logo : '/LOGO_SMALL.png'} alt='DB-GPT' width={120} height={30} className="object-contain" />
        </Link>
        
        {/* New Chat Button */}
        <Link 
          href="/chat" 
          className="flex items-center gap-2 px-3 py-2 mb-4 bg-white dark:bg-[#1F1F1F] hover:bg-gray-50 dark:hover:bg-[#2A2A2A] border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm transition-all group"
        >
           <div className="w-5 h-5 flex items-center justify-center text-gray-500 group-hover:text-blue-500 transition-colors">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 4V20M4 12H20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
           </div>
           <span className="font-medium text-gray-700 dark:text-gray-200 text-sm">新对话</span>
        </Link>

        {/* Navigation Menu */}
        <div className='flex flex-col w-full space-y-1 mb-6'>
          {functions.map(item => {
            if (item?.children) {
              return <MenuList value={item} isStow={false} key={item.key} defaultOpen={item.key === 'application'} />;
            }

            // 应用列表项单独处理点击事件
            if ((item as any).app) {
              return (
                <div
                  onClick={() => handleChat((item as any).app)}
                  className={cls(
                    'flex items-center w-full h-9 cursor-pointer px-3 rounded-lg transition-all duration-200',
                    item.isActive 
                      ? 'bg-gray-200/50 dark:bg-gray-800 text-gray-900 dark:text-white font-medium' 
                      : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                  )}
                  key={item.key + Date.now()}
                >
                  <div className='mr-3 w-5 h-5 flex-shrink-0 flex items-center justify-center opacity-80'>{item.icon}</div>
                  <span className='text-sm truncate'>{item.name}</span>
                </div>
              );
            }

            return (
              <Link
                href={item.path ?? '/'}
                className={cls(
                  'flex items-center w-full h-9 cursor-pointer px-3 rounded-lg transition-all duration-200',
                  item.isActive 
                    ? 'bg-gray-200/50 dark:bg-gray-800 text-gray-900 dark:text-white font-medium' 
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800',
                  item.key === 'application' ? 'mt-4' : ''
                )}
                key={item.key}
              >
                <div className='mr-3 w-5 h-5 flex-shrink-0 flex items-center justify-center opacity-80'>{item.icon}</div>
                <span className='text-sm truncate'>{t(item.name as any)}</span>
              </Link>
            );
          })}
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-hidden px-4">
        {/* Chat History Header */}
        <div className="flex items-center justify-between text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-3">
           <span>{t('chat_history')}</span>
           <SearchOutlined className="cursor-pointer hover:text-gray-600" />
        </div>

        <div className='flex-1 overflow-y-auto -mx-2 px-2 custom-scrollbar pr-1' style={{ maxHeight: 'calc(100vh - 380px)' }}>
        {listLoading ? (
          Array.from({ length: 3 }).map((_, index) => (
            <MenuItem
              key={`loading-${index}`}
              item={{}}
              order={{ current: 0 }}
              loading={true}
            />
          ))
        ) : dialogueLists.length > 0 ? (
          renderGroupedDialogues(dialogueLists)
        ) : (
          <div className='px-4 text-gray-400 text-xs py-4 text-center'>
            {searchValue ? t('no_matching_session') : t('no_history_session')}
          </div>
        )}
      </div>
      </div>

      {/* User & Settings */}
      <div className='px-4 py-4 mt-2 border-t border-gray-100 dark:border-gray-800 bg-[#F9FAFB] dark:bg-[#111] flex items-center justify-between gap-2'>
        <div className='flex-1 min-w-0 overflow-hidden'>
           <UserBar />
        </div>
        <div className='flex items-center gap-1 shrink-0'>
          {settings.map(item => (
            <Tooltip key={item.key} title={item.name} placement='top'>
              <div 
                className={cls(
                  'w-8 h-8 flex items-center justify-center rounded-lg cursor-pointer transition-colors text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800', 
                  { 'text-gray-300 cursor-not-allowed': item.disable }
                )} 
                onClick={item.onClick}
              >
                {item.icon}
              </div>
            </Tooltip>
          ))}
        </div>
      </div>
    </div>
  );
}

export default SideBar;
