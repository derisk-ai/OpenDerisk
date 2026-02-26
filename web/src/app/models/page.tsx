'use client';
import { apiInterceptors, getModelList, newDialogue, startModel, stopModel } from '@/client/api';
import { InnerDropdown } from '@/components/blurred-card';
import ModelForm from '@/components/model/model-form';
import { ChatContext } from '@/contexts';
import { IModelData } from '@/types/model';
import { ReloadOutlined, SearchOutlined, AppstoreOutlined, UnorderedListOutlined, PlusOutlined, DeleteOutlined, PlayCircleOutlined, StopOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Button, Modal, Tag, message, Pagination, PaginationProps } from 'antd';
import moment from 'moment';
import { useRouter } from 'next/navigation';
import { useContext, useEffect, useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import './model-page.css';

const { confirm: modalConfirm } = Modal;

export default function ModelManage() {
  const { t } = useTranslation();
  const { setModel } = useContext(ChatContext);
  const router = useRouter();

  const [models, setModels] = useState<IModelData[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchValue, setSearchValue] = useState('');
  const [paginationParams, setPaginationParams] = useState({
    page: 1,
    page_size: 20,
  });

  const { loading: listLoading, run: runGetModels } = useRequest(
    async () => {
      const [, res] = await apiInterceptors(getModelList());
      return res ?? [];
    },
    {
      manual: false,
      onSuccess: data => {
        setModels(data);
      },
    },
  );

  async function getModels() {
    const [, res] = await apiInterceptors(getModelList());
    setModels(res ?? []);
  }

  async function startTheModel(info: IModelData) {
    if (loading) return;
    const content = t(`confirm_start_model`) + info.model_name;

    showConfirm(t('start_model'), content, async () => {
      setLoading(true);
      const [, , res] = await apiInterceptors(
        startModel({
          host: info.host,
          port: info.port,
          model: info.model_name,
          worker_type: info.worker_type,
          delete_after: false,
          params: {},
        }),
      );
      setLoading(false);
      if (res?.success) {
        message.success(t('start_model_success'));
        await getModels();
      }
    });
  }

  async function stopTheModel(info: IModelData, delete_after = false) {
    if (loading) return;

    const action = delete_after ? 'stop_and_delete' : 'stop';
    const content = t(`confirm_${action}_model`) + info.model_name;
    showConfirm(t(`${action}_model`), content, async () => {
      setLoading(true);
      const [, , res] = await apiInterceptors(
        stopModel({
          host: info.host,
          port: info.port,
          model: info.model_name,
          worker_type: info.worker_type,
          delete_after: delete_after,
          params: {},
        }),
      );
      setLoading(false);
      if (res?.success === true) {
        message.success(t(`${action}_model_success`));
        await getModels();
      }
    });
  }

  const confirmDelete = (item: IModelData) => {
    modalConfirm({
      title: t('delete_model'),
      content: t('delete_model_confirm') + item.model_name + '?',
      okText: t('Yes'),
      cancelText: t('No'),
      okButtonProps: { danger: true },
      onOk() {
        message.info(t('delete_model_tip'));
      },
    });
  };

  const showConfirm = (title: string, content: string, onOk: () => Promise<void>) => {
    Modal.confirm({
      title,
      content,
      onOk: async () => {
        await onOk();
      },
      okButtonProps: {
        className: 'bg-button-gradient',
      },
    });
  };

  const handleChat = async (info: IModelData) => {
    const [_, data] = await apiInterceptors(
      newDialogue({
        app_code: 'chat_normal',
        model: info.model_name,
      }),
    );
    if (data?.conv_uid) {
      setModel(info.model_name);
      router.push(`/chat?app_code=chat_normal&conv_uid=${data?.conv_uid}&model=${info.model_name}`);
    }
  };

  const filteredModels = useMemo(() => {
    if (!searchValue.trim()) return models;
    return models.filter(item => 
      item.model_name?.toLowerCase().includes(searchValue.toLowerCase()) ||
      item.host?.toLowerCase().includes(searchValue.toLowerCase())
    );
  }, [models, searchValue]);

  const stats = useMemo(() => {
    const total = models?.length || 0;
    const online = models?.filter(i => i.healthy)?.length || 0;
    const offline = total - online;
    return { total, online, offline };
  }, [models]);

  const onShowSizeChange: PaginationProps['onShowSizeChange'] = (current: number, pageSize: number) => {
    setPaginationParams(pre => ({ ...pre, page: current, page_size: pageSize }));
  };

  return (
    <div className='model-page-root'>
      <div className='model-page-bg' />

      <div className='model-page-content'>
        <div className='model-header'>
          <div className='model-header-left'>
            <div className='model-header-icon'>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div>
              <h1 className='model-title'>{t('model_management')}</h1>
              <p className='model-subtitle'>
                {t('model_page_subtitle')}
              </p>
            </div>
          </div>
          <div className='model-header-actions'>
            <Button
              className='model-btn-refresh'
              icon={<ReloadOutlined />}
              onClick={() => getModels()}
            />
            <Button
              className='border-none text-white bg-button-gradient model-btn-primary'
              icon={<PlusOutlined />}
              onClick={() => {
                setIsModalOpen(true);
              }}
            >
              {t('create_model')}
            </Button>
          </div>
        </div>

        <div className='model-stats-bar'>
          <div className='model-stats-group'>
            <div className='model-stat'>
              <span className='model-stat-value'>{stats.total}</span>
              <span className='model-stat-label'>{t('model_stat_total')}</span>
            </div>
            <div className='model-stat-divider' />
            <div className='model-stat'>
              <span className='model-stat-value model-stat-online'>{stats.online}</span>
              <span className='model-stat-label'>{t('model_stat_online')}</span>
            </div>
            <div className='model-stat-divider' />
            <div className='model-stat'>
              <span className='model-stat-value model-stat-offline'>{stats.offline}</span>
              <span className='model-stat-label'>{t('model_stat_offline')}</span>
            </div>
          </div>

          <div className='model-toolbar'>
            <div className='model-search-wrapper'>
              <SearchOutlined className='model-search-icon' />
              <input
                className='model-search-input'
                placeholder={t('Search_models')}
                value={searchValue}
                onChange={e => setSearchValue(e.target.value)}
              />
            </div>
            <div className='model-view-toggle'>
              <button
                className={`model-view-btn ${viewMode === 'grid' ? 'active' : ''}`}
                onClick={() => setViewMode('grid')}
              >
                <AppstoreOutlined />
              </button>
              <button
                className={`model-view-btn ${viewMode === 'list' ? 'active' : ''}`}
                onClick={() => setViewMode('list')}
              >
                <UnorderedListOutlined />
              </button>
            </div>
          </div>
        </div>

        {filteredModels?.length ? (
          <div className={viewMode === 'grid' ? 'model-grid' : 'model-list-view'}>
            {filteredModels.map((item, index) => (
              <div
                key={item.model_name || index}
                className={`model-card ${item.healthy ? 'model-card--online' : 'model-card--offline'} ${viewMode === 'list' ? 'model-card--list' : ''}`}
              >
                {item.healthy && <div className='model-card-glow' />}

                <div className='model-card-header'>
                  <div className='model-card-identity'>
                    <div className={`model-card-avatar ${item.healthy ? 'model-card-avatar--online' : ''}`}>
                      <span className='model-card-avatar-text'>
                        {(item.model_name || 'M').charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div className='model-card-meta'>
                      <h3 className='model-card-name'>{item.model_name}</h3>
                      <div className='model-card-badges'>
                        <span className='model-badge model-badge--type'>{item.worker_type}</span>
                        <span className={`model-badge ${item.healthy ? 'model-badge--online' : 'model-badge--offline'}`}>
                          <span className={`model-status-dot ${item.healthy ? 'model-status-dot--online' : ''}`} />
                          {item.healthy ? t('model_healthy') : t('model_unhealthy')}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className='model-card-actions'>
                    <InnerDropdown
                      menu={{
                        items: [
                          {
                            key: 'start_model',
                            label: (
                              <span className='model-dropdown-success' onClick={() => startTheModel(item)}>
                                <PlayCircleOutlined /> {t('start_model')}
                              </span>
                            ),
                          },
                          {
                            key: 'stop_model',
                            label: (
                              <span className='model-dropdown-warning' onClick={() => stopTheModel(item)}>
                                <StopOutlined /> {t('stop_model')}
                              </span>
                            ),
                          },
                          { type: 'divider' as const },
                          {
                            key: 'stop_and_delete',
                            label: (
                              <span className='model-dropdown-danger' onClick={() => stopTheModel(item, true)}>
                                <StopOutlined /> {t('stop_and_delete_model')}
                              </span>
                            ),
                          },
                          {
                            key: 'delete',
                            label: (
                              <span className='model-dropdown-danger'>
                                <DeleteOutlined /> {t('Delete')}
                              </span>
                            ),
                            onClick: () => confirmDelete(item),
                          },
                        ].filter(Boolean) as any,
                      }}
                    />
                  </div>
                </div>

                <div className='model-card-desc'>
                  <div className='model-info-list'>
                    <div className='model-info-item'>
                      <span className='model-info-label'>Host</span>
                      <span className='model-info-value'>{item.host}:{item.port}</span>
                    </div>
                    <div className='model-info-item'>
                      <span className='model-info-label'>Manager</span>
                      <span className='model-info-value'>{item.manager_host}:{item.manager_port}</span>
                    </div>
                    <div className='model-info-item'>
                      <span className='model-info-label'>Heartbeat</span>
                      <span className='model-info-value'>{moment(item.last_heartbeat).format('MM-DD HH:mm')}</span>
                    </div>
                  </div>
                </div>

                <div className='model-card-footer'>
                  <div className='model-card-footer-left'>
                    <span className='model-card-port'>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
                      </svg>
                      {item.host}:{item.port}
                    </span>
                  </div>
                  <Button
                    type="primary"
                    size="small"
                    className="model-chat-btn"
                    onClick={() => handleChat(item)}
                  >
                    {t('start_chat')}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          !listLoading && (
            <div className='model-empty'>
              <div className='model-empty-icon'>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
              </div>
              <h3 className='model-empty-title'>{t('No_models_found')}</h3>
              <p className='model-empty-desc'>
                {t('model_empty_desc')}
              </p>
            </div>
          )
        )}

        {filteredModels?.length > 0 && (
          <div className='model-pagination'>
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

      <Modal
        width={800}
        open={isModalOpen}
        title={t('create_model')}
        onCancel={() => {
          setIsModalOpen(false);
        }}
        footer={null}
        className='model-modal'
      >
        <ModelForm
          onCancel={() => {
            setIsModalOpen(false);
          }}
          onSuccess={() => {
            setIsModalOpen(false);
            getModels();
          }}
        />
      </Modal>
    </div>
  );
}