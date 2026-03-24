'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Card, List, Space, Switch, Tag, Typography, App } from 'antd';
import { AppstoreOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { configService, type FeaturePluginCatalogItem } from '@/services/config';
import UserGroupsPluginPanel from '@/components/config/UserGroupsPluginPanel';
import { getApiErrorMessage, isHttpStatus } from '@/utils/apiError';

const { Text, Paragraph } = Typography;

/**
 * List `loading` wraps content in Spin; when spinning, Spin's blur overlay uses
 * pointer-events and blocks all clicks (Switch, 新建分组, etc.). Only use full
 * List loading on the first fetch; refreshes after toggle run silently.
 */
export default function FeaturePluginsSection({ onChange }: { onChange?: () => void }) {
  const { t } = useTranslation();
  const { message, notification } = App.useApp();
  const [initialLoading, setInitialLoading] = useState(true);
  const [items, setItems] = useState<FeaturePluginCatalogItem[]>([]);
  const [togglingPluginId, setTogglingPluginId] = useState<string | null>(null);

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      const silent = opts?.silent === true;
      if (!silent) {
        setInitialLoading(true);
      }
      try {
        const data = await configService.getFeaturePluginsCatalog();
        setItems(data);
      } catch (e: unknown) {
        message.error(t('plugin_market_load_error') + ': ' + getApiErrorMessage(e));
      } finally {
        if (!silent) {
          setInitialLoading(false);
        }
      }
    },
    [message, t],
  );

  useEffect(() => {
    load({ silent: false });
  }, [load]);

  const handleToggle = async (pluginId: string, enabled: boolean) => {
    setTogglingPluginId(pluginId);
    try {
      await configService.updateFeaturePlugin({ plugin_id: pluginId, enabled });
      message.success(
        enabled ? t('plugin_market_enabled_restart') : t('plugin_market_disabled_restart'),
      );
      await load({ silent: true });
      onChange?.();
    } catch (e: unknown) {
      const detail = getApiErrorMessage(e);
      message.error({
        content: `${t('plugin_market_save_error')}: ${detail}`,
        duration: 8,
      });
      if (isHttpStatus(e, 403)) {
        notification.warning({
          message: t('plugin_market_forbidden_title'),
          description: t('plugin_market_forbidden_desc'),
          duration: 12,
        });
      }
      await load({ silent: true });
    } finally {
      setTogglingPluginId(null);
    }
  };

  return (
    <div className="space-y-4">
      <Alert
        type="info"
        showIcon
        message={t('plugin_market_alert_title')}
        description={t('plugin_market_alert_desc')}
      />
      <List
        loading={initialLoading}
        dataSource={items}
        locale={{ emptyText: t('plugin_market_empty') }}
        renderItem={(item) => (
          <List.Item key={item.id}>
            <Card size="small" className="w-full" title={<Space><AppstoreOutlined /><span>{item.title}</span></Space>}>
              <Paragraph type="secondary" className="!mb-3">{item.description}</Paragraph>
              <Space wrap>
                <Tag>{item.category}</Tag>
                {item.requires_restart ? <Tag color="blue">需重启</Tag> : null}
                {item.suggest_oauth2_admin ? <Tag color="gold">建议配置 OAuth2 管理员</Tag> : null}
              </Space>
              <div className="mt-4 flex items-center justify-between">
                <Text type="secondary">{t('plugin_market_enable_label')}</Text>
                <Switch
                  checked={item.enabled}
                  loading={togglingPluginId === item.id}
                  onChange={(v) => handleToggle(item.id, v)}
                />
              </div>
              {item.id === 'user_groups' ? (
                <UserGroupsPluginPanel catalogEnabled={item.enabled} />
              ) : null}
            </Card>
          </List.Item>
        )}
      />
    </div>
  );
}
