'use client';
import {
  apiInterceptors,
  getAppList,
  newDialogue,
} from '@/client/api';
import BlurredCard, { ChatButton } from '@/components/blurred-card';
import { IApp } from '@/types/app';
import { SearchOutlined, FireFilled, GlobalOutlined, RocketFilled } from '@ant-design/icons';
import { useDebounceFn } from 'ahooks';
import { App as AntdApp, Button, Flex, Input, Pagination, Segmented, SegmentedProps, Space, Spin, Tag, Typography } from 'antd';
import moment from 'moment';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

type TabKey = 'all' | 'published' | 'unpublished';

const { Title, Text } = Typography;

// Define trending tags for additional navigation
const TrendingTags = [
  'AI Assistant',
  'Data Analysis',
  'Code Generator', 
  'Research',
  'Finance',
  'Customer Support'
];

export default function ExplorePage() {
  const { notification } = AntdApp.useApp();
  const { t } = useTranslation();
  const [spinning, setSpinning] = useState<boolean>(false);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [activeKey, setActiveKey] = useState<TabKey>('all');
  const [apps, setApps] = useState<IApp[]>([]);
  const [filterValue, setFilterValue] = useState('');
  const totalRef = useRef<{
    current_page: number;
    total_count: number;
    total_page: number;
    page_size: number;
  } | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const lastElementRef = useCallback((node: HTMLDivElement | null) => {
    if (spinning) return;
    if (observerRef.current) observerRef.current.disconnect();
    observerRef.current = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && hasMore) {
        loadMoreData();
      }
    });
    if (node) observerRef.current.observe(node);
  }, [spinning, hasMore]);

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
      setHasMore(true);
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
      setHasMore((data?.current_page || 1) < (data?.total_page || 1));
      setSpinning(false);
    },
    {
      wait: 500,
    },
  ).run;

  const loadMoreData = useCallback(async () => {
    if (loadingMore || !hasMore || !totalRef.current) return;
    setLoadingMore(true);
    const nextPage = totalRef.current.current_page + 1;
    let published = undefined;
    if (activeKey === 'published') {
      published = 'true';
    }
    if (activeKey === 'unpublished') {
      published = 'false';
    }
    const obj: any = {
      page: nextPage,
      page_size: 12,
      name_filter: filterValue,
      published,
    };
    const [error, data] = await apiInterceptors(getAppList(obj), notification);
    if (error) {
      setLoadingMore(false);
      return;
    }
    if (!data) {
      setLoadingMore(false);
      return;
    }
    setApps(prev => [...prev, ...(data?.app_list || [])]);
    totalRef.current = {
      ...totalRef.current,
      current_page: data?.current_page || nextPage,
    };
    setHasMore((data?.current_page || nextPage) < (data?.total_page || 1));
    setLoadingMore(false);
  }, [loadingMore, hasMore, activeKey, filterValue, notification]);

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
    { value: 'all', label: 
      <div className="flex items-center gap-2">
        <RocketFilled className="text-blue-500" /> 
        <span>{t('apps')}</span>
      </div> 
    },
    { value: 'published', label: 
      <div className="flex items-center gap-2">
        <GlobalOutlined className="text-green-500" /> 
        <span>{t('published')}</span>
      </div> 
    },
    { value: 'unpublished', label: 
      <div className="flex items-center gap-2">
        <FireFilled className="text-orange-500" /> 
        <span>{t('unpublished')}</span>
      </div> 
    },
  ];

  const onSearch = async (e: any) => {
    setFilterValue(e.target.value);
  };

  useEffect(() => {
    getListFiltered();
  }, [getListFiltered]);

  return (
    <Spin spinning={spinning} size="large" tip={t('loading')}>
      <div className="min-h-screen max-w-[1200px] w-full mx-auto px-5 py-6 md:px-5 md:py-8 pb-20 bg-gradient-to-br from-gray-50 via-white to-gray-100 dark:from-gray-900 dark:via-gray-950 dark:to-gray-900">
        {/* Header Section */}
        <div className="mb-10">
          <Flex vertical gap={16}>
            <div>
              <Title level={2} className="font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent m-0">
                {t('explore_agents')}
              </Title>
            </div>
            
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
              {/* Search and Filters */}
              <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
                <div className="relative w-full sm:w-80">
                  <Input
                    variant="outlined"
                    value={filterValue}
                    prefix={
                      <div className="pr-2 text-gray-400">
                        <SearchOutlined className="text-gray-400" />
                      </div>
                    }
                    placeholder={t('search_agents') || t('please_enter_the_keywords')}
                    onChange={onSearch}
                    onPressEnter={onSearch}
                    allowClear
                    className="py-3 pl-2 pr-4 w-full rounded-xl border-gray-200 shadow-sm hover:shadow-md focus:shadow-md focus-within:shadow-md dark:bg-gray-800/50 dark:border-gray-700 dark:text-white"
                    size="large"
                  />
                </div>
                
                <Segmented
                  className="backdrop-filter backdrop-blur-lg bg-white/70 dark:bg-gray-800/70 border border-gray-200 rounded-2xl shadow-sm dark:border-gray-700 [&_.ant-segmented-item-selected]:bg-gradient-to-r [&_.ant-segmented-item-selected]:from-blue-500 [&_.ant-segmented-item-selected]:to-indigo-500 [&_.ant-segmented-item-selected]:text-white [&_.ant-segmented-item-selected]:rounded-xl"
                  options={items as any}
                  onChange={handleTabChange}
                  value={activeKey}
                  size="large"
                />
              </div>
            </div>
          </Flex>
        </div>
        
        {/* Agents Grid */}
        <div className="flex flex-col w-full overflow-y-auto max-h-[calc(100vh-380px)]">
          {apps.length > 0 ? (
            <div className="explore-grid">
              {apps.map((item, index) => {
                const isUpdatedRecently = item.updated_at && 
                  moment().diff(moment(item.updated_at), 'days') <= 7;
                
                return (
                  <div 
                    key={item.app_code}
                    ref={index === apps.length - 1 ? lastElementRef : null}
                    className="transition-all duration-300 hover:-translate-y-1"
                  >
                    <div className="relative">
                      {isUpdatedRecently && (
                        <div className="absolute -top-2 -right-2 z-10">
                          <Tag color="gold" className="font-semibold rounded-full px-2 py-0.5 text-xs">
                            <FireFilled /> New
                          </Tag>
                        </div>
                      )}
                      
                      <BlurredCard
                        code={item.app_code}
                        name={item.app_name}
                        description={item.app_describe}
                        logo={item.icon || '/icons/colorful-plugin.png'}
                        Tags={
                          <div className="flex flex-wrap gap-1">
                            <Tag 
                              className="rounded-full px-2 py-0.5 text-xs font-medium flex items-center bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800"
                              icon={item.language === 'en' ? <GlobalOutlined /> : null}
                            >
                              {languageMap[item.language]}
                            </Tag>
                            <Tag 
                              className="rounded-full px-2 py-0.5 text-xs font-medium bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 border-purple-200 dark:border-purple-800"
                            >
                              {item.team_mode}
                            </Tag>
                            <Tag 
                              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                                item.published 
                                  ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800' 
                                  : 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-800'
                              }`}
                            >
                              {item.published ? t('published') : t('unpublished')}
                            </Tag>
                          </div>
                        }
                        rightTopHover={false}
                        LeftBottom={
                          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                            <span>{item.owner_name}</span>
                            <span>•</span>
                            {item?.updated_at && (
                              <span>{moment(item?.updated_at).fromNow()}</span>
                            )}
                          </div>
                        }
                        RightBottom={
                          <div className="transform transition-transform duration-200 group-hover:scale-105">
                            <ChatButton
                              onClick={() => {
                                handleChat(item);
                              }}
                              Icon="/pictures/card_chat.png"
                            />
                          </div>
                        }
                        onClick={() => {
                          handleChat(item);
                        }}
                        scene={item?.team_context?.chat_scene || 'chat_agent'}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            !spinning && (
              <div className="w-full flex flex-col items-center justify-center py-20 px-4">
                <div className="bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-900 rounded-2xl p-12 text-center max-w-md">
                  <div className="w-24 h-24 mx-auto mb-6 flex items-center justify-center bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-blue-900/30 dark:to-indigo-900/30 rounded-full">
                    <RocketFilled className="text-4xl text-blue-500" />
                  </div>
                  <Title level={4} className="text-gray-700 dark:text-gray-200">
                    {t('no_agents_found') || 'No agents found'}
                  </Title>
                  <Text className="block text-gray-500 dark:text-gray-400 mb-6">
                    {t('try_adjusting_filters') || 'Try adjusting your search or filters to find what you are looking for'}
                  </Text>
                  <Button 
                    type="primary" 
                    size="large"
                    className="rounded-xl bg-gradient-to-r from-blue-500 to-indigo-500 border-none"
                    onClick={() => setFilterValue('')}
                  >
                    {t('clear_filters') || 'Clear Filters'}
                  </Button>
                </div>
              </div>
            )
          )}
           
           
           {/* Loading More Indicator */}
           {loadingMore && (
             <div className="w-full flex justify-center mt-8 mb-6">
               <Spin size="large" tip={t('loading')} />
             </div>
           )}
           
           {/* No More Data Indicator */}
           {!hasMore && apps.length > 0 && (
             <div className="w-full flex justify-center mt-8 mb-6">
               <Text type="secondary">{t('no_more_data') || 'No more data'}</Text>
             </div>
           )}
         </div>
      </div>
    </Spin>
  );
}
