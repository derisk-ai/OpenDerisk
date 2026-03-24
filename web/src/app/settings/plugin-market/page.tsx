'use client';

import React from 'react';
import { Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import FeaturePluginsSection from '@/components/config/FeaturePluginsSection';

const { Title, Text } = Typography;

export default function PluginMarketPage() {
  const { t } = useTranslation();

  return (
    <div className="p-6 h-full overflow-auto">
      <Title level={3}>{t('plugin_market')}</Title>
      <Text type="secondary">{t('plugin_market_page_desc')}</Text>
      <div className="mt-4">
        <FeaturePluginsSection />
      </div>
    </div>
  );
}
