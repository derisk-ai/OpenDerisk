'use client';

import {
  apiInterceptors,
  getDbList,
  getDbSupportType,
  getDbSpec,
  postDbDelete,
  postDbLearn,
} from '@/client/api';
import { DbSpecResponse, IChatDbSchema, IChatDbSupportTypeSchema } from '@/types/db';
import {
  DatabaseOutlined,
  DeleteOutlined,
  EyeOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
  SearchOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Button, Spin } from 'antd';
import { useRouter } from 'next/navigation';
import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import DatabaseAddModal from './components/DatabaseAddModal';
import './db-page.css';

type SpecStatus = 'ready' | 'generating' | 'failed' | 'none';

interface DatabaseWithStatus extends IChatDbSchema {
  specStatus?: SpecStatus;
}

/** Map new API format {type, params, description} to flat display fields */
function normalizeDatasource(raw: any): IChatDbSchema {
  const params = raw.params || {};
  return {
    ...raw,
    db_type: raw.db_type || raw.type || '',
    db_name: raw.db_name || params.database || params.db_name || (params.path ? params.path.split('/').pop()?.replace(/\.\w+$/, '') : '') || '',
    db_host: raw.db_host || params.host || '',
    db_port: raw.db_port || params.port || 0,
    db_path: raw.db_path || params.path || '',
    db_user: raw.db_user || params.user || '',
    comment: raw.comment || raw.description || '',
  };
}

export default function DatabasePage() {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const router = useRouter();
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [searchValue, setSearchValue] = useState('');
  const [dbsWithStatus, setDbsWithStatus] = useState<DatabaseWithStatus[]>([]);

  // Fetch database list
  const {
    data: dbListData,
    loading: dbListLoading,
    refresh: refreshDbList,
  } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getDbList());
    if (err) return [];
    return ((res || []) as any[]).map(normalizeDatasource) as IChatDbSchema[];
  });

  // Fetch supported types — Fix Bug 1+2: proper destructuring + unwrap ResourceTypes
  const { data: supportTypes } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getDbSupportType());
    if (err) return [];
    // Backend returns ResourceTypes { types: [...] }, unwrap it
    const types = (res as any)?.types || res || [];
    return Array.isArray(types) ? types : [];
  });

  // Fetch spec status for each database — Fix Bug 3
  useEffect(() => {
    if (!dbListData || dbListData.length === 0) {
      setDbsWithStatus([]);
      return;
    }

    const fetchStatuses = async () => {
      const results: DatabaseWithStatus[] = await Promise.all(
        dbListData.map(async (db) => {
          try {
            const [err, res] = await apiInterceptors(getDbSpec(db.id));
            if (err || !res) return { ...db, specStatus: 'none' as SpecStatus };
            const status = (res as DbSpecResponse).status;
            if (status === 'ready') return { ...db, specStatus: 'ready' as SpecStatus };
            if (status === 'generating') return { ...db, specStatus: 'generating' as SpecStatus };
            if (status === 'failed') return { ...db, specStatus: 'failed' as SpecStatus };
            return { ...db, specStatus: 'none' as SpecStatus };
          } catch {
            return { ...db, specStatus: 'none' as SpecStatus };
          }
        }),
      );
      setDbsWithStatus(results);
    };

    fetchStatuses();
  }, [dbListData]);

  // Delete database
  const { run: runDelete } = useRequest(
    async (id: string) => {
      const [err] = await apiInterceptors(postDbDelete(id));
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('db_deleted'));
        refreshDbList();
      },
      onError: () => {
        message.error(t('db_delete_failed'));
      },
    },
  );

  // Trigger learning
  const { run: runLearn } = useRequest(
    async (id: string) => {
      const [err] = await apiInterceptors(postDbLearn(id));
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success(t('learning_started'));
        refreshDbList();
      },
      onError: () => {
        message.error(t('learning_failed'));
      },
    },
  );

  const handleViewDetail = useCallback((db: IChatDbSchema) => {
    router.push(`/database/detail?id=${db.id}`);
  }, [router]);

  const handleAddSuccess = useCallback(() => {
    setAddModalOpen(false);
    refreshDbList();
  }, [refreshDbList]);

  const handleDelete = useCallback(
    (db: IChatDbSchema) => {
      modal.confirm({
        title: t('delete_database'),
        content: t('delete_database_confirm'),
        okText: t('Yes'),
        cancelText: t('No'),
        okButtonProps: { danger: true },
        onOk: () => runDelete(String(db.id)),
      });
    },
    [runDelete, t],
  );

  // Stats
  const stats = useMemo(() => {
    const total = dbsWithStatus.length;
    const withSpec = dbsWithStatus.filter((d) => d.specStatus === 'ready').length;
    const noSpec = total - withSpec;
    return { total, withSpec, noSpec };
  }, [dbsWithStatus]);

  // Filtered list
  const filteredDbs = useMemo(() => {
    if (!searchValue.trim()) return dbsWithStatus;
    const q = searchValue.toLowerCase();
    return dbsWithStatus.filter(
      (db) =>
        (db.db_name || db.name || '').toLowerCase().includes(q) ||
        (db.db_type || '').toLowerCase().includes(q) ||
        (db.db_host || '').toLowerCase().includes(q) ||
        (db.comment || '').toLowerCase().includes(q),
    );
  }, [dbsWithStatus, searchValue]);

  // DB type avatar class
  const getAvatarClass = (dbType: string) => {
    const typeStr = (dbType || '').toLowerCase();
    if (typeStr.includes('mysql')) return 'db-card-avatar--mysql';
    if (typeStr.includes('postgres')) return 'db-card-avatar--postgresql';
    if (typeStr.includes('sqlite')) return 'db-card-avatar--sqlite';
    if (typeStr.includes('clickhouse')) return 'db-card-avatar--clickhouse';
    if (typeStr.includes('oracle')) return 'db-card-avatar--oracle';
    if (typeStr.includes('mssql') || typeStr.includes('sqlserver')) return 'db-card-avatar--mssql';
    if (typeStr.includes('mongo')) return 'db-card-avatar--mongodb';
    if (typeStr.includes('redis')) return 'db-card-avatar--redis';
    return '';
  };

  // Status badge
  const getStatusBadge = (status?: SpecStatus) => {
    switch (status) {
      case 'ready':
        return (
          <span className="db-badge db-badge--ready">
            <span className="db-status-dot db-status-dot--ready" />
            {t('spec_ready')}
          </span>
        );
      case 'generating':
        return (
          <span className="db-badge db-badge--learning">
            <span className="db-status-dot db-status-dot--learning" />
            {t('spec_learning')}
          </span>
        );
      case 'failed':
        return (
          <span className="db-badge db-badge--failed">
            <span className="db-status-dot db-status-dot--failed" />
            {t('spec_failed')}
          </span>
        );
      default:
        return (
          <span className="db-badge db-badge--nospec">
            <span className="db-status-dot" />
            {t('no_spec')}
          </span>
        );
    }
  };

  return (
    <div className="db-page-root">
      <div className="db-page-bg" />

      <div className="db-page-content">
        {/* Header */}
        <div className="db-header">
          <div className="db-header-left">
            <div className="db-header-icon">
              <DatabaseOutlined style={{ fontSize: 22 }} />
            </div>
            <div>
              <h1 className="db-title">{t('db_management')}</h1>
              <p className="db-subtitle">{t('db_page_subtitle')}</p>
            </div>
          </div>
          <div className="db-header-actions">
            <Button
              className="db-btn-refresh"
              icon={<ReloadOutlined />}
              onClick={refreshDbList}
            />
            <Button
              className="db-btn-primary"
              icon={<PlusOutlined />}
              onClick={() => setAddModalOpen(true)}
            >
              {t('add_database_connection')}
            </Button>
          </div>
        </div>

        {/* Stats Bar */}
        <div className="db-stats-bar">
          <div className="db-stats-group">
            <div className="db-stat">
              <span className="db-stat-value">{stats.total}</span>
              <span className="db-stat-label">{t('db_stat_total')}</span>
            </div>
            <div className="db-stat-divider" />
            <div className="db-stat">
              <span className="db-stat-value db-stat-ready">{stats.withSpec}</span>
              <span className="db-stat-label">{t('db_stat_with_spec')}</span>
            </div>
            <div className="db-stat-divider" />
            <div className="db-stat">
              <span className="db-stat-value db-stat-nospec">{stats.noSpec}</span>
              <span className="db-stat-label">{t('db_stat_no_spec')}</span>
            </div>
          </div>

          <div className="db-toolbar">
            <div className="db-search-wrapper">
              <SearchOutlined className="db-search-icon" />
              <input
                className="db-search-input"
                placeholder={t('search_databases')}
                value={searchValue}
                onChange={(e) => setSearchValue(e.target.value)}
              />
            </div>
            <div className="db-view-toggle">
              <button
                className={`db-view-btn ${viewMode === 'grid' ? 'active' : ''}`}
                onClick={() => setViewMode('grid')}
              >
                <AppstoreOutlined />
              </button>
              <button
                className={`db-view-btn ${viewMode === 'list' ? 'active' : ''}`}
                onClick={() => setViewMode('list')}
              >
                <UnorderedListOutlined />
              </button>
            </div>
          </div>
        </div>

        {/* Content */}
        {dbListLoading ? (
          <div className="db-loading">
            <Spin size="large" />
          </div>
        ) : filteredDbs.length > 0 ? (
          <div className={viewMode === 'grid' ? 'db-grid' : 'db-list-view'}>
            {filteredDbs.map((db) => (
              <div
                key={db.id}
                className={`db-card ${db.specStatus === 'ready' ? 'db-card--ready' : ''} ${viewMode === 'list' ? 'db-card--list' : ''}`}
                onClick={() => handleViewDetail(db)}
              >
                {db.specStatus === 'ready' && <div className="db-card-glow" />}

                <div className="db-card-header">
                  <div className="db-card-identity">
                    <div className={`db-card-avatar ${getAvatarClass(db.db_type)} ${db.specStatus === 'ready' ? 'db-card-avatar--ready' : ''}`}>
                      <span className="db-card-avatar-text">
                        {(db.db_type || db.db_name || 'D').charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div className="db-card-meta">
                      <h3 className="db-card-name">{db.db_name || db.name}</h3>
                      <div className="db-card-badges">
                        <span className="db-badge db-badge--type">{db.db_type || '-'}</span>
                        {getStatusBadge(db.specStatus)}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="db-card-desc">
                  <div className="db-info-list">
                    {db.db_host && (
                      <div className="db-info-item">
                        <span className="db-info-label">{t('host')}</span>
                        <span className="db-info-value">
                          {db.db_host}
                          {db.db_port ? `:${db.db_port}` : ''}
                        </span>
                      </div>
                    )}
                    {db.db_path && (
                      <div className="db-info-item">
                        <span className="db-info-label">Path</span>
                        <span className="db-info-value">{db.db_path}</span>
                      </div>
                    )}
                    {(db.comment || db.description) && (
                      <div className="db-info-item">
                        <span className="db-info-label">{t('description')}</span>
                        <span className="db-info-value">{db.comment || db.description}</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="db-card-footer">
                  <div className="db-card-footer-left">
                    <button
                      className="db-footer-btn db-footer-btn--learn"
                      onClick={(e) => {
                        e.stopPropagation();
                        runLearn(String(db.id));
                      }}
                    >
                      <SyncOutlined />
                      {t('learn_schema')}
                    </button>
                    <button
                      className="db-footer-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleViewDetail(db);
                      }}
                    >
                      <EyeOutlined />
                      {t('view_details')}
                    </button>
                  </div>
                  <button
                    className="db-footer-btn db-footer-btn--danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(db);
                    }}
                  >
                    <DeleteOutlined />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="db-empty">
            <div className="db-empty-icon">
              <DatabaseOutlined style={{ fontSize: 40 }} />
            </div>
            <h3 className="db-empty-title">{t('no_databases')}</h3>
            <p className="db-empty-desc">{t('no_databases_desc')}</p>
          </div>
        )}
      </div>

      {/* Add Database Modal */}
      <DatabaseAddModal
        open={addModalOpen}
        supportTypes={(supportTypes || []) as IChatDbSupportTypeSchema[]}
        onCancel={() => setAddModalOpen(false)}
        onSuccess={handleAddSuccess}
      />

    </div>
  );
}
