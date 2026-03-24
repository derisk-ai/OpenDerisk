'use client';
import {
  apiInterceptors,
  getAppList,
  newDialogue,
} from '@/client/api';
import { IApp } from '@/types/app';
import { ReloadOutlined, SearchOutlined, GlobalOutlined, RocketFilled, FireFilled, AppstoreOutlined, UnorderedListOutlined, MessageOutlined } from '@ant-design/icons';
import { useDebounceFn } from 'ahooks';
import { App as AntdApp, Spin } from 'antd';
import moment from 'moment';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import './explore-page.css';

type TabKey = 'all' | 'published' | 'unpublished';

export default function ExplorePage() {
  const { notification } = AntdApp.useApp();
  const { t } = useTranslation();
  const [spinning, setSpinning] = useState<boolean>(false);
  const [loadingMore, setLoadingMore] = useState<boolean>(false);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [activeKey, setActiveKey] = useState<TabKey>('all');
  const [apps, setApps] = useState<IApp[]>([]);
  const [filterValue, setFilterValue] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
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

  const handleTabChange = (key: TabKey) => {
    setActiveKey(key);
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

  const handleChat = async (app: IApp) => {
    const [, res] = await apiInterceptors(newDialogue({ app_code: app.app_code }));
    if (res) {
      window.open(`/chat/?app_code=${app.app_code}&conv_uid=${res.conv_uid}`, '_blank');
    }
  };

  useEffect(() => {
    getListFiltered();
  }, [getListFiltered]);

  const stats = {
    total: apps?.length || 0,
    published: apps?.filter(a => a.published)?.length || 0,
    unpublished: apps?.length - apps?.filter(a => a.published)?.length || 0,
  };

  const tabs = [
    { key: 'all' as TabKey, label: t('apps'), icon: <RocketFilled />, count: stats.total },
    { key: 'published' as TabKey, label: t('published'), icon: <GlobalOutlined />, count: stats.published },
    { key: 'unpublished' as TabKey, label: t('unpublished'), icon: <FireFilled />, count: stats.unpublished },
  ];

  return (
    <Spin spinning={spinning} size="large" tip={t('loading')}>
      <div className='explore-page-root'>
        <div className='explore-page-bg' />

        <div className='explore-page-content'>
          <div className='explore-header'>
            <div className='explore-header-left'>
              <div className='explore-header-icon'>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <div>
                <h1 className='explore-title'>{t('explore_agents')}</h1>
                <p className='explore-subtitle'>
                  {t('explore_page_subtitle') || 'Discover and explore available agents'}
                </p>
              </div>
            </div>
            <div className='explore-header-actions'>
              <button
                className='explore-btn-refresh'
                onClick={() => getListFiltered()}
              >
                <ReloadOutlined />
              </button>
            </div>
          </div>

          <div className='explore-stats-bar'>
            <div className='explore-stats-group'>
              {tabs.map(tab => (
                <button
                  key={tab.key}
                  className={`explore-stat ${activeKey === tab.key ? 'active' : ''}`}
                  onClick={() => handleTabChange(tab.key)}
                  style={{
                    background: activeKey === tab.key ? 'var(--mcp-accent-light)' : 'transparent',
                    border: activeKey === tab.key ? '1px solid var(--mcp-accent)' : '1px solid transparent',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <span className='explore-stat-value' style={{ color: activeKey === tab.key ? 'var(--mcp-accent)' : 'var(--mcp-text-primary)' }}>
                    {tab.count}
                  </span>
                  <span className='explore-stat-label'>{tab.label}</span>
                </button>
              ))}
            </div>

            <div className='explore-toolbar'>
              <div className='explore-search-wrapper'>
                <SearchOutlined className='explore-search-icon' />
                <input
                  className='explore-search-input'
                  placeholder={t('search_agents') || t('please_enter_the_keywords')}
                  value={filterValue}
                  onChange={e => setFilterValue(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && getListFiltered()}
                />
              </div>
              <div className='explore-view-toggle'>
                <button
                  className={`explore-view-btn ${viewMode === 'grid' ? 'active' : ''}`}
                  onClick={() => setViewMode('grid')}
                >
                  <AppstoreOutlined />
                </button>
                <button
                  className={`explore-view-btn ${viewMode === 'list' ? 'active' : ''}`}
                  onClick={() => setViewMode('list')}
                >
                  <UnorderedListOutlined />
                </button>
              </div>
            </div>
          </div>

          {apps.length > 0 ? (
            <div className={viewMode === 'grid' ? 'explore-grid' : 'explore-list-view'}>
              {apps.map((item, index) => {
                const isUpdatedRecently = item.updated_at && 
                  moment().diff(moment(item.updated_at), 'days') <= 7;
                
                return (
                  <div
                    key={item.app_code}
                    ref={index === apps.length - 1 ? lastElementRef : null}
                    className={`explore-card ${item.published ? 'explore-card--published' : ''} ${viewMode === 'list' ? 'explore-card--list' : ''}`}
                  >
                    {item.published && <div className='explore-card-glow' />}
                    
                    <div className='explore-card-header'>
                      <div className='explore-card-identity' onClick={() => handleChat(item)}>
                        <div className='explore-card-avatar'>
                          {item.icon ? (
                            <img
                              src={item.icon}
                              alt={item.app_name}
                              onError={(e) => {
                                const target = e.target as HTMLImageElement;
                                target.onerror = null;
                                target.src = '/icons/colorful-plugin.png';
                              }}
                            />
                          ) : (
                            <span className='explore-card-avatar-text'>
                              {(item.app_name || 'A').charAt(0).toUpperCase()}
                            </span>
                          )}
                        </div>
                        <div className='explore-card-meta'>
                          <h3 className='explore-card-name'>{item.app_name}</h3>
                          <div className='explore-card-badges'>
                            {item.language && (
                              <span className='explore-badge explore-badge--type'>
                                {languageMap[item.language]}
                              </span>
                            )}
                            <span className={`explore-badge ${item.published ? 'explore-badge--published' : 'explore-badge--unpublished'}`}>
                              <span className={`explore-status-dot ${item.published ? 'explore-status-dot--published' : ''}`} />
                              {item.published ? t('published') : t('unpublished')}
                            </span>
                          </div>
                        </div>
                      </div>
                      {viewMode === 'grid' && isUpdatedRecently && (
                        <span className='explore-card-new-badge'>
                          <FireFilled style={{ marginRight: 4 }} />
                          New
                        </span>
                      )}
                      {viewMode === 'list' && isUpdatedRecently && (
                        <span className='explore-card-new-badge'>
                          <FireFilled style={{ marginRight: 4 }} />
                          New
                        </span>
                      )}
                    </div>

                    <p className='explore-card-desc'>{item.app_describe}</p>

                    <div className='explore-card-footer'>
                      <div className='explore-card-footer-left'>
                        <span className='explore-card-id'>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                            <line x1="9" y1="3" x2="9" y2="21" />
                          </svg>
                          {item.app_code}
                        </span>
                        {item.owner_name && (
                          <span className='explore-card-author'>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
                              <circle cx="12" cy="7" r="4" />
                            </svg>
                            {item.owner_name}
                          </span>
                        )}
                      </div>
                      <button
                        className='explore-chat-btn'
                        onClick={(e) => {
                          e.stopPropagation();
                          handleChat(item);
                        }}
                      >
                        <MessageOutlined style={{ marginRight: 6 }} />
                        {t('start_chat') || 'Chat'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            !spinning && (
              <div className='explore-empty'>
                <div className='explore-empty-icon'>
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" />
                    <path d="M2 17L12 22L22 17" />
                    <path d="M2 12L12 17L22 12" />
                  </svg>
                </div>
                <h3 className='explore-empty-title'>{t('no_agents_found') || 'No agents found'}</h3>
                <p className='explore-empty-desc'>
                  {t('try_adjusting_filters') || 'Try adjusting your search or filters'}
                </p>
              </div>
            )
          )}

          {loadingMore && (
            <div className='explore-pagination'>
              <Spin size="large" tip={t('loading')} />
            </div>
          )}
        </div>
      </div>
    </Spin>
  );
}