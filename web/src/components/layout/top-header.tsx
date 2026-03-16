'use client';

import { STORAGE_USERINFO_KEY } from '@/utils/constants/index';
import { LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { Avatar, Dropdown, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { authService } from '@/services/auth';

interface UserInfo {
  nick_name?: string;
  avatar_url?: string;
  role?: string;
}

function TopHeader() {
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [oauthEnabled, setOauthEnabled] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const init = async () => {
      try {
        const status = await authService.getOAuthStatus();
        setOauthEnabled(status.enabled);

        if (status.enabled) {
          // OAuth 开启：直接从 /auth/me 拿最新数据
          try {
            const me = await authService.getMe();
            const info: UserInfo = {
              nick_name: me.nick_name,
              avatar_url: me.avatar_url || me.user?.avatar || '',
              role: me.role || 'normal',
            };
            setUserInfo(info);
            // 同步更新 localStorage 供其他组件使用
            const stored = {
              user_channel: me.user_channel,
              user_no: me.user_no,
              nick_name: me.nick_name,
              avatar_url: info.avatar_url,
              email: me.email || me.user?.email || '',
              role: info.role,
            };
            localStorage.setItem(STORAGE_USERINFO_KEY, JSON.stringify(stored));
          } catch {
            // /auth/me 失败：未登录，layout.tsx 会跳转 /login
          }
        } else {
          // OAuth 关闭：显示 mock 用户
          setUserInfo({ nick_name: 'derisk' });
        }
      } finally {
        setReady(true);
      }
    };

    init();
  }, []);

  const handleLogout = async () => {
    try {
      await authService.logout();
    } catch {
      /* ignore */
    }
    localStorage.removeItem(STORAGE_USERINFO_KEY);
    window.location.href = '/login';
  };

  if (!ready) return <div className="h-12 border-b border-gray-100 dark:border-gray-800 flex-shrink-0" />;

  const displayName = userInfo?.nick_name || '用户';
  const avatarSrc = oauthEnabled ? (userInfo?.avatar_url || undefined) : undefined;

  const menuItems = oauthEnabled
    ? [
        {
          key: 'logout',
          icon: <LogoutOutlined />,
          label: '退出登录',
          onClick: handleLogout,
          danger: true,
        },
      ]
    : [];

  const avatarEl = (
    <span className="flex items-center gap-2 cursor-pointer select-none">
      <Avatar
        src={avatarSrc}
        size={28}
        icon={!avatarSrc ? <UserOutlined /> : undefined}
        className="bg-gradient-to-tr from-[#31afff] to-[#1677ff] flex-shrink-0"
      />
      <Typography.Text className="text-sm font-medium text-gray-700 dark:text-gray-200 max-w-[140px] truncate">
        {displayName}
      </Typography.Text>
    </span>
  );

  return (
    <div className="h-12 border-b border-gray-100 dark:border-gray-800 flex items-center justify-end px-4 bg-white dark:bg-[#111] flex-shrink-0 z-10">
      {oauthEnabled && menuItems.length > 0 ? (
        <Dropdown menu={{ items: menuItems }} placement="bottomRight" trigger={['click']}>
          {avatarEl}
        </Dropdown>
      ) : (
        avatarEl
      )}
    </div>
  );
}

export default TopHeader;
