'use client';

import { apiInterceptors, getDbList } from '@/client/api';
import { IChatDbSchema } from '@/types/db';
import { ArrowLeftOutlined, DatabaseOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Button, Spin } from 'antd';
import { useSearchParams, useRouter } from 'next/navigation';
import React from 'react';
import { useTranslation } from 'react-i18next';
import DatabaseDetail from '../components/DatabaseDetail';
import '../db-page.css';

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

export default function DatabaseDetailPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const id = searchParams.get('id') || '';

  // Fetch datasource info by id
  const {
    data: datasource,
    loading,
    refresh,
  } = useRequest(async () => {
    if (!id) return null;
    const [err, res] = await apiInterceptors(getDbList());
    if (err || !res) return null;
    const list = (res as any[]).map(normalizeDatasource) as IChatDbSchema[];
    return list.find((d) => String(d.id) === id) || null;
  });

  if (loading) {
    return (
      <div className="db-page-root">
        <div className="db-page-content">
          <div className="db-loading">
            <Spin size="large" />
          </div>
        </div>
      </div>
    );
  }

  if (!datasource) {
    return (
      <div className="db-page-root">
        <div className="db-page-content">
          <div className="db-empty">
            <h3 className="db-empty-title">Database not found</h3>
            <Button
              type="link"
              icon={<ArrowLeftOutlined />}
              onClick={() => router.push('/database')}
            >
              {t('back') || 'Back'}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="db-page-root">
      <div className="db-page-bg" />
      <div className="db-page-content">
        {/* Header with back button */}
        <div className="db-header" style={{ marginBottom: 16 }}>
          <div className="db-header-left">
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={() => router.push('/database')}
              style={{ marginRight: 8 }}
            />
            <div className="db-header-icon">
              <DatabaseOutlined style={{ fontSize: 22 }} />
            </div>
            <div>
              <h1 className="db-title">{datasource.db_name || datasource.name}</h1>
              <p className="db-subtitle">
                {datasource.db_type}
                {datasource.db_host ? ` · ${datasource.db_host}` : ''}
                {datasource.db_port ? `:${datasource.db_port}` : ''}
              </p>
            </div>
          </div>
        </div>

        {/* Full-width DatabaseDetail */}
        <DatabaseDetail datasource={datasource} onRefresh={refresh} />
      </div>
    </div>
  );
}
