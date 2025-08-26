'use client';
import { apiInterceptors, delDialogue, getAppList, getDialogueListBByFilter, newDialogue } from '@/client/api';
import { ChatContext } from '@/contexts';
import { IApp } from '@/types/app';
import { STORAGE_LANG_KEY, STORAGE_THEME_KEY } from '@/utils/constants/index';
import Icon, {
  ClockCircleOutlined,
  ConsoleSqlOutlined,
  DeleteOutlined,
  GlobalOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PartitionOutlined,
  SettingOutlined,
  ShareAltOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Flex, Input, Popover, Spin, Tooltip, Typography } from 'antd';
import cls from 'classnames';
import moment from 'moment';
import 'moment/locale/zh-cn';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import ModelSvg from '../icons/model-svg';
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
  app_code?: string; // Added property to fix type error
  // Add other properties if needed
}

interface DialogueListItem {
  key: string;
  name: string | undefined;
  path: string;
  dialogue: Dialogue;
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

  // 删除会话
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
      className={cls(`group/item w-full cursor-pointer relative max-w-full`, )}
      onClick={() => {
        if (historyLoading) {
          return;
        }
        router.push(`/chat/?conv_uid=${item.conv_uid}&app_code=${item.app_code}`);
      }}
    >
      <Tooltip title={item.chat_mode}>
        {typeof item.icon === 'string' ? (
          <img src={item.icon} className='flex-shrink-0 w-6 h-6 rounded-lg mr-3' />
        ) : (
          <div className='flex items-center justify-center w-6 h-6 rounded-lg flex-shrink-0'>{item.icon}</div>
        )}
      </Tooltip>
      <div className={cls('flex-1 flex flex-row min-w-0 overflow-hidden hover:bg-slate-100 dark:hover:bg-theme-dark rounded-md px-3 py-1', {
        'bg-white dark:bg-black': isActive,
      })}>
        <div className='flex-1 min-w-0 overflow-hidden hover:bg-slate-100 dark:hover:bg-theme-dark'>
          <Typography.Text
            ellipsis={{
              tooltip: true,
            }}
            className='block text-gray-500 text-[14px]'
          >
            {item.label}
          </Typography.Text>
          {/* 第二行：用户名和创建时间 */}
          <div className='flex text-xs text-gray-400 whitespace-nowrap overflow-hidden text-ellipsis'>
            <span className='mr-2'>{item.user_name}</span>
            <span>{item.gmt_created ? moment(item.gmt_created).format('YYYY-MM-DD HH:mm') : item.gmt_modified}</span>
          </div>
        </div>
        <div className='flex gap-1 ml-1 flex-shrink-0'>
          <div
            className='group-hover/item:opacity-100 cursor-pointer opacity-0'
            onClick={e => {
              e.stopPropagation();
            }}
          >
            <ShareAltOutlined
              style={{ fontSize: 16 }}
              onClick={() => {
                const success = copy(`${location.origin}/chat?scene=${item.chat_mode}&id=${item.conv_uid}`);
                message[success ? 'success' : 'error'](success ? t('copy_success') : t('copy_failed'));
              }}
            />
          </div>
          <div
            className='group-hover/item:opacity-100 cursor-pointer opacity-0'
            onClick={e => {
              e.stopPropagation();
              handleDelChat();
            }}
          >
            <DeleteOutlined style={{ fontSize: 16 }} />
          </div>
        </div>
      </div>
    </Flex>
  );
};

function SideBar() {
  const { isMenuExpand, setIsMenuExpand, mode, setMode, dialogueList } = useContext(ChatContext);
  const pathname = usePathname();
  const router = useRouter();
  const { t, i18n } = useTranslation();
  const [logo, setLogo] = useState<string>('/logo_zh_latest.png');
  const [appList, setAppList] = useState<IApp[]>([]);
  const [dialogueLists, setDialogueLists] = useState<DialogueListItem[]>([]);
  const [searchValue, setSearchValue] = useState<string>('');

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
    // const language = i18n.language === 'en' ? 'zh' : 'en';
    // i18n.changeLanguage(language);
    // if (language === 'zh') moment.locale('zh-cn');
    // if (language === 'en') moment.locale('en');
    // localStorage.setItem(STORAGE_LANG_KEY, language);
  }, [i18n]);
  const settings = useMemo(() => {
    const items: SettingItem[] = [
      // {
      //   key: 'theme',
      //   name: t('Theme'),
      //   icon: mode === 'dark' ? <Icon component={DarkSvg} /> : <Icon component={SunnySvg} />,
      //   items: [
      //     {
      //       key: 'light',
      //       label: (
      //         <div className='py-1 flex justify-between gap-8 '>
      //           <span className='flex gap-2 items-center'>
      //             <Image src='/pictures/theme_light.png' alt='english' width={38} height={32}></Image>
      //             <span>Light</span>
      //           </span>
      //           <span
      //             className={cls({
      //               block: mode === 'light',
      //               hidden: mode !== 'light',
      //             })}
      //           >
      //             ✓
      //           </span>
      //         </div>
      //       ),
      //     },
      //     {
      //       key: 'dark',
      //       label: (
      //         <div className='py-1 flex justify-between gap-8 '>
      //           <span className='flex gap-2 items-center'>
      //             <Image src='/pictures/theme_dark.png' alt='english' width={38} height={32}></Image>
      //             <span>Dark</span>
      //           </span>
      //           <span
      //             className={cls({
      //               block: mode === 'dark',
      //               hidden: mode !== 'dark',
      //             })}
      //           >
      //             ✓
      //           </span>
      //         </div>
      //       ),
      //     },
      //   ],
      //   onClick: handleToggleTheme,
      //   onSelect: ({ key }: { key: string }) => {
      //     if (mode === key) return;
      //     setMode(key as 'light' | 'dark');
      //     localStorage.setItem(STORAGE_THEME_KEY, key);
      //   },
      //   defaultSelectedKeys: [mode],
      //   placement: 'topLeft',
      // },
      {
        key: 'language',
        name: t('language'),
        icon: <GlobalOutlined />,
        disable: true,
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
      router.push(`/chat/?app_code=${app.app_code}&conv_uid=${res.conv_uid}&isNew=true`);
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
          width={30}
          height={30}
          className='rounded-2xl'
        />
      ),
      path: '/',
      app: app,
      isActive: pathname.startsWith('/chat') && (currentAppCode === app.app_code) && isNew,
    }));
  }, [appList, pathname, searchParams]);

  useEffect(() => {
     if (dialogueList && dialogueList[1]) {
      const di =  (dialogueList[1] as unknown as Dialogue[]).map(
        (dialogue: Dialogue): DialogueListItem => ({
          key: dialogue?.conv_uid,
          name: dialogue.user_input || dialogue.select_param,
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
      {
      key: 'chat',
      name: t('chat_online'),
      icon: (
        <Image
        key='image_chat'
        src={pathname.startsWith('/chat') ? '/pictures/chat_active.png' : '/pictures/chat.png'}
        alt='chat_image'
        width={40}
        height={40}
        />
      ),
      path: '/chat/',
      isActive: (pathname === '/chat' || pathname === '/chat/') && !currentAppCode,
      },
      ...appLists,
      {
      key: 'application',
      name: t('application'),
      isActive: pathname.startsWith('/application'),
      icon: (
        <Image
        key='image_application'
        src={pathname.startsWith('/application') ? '/pictures/app_active.png' : '/pictures/app.png'}
        alt='application_image'
        width={40}
        height={40}
        />
      ),
      path: '/application/app',
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
          <Icon component={ModelSvg} className='w-5 h-5 text-[#515964]' />
        ),
        path: '/models',
        },
        {
        key: 'knowledge',
        name: t('Knowledge_Space'),
        isActive: pathname.startsWith('/knowledge'),
        icon: <PartitionOutlined className='w-5 h-5 text-[#515964]'  />,
        path: '/knowledge',
        },
        {
          key: 'MCP',
          name: 'MCP',
          isActive: pathname.startsWith('/mcp'),
          icon: <ConsoleSqlOutlined className='w-5 h-5 text-[#515964]' />,
          path: '/mcp',
        },
        {
        key: 'prompt',
        name: t('Prompt'),
        isActive: pathname.startsWith('/prompt'),
        icon: <MessageOutlined  className='w-5 h-5 text-[#515964]' />,
        path: '/prompt',
        },
      ],
      isActive: pathname.startsWith('/models') || pathname.startsWith('/knowledge') || pathname.startsWith('/prompt') || pathname.startsWith('/mcp'),
      },
    ];
    return items;
  }, [t, pathname, appLists]);

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
      // 如果搜索框为空，显示原始列表
      if (dialogueList && dialogueList[1]) {
        const di = (dialogueList[1] as unknown as Dialogue[]).map(
          (dialogue: Dialogue): DialogueListItem => ({
            key: dialogue?.conv_uid,
            name: dialogue.user_input || dialogue.select_param,
            path: '/',
            dialogue: dialogue,
          }),
        );
        setDialogueLists(di);
      }
    }
  };

  if (pathname === '/') return null;

  if (!isMenuExpand) {
    return (
      <div className='flex flex-col justify-between pt-4 h-screen bg-bar dark:bg-[#232734] animate-fade animate-duration-300 '>
        <div>
          <Link href='/' className='flex justify-center items-center pb-4'>
            <Image src={isMenuExpand ? logo : '/LOGO_SMALL.png'} alt='DB-GPT' width={40} height={40} />
          </Link>
          <div className='flex flex-col gap-3 items-center'>
            {functions.map(item => {
              if (item?.children) {
                return (
                  <div className='w-10 h-10 flex items-center justify-center' onClick={() => setIsMenuExpand(true)}>{item.icon}</div>
                )
              }
              if ((item as any).app) {
                return (
                  <div className='h-10 flex items-center justify-center' onClick={() => handleChat((item as any).app)} key={item.key + Date.now()}>
                    <div className='w-8 h-8 items-center justify-center'>{item.icon}</div>
                  </div>
                );
              }

              return (
                <Link key={item.key} className='h-10 flex items-center justify-center' href={item.path || '#'}>
                  <div className='w-8 h-8 flex items-center justify-center'>{item.icon}</div>
                </Link>
              );
            })}
          </div>
        </div>
        <div className='py-4'>
          <UserBar onlyAvatar />
          {settings
            .filter(item => item.noDropdownItem)
            .map(item => (
              <Tooltip key={item.key} title={item.name} placement='right'>
                <div className={smallMenuItemStyle()} onClick={item.onClick}>
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
        'flex flex-col justify-between flex-1 px-4 pt-2 overflow-hidden',
        'bg-bar dark:bg-[#232734]',
        'animate-fade animate-duration-300 max-w-[240px]',
      )}
    >
      <div className='flex flex-col w-full'>
        {/* LOGO */}
        <Link href='/' className='flex ml-[-10px] mt-[-8px] flex-row justify-space-between items-center'>
          <Image src={isMenuExpand ? logo : '/LOGO_SMALL.png'} alt='DB-GPT' width={160} height={38} />
          {/* <Fold onClick={(e) => {
            e && e.stopPropagation();
            setIsMenuExpand(!isMenuExpand);
          }} /> */}
        </Link>
        {/* functions */}
        <div className='flex flex-col flex-1 w-full' key={Date.now()}>
          {functions.map(item => {
            if (item?.children) {
              return <MenuList value={item} isStow={false} key={item.key + Date.now()} />;
            }

            // 应用列表项单独处理点击事件
            if ((item as any).app) {
              return (
                <div
                  onClick={() => handleChat((item as any).app)}
                  className={cls(
                    'flex items-center w-full h-10 cursor-pointer text-black dark:text-white pl-1',
                    'hover:bg-slate-100 hover:rounded-md',
                    'dark:hover:bg-theme-dark',
                    { 'bg-white rounded-md dark:bg-black': item.isActive },
                  )}
                  key={item.key + Date.now()}
                >
                  <div className='mr-3 w-5 h-5'>{item.icon}</div>
                  <span className='text-sm'>{item.name}</span>
                </div>
              );
            }

            return (
              <Link
                href={item.path ?? '/'}
                className={cls(
                  'flex items-center w-full h-10 cursor-pointer text-black dark:text-white pl-1 mt-1',
                  'hover:bg-slate-100 hover:rounded-md',
                  'dark:hover:bg-theme-dark',
                  { 'bg-white rounded-md dark:bg-black': item.isActive },
                  {'border-t border-gray-300 dark:border-gray-700': item.key === 'application'}
                )}
                key={item.key}
              >
                <div className='mr-3 w-6 h-6'>{item.icon}</div>
                <span className='text-sm'>{t(item.name as any)}</span>
              </Link>
            );
          })}
        </div>
      </div>

      {/* dialog */}
      <div className="text-base flex flex-row items-center font-medium text-sm py-1 px-2 border-t border-gray-300 dark:border-gray-700 mt-1">
        <ClockCircleOutlined className='mr-1 w-7 h-7' />
         历史会话
      </div>
      
      {/* 筛选框 */}
      <div className='pb-1 px-3'>
        <Input.Search
          placeholder="搜索会话..."
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          onSearch={handleSearch}
          allowClear
          loading={listLoading}
        />
      </div>

      <div className='flex-1 overflow-y-auto'>
        {listLoading ? (
          // 显示加载状态
          Array.from({ length: 3 }).map((_, index) => (
            <MenuItem
              key={`loading-${index}`}
              item={{}}
              order={{ current: 0 }}
              loading={true}
            />
          ))
        ) : dialogueLists.length > 0 ? (
          dialogueLists.map(item => (
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
          ))
        ) : (
          <div className='px-8 text-gray-500 text-sm py-4'>
            {searchValue ? '未找到匹配的会话' : '暂无历史会话'}
          </div>
        )}
      </div>

      {/* Settings */}
      <div className='py-2'>
        <span className={cls('flex items-center w-full h-10 px-4 bg-[#F1F5F9] dark:bg-theme-dark rounded-xl')}>
          <div className='mr-3 w-full'>
            <UserBar />
          </div>
        </span>
        <div className='flex items-center justify-around pt-2 border-t border-dashed border-gray-200 dark:border-gray-700'>
          {settings.map(item => (
            <div key={item.key}>
              <Popover content={item.disable ? `${item.name}敬请期待`: item.name}>
                <div className={cls('flex-1 flex items-center justify-center cursor-pointer text-xl', { 'text-gray-400': item.disable })} onClick={item.onClick}>
                  {item.icon}
                </div>
              </Popover>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default SideBar;
