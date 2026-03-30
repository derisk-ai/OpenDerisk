'use client';

import React from 'react';
import { Card, Button, Typography, Space, App } from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  BellOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import Link from 'next/link';
import { useTranslation } from 'react-i18next';
import RiskSummaryCard from './components/RiskSummary';
import RiskHeatmap from './components/RiskHeatmap';
import EntityList from './components/EntityList';
import {
  mockEntities,
  mockRiskSummary,
  mockHeatmapData,
} from './mock/data';

const { Title } = Typography;

export default function RiskDashboardPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();

  // Mock data loading - replace with API calls later
  const { data: entities, loading: entitiesLoading, refresh: refreshEntities } = useRequest(
    async () => {
      // Simulate API delay
      await new Promise((resolve) => setTimeout(resolve, 500));
      return mockEntities;
    }
  );

  const { data: summary, loading: summaryLoading, refresh: refreshSummary } = useRequest(
    async () => {
      await new Promise((resolve) => setTimeout(resolve, 300));
      return mockRiskSummary;
    }
  );

  const { data: heatmapData, loading: heatmapLoading } = useRequest(
    async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
      return mockHeatmapData;
    }
  );

  const handleRefresh = () => {
    refreshEntities();
    refreshSummary();
    message.success(t('risk_refresh_success'));
  };

  const handleCheck = (entityId: string) => {
    message.info(`${t('risk_check_triggered')}: ${entityId}`);
  };

  const handleSubscribe = (entityId: string) => {
    message.success(`${t('risk_subscribe_success')}: ${entityId}`);
  };

  // Get subscribed entities for "My Subscriptions" section
  const subscribedEntities = entities?.filter((e) => e.subscribed) || [];

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <Title level={3} className="mb-0">
          {t('risk_dashboard_title')}
        </Title>
        <Space>
          <Link href="/risk-dashboard/subscriptions">
            <Button icon={<BellOutlined />}>
              {t('risk_subscription_manage')}
            </Button>
          </Link>
          <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
            {t('Refresh_status')}
          </Button>
        </Space>
      </div>

      {/* Risk Summary */}
      <RiskSummaryCard summary={summary || mockRiskSummary} loading={summaryLoading} />

      {/* Heatmap */}
      <RiskHeatmap data={heatmapData || mockHeatmapData} loading={heatmapLoading} />

      {/* My Subscriptions */}
      <Card
        title={
          <div className="flex items-center justify-between">
            <span>{t('risk_my_subscriptions')}</span>
            <Link href="/risk-dashboard/subscriptions">
              <Button type="link" size="small">
                {t('risk_view_all')}
              </Button>
            </Link>
          </div>
        }
        className="mb-6"
      >
        <EntityList
          entities={subscribedEntities}
          loading={entitiesLoading}
          onCheck={handleCheck}
          onSubscribe={handleSubscribe}
        />
      </Card>

      {/* All Entities */}
      <Card
        title={
          <div className="flex items-center justify-between">
            <span>{t('risk_all_entities')}</span>
            <Link href="/risk-dashboard/entities">
              <Button type="primary" icon={<PlusOutlined />}>
                {t('risk_add_entity')}
              </Button>
            </Link>
          </div>
        }
      >
        <EntityList
          entities={entities || mockEntities}
          loading={entitiesLoading}
          onCheck={handleCheck}
          onSubscribe={handleSubscribe}
        />
      </Card>
    </div>
  );
}