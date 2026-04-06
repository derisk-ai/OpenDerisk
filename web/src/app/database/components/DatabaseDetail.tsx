'use client';

import {
  apiInterceptors,
  getDbSpec,
  getDbTables,
  getDbTableDetail,
  getDbLearnStatus,
  getDbTableData,
  postDbLearn,
  getSensitiveColumns,
  addSensitiveColumn,
  toggleSensitiveColumn,
  updateSensitiveColumn,
  detectSensitiveColumns,
} from '@/client/api';
import {
  IChatDbSchema,
  DbSpecResponse,
  TableSpecSummary,
  TableSpecDetail,
  LearningTaskResponse,
  TableDataPreview,
  SensitiveColumnConfig,
  SENSITIVE_TYPES,
  MASKING_MODES,
} from '@/types/db';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  TableOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  LockOutlined,
  PlusOutlined,
  SearchOutlined,
  EditOutlined,
} from '@ant-design/icons';
import { useRequest } from 'ahooks';
import {
  App,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Modal,
  Progress,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import React, { useState, useCallback, useMemo } from 'react';

const { Text } = Typography;

/** Color map for sensitive type tags. */
const SENSITIVE_TYPE_COLORS: Record<string, string> = {
  phone: 'red',
  email: 'orange',
  id_card: 'volcano',
  bank_card: 'magenta',
  address: 'gold',
  name: 'cyan',
  password: 'purple',
  token: 'purple',
  ip_address: 'geekblue',
  custom: 'default',
};

interface DatabaseDetailProps {
  datasource: IChatDbSchema;
  onRefresh?: () => void;
}

export default function DatabaseDetail({
  datasource,
  onRefresh,
}: DatabaseDetailProps) {
  const { message } = App.useApp();
  const datasourceId = String(datasource.id);
  const [tableDetailDrawerOpen, setTableDetailDrawerOpen] = useState(false);
  const [selectedTableName, setSelectedTableName] = useState<string>('');
  const [addSensitiveModalOpen, setAddSensitiveModalOpen] = useState(false);
  const [editSensitiveModalOpen, setEditSensitiveModalOpen] = useState(false);
  const [editingColumn, setEditingColumn] = useState<SensitiveColumnConfig | null>(null);
  const [addForm] = Form.useForm();
  const [editForm] = Form.useForm();

  // Fetch DB spec
  const {
    data: dbSpec,
    loading: specLoading,
    refresh: refreshSpec,
  } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getDbSpec(datasourceId));
    if (err) return null;
    return res as DbSpecResponse | null;
  });

  // Fetch table specs
  const {
    data: tableSpecs,
    loading: tablesLoading,
    refresh: refreshTables,
  } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getDbTables(datasourceId));
    if (err) return [];
    return (res || []) as TableSpecSummary[];
  });

  // Fetch learning status
  const {
    data: learningStatus,
    refresh: refreshLearning,
  } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getDbLearnStatus(datasourceId));
    if (err) return null;
    return res as LearningTaskResponse | null;
  });

  // Fetch all sensitive column configs for this datasource
  const {
    data: sensitiveColumns,
    refresh: refreshSensitive,
  } = useRequest(async () => {
    const [err, res] = await apiInterceptors(getSensitiveColumns(datasourceId));
    if (err) return [];
    return (res || []) as SensitiveColumnConfig[];
  });

  // Sensitive column count per table (for Tables tab)
  const sensitiveCountByTable = useMemo(() => {
    const map: Record<string, number> = {};
    for (const sc of sensitiveColumns || []) {
      map[sc.table_name] = (map[sc.table_name] || 0) + 1;
    }
    return map;
  }, [sensitiveColumns]);

  // Sensitive columns for the currently selected table
  const currentTableSensitive = useMemo(() => {
    if (!selectedTableName || !sensitiveColumns) return [];
    return sensitiveColumns.filter((sc) => sc.table_name === selectedTableName);
  }, [selectedTableName, sensitiveColumns]);

  // Map column_name → SensitiveColumnConfig for quick lookup in schema tab
  const sensitiveByColumn = useMemo(() => {
    const map: Record<string, SensitiveColumnConfig> = {};
    for (const sc of currentTableSensitive) {
      map[sc.column_name] = sc;
    }
    return map;
  }, [currentTableSensitive]);

  // Fetch table detail
  const {
    data: tableDetail,
    loading: tableDetailLoading,
    run: fetchTableDetail,
  } = useRequest(
    async (tableName: string) => {
      const [err, res] = await apiInterceptors(
        getDbTableDetail(datasourceId, tableName),
      );
      if (err) return null;
      return res as TableSpecDetail | null;
    },
    { manual: true },
  );

  // Fetch table data preview
  const {
    data: tableData,
    loading: tableDataLoading,
    run: fetchTableData,
  } = useRequest(
    async (tableName: string, page = 1, pageSize = 10) => {
      const [err, res] = await apiInterceptors(
        getDbTableData(datasourceId, tableName, page, pageSize),
      );
      if (err) return null;
      return res as TableDataPreview | null;
    },
    { manual: true },
  );

  // Trigger learning
  const { run: runLearn, loading: learnLoading } = useRequest(
    async () => {
      const [err] = await apiInterceptors(postDbLearn(datasourceId));
      if (err) throw err;
    },
    {
      manual: true,
      onSuccess: () => {
        message.success('Learning task started');
        refreshLearning();
        refreshSpec();
        refreshTables();
        refreshSensitive();
        onRefresh?.();
      },
      onError: () => {
        message.error('Failed to start learning');
      },
    },
  );

  // Auto-detect sensitive columns for a table
  const { run: runDetect, loading: detectLoading } = useRequest(
    async (tableNames?: string[]) => {
      const [err, res] = await apiInterceptors(
        detectSensitiveColumns(datasourceId, tableNames),
      );
      if (err) throw err;
      return res;
    },
    {
      manual: true,
      onSuccess: (data) => {
        const count = data?.length || 0;
        message.success(`Detected ${count} sensitive column(s)`);
        refreshSensitive();
      },
      onError: () => {
        message.error('Detection failed');
      },
    },
  );

  // Toggle sensitive column enabled
  const handleToggleSensitive = useCallback(
    async (tableName: string, columnName: string, enabled: boolean) => {
      const [err] = await apiInterceptors(
        toggleSensitiveColumn(datasourceId, tableName, columnName, enabled),
      );
      if (err) {
        message.error('Failed to update masking status');
        return;
      }
      refreshSensitive();
    },
    [datasourceId, message, refreshSensitive],
  );

  // Add sensitive column manually
  const handleAddSensitive = useCallback(async () => {
    try {
      const values = await addForm.validateFields();
      const [err] = await apiInterceptors(
        addSensitiveColumn(datasourceId, {
          table_name: selectedTableName,
          column_name: values.column_name,
          sensitive_type: values.sensitive_type,
          masking_mode: values.masking_mode,
        }),
      );
      if (err) throw err;
      message.success('Sensitive column added');
      setAddSensitiveModalOpen(false);
      addForm.resetFields();
      refreshSensitive();
    } catch {
      message.error('Failed to add sensitive column');
    }
  }, [datasourceId, selectedTableName, addForm, message, refreshSensitive]);

  // Edit sensitive column
  const handleEditSensitive = useCallback(async () => {
    if (!editingColumn) return;
    try {
      const values = await editForm.validateFields();
      const [err] = await apiInterceptors(
        updateSensitiveColumn(
          datasourceId,
          editingColumn.table_name,
          editingColumn.column_name,
          {
            sensitive_type: values.sensitive_type,
            masking_mode: values.masking_mode,
          },
        ),
      );
      if (err) throw err;
      message.success('Sensitive column updated');
      setEditSensitiveModalOpen(false);
      setEditingColumn(null);
      refreshSensitive();
    } catch {
      message.error('Failed to update');
    }
  }, [datasourceId, editingColumn, editForm, message, refreshSensitive]);

  const handleViewTable = useCallback(
    (tableName: string) => {
      setSelectedTableName(tableName);
      setTableDetailDrawerOpen(true);
      fetchTableDetail(tableName);
      fetchTableData(tableName);
    },
    [fetchTableDetail, fetchTableData],
  );

  const refreshAll = useCallback(() => {
    refreshSpec();
    refreshTables();
    refreshLearning();
    refreshSensitive();
  }, [refreshSpec, refreshTables, refreshLearning, refreshSensitive]);

  // Table columns for table spec list (Tables tab)
  const tableColumns = [
    {
      title: 'Table Name',
      dataIndex: 'table_name',
      key: 'table_name',
      render: (name: string) => (
        <a
          onClick={() => handleViewTable(name)}
          className="text-blue-500 hover:text-blue-700"
        >
          <TableOutlined className="mr-1" />
          {name}
        </a>
      ),
    },
    {
      title: 'Comment',
      dataIndex: 'table_comment',
      key: 'table_comment',
      ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: 'Row Count',
      dataIndex: 'row_count',
      key: 'row_count',
      render: (v: number | null) =>
        v !== null && v !== undefined ? v.toLocaleString() : '-',
    },
    {
      title: 'Columns',
      dataIndex: 'column_count',
      key: 'column_count',
    },
    {
      title: 'Sensitive',
      key: 'sensitive_count',
      render: (_: any, record: TableSpecSummary) => {
        const count = sensitiveCountByTable[record.table_name] || 0;
        return count > 0 ? (
          <Tag color="red" icon={<LockOutlined />}>
            {count}
          </Tag>
        ) : (
          '-'
        );
      },
    },
    {
      title: 'Group',
      dataIndex: 'group_name',
      key: 'group_name',
      render: (v: string | null) => (v ? <Tag>{v}</Tag> : '-'),
    },
  ];

  const renderSpecOverview = () => {
    if (specLoading) return <Empty description="Loading..." />;
    if (!dbSpec) return <Empty description="No spec generated yet. Click 'Learn Schema' to start." />;

    return (
      <div>
        <Descriptions bordered column={2} size="small" className="mb-4">
          <Descriptions.Item label="Database Type">
            <Tag color="blue">{dbSpec.db_type}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Status">
            {dbSpec.status === 'ready' ? (
              <Tag color="success" icon={<CheckCircleOutlined />}>
                Ready
              </Tag>
            ) : dbSpec.status === 'generating' ? (
              <Tag color="processing" icon={<SyncOutlined spin />}>
                Generating
              </Tag>
            ) : (
              <Tag color="error" icon={<CloseCircleOutlined />}>
                Failed
              </Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="Table Count">
            {dbSpec.table_count ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="Last Updated">
            {dbSpec.gmt_modified || '-'}
          </Descriptions.Item>
        </Descriptions>

        {dbSpec.spec_content && dbSpec.spec_content.length > 0 && (
          <Card title="Table Index" size="small">
            {dbSpec.spec_content.map((entry, idx) => (
              <div key={idx} className="py-1 border-b border-gray-100 last:border-0">
                <a
                  onClick={() => handleViewTable(entry.table_name)}
                  className="text-blue-500 hover:text-blue-700 cursor-pointer"
                >
                  {entry.table_name}
                </a>
                <Text type="secondary" className="ml-2">
                  {entry.row_count !== null ? `${entry.row_count?.toLocaleString()} rows` : ''}
                </Text>
                {entry.group && entry.group !== 'default' && (
                  <Tag className="ml-2" color="default">
                    {entry.group}
                  </Tag>
                )}
                <br />
                <Text type="secondary" className="text-xs">
                  {entry.summary}
                </Text>
              </div>
            ))}
          </Card>
        )}
      </div>
    );
  };

  const renderLearningStatus = () => {
    return (
      <div>
        <Space direction="vertical" className="w-full">
          <Button
            type="primary"
            icon={<SyncOutlined />}
            loading={learnLoading}
            onClick={runLearn}
          >
            Learn Schema Now
          </Button>

          {learningStatus && (
            <Card title="Latest Learning Task" size="small">
              <Descriptions column={2} size="small">
                <Descriptions.Item label="Status">
                  <Tag
                    color={
                      learningStatus.status === 'completed'
                        ? 'success'
                        : learningStatus.status === 'running'
                          ? 'processing'
                          : learningStatus.status === 'failed'
                            ? 'error'
                            : 'default'
                    }
                  >
                    {learningStatus.status}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Type">
                  {learningStatus.task_type}
                </Descriptions.Item>
                <Descriptions.Item label="Progress">
                  <Progress
                    percent={learningStatus.progress}
                    size="small"
                    status={
                      learningStatus.status === 'failed'
                        ? 'exception'
                        : learningStatus.status === 'completed'
                          ? 'success'
                          : 'active'
                    }
                  />
                </Descriptions.Item>
                <Descriptions.Item label="Tables">
                  {learningStatus.processed_tables}/{learningStatus.total_tables ?? '?'}
                </Descriptions.Item>
                <Descriptions.Item label="Trigger">
                  {learningStatus.trigger_type}
                </Descriptions.Item>
                <Descriptions.Item label="Started">
                  {learningStatus.gmt_created || '-'}
                </Descriptions.Item>
              </Descriptions>
              {learningStatus.error_message && (
                <div className="mt-2">
                  <Text type="danger">{learningStatus.error_message}</Text>
                </div>
              )}
            </Card>
          )}
        </Space>
      </div>
    );
  };

  /** Render the Sensitive Columns tab inside the table detail drawer. */
  const renderSensitiveColumnsTab = () => {
    const configuredNames = new Set(currentTableSensitive.map((sc) => sc.column_name));
    const availableColumns = (tableDetail?.columns || [])
      .map((c) => c.name)
      .filter((name) => !configuredNames.has(name));

    return (
      <div>
        <Space className="mb-4">
          <Button
            icon={<SearchOutlined />}
            loading={detectLoading}
            onClick={() => runDetect([selectedTableName])}
          >
            Auto Detect
          </Button>
          <Button
            icon={<PlusOutlined />}
            onClick={() => {
              addForm.resetFields();
              setAddSensitiveModalOpen(true);
            }}
          >
            Add Manual
          </Button>
        </Space>

        <Table
          dataSource={currentTableSensitive.map((sc, idx) => ({
            key: idx,
            ...sc,
          }))}
          pagination={false}
          size="small"
          locale={{
            emptyText: (
              <Empty description="No sensitive columns configured. Click 'Auto Detect' to scan." />
            ),
          }}
          columns={[
            {
              title: 'Column',
              dataIndex: 'column_name',
              key: 'column_name',
            },
            {
              title: 'Type',
              dataIndex: 'sensitive_type',
              key: 'sensitive_type',
              render: (v: string) => (
                <Tag color={SENSITIVE_TYPE_COLORS[v] || 'default'}>{v}</Tag>
              ),
            },
            {
              title: 'Mode',
              dataIndex: 'masking_mode',
              key: 'masking_mode',
              render: (v: string) => {
                const label = v === 'mask' ? 'Partial Mask' : v === 'token' ? 'Tokenize' : 'None';
                return <Tag>{label}</Tag>;
              },
            },
            {
              title: 'Confidence',
              dataIndex: 'confidence',
              key: 'confidence',
              render: (v: number | null) =>
                v !== null && v !== undefined
                  ? `${(v * 100).toFixed(0)}%`
                  : '-',
            },
            {
              title: 'Source',
              dataIndex: 'source',
              key: 'source',
              render: (v: string) => (
                <Tag color={v === 'auto' ? 'blue' : 'green'}>{v}</Tag>
              ),
            },
            {
              title: 'Enabled',
              dataIndex: 'enabled',
              key: 'enabled',
              render: (v: boolean, record: SensitiveColumnConfig) => (
                <Switch
                  size="small"
                  checked={v}
                  onChange={(checked) =>
                    handleToggleSensitive(
                      record.table_name,
                      record.column_name,
                      checked,
                    )
                  }
                />
              ),
            },
            {
              title: 'Action',
              key: 'action',
              render: (_: any, record: SensitiveColumnConfig) => (
                <Button
                  type="link"
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => {
                    setEditingColumn(record);
                    editForm.setFieldsValue({
                      sensitive_type: record.sensitive_type,
                      masking_mode: record.masking_mode,
                    });
                    setEditSensitiveModalOpen(true);
                  }}
                >
                  Edit
                </Button>
              ),
            },
          ]}
        />

        {/* Add Sensitive Column Modal */}
        <Modal
          title="Add Sensitive Column"
          open={addSensitiveModalOpen}
          onOk={handleAddSensitive}
          onCancel={() => setAddSensitiveModalOpen(false)}
          destroyOnClose
        >
          <Form form={addForm} layout="vertical">
            <Form.Item
              name="column_name"
              label="Column"
              rules={[{ required: true, message: 'Select a column' }]}
            >
              <Select placeholder="Select column">
                {availableColumns.map((name) => (
                  <Select.Option key={name} value={name}>
                    {name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item
              name="sensitive_type"
              label="Sensitive Type"
              rules={[{ required: true, message: 'Select sensitive type' }]}
            >
              <Select placeholder="Select type">
                {SENSITIVE_TYPES.map((t) => (
                  <Select.Option key={t} value={t}>
                    {t}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item
              name="masking_mode"
              label="Masking Mode"
              initialValue="mask"
              rules={[{ required: true }]}
            >
              <Select>
                {MASKING_MODES.map((m) => (
                  <Select.Option key={m} value={m}>
                    {m === 'mask' ? 'Partial Mask' : m === 'token' ? 'Tokenize' : 'None'}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          </Form>
        </Modal>

        {/* Edit Sensitive Column Modal */}
        <Modal
          title={`Edit: ${editingColumn?.column_name || ''}`}
          open={editSensitiveModalOpen}
          onOk={handleEditSensitive}
          onCancel={() => {
            setEditSensitiveModalOpen(false);
            setEditingColumn(null);
          }}
          destroyOnClose
        >
          <Form form={editForm} layout="vertical">
            <Form.Item
              name="sensitive_type"
              label="Sensitive Type"
              rules={[{ required: true }]}
            >
              <Select>
                {SENSITIVE_TYPES.map((t) => (
                  <Select.Option key={t} value={t}>
                    {t}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item
              name="masking_mode"
              label="Masking Mode"
              rules={[{ required: true }]}
            >
              <Select>
                {MASKING_MODES.map((m) => (
                  <Select.Option key={m} value={m}>
                    {m === 'mask' ? 'Partial Mask' : m === 'token' ? 'Tokenize' : 'None'}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          </Form>
        </Modal>
      </div>
    );
  };

  const renderTableDetail = () => {
    if (tableDetailLoading) return <Empty description="Loading..." />;
    if (!tableDetail) return <Empty description="No data" />;

    const columnTableData = (tableDetail.columns || []).map(
      (col, idx) => ({
        key: idx,
        ...col,
      }),
    );

    const indexTableData = (tableDetail.indexes || []).map(
      (idx, i) => ({
        key: i,
        ...idx,
        columns_str: (idx.columns || []).join(', '),
      }),
    );

    return (
      <Tabs
        defaultActiveKey="schema"
        items={[
          {
            key: 'schema',
            label: 'Schema',
            children: (
              <div>
                <Descriptions bordered column={2} size="small" className="mb-4">
                  <Descriptions.Item label="Table">{tableDetail.table_name}</Descriptions.Item>
                  <Descriptions.Item label="Comment">
                    {tableDetail.table_comment || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Row Count">
                    {tableDetail.row_count?.toLocaleString() ?? '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Group">
                    {tableDetail.group_name || '-'}
                  </Descriptions.Item>
                </Descriptions>

                <h4 className="font-semibold mb-2">Columns ({columnTableData.length})</h4>
                <Table
                  dataSource={columnTableData}
                  pagination={false}
                  size="small"
                  columns={[
                    { title: 'Name', dataIndex: 'name', key: 'name' },
                    { title: 'Type', dataIndex: 'type', key: 'type' },
                    {
                      title: 'Nullable',
                      dataIndex: 'nullable',
                      key: 'nullable',
                      render: (v: boolean) => (v ? 'YES' : 'NO'),
                    },
                    {
                      title: 'PK',
                      dataIndex: 'pk',
                      key: 'pk',
                      render: (v: boolean) =>
                        v ? <Tag color="gold">PK</Tag> : '-',
                    },
                    {
                      title: 'Comment',
                      dataIndex: 'comment',
                      key: 'comment',
                      ellipsis: true,
                      render: (v: string | null) => v || '-',
                    },
                    {
                      title: 'Sensitive',
                      key: 'sensitive',
                      render: (_: any, record: any) => {
                        const sc = sensitiveByColumn[record.name];
                        if (!sc) return '-';
                        return (
                          <Tooltip title={`Mode: ${sc.masking_mode}`}>
                            <Tag color={SENSITIVE_TYPE_COLORS[sc.sensitive_type] || 'default'}>
                              <LockOutlined className="mr-1" />
                              {sc.sensitive_type}
                            </Tag>
                          </Tooltip>
                        );
                      },
                    },
                    {
                      title: 'Masking',
                      key: 'masking',
                      render: (_: any, record: any) => {
                        const sc = sensitiveByColumn[record.name];
                        if (!sc) return '-';
                        return (
                          <Switch
                            size="small"
                            checked={sc.enabled}
                            onChange={(checked) =>
                              handleToggleSensitive(
                                selectedTableName,
                                record.name,
                                checked,
                              )
                            }
                          />
                        );
                      },
                    },
                  ]}
                />

                {indexTableData.length > 0 && (
                  <>
                    <h4 className="font-semibold mb-2 mt-4">
                      Indexes ({indexTableData.length})
                    </h4>
                    <Table
                      dataSource={indexTableData}
                      pagination={false}
                      size="small"
                      columns={[
                        { title: 'Name', dataIndex: 'name', key: 'name' },
                        {
                          title: 'Columns',
                          dataIndex: 'columns_str',
                          key: 'columns_str',
                        },
                        {
                          title: 'Unique',
                          dataIndex: 'unique',
                          key: 'unique',
                          render: (v: boolean) => (v ? 'YES' : 'NO'),
                        },
                      ]}
                    />
                  </>
                )}
              </div>
            ),
          },
          {
            key: 'sensitive',
            label: (
              <span>
                <LockOutlined /> Sensitive Columns
                {currentTableSensitive.length > 0 && (
                  <Tag color="red" className="ml-1" style={{ marginRight: 0 }}>
                    {currentTableSensitive.length}
                  </Tag>
                )}
              </span>
            ),
            children: renderSensitiveColumnsTab(),
          },
          {
            key: 'ddl',
            label: 'DDL',
            children: tableDetail.create_ddl ? (
              <pre className="bg-gray-50 p-4 rounded text-sm overflow-auto max-h-96">
                {tableDetail.create_ddl}
              </pre>
            ) : (
              <Empty description="No DDL available" />
            ),
          },
          {
            key: 'sample',
            label: 'Sample Data',
            children: tableDetail.sample_data ? (
              <Table
                dataSource={tableDetail.sample_data.rows.map(
                  (row, idx) => {
                    const obj: any = { key: idx };
                    tableDetail.sample_data!.columns.forEach(
                      (col, ci) => {
                        obj[col] = row[ci];
                      },
                    );
                    return obj;
                  },
                )}
                columns={tableDetail.sample_data.columns.map(
                  (col) => ({
                    title: col,
                    dataIndex: col,
                    key: col,
                    ellipsis: true,
                  }),
                )}
                pagination={false}
                size="small"
                scroll={{ x: 'max-content' }}
              />
            ) : (
              <Empty description="No sample data" />
            ),
          },
          {
            key: 'data',
            label: 'Data Preview',
            children: (
              <div>
                {!tableData && !tableDataLoading && (
                  <Button
                    onClick={() =>
                      fetchTableData(selectedTableName)
                    }
                  >
                    Load Data
                  </Button>
                )}
                {tableDataLoading && <Empty description="Loading..." />}
                {tableData && (
                  <Table
                    dataSource={tableData.rows.map((row, idx) => {
                      const obj: any = { key: idx };
                      tableData.columns.forEach((col, ci) => {
                        obj[col] = row[ci];
                      });
                      return obj;
                    })}
                    columns={tableData.columns.map((col) => ({
                      title: col,
                      dataIndex: col,
                      key: col,
                      ellipsis: true,
                    }))}
                    size="small"
                    scroll={{ x: 'max-content' }}
                    pagination={{
                      total: tableData.total,
                      current: tableData.page,
                      pageSize: tableData.page_size,
                      onChange: (page, pageSize) =>
                        fetchTableData(selectedTableName, page, pageSize),
                    }}
                  />
                )}
              </div>
            ),
          },
        ]}
      />
    );
  };

  return (
    <div>
      <div className="mb-4">
        <Button icon={<ReloadOutlined />} onClick={refreshAll} size="small">
          Refresh All
        </Button>
      </div>

      <Tabs
        defaultActiveKey="overview"
        items={[
          {
            key: 'overview',
            label: (
              <span>
                <DatabaseOutlined /> Overview
              </span>
            ),
            children: renderSpecOverview(),
          },
          {
            key: 'tables',
            label: (
              <span>
                <TableOutlined /> Tables
              </span>
            ),
            children: (
              <Table
                columns={tableColumns}
                dataSource={tableSpecs}
                rowKey="table_name"
                loading={tablesLoading}
                size="small"
                pagination={{ pageSize: 20 }}
                locale={{
                  emptyText: (
                    <Empty description="No table specs. Run schema learning first." />
                  ),
                }}
              />
            ),
          },
          {
            key: 'learning',
            label: (
              <span>
                <SyncOutlined /> Learning
              </span>
            ),
            children: renderLearningStatus(),
          },
        ]}
      />

      {/* Table Detail Drawer */}
      <Drawer
        title={
          <span>
            <TableOutlined className="mr-2" />
            {selectedTableName}
          </span>
        }
        placement="right"
        width={700}
        open={tableDetailDrawerOpen}
        onClose={() => setTableDetailDrawerOpen(false)}
        destroyOnClose
      >
        {renderTableDetail()}
      </Drawer>
    </div>
  );
}
