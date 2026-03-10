"use client"
import { apiInterceptors, getMCPList, offlineMCP, startMCP, deleteMCP } from '@/client/api';
import { InnerDropdown } from '@/components/blurred-card';
import { ReloadOutlined, SearchOutlined, AppstoreOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Pagination, Spin, Button, message, PaginationProps, Popconfirm } from 'antd';
import { useRouter } from 'next/navigation';
import React, { memo, useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import CreatMcpModel from './CreatMcpModel';
import './index.css';

type FieldType = {
  name?: string;
  mcp_code?: string;
  id?: string;
  [key: string]: any;
};

const McpPage: React.FC = () => {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  const [queryParams, setQueryparams] = useState({
    filter: '',
  });
  const [paginationParams, setPaginationParams] = useState({
    page: 1,
    page_size: 20,
  });

  const [mcpList, setMcpList] = useState<any>([]);
  const [formData, setFormData] = useState<any>({});
  const router = useRouter();

  const { loading, run: runGetMPCList } = useRequest(
    async (
      params = { filter: '' },
      other = { page: 1, page_size: 20 },
    ): Promise<any> => {
      return await apiInterceptors(getMCPList(params, other));
    },
    {
      manual: false,
      onSuccess: data => {
        const [, res] = data;
        setMcpList(res?.items || []);
      },
      debounceWait: 300,
    },
  );

  const { run: runStartMCP } = useRequest(
    async (params): Promise<any> => {
      return await apiInterceptors(startMCP(params));
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          message.success(t('start_mcp_success'));
          runGetMPCList(queryParams, paginationParams);
        } else {
          message.error(t('start_mcp_failed'));
        }
      },
      onError: () => {
        message.error(t('start_mcp_failed'));
      },
      throttleWait: 300,
    },
  );

  const handleDelete = async (item: FieldType) => {
    if (!item.name || !item.mcp_code) {
      message.error(t('missing_params'));
      return;
    }
    const params: Record<string, string> = {
      name: item.name || '',
      mcp_code: item.mcp_code || '',
    };
    const [err, , res] = await apiInterceptors(deleteMCP(params));
    if (!err && res?.success) {
      message.success(t('delete_success'));
      onSearch();
    } else {
      message.error(res?.err_msg || t('delete_failed'));
    }
  };

  const { run: runOfflineMCP } = useRequest(
    async (params): Promise<any> => {
      return await apiInterceptors(offlineMCP(params));
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          message.success(t('stop_mcp_success'));
          runGetMPCList(queryParams, paginationParams);
        }
      },
      throttleWait: 300,
    },
  );

  const goMcpDetail = (mcp_code: string, name: string) => {
    router.push(`/mcp/detail/?id=${mcp_code}&name=${name}`);
  };

  const onShowSizeChange: PaginationProps['onShowSizeChange'] = (current: number, pageSize: number) => {
    setPaginationParams(pre => ({ ...pre, page: current, page_size: pageSize }));
    runGetMPCList(queryParams, { page: current, page_size: pageSize });
  };

  const onStopTheMCP = (item: any) => {
    runOfflineMCP({ mcp_code: item?.mcp_code, name: item?.name });
  };

  const onStartTheMCP = (item: any) => {
    runStartMCP({ mcp_code: item?.mcp_code, name: item?.name, sse_headers: item?.sse_headers });
  };

  const onSearch = () => {
    runGetMPCList(queryParams, paginationParams);
  };

  const editMcp = (item: any) => {
    setFormData(item);
  };

  // Stats
  const stats = useMemo(() => {
    const total = mcpList?.length || 0;
    const online = mcpList?.filter((i: any) => i?.available)?.length || 0;
    const offline = total - online;
    return { total, online, offline };
  }, [mcpList]);

  return (
    <Spin spinning={loading}>
      <div className='mcp-page-root'>
        {/* Ambient background */}
        <div className='mcp-page-bg' />

        <div className='mcp-page-content'>
          {/* Header */}
          <div className='mcp-header'>
            <div className='mcp-header-left'>
              <div className='mcp-header-icon'>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 17L12 22L22 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  <path d="M2 12L12 17L22 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <div>
                <h1 className='mcp-title'>MCP Servers</h1>
                <p className='mcp-subtitle'>
                  {t('mcp_page_subtitle')}
                </p>
              </div>
            </div>
            <div className='mcp-header-actions'>
              <Button
                className='mcp-btn-refresh'
                icon={<ReloadOutlined />}
                onClick={() => runGetMPCList(queryParams, paginationParams)}
              />
              <CreatMcpModel
                formData={formData}
                setFormData={setFormData}
                onSuccess={() => runGetMPCList(queryParams, paginationParams)}
              />
            </div>
          </div>

          {/* Stats bar */}
          <div className='mcp-stats-bar'>
            <div className='mcp-stats-group'>
              <div className='mcp-stat'>
                <span className='mcp-stat-value'>{stats.total}</span>
                <span className='mcp-stat-label'>{t('mcp_stat_total')}</span>
              </div>
              <div className='mcp-stat-divider' />
              <div className='mcp-stat'>
                <span className='mcp-stat-value mcp-stat-online'>{stats.online}</span>
                <span className='mcp-stat-label'>{t('mcp_stat_online')}</span>
              </div>
              <div className='mcp-stat-divider' />
              <div className='mcp-stat'>
                <span className='mcp-stat-value mcp-stat-offline'>{stats.offline}</span>
                <span className='mcp-stat-label'>{t('mcp_stat_offline')}</span>
              </div>
            </div>

            <div className='mcp-toolbar'>
              <div className='mcp-search-wrapper'>
                <SearchOutlined className='mcp-search-icon' />
                <input
                  className='mcp-search-input'
                  placeholder={t('Search MCP servers...')}
                  value={queryParams?.filter}
                  onChange={e => setQueryparams(pre => ({ ...pre, filter: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && onSearch()}
                />
              </div>
              <div className='mcp-view-toggle'>
                <button
                  className={`mcp-view-btn ${viewMode === 'grid' ? 'active' : ''}`}
                  onClick={() => setViewMode('grid')}
                >
                  <AppstoreOutlined />
                </button>
                <button
                  className={`mcp-view-btn ${viewMode === 'list' ? 'active' : ''}`}
                  onClick={() => setViewMode('list')}
                >
                  <UnorderedListOutlined />
                </button>
              </div>
            </div>
          </div>

          {/* Cards */}
          {mcpList?.length ? (
            <div className={viewMode === 'grid' ? 'mcp-grid' : 'mcp-list-view'}>
              {mcpList.map((item: any, index: number) => (
                <div
                  key={item?.mcp_code || index}
                  className={`mcp-card ${item?.available ? 'mcp-card--online' : 'mcp-card--offline'} ${viewMode === 'list' ? 'mcp-card--list' : ''}`}
                  onClick={() => goMcpDetail(item?.mcp_code, item?.name)}
                >
                  {/* Status glow */}
                  {item?.available && <div className='mcp-card-glow' />}

                  <div className='mcp-card-header'>
                    <div className='mcp-card-identity'>
                      <div className={`mcp-card-avatar ${item?.available ? 'mcp-card-avatar--online' : ''}`}>
                        {item?.icon ? (
                          <img loading='lazy' src={item?.icon} alt={item?.name} />
                        ) : (
                          <span className='mcp-card-avatar-text'>
                            {(item?.name || 'M').charAt(0).toUpperCase()}
                          </span>
                        )}
                      </div>
                      <div className='mcp-card-meta'>
                        <h3 className='mcp-card-name'>{item?.name}</h3>
                        <div className='mcp-card-badges'>
                          {item?.type && (
                            <span className='mcp-badge mcp-badge--type'>{item.type.toUpperCase()}</span>
                          )}
                          <span className={`mcp-badge ${item?.available ? 'mcp-badge--online' : 'mcp-badge--offline'}`}>
                            <span className={`mcp-status-dot ${item?.available ? 'mcp-status-dot--online' : ''}`} />
                            {item?.available ? t('mcp_online') : t('mcp_offline')}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div onClick={e => e.stopPropagation()} className='mcp-card-actions'>
                      <InnerDropdown
                        menu={{
                          items: [
                            item?.available
                              ? {
                                  key: 'stop_mcp',
                                  label: (
                                    <span className='mcp-dropdown-danger' onClick={() => onStopTheMCP(item)}>
                                      {t('stop_mcp')}
                                    </span>
                                  ),
                                }
                              : {
                                  key: 'start_mcp',
                                  label: (
                                    <span className='mcp-dropdown-success' onClick={() => onStartTheMCP(item)}>
                                      {t('start_mcp')}
                                    </span>
                                  ),
                                },
                            {
                              key: 'edit',
                              label: t('Edit'),
                              onClick: () => editMcp(item),
                            },
                            { type: 'divider' as const },
                            {
                              key: 'delete',
                              label: (
                                <Popconfirm
                                  title={t('delete_mcp')}
                                  description={t('delete_mcp_confirm')}
                                  onConfirm={() => handleDelete(item)}
                                  okText={t('Yes')}
                                  cancelText={t('No')}
                                  okButtonProps={{ danger: true }}
                                >
                                  <span className='mcp-dropdown-danger'>{t('Delete')}</span>
                                </Popconfirm>
                              ),
                            },
                          ].filter(Boolean) as any,
                        }}
                      />
                    </div>
                  </div>

                  <p className='mcp-card-desc'>{item?.description}</p>

                  <div className='mcp-card-footer'>
                    <div className='mcp-card-footer-left'>
                      {item?.author && (
                        <span className='mcp-card-author'>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
                            <circle cx="12" cy="7" r="4" />
                          </svg>
                          {item.author}
                        </span>
                      )}
                    </div>
                    <span className='mcp-card-version'>{item?.version || 'v1.0.0'}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            !loading && (
              <div className='mcp-empty'>
                <div className='mcp-empty-icon'>
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" />
                    <path d="M2 17L12 22L22 17" />
                    <path d="M2 12L12 17L22 12" />
                  </svg>
                </div>
                <h3 className='mcp-empty-title'>{t('No MCP servers found')}</h3>
                <p className='mcp-empty-desc'>
                  {t('mcp_empty_desc')}
                </p>
              </div>
            )
          )}

          {/* Pagination */}
          {mcpList?.length > 0 && (
            <div className='mcp-pagination'>
              <Pagination
                current={paginationParams?.page}
                pageSize={paginationParams?.page_size}
                showSizeChanger
                onChange={onShowSizeChange}
                size="small"
              />
            </div>
          )}
        </div>
      </div>
    </Spin>
  );
};

export default memo(McpPage);
