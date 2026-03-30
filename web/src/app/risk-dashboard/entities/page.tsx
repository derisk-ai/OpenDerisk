'use client';

import React, { useState, useMemo } from 'react';
import { Card, Button, Typography, Space, Select, App, Modal, Form, Input, Tabs, Descriptions, Tag, Empty } from 'antd';
import {
  PlusOutlined,
  ReloadOutlined,
  ArrowLeftOutlined,
  PlayCircleOutlined,
  BellOutlined,
  BellFilled,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import moment from 'moment';
import EntityList from '../components/EntityList';
import CheckHistory from '../components/CheckHistory';
import EntitySkillConfigPanel from '../components/EntitySkillConfig';
import { mockEntities, mockEntityTypes, mockCheckHistory, mockEntityRelations, mockEntitySkillConfigs, riskLevelMap } from '../mock/data';

const { Title, Text } = Typography;

export default function EntitiesPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  const [riskFilter, setRiskFilter] = useState<string | undefined>(undefined);

  const entityId = searchParams.get('id');
  const isDetailView = !!entityId;

  // Mock data loading for entity list
  const {
    data: entities,
    loading,
    refresh,
  } = useRequest(async () => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    let filtered = [...mockEntities];

    if (typeFilter) {
      filtered = filtered.filter((e) => e.typeId === typeFilter);
    }
    if (riskFilter) {
      filtered = filtered.filter((e) => e.riskLevel === riskFilter);
    }

    return filtered;
  }, {
    refreshDeps: [typeFilter, riskFilter],
  });

  // Mock data loading for single entity
  const { data: entity, loading: entityLoading } = useRequest(async () => {
    if (!entityId) return null;
    await new Promise((resolve) => setTimeout(resolve, 300));
    return mockEntities.find((e) => e.id === entityId);
  }, {
    ready: !!entityId,
    refreshDeps: [entityId],
  });

  const { data: entityType } = useRequest(async () => {
    if (!entity?.typeId) return null;
    return mockEntityTypes.find((t) => t.id === entity.typeId);
  }, {
    ready: !!entity?.typeId,
  });

  const { data: relations, loading: relationsLoading } = useRequest(async () => {
    if (!entityId) return [];
    await new Promise((resolve) => setTimeout(resolve, 200));
    return mockEntityRelations.filter(
      (r) => r.sourceEntityId === entityId || r.targetEntityId === entityId
    );
  }, {
    ready: !!entityId,
  });

  const { data: checkHistory, loading: historyLoading } = useRequest(async () => {
    if (!entityId) return [];
    await new Promise((resolve) => setTimeout(resolve, 300));
    return mockCheckHistory;
  }, {
    ready: !!entityId,
  });

  const { data: entitySkills, loading: skillsLoading } = useRequest(async () => {
    if (!entityId) return [];
    await new Promise((resolve) => setTimeout(resolve, 200));
    return mockEntitySkillConfigs.filter((s) => s.entityId === entityId);
  }, {
    ready: !!entityId,
  });

  const handleCheck = (id: string) => {
    message.info(`${t('risk_check_triggered')}: ${id}`);
  };

  const handleSubscribe = (id: string) => {
    message.success(`${t('risk_subscribe_success')}: ${id}`);
  };

  const handleDelete = (id: string) => {
    message.success(`${t('risk_delete_success')}: ${id}`);
    refresh();
  };

  const handleCreate = async (values: any) => {
    message.success(t('risk_entity_created'));
    setCreateModalOpen(false);
    form.resetFields();
    refresh();
  };

  const getRelationTypeName = (type: string) => {
    const map: Record<string, string> = {
      depends_on: t('risk_relation_depends_on'),
      contains: t('risk_relation_contains'),
      impacts: t('risk_relation_impacts'),
    };
    return map[type] || type;
  };

  // Detail view
  if (isDetailView) {
    if (!entity && !entityLoading) {
      return (
        <div className="p-6">
          <Card>
            <Empty description={t('risk_entity_not_found')} />
            <div className="text-center mt-4">
              <Link href="/risk-dashboard/entities">
                <Button type="primary">{t('risk_back_to_list')}</Button>
              </Link>
            </div>
          </Card>
        </div>
      );
    }

    const riskLevelInfo = entity?.riskLevel ? riskLevelMap[entity.riskLevel] : null;

    const tabItems = [
      {
        key: 'history',
        label: t('risk_check_history'),
        children: (
          <CheckHistory records={checkHistory || []} loading={historyLoading} mode="timeline" />
        ),
      },
      {
        key: 'relations',
        label: t('risk_entity_relations'),
        children: (
          <Card loading={relationsLoading}>
            {relations && relations.length > 0 ? (
              <Descriptions column={1} bordered size="small">
                {relations.map((relation) => {
                  const isSource = relation.sourceEntityId === entityId;
                  const relatedEntityName = isSource
                    ? relation.targetEntityName
                    : relation.sourceEntityName;
                  const relatedEntityId = isSource
                    ? relation.targetEntityId
                    : relation.sourceEntityId;

                  return (
                    <Descriptions.Item
                      key={relation.id}
                      label={
                        <Space>
                          {isSource ? (
                            <span className="text-gray-400">→</span>
                          ) : (
                            <span className="text-gray-400">←</span>
                          )}
                          <span>{getRelationTypeName(relation.relationType)}</span>
                          <Tag color={relation.strength === 'strong' ? 'red' : 'default'}>
                            {relation.strength === 'strong' ? t('risk_strong') : t('risk_weak')}
                          </Tag>
                        </Space>
                      }
                    >
                      <Link
                        href={`/risk-dashboard/entities?id=${relatedEntityId}`}
                        className="text-blue-500 hover:text-blue-700"
                      >
                        {relatedEntityName}
                      </Link>
                    </Descriptions.Item>
                  );
                })}
              </Descriptions>
            ) : (
              <Empty
                description={t('risk_no_relations')}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            )}
          </Card>
        ),
      },
      {
        key: 'skills',
        label: t('risk_entity_skills'),
        children: (
          <EntitySkillConfigPanel
            entityId={entityId}
            entityTypeId={entity?.typeId}
            skills={entitySkills || []}
          />
        ),
      },
      {
        key: 'config',
        label: t('risk_entity_config'),
        children: (
          <Card>
            <pre className="bg-gray-50 dark:bg-gray-800 p-4 rounded text-sm overflow-auto">
              {JSON.stringify(entity?.config || {}, null, 2)}
            </pre>
          </Card>
        ),
      },
    ];

    return (
      <div className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <Link href="/risk-dashboard/entities">
              <Button icon={<ArrowLeftOutlined />}>{t('Back')}</Button>
            </Link>
            <Title level={3} className="mb-0">
              {entity?.name || t('risk_entity_detail')}
            </Title>
            {riskLevelInfo && (
              <Tag color={riskLevelInfo.color} className="text-base px-3 py-1">
                {riskLevelInfo.icon} {riskLevelInfo.text}
              </Tag>
            )}
          </div>
          <Space>
            <Button
              icon={entity?.subscribed ? <BellFilled style={{ color: '#1890ff' }} /> : <BellOutlined />}
              onClick={() => handleSubscribe(entityId)}
            >
              {entity?.subscribed ? t('risk_unsubscribe') : t('risk_subscribe')}
            </Button>
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => handleCheck(entityId)}>
              {t('risk_check_now')}
            </Button>
          </Space>
        </div>

        {/* Basic Info */}
        <Card className="mb-6" loading={entityLoading}>
          <Descriptions column={4} bordered size="small">
            <Descriptions.Item label={t('risk_entity_name')}>
              {entity?.name}
            </Descriptions.Item>
            <Descriptions.Item label={t('risk_entity_type')}>
              <Tag>{entity?.typeName || entityType?.name}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('risk_level')}>
              {riskLevelInfo && (
                <Tag color={riskLevelInfo.color}>
                  {riskLevelInfo.icon} {riskLevelInfo.text}
                </Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('risk_last_check')}>
              {entity?.lastCheckAt
                ? moment(entity.lastCheckAt).format('YYYY-MM-DD HH:mm:ss')
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('creation_time')} span={2}>
              {entity?.createdAt
                ? moment(entity.createdAt).format('YYYY-MM-DD HH:mm:ss')
                : '-'}
            </Descriptions.Item>
            <Descriptions.Item label={t('risk_entity_source')} span={2}>
              {entity?.source || 'manual'}
            </Descriptions.Item>
            {entity?.summary && (
              <Descriptions.Item label={t('risk_summary')} span={4}>
                {entity.summary}
              </Descriptions.Item>
            )}
          </Descriptions>
        </Card>

        {/* Tabs */}
        <Tabs items={tabItems} />
      </div>
    );
  }

  // List view
  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link href="/risk-dashboard">
            <Button type="text">{t('Back')}</Button>
          </Link>
          <Title level={3} className="mb-0">
            {t('risk_entities_title')}
          </Title>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => refresh()}>
            {t('Refresh_status')}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            {t('risk_add_entity')}
          </Button>
        </Space>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <Space size="large">
          <div className="flex items-center gap-2">
            <span className="text-gray-500">{t('risk_entity_type')}:</span>
            <Select
              allowClear
              placeholder={t('risk_all_types')}
              style={{ width: 150 }}
              value={typeFilter}
              onChange={setTypeFilter}
              options={mockEntityTypes.map((t) => ({ label: t.name, value: t.id }))}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-gray-500">{t('risk_level')}:</span>
            <Select
              allowClear
              placeholder={t('risk_all_levels')}
              style={{ width: 120 }}
              value={riskFilter}
              onChange={setRiskFilter}
              options={[
                { label: t('risk_level_green'), value: 'green' },
                { label: t('risk_level_blue'), value: 'blue' },
                { label: t('risk_level_yellow'), value: 'yellow' },
                { label: t('risk_level_red'), value: 'red' },
              ]}
            />
          </div>
        </Space>
      </Card>

      {/* Entity List */}
      <EntityList
        entities={entities || []}
        loading={loading}
        onCheck={handleCheck}
        onSubscribe={handleSubscribe}
        onDelete={handleDelete}
      />

      {/* Create Modal */}
      <Modal
        title={t('risk_add_entity')}
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="typeId"
            label={t('risk_entity_type')}
            rules={[{ required: true, message: t('risk_select_type') }]}
          >
            <Select
              placeholder={t('risk_select_type')}
              options={mockEntityTypes.map((t) => ({ label: t.name, value: t.id }))}
            />
          </Form.Item>
          <Form.Item
            name="name"
            label={t('risk_entity_name')}
            rules={[{ required: true, message: t('Please_Input') }]}
          >
            <Input placeholder={t('Please_Input')} />
          </Form.Item>
          <Form.Item name="config" label={t('risk_entity_config')}>
            <Input.TextArea
              rows={4}
              placeholder='{"key": "value"}'
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}