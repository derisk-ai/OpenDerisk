import { ChatContext } from '@/app/chat-context';
import { DarkSvg, ModelSvg, SunnySvg } from '@/components/icons';
import MenuList from '@/components/menuList';
import UserBar from '@/new-components/layout/UserBar';
import { STORAGE_LANG_KEY, STORAGE_THEME_KEY, STORAGE_USERINFO_KEY } from '@/utils/constants/index';
import Icon, {
  ConsoleSqlOutlined,
  GlobalOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PartitionOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { Popover, Tooltip } from 'antd';
import { ItemType } from 'antd/es/menu/hooks/useItems';
import cls from 'classnames';
import moment from 'moment';
import 'moment/locale/zh-cn';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

type SettingItem = {
  key: string;
  name: string;
  icon: ReactNode;
  noDropdownItem?: boolean;
  onClick?: () => void;
  items?: ItemType[];
  onSelect?: (p: { key: string }) => void;
  defaultSelectedKeys?: string[];
  placement?: 'top' | 'topLeft';
};

export type RouteItem = {
  key: string;
  name: string;
  icon: ReactNode;
  path: string;
  isActive?: boolean;
  children?: RouteItem[];
  hideInMenu?: boolean;
};

// TODO: unused function
// function menuItemStyle(active?: boolean) {
//   return `flex items-center h-12 hover:bg-[#F1F5F9] dark:hover:bg-theme-dark text-base w-full transition-colors whitespace-nowrap px-4 ${
//     active ? 'bg-[#F1F5F9] dark:bg-theme-dark' : ''
//   }`;
// }

function smallMenuItemStyle(active?: boolean) {
  return `flex items-center justify-center mx-auto rounded w-14 h-14 text-xl hover:bg-[#F1F5F9] dark:hover:bg-theme-dark transition-colors cursor-pointer ${
    active ? 'bg-[#F1F5F9] dark:bg-theme-dark' : ''
  }`;
}

function SideBar() {
  const { isMenuExpand, setIsMenuExpand, mode, setMode, adminList } = useContext(ChatContext);
  const { pathname } = useRouter();
  const { t, i18n } = useTranslation();
  const [logo, setLogo] = useState<string>('/logo_zh_latest.png');

  const hasAdmin = useMemo(() => {
    const { user_id } = JSON.parse(localStorage.getItem(STORAGE_USERINFO_KEY) || '{}');
    return adminList.some(admin => admin.user_id === user_id);
  }, [adminList]);

  const handleToggleMenu = useCallback(() => {
    setIsMenuExpand(!isMenuExpand);
  }, [isMenuExpand, setIsMenuExpand]);

  const handleToggleTheme = useCallback(() => {
    const theme = mode === 'light' ? 'dark' : 'light';
    setMode(theme);
    localStorage.setItem(STORAGE_THEME_KEY, theme);
  }, [mode, setMode]);

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
        key: 'theme',
        name: t('Theme'),
        icon: mode === 'dark' ? <Icon component={DarkSvg} /> : <Icon component={SunnySvg} />,
        items: [
          {
            key: 'light',
            label: (
              <div className='py-1 flex justify-between gap-8 '>
                <span className='flex gap-2 items-center'>
                  <Image src='/pictures/theme_light.png' alt='english' width={38} height={32}></Image>
                  <span>Light</span>
                </span>
                <span
                  className={cls({
                    block: mode === 'light',
                    hidden: mode !== 'light',
                  })}
                >
                  ✓
                </span>
              </div>
            ),
          },
          {
            key: 'dark',
            label: (
              <div className='py-1 flex justify-between gap-8 '>
                <span className='flex gap-2 items-center'>
                  <Image src='/pictures/theme_dark.png' alt='english' width={38} height={32}></Image>
                  <span>Dark</span>
                </span>
                <span
                  className={cls({
                    block: mode === 'dark',
                    hidden: mode !== 'dark',
                  })}
                >
                  ✓
                </span>
              </div>
            ),
          },
        ],
        onClick: handleToggleTheme,
        onSelect: ({ key }: { key: string }) => {
          if (mode === key) return;
          setMode(key as 'light' | 'dark');
          localStorage.setItem(STORAGE_THEME_KEY, key);
        },
        defaultSelectedKeys: [mode],
        placement: 'topLeft',
      },
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

  const functions = useMemo(() => {
    const items: RouteItem[] = [
      {
        key: 'chat',
        name: t('chat_online'),
        icon: (
          <Image
            key='image_chat'
            src={pathname === '/chat' ? '/pictures/chat_active.png' : '/pictures/chat.png'}
            alt='chat_image'
            width={40}
            height={40}
          />
        ),
        path: '/chat',
        isActive: pathname.startsWith('/chat'),
      },
      {
        //
        key: 'configuration_management',
        name: t('configuration_management'),
        icon: <SettingOutlined style={{ fontSize: '20px', margin: '0 10px' }} />,
        path: '/configuration_management',
        children: [
          {
            key: 'knowledge',
            name: t('knowledge'),
            isActive: pathname.startsWith('/construct/knowledge'),
            icon: <PartitionOutlined style={{ fontSize: '20px', margin: '0 10px' }} />,
            path: '/construct/knowledge',
          },
          {
            key: 'MCP',
            name: 'MCP',
            isActive: pathname.startsWith('/construct/mpc'),
            icon: <ConsoleSqlOutlined style={{ fontSize: '20px', margin: '0 10px' }} />,
            path: '/construct/mpc',
          },
          {
            key: 'model',
            name: t('modelMenu'),
            isActive: pathname.startsWith('/construct/models'),
            icon: <Icon component={ModelSvg} style={{ fontSize: '20px', margin: '0 10px' }} />,
            path: '/construct/models',
          },
        ],
      },
    ];
    return items;
  }, [t, pathname, hasAdmin]);

  useEffect(() => {
    const language = i18n.language;
    if (language === 'zh') moment.locale('zh-cn');
    if (language === 'en') moment.locale('en');
  }, []);

  useEffect(() => {
    setLogo(mode === 'dark' ? '/logo_s_latest.png' : '/logo_zh_latest.png');
  }, [mode]);

  if (!isMenuExpand) {
    return (
      <div
        className='flex flex-col justify-between pt-4 h-screen bg-bar dark:bg-[#232734] animate-fade animate-duration-300'
        // onMouseEnter={() => {
        // setIsMenuExpand(true);
        // }}
      >
        <div>
          <Link href='/' className='flex justify-center items-center pb-4'>
            <Image src={isMenuExpand ? logo : '/LOGO_SMALL.png'} alt='DB-GPT' width={40} height={40} />
          </Link>
          <div className='flex flex-col gap-4 items-center'>
            {functions.map(i => {
              if (i?.hideInMenu) return <></>;
              if (i?.children) {
                return (
                  <>
                    <MenuList value={i} isStow={true} />
                  </>
                );
              }

              return (
                <Link key={i.key} className='h-12 flex items-center' href={i.path}>
                  {i?.icon}
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
      className='flex flex-col justify-between h-screen px-4 pt-4 bg-bar dark:bg-[#232734] animate-fade animate-duration-300'
      // onMouseLeave={() => {
      //   setIsMenuExpand(false);
      // }}
    >
      <div>
        {/* LOGO */}
        <Link href='/' className='flex items-center justify-center p-2 pb-4'>
          <Image src={isMenuExpand ? logo : '/LOGO_SMALL.png'} alt='DB-GPT' width={180} height={40} />
        </Link>
        {/* functions */}
        <div className='flex flex-col gap-4'>
          {functions.map((item: RouteItem) => {
            if (item?.hideInMenu) return <></>;
            if (item?.children) {
              return (
                <div key={item?.key}>
                  <MenuList value={item} />
                </div>
              );
            }
            return (
              <Link
                href={item.path}
                className={cls(
                  'flex items-center w-full h-12 px-4 cursor-pointer hover:bg-[#F1F5F9] dark:hover:bg-theme-dark hover:rounded-xl',
                  {
                    'bg-white rounded-xl dark:bg-black': item.isActive,
                  },
                )}
                key={item.key}
              >
                <div className='mr-3'>{item.icon}</div>
                <span className='text-sm'>{t(item.name as any)}</span>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Settings */}
      <div className='pt-4'>
        <span className={cls('flex items-center w-full h-12 px-4 bg-[#F1F5F9] dark:bg-theme-dark rounded-xl')}>
          <div className='mr-3 w-full'>
            <UserBar />
          </div>
        </span>
        <div className='flex items-center justify-around py-4 mt-2 border-t border-dashed border-gray-200 dark:border-gray-700'>
          {settings.map(item => (
            <div key={item.key}>
              <Popover content={item.name}>
                <div className='flex-1 flex items-center justify-center cursor-pointer text-xl' onClick={item.onClick}>
                  {item.icon}
                </div>
              </Popover>
              {/* {item.items ? (
                <Dropdown
                  menu={{ items: item.items, selectable: true, onSelect: item.onSelect, defaultSelectedKeys: item.defaultSelectedKeys }}
                  placement={item.placement || 'top'}
                  arrow
                >
                  <span onClick={item.onClick}>{item.icon}</span>
                </Dropdown>
              ) : (
                <Popover content={item.name}>
                  <div className="flex-1 flex items-center justify-center cursor-pointer text-xl" onClick={item.onClick}>
                    {item.icon}
                  </div>
                </Popover>
              )} */}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default SideBar;
