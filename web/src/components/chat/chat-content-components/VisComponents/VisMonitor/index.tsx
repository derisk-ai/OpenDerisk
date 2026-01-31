import React from 'react';
import { VisMonitorDiv } from './style';
import { CodePreview } from '../../code-preview';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import {
  Card,
  Collapse,
  Descriptions,
  Flex,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import { FileOutlined, QuestionCircleOutlined } from '@ant-design/icons';
import { uniqueId } from 'lodash';
import { getFileNameByURL } from './helps';

interface IProps {
  uid?: string;
  tool_name?: string;
  tool_cost?: number;
  tool_version?: string;
  tool_args?: unknown;
  run_env?: string;
  out_type?: 'json' | 'file';
  data?: unknown;
  [key: string]: unknown;
}

const VisMonitor = ({
  uid = uniqueId('chart_id_'),
  ...data_source
}: IProps) => {
  const chartLineNums =
    data_source.out_type === 'json' && Array.isArray(data_source.data)
      ? (data_source.data as unknown[]).length
      : 0;
  const fileSize = '';
  const cols: { key: string; dataIndex: string; title: string }[] = [];
  const tableData: Record<string, unknown>[] = [];

  return (
    <VisMonitorDiv key={uid} className="d-monitor">
      <Space direction="vertical" style={{ width: '100%' }}>
        <Card
          variant="borderless"
          title="数据源信息"
          extra={
            <Tag color="blue">
              {data_source.out_type === 'json' ? 'JSON数据源' : '文件数据源'}
            </Tag>
          }
        >
          <Space style={{ width: '100%' }} direction="vertical">
            <Card
              size="small"
              variant="borderless"
              style={{ background: 'rgba(0,0,0,0.02)' }}
            >
              <Descriptions
                size="small"
                title={data_source.tool_name}
                items={[
                  {
                    key: '1',
                    label: '耗时',
                    children: data_source.tool_cost
                      ? `${data_source.tool_cost}s`
                      : '-',
                  },
                  {
                    key: '2',
                    label: '工具版本',
                    children: data_source.tool_version || '-',
                  },
                  {
                    key: '3',
                    label: '数据行数',
                    children: chartLineNums || '-',
                  },
                  {
                    key: '4',
                    label: '运行环境',
                    children: data_source.run_env || '-',
                  },
                ]}
              />
            </Card>
            <Collapse
              bordered={false}
              destroyOnHidden
              items={[
                {
                  label: '输入参数',
                  children: (
                    <CodePreview
                      language="json"
                      code={
                        typeof data_source?.tool_args === 'object'
                          ? JSON.stringify(
                              data_source?.tool_args as object,
                              null,
                              2,
                            )
                          : String(data_source?.tool_args ?? '')
                      }
                      light={oneLight}
                    />
                  ),
                },
              ]}
            />
            {data_source.out_type === 'json' && (
              <Collapse
                bordered={false}
                items={[
                  {
                    key: '1',
                    label: '数据内容',
                    children: (
                      <CodePreview
                        language="json"
                        code={JSON.stringify(
                          data_source.data ?? {},
                          null,
                          2,
                        )}
                        light={oneLight}
                      />
                    ),
                  },
                ]}
              />
            )}
            {data_source.out_type === 'file' &&
              typeof data_source?.data === 'string' && (
                <Collapse
                  bordered={false}
                  items={[
                    {
                      key: '1',
                      label: (
                        <Flex gap={10}>
                          <FileOutlined />
                          {getFileNameByURL(data_source.data)}
                        </Flex>
                      ),
                      children: (
                        <Space
                          direction="vertical"
                          style={{ width: '100%' }}
                        >
                          <Typography.Text>文件信息</Typography.Text>
                          <Typography.Text>
                            <Tag color="orange">
                              文件大小: {fileSize || '-'}
                            </Tag>
                            <Tag color="orange">
                              数据行数: {chartLineNums} 行
                            </Tag>
                          </Typography.Text>
                          <Typography.Text>文件链接</Typography.Text>
                          <Typography.Link href={data_source.data}>
                            {data_source.data}
                          </Typography.Link>
                          <Typography.Text>
                            <Space>
                              <span>数据预览</span>
                              <Tooltip title="预览只展示5条数据">
                                <QuestionCircleOutlined
                                  style={{ marginRight: 12 }}
                                />
                              </Tooltip>
                            </Space>
                          </Typography.Text>
                          <Table
                            size="small"
                            pagination={false}
                            columns={cols}
                            bordered={false}
                            scroll={{ x: '100%' }}
                            dataSource={tableData}
                          />
                        </Space>
                      ),
                    },
                  ]}
                />
              )}
          </Space>
        </Card>
        <Card bodyStyle={{ padding: 0 }} title="监控数据曲线图">
          <div
            id={`chart-${uid}-0`}
            style={{ width: '100%', minHeight: 200 }}
          />
        </Card>
      </Space>
    </VisMonitorDiv>
  );
};

export default React.memo(VisMonitor);
