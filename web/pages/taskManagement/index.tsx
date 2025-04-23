import type { TableProps } from 'antd';
import { Button, Card, Col, Form, Input, Row, Select, Space, Table, Tag } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import React, {useState} from 'react';
interface DataType {
  gmtCreate: number;
  gmtModified: number;
  triggerId: number;
  taskId: number;
  agentId: number;
  traceId: number;
  sessionId: number;
  source: string;
  input: string;
  taskStatus: number;
  sendTime: number;
  finishTime: number;
  viewer: number;
  shareUrl: number;
  deleteStatus: number;
  sourceTaskUnique: string;
}

const TaskManagement = () => {
  const [depositbackForm] = Form.useForm();
  const { t } = useTranslation();

  const taskStatusOption = [
    {
      label: t('in_execution'),
      value: 0,
      color: 'gold',
    },
    {
      label: t('successful_execution'),
      value: 1,
      color: 'green',
    },
    {
      label: t('execution_failed'),
      value: 2,
      color: 'red',
    },
  ];
  const deleteStatusOption = [
    {
      label: t('not_deleted'),
      value: 0,
    },
    {
      label: t('deleted'),
      value: 1,
      color: 'red',
    },
  ];

  const sourceOption = [
    {
      label: t('db_alarm_task'),
      value: 'ob',
    },
    {
      label: t('monitoring_alarm_tasks'),
      value: 'antmonitor',
    },
  ];
  const columns: TableProps<DataType>['columns'] = [
    {
      title: t('creation_time'),
      dataIndex: 'gmtCreate',
      key: 'gmtCreate',
      render: (_, record) => {
        return record?.gmtCreate ? dayjs(record?.gmtCreate).format('YYYY-MM-DD HH:mm:ss') : '-';
      },
      width: 160,
      align: 'center',
    },
    {
      title: t('update_time'),
      dataIndex: 'gmtModified',
      key: 'gmtModified',
      render: (_, record) => {
        return record?.gmtModified ? dayjs(record?.gmtModified).format('YYYY-MM-DD HH:mm:ss') : '-';
      },
      width: 160,
      align: 'center',
    },
    {
      title: 'traceId',
      dataIndex: 'traceId',
      key: 'traceId',
      width: 200,
      align: 'center',
    },
    {
      title: t('trigger_id'),
      dataIndex: 'triggerId',
      key: 'triggerId',
      width: 200,
      align: 'center',
    },
    {
      title: t('task_id'),
      dataIndex: 'taskId',
      key: 'taskId',
      width: 200,
      align: 'center',
    },
    {
      title: t('agent_id'),
      dataIndex: 'agentId',
      key: 'agentId',
      width: 200,
      align: 'center',
    },

    {
      title: t('agentsessionId_id'),
      dataIndex: 'agentsessionId_id',
      key: 'sessionId',
      width: 200,
      align: 'center',
    },
    {
      title: t('source'),

      dataIndex: 'source',
      key: 'source',
      width: 200,
      align: 'center',
      render: (_, record) => {
        const _value = sourceOption?.find(item => item.value === record?.source)?.label;
        return <Tag>{_value || '-'}</Tag>;
      },
    },
    {
      title: t('task_input'),
      dataIndex: 'input',
      key: 'input',
      width: 200,
      align: 'center',
    },
    {
      title: t('task_status'),
      dataIndex: 'taskStatus',
      key: 'taskStatus',
      render: (_, record) => {
        const _value = taskStatusOption?.find(item => item.value === record?.taskStatus);
        return <Tag color={_value?.color}>{_value?.label || '-'}</Tag>;
      },
      width: 130,
      align: 'center',
    },
    {
      title: t('send_time'),
      dataIndex: 'sendTime',
      key: 'sendTime',
      render: (_, record) => {
        return record?.sendTime ? dayjs(record?.sendTime).format('YYYY-MM-DD HH:mm:ss') : '-';
      },
      width: 160,
      align: 'center',
    },
    {
      title: t('finish_time'),
      dataIndex: 'finishTime',
      key: 'finishTime',
      render: (_, record) => {
        return record?.finishTime ? dayjs(record?.finishTime).format('YYYY-MM-DD HH:mm:ss') : '-';
      },
      width: 160,
      align: 'center',
    },
    {
      title: t('viewer'),
      dataIndex: 'viewer',
      key: 'viewer',
      width: 200,
      align: 'center',
    },
    {
      title: t('share_url'),
      dataIndex: 'shareUrl',
      key: 'shareUrl',
      width: 200,
      align: 'center',
    },
    {
      title: t('status'),
      dataIndex: 'deleteStatus',
      key: 'deleteStatus',
      render: (_, record) => {
        const _value = deleteStatusOption?.find(item => item.value === record?.deleteStatus);
        return <Tag color={_value?.color}>{_value?.label || '-'}</Tag>;
      },
      width: 130,
      align: 'center',
    },
    {
      title: t('source_task_unique'),
      dataIndex: 'sourceTaskUnique',
      key: 'sourceTaskUnique',
      width: 200,
      align: 'center',
    },
  ];

  const data: DataType[] = [];
  for (let index = 0; index < 40; index++) {
    data?.push( {
        gmtCreate: new Date()?.getTime(),
        gmtModified: new Date()?.getTime(),
        triggerId: 1,
        taskId: 1,
        agentId: 1,
        traceId: 1,
        sessionId: 1,
        source: 'ob',
        input: 'dsadas',
        taskStatus: 1,
        sendTime: new Date()?.getTime(),
        finishTime: new Date()?.getTime(),
        viewer: 1,
        shareUrl: 1,
        deleteStatus: 1,
        sourceTaskUnique: '1',
      })
  }
  
  const queryDepositback = () => {
    depositbackForm.validateFields().then(values => {
      console.log(values, 'values');
    });
  };
  return (
    <div className='px-6 mt-2' style={{ overflow: 'auto' }}>
      <Card className='my-2'>
        <Form form={depositbackForm} onFinish={queryDepositback}>
          <Row gutter={24}>
            <Col span={8}>
              <Form.Item label={t('task_id')} name='taskId'>
                <Input placeholder={t('Please_Input')} allowClear />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label={t('agent_id')} name='agentId'>
                <Input placeholder={t('Please_Input')} allowClear />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label={t('time_id')} name='teamId'>
                <Input placeholder={t('Please_Input')} allowClear />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label={t('task_status')} name='taskStatus'>
                <Select placeholder={t('please_select')} allowClear>
                  {taskStatusOption?.map(item => {
                    return (
                      <Select.Option value={item.value} key={item.value}>
                        {item.label}
                      </Select.Option>
                    );
                  })}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label={t('task_name')} name='taskName'>
                <Input placeholder={t('Please_Input')} />
              </Form.Item>
            </Col>

            <Col span={8}>
              <Form.Item label={t('source')} name='source'>
                <Select placeholder={t('please_select')} allowClear>
                  {sourceOption?.map(item => {
                    return (
                      <Select.Option value={item.value} key={item.value}>
                        {item.label}
                      </Select.Option>
                    );
                  })}
                </Select>
              </Form.Item>
            </Col>
            <Col className='w-full flex justify-end'>
              <Space>
                <Button type='primary' htmlType='reset'>
                  {t('Reset')} 
                </Button>
                <Button type='primary' htmlType='submit'>
                  {t('Query')}
                </Button>
              </Space>
            </Col>
          </Row>
        </Form>
      </Card>

      <Card>
        <Table<DataType> pagination={{
            onChange: (page, pageSize) => {
                console.log(page, pageSize, 'dasdasdsa');
            },
            pageSizeOptions: ['10', '20', '50', '100'],

        }} columns={columns} dataSource={data} scroll={{ x: 'max-content' }} bordered />
      </Card>
    </div>
  );
};
export default TaskManagement;
