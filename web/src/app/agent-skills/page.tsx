"use client"
import { apiInterceptors } from '@/client/api';
import { getSkillList, createSkill, updateSkill, deleteSkill, createSyncTask, getSyncTaskStatus, getRecentSyncTasks, updateSkillAutoSync, uploadSkillFromZip } from '@/client/api/skill';
import { InnerDropdown } from '@/components/blurred-card';
import { FolderOpenFilled, ReloadOutlined, PlusOutlined, GithubOutlined, SyncOutlined, HistoryOutlined, CloudSyncOutlined, CloudOutlined, UploadOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Form, Pagination, Result, Spin, Tooltip, Button, message, Tag, Input, Modal, Select, Switch, PaginationProps, Progress, Drawer, List, Typography, Space, Upload } from 'antd';
import { useRouter } from 'next/navigation';
import React, { memo, useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';

const { Search } = Input;
const { Option } = Select;
const { Text } = Typography;

const SkillPage: React.FC = () => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [syncForm] = Form.useForm();
  const router = useRouter();

  const [queryParams, setQueryparams] = useState({
    filter: '',
  });
  const [paginationParams, setPaginationParams] = useState({
    page: 1,
    page_size: 20,
  });

  const [skillList, setSkillList] = useState<any>([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isSyncModalVisible, setIsSyncModalVisible] = useState(false);
  const [isSyncProgressDrawerVisible, setIsSyncProgressDrawerVisible] = useState(false);
  const [editingSkill, setEditingSkill] = useState<any>(null);
  const [uploading, setUploading] = useState(false);

  // Sync task state
  const [currentSyncTask, setCurrentSyncTask] = useState<any>(null);
  const [recentSyncTasks, setRecentSyncTasks] = useState<any[]>([]);

  // Query skills
  const { loading, run: runGetSkillList } = useRequest(
    async (
      params = { filter: '' },
      other = { page: 1, page_size: 20 },
    ): Promise<any> => {
      return await apiInterceptors(getSkillList(params, other));
    },
    {
      manual: false,
      onSuccess: data => {
        const [, res] = data;
        setSkillList(res?.items || []);
      },
      debounceWait: 300,
    },
  );

  // Query recent sync tasks
  const { run: runGetRecentSyncTasks } = useRequest(
    async () => apiInterceptors(getRecentSyncTasks(5)),
    {
      manual: true,
      onSuccess: data => {
        const [, res] = data;
        setRecentSyncTasks(res?.data || []);
      },
    },
  );

  // Check sync task status
  const checkSyncTaskStatus = useCallback(async (taskId: string) => {
    const [err, res] = await apiInterceptors(getSyncTaskStatus(taskId));
    if (res) {
      const task = res;
      setCurrentSyncTask(task);

      // If task is still running, poll after 2 seconds
      if (task.status === 'running' || task.status === 'pending') {
        clearTimeout((window as any).syncPollTimer);
        (window as any).syncPollTimer = setTimeout(() => checkSyncTaskStatus(taskId), 2000);
      }

      // Refresh skill list when task completes
      if (task.status === 'completed') {
        runGetRecentSyncTasks();
        runGetSkillList(queryParams, paginationParams);
        message.success('Skill sync completed successfully!');
      } else if (task.status === 'failed') {
        runGetRecentSyncTasks();
        message.error('Skill sync failed');
      }
    }
  }, [runGetRecentSyncTasks, runGetSkillList, queryParams, paginationParams]);

  // Poll for active sync task on mount
  useEffect(() => {
    runGetRecentSyncTasks();

    return () => {
      if ((window as any).syncPollTimer) {
        clearTimeout((window as any).syncPollTimer);
      }
    };
  }, [runGetRecentSyncTasks]);

  // Auto-show sync progress drawer when there's an active task
  useEffect(() => {
    const activeTask = recentSyncTasks.find(t => t.status === 'running' || t.status === 'pending');
    if (activeTask && !currentSyncTask) {
      setCurrentSyncTask(activeTask);
      setIsSyncProgressDrawerVisible(true);
      checkSyncTaskStatus(activeTask.task_id);
    }
  }, [recentSyncTasks, currentSyncTask, checkSyncTaskStatus]);

  const handleCreate = () => {
    setEditingSkill(null);
    form.resetFields();
    setIsModalVisible(true);
  };

  const handleEdit = (record: any) => {
    // Navigate to detail page for editing
    goSkillDetail(record.skill_code);
  };

  const handleDelete = async (item: any) => {
    try {
      await apiInterceptors(deleteSkill({ skill_code: item.skill_code }));
      message.success('Skill deleted successfully');
      runGetSkillList(queryParams, paginationParams);
    } catch (error) {
      message.error('Failed to delete skill');
    }
  };

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const [err, res] = await apiInterceptors(uploadSkillFromZip(file));
      if (err) {
        message.error(`Upload failed: ${err}`);
        return;
      }
      message.success(`Skill "${res?.name || 'Unknown'}" uploaded successfully`);
      runGetSkillList(queryParams, paginationParams);
    } catch (error: any) {
      message.error(`Upload failed: ${error?.message || 'Unknown error'}`);
    } finally {
      setUploading(false);
    }
  };

  const uploadProps = {
    accept: '.zip,.skill',
    showUploadList: false,
    beforeUpload: (file: File) => {
      const isValid = file.name.endsWith('.zip') || file.name.endsWith('.skill');
      if (!isValid) {
        message.error('Only .zip and .skill files are supported');
        return false;
      }
      handleUpload(file);
      return false;
    },
  };

  // Handle auto_sync toggle
  const handleAutoSyncChange = async (item: any, checked: boolean) => {
    try {
      const [err, res] = await apiInterceptors(updateSkillAutoSync(item.skill_code, checked));
      if (err) {
        message.error('Failed to update auto sync setting');
        return;
      }
      message.success(`Auto sync ${checked ? 'enabled' : 'disabled'} for ${item.name}`);
      // Update local state
      setSkillList((prev: any[]) =>
        prev.map((skill: any) =>
          skill.skill_code === item.skill_code
            ? { ...skill, auto_sync: checked }
            : skill
        )
      );
    } catch (error) {
      message.error('Failed to update auto sync setting');
    }
  };

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      if (editingSkill) {
        await apiInterceptors(updateSkill({ ...values, skill_code: editingSkill.skill_code }));
        message.success('Skill updated successfully');
      } else {
        await apiInterceptors(createSkill(values));
        message.success('Skill created successfully');
      }
      setIsModalVisible(false);
      runGetSkillList(queryParams, paginationParams);
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  };

  const handleSyncStart = async () => {
    try {
      const values = await syncForm.validateFields();
      // Reset current task before creating new one
      setCurrentSyncTask(null);
      setIsSyncProgressDrawerVisible(true);

      const [err, res] = await apiInterceptors(createSyncTask({
        repo_url: values.repo_url,
        branch: values.branch,
        force_update: values.force_update,
      }));

      if (res) {
        message.success('Sync task started');
        setIsSyncModalVisible(false);
        setCurrentSyncTask(res);
        checkSyncTaskStatus(res.task_id);
      }
    } catch (error) {
      console.error('Sync form validation failed:', error);
      message.error('Failed to start sync task');
    }
  };

  const handleSyncStop = async () => {
    if (currentSyncTask) {
      message.info('Stopping sync task...');
      // Note: Current implementation doesn't support stopping running tasks
      // This would require more complex task management
    }
  };

  const handleShowSyncProgress = async () => {
    // Load recent tasks before showing drawer
    await runGetRecentSyncTasks();
    // Set the most recent task as current if no active task
    if (!currentSyncTask || (currentSyncTask.status !== 'running' && currentSyncTask.status !== 'pending')) {
      // Get the most recent task (completed or failed)
      const recentData = await apiInterceptors(getRecentSyncTasks(1));
      if (recentData[1]?.[0]) {
        setCurrentSyncTask(recentData[1][0]);
      }
    }
    setIsSyncProgressDrawerVisible(true);
  };

  const onShowSizeChange: PaginationProps['onShowSizeChange'] = (current: number, pageSize: number) => {
    setPaginationParams(pre => ({ ...pre, page: current, page_size: pageSize }));
    runGetSkillList(queryParams, { page: current, page_size: pageSize });
  };

  const onSearch = () => {
    runGetSkillList(queryParams, paginationParams);
  };

  const goSkillDetail = (skill_code: string) => {
    router.push(`/agent-skills/detail?code=${skill_code}`);
  };

  // Sync button based on current task status
  const renderSyncButton = () => {
    const activeTask = recentSyncTasks.find(t => t.status === 'running' || t.status === 'pending');

    return (
      <Space>
        {/* Button to view sync history */}
        <Button
          icon={<HistoryOutlined />}
          onClick={handleShowSyncProgress}
        >
          Sync History
        </Button>

        {activeTask ? (
          // Show progress button when syncing
          <Button
            icon={<SyncOutlined spin={activeTask.status === 'running'} />}
            onClick={handleShowSyncProgress}
          >
            Syncing {activeTask.progress}%
          </Button>
        ) : (
          // Show normal sync button
          <Button
            icon={<GithubOutlined />}
            onClick={() => {
              syncForm.resetFields();
              setIsSyncModalVisible(true);
            }}
          >
            Sync from Git
          </Button>
        )}
      </Space>
    );
  };

  return (
    <Spin spinning={loading}>
      <div className='page-body px-5 py-4 md:px-5 md:py-6 h-[90vh] overflow-auto bg-[#FAFAFA] dark:bg-[#111]'>
        <div className='max-w-6xl xl:max-w-[1600px] 2xl:max-w-[2000px] mx-auto'>
          <div className='flex justify-between items-center mb-6'>
            <div>
              <h1 className='text-2xl font-bold tracking-tight'>{t('Agent_Skills')}</h1>
              <p className='text-muted-foreground'>Manage capabilities and tools available to your agents</p>
            </div>
            <div className='flex gap-2'>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => runGetSkillList(queryParams, paginationParams)}
              >
                Refresh
              </Button>
              {renderSyncButton()}
              <Upload {...uploadProps}>
                <Button
                  icon={<UploadOutlined />}
                  loading={uploading}
                >
                  Upload Skill
                </Button>
              </Upload>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleCreate}
                className="bg-black hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200"
              >
                Create Skill
              </Button>
            </div>
          </div>

          <div className='mb-6'>
            <Search
              placeholder="Search skills..."
              allowClear
              style={{ width: 300 }}
              value={queryParams.filter}
              onChange={e => setQueryparams(pre => ({ ...pre, filter: e.target.value }))}
              onSearch={onSearch}
            />
          </div>

          {skillList?.length ? (
            <div className='skill-grid'>
              {skillList.map((item: any, index: number) => (
                <div
                  key={index}
                  className='bg-white dark:bg-[#1f1f1f] rounded-lg shadow p-4 relative hover:shadow-md transition-all cursor-pointer border border-gray-100 dark:border-gray-800'
                  onClick={() => goSkillDetail(item.skill_code)}
                >
                  <div className='flex items-start justify-between mb-2'>
                    <div className='flex items-center gap-3'>
                      <div className='h-10 w-10 rounded-lg bg-blue-50 dark:bg-blue-900/20 flex items-center justify-center text-blue-500'>
                        {item.icon ? (
                          <img src={item.icon} alt={item.name} className="w-6 h-6 object-contain" />
                        ) : (
                          <FolderOpenFilled style={{ fontSize: '20px' }} />
                        )}
                      </div>
                      <div>
                        <h3 className='font-medium text-base line-clamp-1'>{item.name}</h3>
                        <div className="flex items-center gap-1">
                          <Tag
                            color={item.repo_url ? "green" : "default"}
                            className="mr-0 scale-90 origin-left"
                          >
                            {item.repo_url ? "Git" : "Local"}
                          </Tag>
                          {item.repo_url && (
                            <Tooltip title={item.auto_sync !== false ? "Auto sync enabled" : "Auto sync disabled"}>
                              {item.auto_sync !== false ? (
                                <CloudSyncOutlined className="text-blue-500 text-xs" />
                              ) : (
                                <CloudOutlined className="text-gray-400 text-xs" />
                              )}
                            </Tooltip>
                          )}
                        </div>
                      </div>
                    </div>
                    <div onClick={e => e.stopPropagation()}>
                      <InnerDropdown
                        menu={{
                          items: [
                            {
                              key: 'edit',
                              label: 'Edit',
                              onClick: () => handleEdit(item),
                            },
                            {
                              key: 'delete',
                              label: <span className="text-red-500">Delete</span>,
                              onClick: () => handleDelete(item),
                            },
                          ],
                        }}
                      />
                    </div>
                  </div>

                  <p className='text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-4 h-10'>
                    {item.description}
                  </p>

                  <div className='flex justify-between items-center text-xs text-gray-400 border-t border-gray-100 dark:border-gray-800 pt-3'>
                    <span>{item.author || 'Unknown Author'}</span>
                    <div className="flex items-center gap-2">
                      {item.repo_url && (
                        <div
                          className="flex items-center gap-1"
                          onClick={e => e.stopPropagation()}
                        >
                          <span className="text-[10px] text-gray-400">Auto Sync</span>
                          <Switch
                            size="small"
                            checked={item.auto_sync !== false}
                            onChange={(checked) => handleAutoSyncChange(item, checked)}
                          />
                        </div>
                      )}
                      <span>{item.version || 'v1.0.0'}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className='flex items-center justify-center h-64'>
              <Result
                status='info'
                icon={<FolderOpenFilled className='text-gray-300' />}
                title={<div className='text-gray-300'>No Skills Found</div>}
              />
            </div>
          )}

          <div className='flex justify-end mt-6'>
            <Pagination
              current={paginationParams.page}
              pageSize={paginationParams.page_size}
              showSizeChanger
              total={skillList.length}
              onChange={onShowSizeChange}
            />
          </div>
        </div>

        <Modal
          title={editingSkill ? "Edit Skill" : "Create New Skill"}
          open={isModalVisible}
          onOk={handleOk}
          onCancel={() => setIsModalVisible(false)}
        >
          <Form
            form={form}
            layout="vertical"
            initialValues={{ type: 'tool', available: true }}
          >
            <Form.Item
              name="name"
              label="Skill Name"
              rules={[{ required: true, message: 'Please enter skill name' }]}
            >
              <Input placeholder="e.g. Web Search" />
            </Form.Item>

            <Form.Item
              name="type"
              label={t('Type')}
              rules={[{ required: true }]}
            >
              <Select>
                <Option value="tool">{t('Tool')}</Option>
                <Option value="retrieval">{t('Retrieval')}</Option>
                <Option value="action">{t('Action')}</Option>
              </Select>
            </Form.Item>

            <Form.Item
              name="description"
              label={t('Description')}
              rules={[{ required: true, message: 'Please enter description' }]}
            >
              <Input.TextArea rows={4} placeholder="Describe what this skill does..." />
            </Form.Item>

            <Form.Item
              name="available"
              label="Available"
              valuePropName="checked"
            >
              <Switch />
            </Form.Item>
          </Form>
        </Modal>

        <Modal
          title="Sync from Git"
          open={isSyncModalVisible}
          onOk={handleSyncStart}
          onCancel={() => setIsSyncModalVisible(false)}
        >
          <Form
            form={syncForm}
            layout="vertical"
            initialValues={{ branch: 'main', force_update: false }}
          >
            <Form.Item
              name="repo_url"
              label="Repository URL"
              rules={[{ required: true, message: 'Please enter git repository URL' }]}
            >
              <Input placeholder="https://github.com/username/repo.git" />
            </Form.Item>

            <Form.Item
              name="branch"
              label="Branch"
            >
              <Input placeholder="main" />
            </Form.Item>

            <Form.Item
              name="force_update"
              label="Force Update"
              valuePropName="checked"
              tooltip="Overwrite existing skills with the same name"
            >
              <Switch />
            </Form.Item>
          </Form>
        </Modal>

        <Drawer
          title="Sync Progress"
          placement="right"
          width={480}
          open={isSyncProgressDrawerVisible}
          onClose={() => setIsSyncProgressDrawerVisible(false)}
          closable={true}
        >
          <div className="flex flex-col h-full">
            {currentSyncTask ? (
              <div className="flex-1 overflow-auto">
                <div className="mb-6">
                  <Text type="secondary">Repository</Text>
                  <div className="font-medium">{currentSyncTask.repo_url}</div>
                </div>

                <div className="mb-6">
                  <Text type="secondary">Status</Text>
                  <div>
                    <Tag color={
                      currentSyncTask.status === 'completed' ? 'green' :
                      currentSyncTask.status === 'failed' ? 'red' :
                      currentSyncTask.status === 'running' ? 'blue' : 'default'
                    }>
                      {currentSyncTask.status.toUpperCase()}
                    </Tag>
                  </div>
                </div>

                {currentSyncTask.status === 'running' && (
                  <div className="mb-6">
                    <Progress
                      percent={currentSyncTask.progress}
                      status="active"
                      strokeColor={{
                        '0%': '#108ee9',
                        '100%': '#87d068',
                      }}
                    />
                    <Text type="secondary" className="mt-2 block">
                      {currentSyncTask.current_step}
                    </Text>
                  </div>
                )}

                {currentSyncTask.status === 'completed' && (
                  <div className="mb-6">
                    <Progress
                      percent={100}
                      status="success"
                    />
                    <Text type="secondary" className="mt-2 block text-green-600">
                      Sync completed successfully!
                    </Text>
                  </div>
                )}

                {currentSyncTask.status === 'failed' && (
                  <div className="mb-6">
                    <Progress
                      percent={currentSyncTask.progress}
                      status="exception"
                    />
                    <Text type="secondary" className="mt-2 block text-red-600">
                      {currentSyncTask.error_msg || 'Sync failed'}
                    </Text>
                  </div>
                )}

                <div className="mb-6">
                  <Text type="secondary">Progress</Text>
                  <div>
                    {currentSyncTask.steps_completed} / {currentSyncTask.total_steps} skills
                    ({currentSyncTask.progress}%)
                  </div>
                </div>

                {currentSyncTask.synced_skills_count > 0 && (
                  <div className="mb-6">
                    <Text type="secondary">Synced Skills</Text>
                    <div>{currentSyncTask.synced_skills_count} skills synced</div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
                <SyncOutlined className="text-4xl mb-2" />
                <p>No active sync task</p>
              </div>
            )}

            <div className="border-t pt-4">
              <Text type="secondary" className="mb-2">Recent Sync Tasks</Text>
              <List
                size="small"
                dataSource={recentSyncTasks.slice(0, 3)}
                renderItem={(task: any) => (
                  <List.Item>
                    <div className="w-full">
                      <div className="flex justify-between mb-1">
                        <span className="text-xs">{new Date(task.gmt_created).toLocaleString()}</span>
                        <Tag
                          color={
                            task.status === 'completed' ? 'green' :
                            task.status === 'failed' ? 'red' :
                            task.status === 'running' ? 'blue' : 'default'
                          }
                          size="small"
                        >
                          {task.status}
                        </Tag>
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {task.repo_url}
                      </div>
                      {task.status === 'running' && task.progress > 0 && (
                        <Progress percent={task.progress} size="small" showInfo={false} />
                      )}
                    </div>
                  </List.Item>
                )}
              />
            </div>
          </div>
        </Drawer>
      </div>
    </Spin>
  );
};

export default memo(SkillPage);