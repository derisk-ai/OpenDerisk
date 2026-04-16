'use client';

import React, { useEffect, useState } from 'react';
import { Select, Space, Tag, Typography, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { ins as axios } from '@/client/api';

const { Text } = Typography;

export interface ResourceOption {
  value: string;
  label: string;
  type: string;
  disabled?: boolean;
}

export interface ResourceSelectorProps {
  resourceType: string;
  selectedResourceIds: string[];
  onChange: (resourceIds: string[]) => void;
  allowWildcard?: boolean;
}

/**
 * Resource Selector Component (T2.1)
 *
 * Displays a list of resources for the given resource type with:
 * - Search functionality
 * - Multi-select support
 * - "All resources" wildcard option
 */
export default function ResourceSelector({
  resourceType,
  selectedResourceIds,
  onChange,
  allowWildcard = true,
}: ResourceSelectorProps) {
  const { t } = useTranslation();
  const [options, setOptions] = useState<ResourceOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const newOptions: ResourceOption[] = [];

    // Add wildcard option
    if (allowWildcard) {
      newOptions.push({
        value: '*',
        label: t('permissions_all_resources'),
        type: 'wildcard',
      });
    }

    // Load resources based on type
    const loadResources = async () => {
      try {
        let resources: Array<{ name?: string; displayName?: string; id?: string | number }> = [];

        switch (resourceType) {
          case 'agent':
            {
              const res = await axios.get('/api/v1/config/agents');
              resources = res.data?.data?.list || res.data?.data || [];
            }
            break;
          case 'tool':
            {
              const res = await axios.get('/api/v1/tools/list');
              resources = res.data?.data?.list || res.data?.data || [];
            }
            break;
          case 'knowledge':
            {
              const res = await axios.get('/api/v1/knowledge/space/list');
              resources = res.data?.data?.list || res.data?.data || [];
            }
            break;
          case 'model':
            {
              const res = await axios.get('/api/v1/serve/model/models');
              resources = res.data?.data?.list || res.data?.data || [];
            }
            break;
          default:
            break;
        }

        resources.forEach((item) => {
          const label =
            'displayName' in item
              ? item.displayName
              : 'name' in item
                ? item.name
                : String(item.id || '');
          const value = 'name' in item ? item.name : String(item.id || '');

          newOptions.push({
            value: value || '',
            label: label || value || '',
            type: resourceType,
          });
        });
      } catch (error) {
        console.error(`Failed to load ${resourceType} resources:`, error);
      } finally {
        setLoading(false);
      }
    };

    loadResources();
  }, [resourceType, t, allowWildcard]);

  const handleChange = (values: string[]) => {
    // If wildcard is selected, clear other selections
    if (values.includes('*')) {
      onChange(['*']);
    } else {
      // Remove wildcard if present when selecting specific resources
      onChange(values.filter((v) => v !== '*'));
    }
  };

  const renderTag = (value: string) => {
    if (value === '*') {
      return (
        <Tag color="red" className="mr-1">
          {t('permissions_all_resources')}
        </Tag>
      );
    }

    const colorMap: Record<string, string> = {
      agent: 'blue',
      tool: 'green',
      knowledge: 'orange',
      model: 'purple',
      wildcard: 'red',
    };

    return (
      <Tag color={colorMap[resourceType] || 'default'} className="mr-1">
        {value}
      </Tag>
    );
  };

  return (
    <div className="resource-selector">
      <div className="mb-2">
        <Space>
          <Text strong>{t('permissions_resource_scope')}:</Text>
          {allowWildcard && (
            <Text type="secondary" className="text-xs">
              {t('permissions_scoped_permission_hint')}
            </Text>
          )}
        </Space>
      </div>
      {loading ? (
        <Spin size="small" />
      ) : (
        <Select
          mode="multiple"
          value={selectedResourceIds}
          onChange={handleChange}
          options={options.map((opt) => ({
            value: opt.value,
            label: opt.label,
            disabled: opt.disabled,
          }))}
          placeholder={t('permissions_select_resource')}
          loading={loading}
          tagRender={({ value }) => renderTag(String(value))}
          className="w-full"
          maxTagCount="responsive"
          allowClear
        />
      )}
    </div>
  );
}