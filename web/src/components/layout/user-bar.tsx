"use client"
import { UserInfoResponse } from '@/types/userinfo';
import { STORAGE_USERINFO_KEY } from '@/utils/constants/index';
import { Avatar } from 'antd';
import cls from 'classnames';
import { useEffect, useState } from 'react';

function UserBar({ onlyAvatar = false }) {
  const [userInfo, setUserInfo] = useState<UserInfoResponse>();
  useEffect(() => {
    try {
      const user = JSON.parse(localStorage.getItem(STORAGE_USERINFO_KEY) ?? '');
      setUserInfo(user);
    } catch {
      return undefined;
    }
  }, []);

  return (
    <div className={cls('flex flex-1 items-center', {
      'justify-center': onlyAvatar,
      'justify-start': !onlyAvatar,
    })}>
      <div
        className={cls('flex items-center group w-full', {
          'justify-center': onlyAvatar,
          'justify-start': !onlyAvatar,
        })}
      >
        <span className='flex gap-2 items-center overflow-hidden'>
          <Avatar src={userInfo?.avatar_url} className='bg-gradient-to-tr from-[#31afff] to-[#1677ff] cursor-pointer shrink-0'>
            {userInfo?.nick_name}
          </Avatar>
          <span
            className={cls('text-sm truncate font-medium text-gray-700 dark:text-gray-200', {
              hidden: onlyAvatar,
            })}
          >
            {userInfo?.nick_name}
          </span>
        </span>
      </div>
    </div>
  );
}

export default UserBar;
