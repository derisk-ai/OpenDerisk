"use client"
import {
  apiInterceptors,
  getAppList,
  newDialogue,
} from '@/client/api';
import BlurredCard, { ChatButton } from '@/components/blurred-card';
import { IApp } from '@/types/app';
import { SearchOutlined } from '@ant-design/icons';
import { useDebounceFn, useRequest } from 'ahooks';
import { App as AntdApp, Input, Pagination, Segmented, SegmentedProps, Spin, Tag } from 'antd';
import moment from 'moment';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

type TabKey = 'all' | 'published' | 'unpublished';

export default function ExplorePage() {
  const { notification } = AntdApp.useApp();
  const { t } = useTranslation();
  const [spinning, setSpinning] = useState<boolean>(false);
  const [activeKey, setActiveKey] = useState<TabKey>('all');
  const [apps, setApps] = useState<IApp[]>([]);
  const [filterValue, setFilterValue] = useState('');
  const totalRef = useRef<{
    current_page: number;
    total_count: number;
    total_page: number;
    page_size: number;
  } | null>(null);

  const handleTabChange = (activeKey: string) => {
    setActiveKey(activeKey as TabKey);
  };

  const getListFiltered = useCallback(() => {
    let published = undefined;
    if (activeKey === 'published') {
      published = 'true';
    }
    if (activeKey === 'unpublished') {
      published = 'false';
    }
    initData({ name_filter: filterValue, published });
  }, [activeKey, filterValue]);

  const initData = useDebounceFn(
    async (params: any) => {
      setSpinning(true);
      const obj: any = {
        page: 1,
        page_size: 12,
        ...params,
      };
      const [error, data] = await apiInterceptors(getAppList(obj), notification);
      if (error) {
        setSpinning(false);
        return;
      }
      if (!data) return;
      setApps(data?.app_list || []);
      totalRef.current = {
        current_page: data?.current_page || 1,
        total_count: data?.total_count || 0,
        total_page: data?.total_page || 0,
        page_size: 12,
      };
      setSpinning(false);
    },
    {
      wait: 500,
    },
  ).run;

  const languageMap: Record<string, string> = {
    en: t('English'),
    zh: t('Chinese'),
  };

  // Open chat in a new browser tab
  const handleChat = async (app: IApp) => {
    const [, res] = await apiInterceptors(newDialogue({ app_code: app.app_code }));
    if (res) {
      window.open(`/chat/?app_code=${app.app_code}&conv_uid=${res.conv_uid}`, '_blank');
    }
  };

  const items: SegmentedProps['options'] = [
    { value: 'all', label: t('apps') },
    { value: 'published', label: t('published') },
    { value: 'unpublished', label: t('unpublished') },
  ];

  const onSearch = async (e: any) => {
    setFilterValue(e.target.value);
  };

  useEffect(() => {
    getListFiltered();
  }, [getListFiltered]);

  return (
    <Spin spinning={spinning}>
      <div className='h-screen w-full p-4 md:p-6 flex flex-col'>
        <div className='flex justify-between items-center mb-4 sticky'>
          <div className='flex items-center gap-4'>
            <Segmented
              className='backdrop-filter backdrop-blur-lg bg-white/30 border border-white rounded-lg shadow p-1 dark:border-[#6f7f95] dark:bg-[#6f7f95]/60 [&_.ant-segmented-item-selected]:bg-[#0c75fc]/80 [&_.ant-segmented-item-selected]:text-white'
              options={items as any}
              onChange={handleTabChange}
              value={activeKey}
            />
            <Input
              variant='filled'
              value={filterValue}
              prefix={<SearchOutlined />}
              placeholder={t('please_enter_the_keywords')}
              onChange={onSearch}
              onPressEnter={onSearch}
              allowClear
              className='w-[230px] h-[40px] border-1 border-white backdrop-filter backdrop-blur-lg bg-white/30 dark:border-[#6f7f95] dark:bg-[#6f7f95]/60'
            />
          </div>
        </div>
        <div className='flex-1 flex-col w-full pb-12 mx-[-8px] overflow-y-auto'>
          <div className='flex flex-wrap flex-1 overflow-y-auto'>
            {apps.length > 0 ? (
              apps.map(item => (
                <BlurredCard
                  key={item.app_code}
                  code={item.app_code}
                  name={item.app_name}
                  description={item.app_describe}
                  logo={item.icon || '/icons/colorful-plugin.png'}
                  Tags={
                    <div>
                      <Tag>{languageMap[item.language]}</Tag>
                      <Tag>{item.team_mode}</Tag>
                      <Tag>{item.published ? t('published') : t('unpublished')}</Tag>
                    </div>
                  }
                  rightTopHover={false}
                  LeftBottom={
                    <div className='flex gap-2'>
                      <span>{item.owner_name}</span>
                      <span>•</span>
                      {item?.updated_at && <span>{moment(item?.updated_at).fromNow() + ' ' + t('update')}</span>}
                    </div>
                  }
                  RightBottom={
                    <ChatButton
                      onClick={() => {
                        handleChat(item);
                      }}
                    />
                  }
                  onClick={() => {
                    handleChat(item);
                  }}
                  scene={item?.team_context?.chat_scene || 'chat_agent'}
                />
              ))
            ) : (
              !spinning && (
                <div className="w-full flex items-center justify-center py-20 text-gray-400">
                  {t('explore_no_agents')}
                </div>
              )
            )}
          </div>
          <div className='w-full flex justify-end shrink-0 pb-12 pt-1'>
            <Pagination
              showSizeChanger={false}
              total={totalRef.current?.total_count || 0}
              pageSize={12}
              current={totalRef.current?.current_page}
              onChange={async (page) => {
                await initData({ page });
              }}
            />
          </div>
        </div>
      </div>
    </Spin>
  );
}
