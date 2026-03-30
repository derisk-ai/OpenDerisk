'use client';

import React, { useState, useMemo } from 'react';
import {
  Card,
  Button,
  Space,
  Tag,
  Typography,
  Empty,
  Modal,
  Form,
  Select,
  Switch,
  Input,
  Popconfirm,
  message,
  Divider,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  StopOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import moment from 'moment';
import {
  EntitySkillConfig as EntitySkillConfigType,
  Skill,
  mockSkills,
  riskLevelMap,
  RiskLevel,
} from '../mock/data';

const { Text, Paragraph } = Typography;

interface EntitySkillConfigProps {
  entityId: string;
  entityTypeId?: string;
  skills?: EntitySkillConfigType[];
  onRefresh?: () => void;
}

// Mock skills data for the entity (would come from API in real implementation)
const getEntitySkills = (entityId: string): EntitySkillConfigType[] => {
  const { mockEntitySkillConfigs } = require('../mock/data');
  return mockEntitySkillConfigs.filter((s: EntitySkillConfigType) => s.entityId === entityId);
};

// Get available skills to add (not already configured)
const getAvailableSkills = (existingCodes: string[]): Skill[] => {
  return mockSkills.filter((s) => !existingCodes.includes(s.skill_code));
};

export default function EntitySkillConfigPanel({
  entityId,
  entityTypeId,
  skills: propSkills,
  onRefresh,
}: EntitySkillConfigProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const [skills, setSkills] = useState<EntitySkillConfigType[]>(
    propSkills || getEntitySkills(entityId)
  );
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<EntitySkillConfigType | null>(null);

  const existingCodes = useMemo(() => skills.map((s) => s.skillCode), [skills]);
  const availableSkills = useMemo(() => getAvailableSkills(existingCodes), [existingCodes]);

  const getRiskLevelTag = (level?: RiskLevel) => {
    if (!level) return <Tag>-</Tag>;
    const info = riskLevelMap[level];
    return (
      <Tag color={info.color} style={{ borderRadius: 4 }}>
        {info.icon} {info.text}
      </Tag>
    );
  };

  const handleToggle = (skillId: string, currentEnabled: boolean) => {
    setSkills((prev) =>
      prev.map((s) => (s.id === skillId ? { ...s, enabled: !currentEnabled } : s))
    );
    message.success(currentEnabled ? t('risk_skill_disabled') : t('risk_skill_enabled'));
  };

  const handleDelete = (skillId: string, skillType: string) => {
    if (skillType === 'default') {
      message.warning(t('risk_skill_cannot_delete_default'));
      return;
    }
    setSkills((prev) => prev.filter((s) => s.id !== skillId));
    message.success(t('risk_skill_deleted'));
  };

  const handleAdd = async (values: any) => {
    const selectedSkill = mockSkills.find((s) => s.skill_code === values.skillCode);
    if (!selectedSkill) return;

    const newSkill: EntitySkillConfigType = {
      id: `es-${Date.now()}`,
      entityId,
      skillCode: selectedSkill.skill_code,
      skillName: selectedSkill.name,
      skillType: 'custom',
      enabled: true,
      checkParams: values.checkParams,
    };

    setSkills((prev) => [...prev, newSkill]);
    setAddModalOpen(false);
    form.resetFields();
    message.success(t('risk_skill_added'));
  };

  const handleEdit = async (values: any) => {
    if (!editingSkill) return;

    setSkills((prev) =>
      prev.map((s) =>
        s.id === editingSkill.id
          ? { ...s, checkParams: values.checkParams }
          : s
      )
    );
    setEditModalOpen(false);
    setEditingSkill(null);
    editForm.resetFields();
    message.success(t('risk_skill_updated'));
  };

  const openEditModal = (skill: EntitySkillConfigType) => {
    setEditingSkill(skill);
    editForm.setFieldsValue({
      checkParams: skill.checkParams || {},
    });
    setEditModalOpen(true);
  };

  const renderSkillCard = (skill: EntitySkillConfigType) => {
    const isDefault = skill.skillType === 'default';
    const skillInfo = mockSkills.find((s) => s.skill_code === skill.skillCode);

    return (
      <Card
        key={skill.id}
        className={`mb-3 ${!skill.enabled ? 'bg-gray-50' : ''}`}
        size="small"
        styles={{
          body: { padding: '12px 16px' },
        }}
      >
        <div className="flex justify-between items-start">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <Text strong>{skill.skillName}</Text>
              <Tag color={isDefault ? 'blue' : 'green'}>
                {isDefault ? t('risk_skill_type_default') : t('risk_skill_type_custom')}
              </Tag>
              {skill.enabled ? (
                <Tag color="success" icon={<CheckCircleOutlined />}>
                  {t('risk_skill_enabled')}
                </Tag>
              ) : (
                <Tag color="default" icon={<StopOutlined />}>
                  {t('risk_skill_disabled')}
                </Tag>
              )}
            </div>
            <Text type="secondary" className="text-xs">
              {skillInfo?.description || '-'}
            </Text>

            {skill.checkParams && Object.keys(skill.checkParams).length > 0 && (
              <div className="mt-2 text-xs text-gray-500">
                {t('risk_skill_params')}: {JSON.stringify(skill.checkParams)}
              </div>
            )}

            <div className="mt-2 flex items-center gap-4 text-xs text-gray-400">
              <span>
                {t('risk_last_check')}: {skill.lastCheckAt
                  ? moment(skill.lastCheckAt).format('YYYY-MM-DD HH:mm')
                  : '-'}
              </span>
              <span className="flex items-center gap-1">
                {t('risk_level')}: {getRiskLevelTag(skill.lastRiskLevel)}
              </span>
            </div>
          </div>

          <Space size="small">
            {!isDefault && (
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => openEditModal(skill)}
              >
                {t('Edit')}
              </Button>
            )}
            <Button
              type="text"
              size="small"
              onClick={() => handleToggle(skill.id, skill.enabled)}
            >
              {skill.enabled ? t('risk_skill_disable') : t('risk_skill_enable')}
            </Button>
            {!isDefault && (
              <Popconfirm
                title={t('risk_skill_delete_confirm')}
                onConfirm={() => handleDelete(skill.id, skill.skillType)}
                okText={t('Yes')}
                cancelText={t('No')}
              >
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                >
                  {t('Delete')}
                </Button>
              </Popconfirm>
            )}
          </Space>
        </div>
      </Card>
    );
  };

  return (
    <div>
      <Card
        title={
          <div className="flex justify-between items-center">
            <span>{t('risk_entity_skills')}</span>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setAddModalOpen(true)}
              disabled={availableSkills.length === 0}
            >
              {t('risk_add_skill')}
            </Button>
          </div>
        }
      >
        {skills.length === 0 ? (
          <Empty
            description={t('risk_no_skills')}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <div>
            {/* Default skills first */}
            {skills.filter((s) => s.skillType === 'default').map(renderSkillCard)}
            {skills.some((s) => s.skillType === 'default') &&
              skills.some((s) => s.skillType === 'custom') && (
                <Divider style={{ margin: '12px 0' }} />
              )}
            {/* Custom skills */}
            {skills.filter((s) => s.skillType === 'custom').map(renderSkillCard)}
          </div>
        )}
      </Card>

      {/* Add Skill Modal */}
      <Modal
        title={t('risk_add_skill')}
        open={addModalOpen}
        onCancel={() => {
          setAddModalOpen(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        okText={t('Add')}
        cancelText={t('cancel')}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Form.Item
            name="skillCode"
            label={t('risk_select_skill')}
            rules={[{ required: true, message: t('risk_select_skill_placeholder') }]}
          >
            <Select
              placeholder={t('risk_select_skill_placeholder')}
              showSearch
              optionFilterProp="label"
              options={availableSkills.map((s) => ({
                label: `${s.name} - ${s.description}`,
                value: s.skill_code,
              }))}
            />
          </Form.Item>
          <Form.Item name="checkParams" label={t('risk_skill_params')}>
            <Input.TextArea
              rows={3}
              placeholder='{"key": "value"}'
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Skill Modal */}
      <Modal
        title={t('risk_edit_skill')}
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingSkill(null);
          editForm.resetFields();
        }}
        onOk={() => editForm.submit()}
        okText={t('Save')}
        cancelText={t('cancel')}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Form.Item label={t('risk_skill_name')}>
            <Text>{editingSkill?.skillName}</Text>
          </Form.Item>
          <Form.Item name="checkParams" label={t('risk_skill_params')}>
            <Input.TextArea
              rows={3}
              placeholder='{"key": "value"}'
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}