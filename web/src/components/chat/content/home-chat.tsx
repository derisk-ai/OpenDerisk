'use client';
import { apiInterceptors, getAppList, newDialogue } from '@/client/api';
import ChatInput from '@/components/chat/input/chat-input';
import { IApp } from '@/types/app';
import { useRequest } from 'ahooks';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function HomeChat() {
  const { t } = useTranslation();
  const [appList, setAppList] = useState<IApp[]>([]);
  const router = useRouter();

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

  const handleChat = async (app: IApp) => {
    const [, res] = await apiInterceptors(newDialogue({ app_code: app.app_code }));
    if (res) {
      router.push(`/chat/?app_code=${app.app_code}&conv_uid=${res.conv_uid}`);
    }
  };

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
          <ChatInput bodyClassName='h-24 items-end' minRows={4} maxRows={8} cneterBtn={false} />
        </div>
        
        {/* 应用卡片展示区域 */}
        {/* {appList.length > 0 && (
          <div className='flex flex-wrap gap-4 mt-6 w-full justify-start' style={{ width: '900px' }}>
            {appList.map((app) => (
                <Card
                key={app.app_code}
                className='w-64 cursor-pointer hover:shadow-lg transition-shadow duration-200 border border-gray-200 dark:border-gray-600 rounded-[12px]'
                styles={{ body: { padding: '12px' } }}
                hoverable
                onClick={() => handleChat(app)}
                >
                <div className='flex items-center space-x-3'>
                  <div className='flex-shrink-0'>
                    {app.icon ? (
                      <img 
                        src={app.icon} 
                        alt={app.app_name} 
                        className='w-12 h-12 rounded-lg object-cover'
                      />
                    ) : (
                      <div className='w-12 h-12 bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg flex items-center justify-center text-white font-bold text-lg'>
                        {app.app_name.charAt(0).toUpperCase()}
                      </div>
                    )}
                  </div>
                  
                  <div className='flex-1 min-w-0'>
                    <Tooltip title={app.app_name} placement="top">
                      <h3 className='text-sm font-semibold text-gray-900 dark:text-gray-100 truncate mb-1'>
                        {app.app_name}
                      </h3>
                    </Tooltip>
                    <Tooltip 
                      title={app.app_describe || '暂无描述'} 
                      placement="bottom"
                      styles={{ root: { maxWidth: '300px' } }}
                    >
                      <p className='text-xs text-gray-600 dark:text-gray-400 line-clamp-2 leading-relaxed'>
                      {app.app_describe || '暂无描述'}
                      </p>
                    </Tooltip>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )} */}
      </div>
    </div>
  );
}
