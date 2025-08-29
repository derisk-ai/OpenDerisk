'use client';
import ChatInput from '@/components/chat/input/chat-input';
import { t } from 'i18next';
import { use, useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useRequest } from 'ahooks';
import { apiInterceptors, getAppList } from '@/client/api';

export default function Home() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (pathname === '/') {
      router.replace('/chat')
    }
  },[pathname, router])

  return (
     <div className='h-screen flex flex-col items-center justify-center'>
      <div className='flex-1 flex flex-col justify-center items-center w-4/5'>
        <div className='text-4xl w-full justify-center flex items-center font-bold text-slate-800 dark:text-slate-200'>
          <span className='mr-2'>🚀</span>
          <span className='text-transparent bg-clip-text font-bold bg-gradient-to-r from-sky-500 to-indigo-800'>
            {t('homeTitle')}
          </span>
        </div>
        <div className='text-l px-5 mt-6 font-thin text-center'>{t('homeTip')}</div>
        <div className='flex flex-col mt-6 w-full' style={{ width: '900px' }}>
          <ChatInput
            bodyClassName='h-24 items-end'
            minRows={4}
            maxRows={8}
            cneterBtn={false}
          />
        </div>
        <div className='flex flex-row w-full items-center justify-center mt-4 mb-4'>
        </div>
      </div>
    </div>
  );
}
