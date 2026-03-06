/**
 * ToolManagementPanel - Tool Management Panel
 *
 * Provides UI for viewing and managing tools:
 * - Tool list with search and filtering
 * - Tool details view (parameters, authorization requirements)
 * - Tool enable/disable toggle
 * - Tool category filtering
 * - Risk level indicators
 */

'use client';

import React, { useState, useCallback, useMemo } from 'react';
import {
  Card,
  Table,
  Input,
  Select,
  Tag,
  Space,
  Button,
  Tooltip,
  Typography,
  Modal,
  Descriptions,
  Badge,
  Switch,
  Empty,
  Collapse,
  Row,
  Col,
  Tabs,
} from 'antd';
import {
  SearchOutlined,
  FilterOutlined,
  InfoCircleOutlined,
  ToolOutlined,
  SafetyOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CodeOutlined,
  ApiOutlined,
  FileOutlined,
  GlobalOutlined,
  DatabaseOutlined,
  ThunderboltOutlined,
  TeamOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { ToolMetadata, ToolCategory, RiskLevel, ToolParameter } from '@/types/tool';
import {
  ToolCategory as ToolCategoryEnum,
  RiskLevel as RiskLevelEnum,
} from '@/types/tool';

const { Text, Title, Paragraph } = Typography;
const { Option } = Select;
const { Panel } = Collapse;
const { TabPane } = Tabs;

// ========== Types ==========

export interface ToolManagementPanelProps {
  /** List of tools to display */
  tools: ToolMetadata[];
  /** Enabled tools (by name) */
  enabledTools?: string[];
  /** Callback when tool enabled state changes */
  onToolToggle?: (toolName: string, enabled: boolean) => void;
  /** Callback when tool is selected */
  onToolSelect?: (tool: ToolMetadata) => void;
  /** Whether to allow enabling/disabling tools */
  allowToggle?: boolean;
  /** Show detailed view in a modal */
  showDetailModal?: boolean;
  /** Loading state */
  loading?: boolean;
}

// ========== Helper Functions ==========

/**
 * Get icon for tool category.
 */
function getCategoryIcon(category: ToolCategory): React.ReactNode {
  switch (category) {
    case ToolCategoryEnum.FILE_SYSTEM:
      return <FileOutlined />;
    case ToolCategoryEnum.SHELL:
      return <ThunderboltOutlined />;
    case ToolCategoryEnum.NETWORK:
      return <GlobalOutlined />;
    case ToolCategoryEnum.CODE:
      return <CodeOutlined />;
    case ToolCategoryEnum.DATA:
      return <DatabaseOutlined />;
    case ToolCategoryEnum.AGENT:
      return <TeamOutlined />;
    case ToolCategoryEnum.INTERACTION:
      return <ApiOutlined />;
    case ToolCategoryEnum.EXTERNAL:
      return <ApiOutlined />;
    case ToolCategoryEnum.CUSTOM:
      return <SettingOutlined />;
    default:
      return <ToolOutlined />;
  }
}

/**
 * Get color for tool category.
 */
function getCategoryColor(category: ToolCategory): string {
  switch (category) {
    case ToolCategoryEnum.FILE_SYSTEM:
      return 'blue';
    case ToolCategoryEnum.SHELL:
      return 'orange';
    case ToolCategoryEnum.NETWORK:
      return 'cyan';
    case ToolCategoryEnum.CODE:
      return 'purple';
    case ToolCategoryEnum.DATA:
      return 'green';
    case ToolCategoryEnum.AGENT:
      return 'magenta';
    case ToolCategoryEnum.INTERACTION:
      return 'gold';
    case ToolCategoryEnum.EXTERNAL:
      return 'lime';
    case ToolCategoryEnum.CUSTOM:
      return 'default';
    default:
      return 'default';
  }
}

/**
 * Get color for risk level.
 */
function getRiskLevelColor(riskLevel: RiskLevel): string {
  switch (riskLevel) {
    case RiskLevelEnum.SAFE:
      return 'success';
    case RiskLevelEnum.LOW:
      return 'blue';
    case RiskLevelEnum.MEDIUM:
      return 'warning';
    case RiskLevelEnum.HIGH:
      return 'orange';
    case RiskLevelEnum.CRITICAL:
      return 'error';
    default:
      return 'default';
  }
}

/**
 * Get badge status for risk level.
 */
function getRiskLevelStatus(riskLevel: RiskLevel): 'success' | 'processing' | 'warning' | 'error' | 'default' {
  switch (riskLevel) {
    case RiskLevelEnum.SAFE:
      return 'success';
    case RiskLevelEnum.LOW:
      return 'processing';
    case RiskLevelEnum.MEDIUM:
      return 'warning';
    case RiskLevelEnum.HIGH:
    case RiskLevelEnum.CRITICAL:
      return 'error';
    default:
      return 'default';
  }
}

/**
 * Format category label.
 */
function formatCategory(category: string): string {
  return category
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

// ========== Sub-Components ==========

/**
 * Tool Detail Modal
 */
function ToolDetailModal({
  tool,
  open,
  onClose,
}: {
  tool: ToolMetadata | null;
  open: boolean;
  onClose: () => void;
}) {
  if (!tool) return null;

  const { authorization } = tool;

  return (
    <Modal
      title={
        <Space>
          <ToolOutlined />
          <span>{tool.name}</span>
          <Tag color={getCategoryColor(tool.category)}>
            {formatCategory(tool.category)}
          </Tag>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={<Button onClick={onClose}>Close</Button>}
      width={700}
    >
      <Tabs defaultActiveKey="overview">
        <TabPane tab="Overview" key="overview">
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="Name" span={1}>
              <Text strong>{tool.name}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Version" span={1}>
              {tool.version}
            </Descriptions.Item>
            <Descriptions.Item label="Description" span={2}>
              {tool.description}
            </Descriptions.Item>
            <Descriptions.Item label="Category" span={1}>
              <Tag color={getCategoryColor(tool.category)} icon={getCategoryIcon(tool.category)}>
                {formatCategory(tool.category)}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Source" span={1}>
              <Tag>{tool.source}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Author" span={1}>
              {tool.author ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="Timeout" span={1}>
              {tool.timeout}s
            </Descriptions.Item>
          </Descriptions>

          {tool.tags.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text strong>Tags:</Text>
              <div style={{ marginTop: 8 }}>
                {tool.tags.map(tag => (
                  <Tag key={tag}>{tag}</Tag>
                ))}
              </div>
            </div>
          )}
        </TabPane>

        <TabPane tab="Parameters" key="parameters">
          {tool.parameters.length === 0 ? (
            <Empty description="No parameters" />
          ) : (
            <Table
              dataSource={tool.parameters.map(p => ({ ...p, key: p.name }))}
              columns={[
                {
                  title: 'Name',
                  dataIndex: 'name',
                  key: 'name',
                  render: (name: string, record: ToolParameter) => (
                    <Space>
                      <Text code>{name}</Text>
                      {record.required && <Tag color="error">Required</Tag>}
                      {record.sensitive && <Tag color="warning">Sensitive</Tag>}
                    </Space>
                  ),
                },
                {
                  title: 'Type',
                  dataIndex: 'type',
                  key: 'type',
                  render: (type: string) => <Tag>{type}</Tag>,
                },
                {
                  title: 'Description',
                  dataIndex: 'description',
                  key: 'description',
                  ellipsis: true,
                },
              ]}
              size="small"
              pagination={false}
            />
          )}
        </TabPane>

        <TabPane tab="Authorization" key="authorization">
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="Requires Authorization" span={1}>
              {authorization.requires_authorization ? (
                <Tag color="warning" icon={<SafetyOutlined />}>Yes</Tag>
              ) : (
                <Tag color="success" icon={<CheckCircleOutlined />}>No</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="Risk Level" span={1}>
              <Tag color={getRiskLevelColor(authorization.risk_level)}>
                {authorization.risk_level.toUpperCase()}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Session Grant" span={1}>
              {authorization.support_session_grant ? (
                <Tag color="success">Supported</Tag>
              ) : (
                <Tag color="default">Not Supported</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="Grant TTL" span={1}>
              {authorization.grant_ttl ? `${authorization.grant_ttl}s` : 'Permanent'}
            </Descriptions.Item>
          </Descriptions>

          {authorization.risk_categories.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text strong>Risk Categories:</Text>
              <div style={{ marginTop: 8 }}>
                {authorization.risk_categories.map(cat => (
                  <Tag key={cat} color="orange">{formatCategory(cat)}</Tag>
                ))}
              </div>
            </div>
          )}

          {authorization.sensitive_parameters.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <Text strong>Sensitive Parameters:</Text>
              <div style={{ marginTop: 8 }}>
                {authorization.sensitive_parameters.map(param => (
                  <Tag key={param} color="red">{param}</Tag>
                ))}
              </div>
            </div>
          )}

          {authorization.authorization_prompt && (
            <div style={{ marginTop: 16 }}>
              <Text strong>Custom Authorization Prompt:</Text>
              <Paragraph
                style={{
                  marginTop: 8,
                  padding: 12,
                  backgroundColor: '#f5f5f5',
                  borderRadius: 4,
                }}
              >
                {authorization.authorization_prompt}
              </Paragraph>
            </div>
          )}
        </TabPane>

        {tool.examples.length > 0 && (
          <TabPane tab="Examples" key="examples">
            <Collapse>
              {tool.examples.map((example, index) => (
                <Panel header={`Example ${index + 1}`} key={index}>
                  <pre style={{ margin: 0, overflow: 'auto' }}>
                    {JSON.stringify(example, null, 2)}
                  </pre>
                </Panel>
              ))}
            </Collapse>
          </TabPane>
        )}
      </Tabs>
    </Modal>
  );
}

// ========== Main Component ==========

export function ToolManagementPanel({
  tools,
  enabledTools = [],
  onToolToggle,
  onToolSelect,
  allowToggle = true,
  showDetailModal = true,
  loading = false,
}: ToolManagementPanelProps) {
  // State
  const [searchText, setSearchText] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<ToolCategory | 'all'>('all');
  const [riskFilter, setRiskFilter] = useState<RiskLevel | 'all'>('all');
  const [selectedTool, setSelectedTool] = useState<ToolMetadata | null>(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);

  // Filtered tools
  const filteredTools = useMemo(() => {
    return tools.filter(tool => {
      // Search filter
      if (searchText) {
        const search = searchText.toLowerCase();
        const matchName = tool.name.toLowerCase().includes(search);
        const matchDesc = tool.description.toLowerCase().includes(search);
        const matchTags = tool.tags.some(t => t.toLowerCase().includes(search));
        if (!matchName && !matchDesc && !matchTags) return false;
      }

      // Category filter
      if (categoryFilter !== 'all' && tool.category !== categoryFilter) {
        return false;
      }

      // Risk filter
      if (riskFilter !== 'all' && tool.authorization.risk_level !== riskFilter) {
        return false;
      }

      return true;
    });
  }, [tools, searchText, categoryFilter, riskFilter]);

  // Available categories from tools
  const availableCategories = useMemo(() => {
    const categories = new Set(tools.map(t => t.category));
    return Array.from(categories);
  }, [tools]);

  // Handlers
  const handleViewDetails = useCallback((tool: ToolMetadata) => {
    setSelectedTool(tool);
    if (showDetailModal) {
      setDetailModalOpen(true);
    }
    onToolSelect?.(tool);
  }, [showDetailModal, onToolSelect]);

  const handleToggle = useCallback((toolName: string, enabled: boolean) => {
    onToolToggle?.(toolName, enabled);
  }, [onToolToggle]);

  // Table columns
  const columns = [
    {
      title: 'Tool',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: ToolMetadata) => (
        <Space direction="vertical" size={0}>
          <Space>
            {getCategoryIcon(record.category)}
            <Text strong>{name}</Text>
            {record.deprecated && (
              <Tag color="error">Deprecated</Tag>
            )}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {record.description.length > 80
              ? record.description.substring(0, 80) + '...'
              : record.description}
          </Text>
        </Space>
      ),
    },
    {
      title: 'Category',
      dataIndex: 'category',
      key: 'category',
      width: 130,
      render: (category: ToolCategory) => (
        <Tag color={getCategoryColor(category)} icon={getCategoryIcon(category)}>
          {formatCategory(category)}
        </Tag>
      ),
    },
    {
      title: 'Risk',
      dataIndex: ['authorization', 'risk_level'],
      key: 'risk',
      width: 100,
      render: (riskLevel: RiskLevel) => (
        <Badge
          status={getRiskLevelStatus(riskLevel)}
          text={riskLevel.toUpperCase()}
        />
      ),
    },
    {
      title: 'Auth',
      dataIndex: ['authorization', 'requires_authorization'],
      key: 'auth',
      width: 80,
      render: (requiresAuth: boolean) => (
        requiresAuth ? (
          <Tooltip title="Requires Authorization">
            <SafetyOutlined style={{ color: '#faad14' }} />
          </Tooltip>
        ) : (
          <Tooltip title="No Authorization Required">
            <CheckCircleOutlined style={{ color: '#52c41a' }} />
          </Tooltip>
        )
      ),
    },
    {
      title: 'Source',
      dataIndex: 'source',
      key: 'source',
      width: 100,
      render: (source: string) => (
        <Tag>{source}</Tag>
      ),
    },
    ...(allowToggle ? [{
      title: 'Enabled',
      key: 'enabled',
      width: 80,
      render: (_: any, record: ToolMetadata) => (
        <Switch
          checked={enabledTools.includes(record.name)}
          onChange={(checked) => handleToggle(record.name, checked)}
          size="small"
        />
      ),
    }] : []),
    {
      title: 'Actions',
      key: 'actions',
      width: 80,
      render: (_: any, record: ToolMetadata) => (
        <Button
          type="text"
          icon={<InfoCircleOutlined />}
          onClick={() => handleViewDetails(record)}
        >
          Details
        </Button>
      ),
    },
  ];

  return (
    <div className="tool-management-panel">
      {/* Filters */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Input
              placeholder="Search tools..."
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              allowClear
            />
          </Col>
          <Col span={6}>
            <Select
              style={{ width: '100%' }}
              placeholder="Filter by category"
              value={categoryFilter}
              onChange={setCategoryFilter}
            >
              <Option value="all">All Categories</Option>
              {availableCategories.map(cat => (
                <Option key={cat} value={cat}>
                  <Space>
                    {getCategoryIcon(cat)}
                    {formatCategory(cat)}
                  </Space>
                </Option>
              ))}
            </Select>
          </Col>
          <Col span={6}>
            <Select
              style={{ width: '100%' }}
              placeholder="Filter by risk level"
              value={riskFilter}
              onChange={setRiskFilter}
            >
              <Option value="all">All Risk Levels</Option>
              <Option value={RiskLevelEnum.SAFE}>
                <Badge status="success" text="Safe" />
              </Option>
              <Option value={RiskLevelEnum.LOW}>
                <Badge status="processing" text="Low" />
              </Option>
              <Option value={RiskLevelEnum.MEDIUM}>
                <Badge status="warning" text="Medium" />
              </Option>
              <Option value={RiskLevelEnum.HIGH}>
                <Badge status="error" text="High" />
              </Option>
              <Option value={RiskLevelEnum.CRITICAL}>
                <Badge status="error" text="Critical" />
              </Option>
            </Select>
          </Col>
          <Col span={4}>
            <Text type="secondary">
              {filteredTools.length} / {tools.length} tools
            </Text>
          </Col>
        </Row>
      </Card>

      {/* Tools Table */}
      <Table
        dataSource={filteredTools.map(t => ({ ...t, key: t.id }))}
        columns={columns}
        loading={loading}
        pagination={{
          pageSize: 10,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total) => `Total ${total} tools`,
        }}
        size="middle"
        scroll={{ x: 900 }}
      />

      {/* Detail Modal */}
      {showDetailModal && (
        <ToolDetailModal
          tool={selectedTool}
          open={detailModalOpen}
          onClose={() => setDetailModalOpen(false)}
        />
      )}
    </div>
  );
}

export default ToolManagementPanel;
