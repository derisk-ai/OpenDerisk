"use client"
import { apiInterceptors, getMCPList, offlineMCP, startMCP, deleteMCP } from '@/client/api';
import { InnerDropdown } from '@/components/blurred-card';
import { FolderOpenFilled, ReloadOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Form, Pagination, Result, Spin, Tooltip, Button, message, Tag, Popconfirm, Input, PaginationProps, Modal } from 'antd';
import { useRouter } from 'next/navigation';
import React, { memo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import CreatMcpModel from './CreatMcpModel';

const { Search } = Input;
const { confirm: modalConfirm } = Modal;

type FieldType = {
  name?: string;
  mcp_code?: string;
  id?: string;
  [key: string]: any;
};

const Mpc: React.FC = () => {
  const { t } = useTranslation();
  const [form] = Form.useForm();

  const [queryParams, setQueryparams] = useState({
    filter: '',
  });
  const [paginationParams, setPaginationParams] = useState({
    page: 1,
    page_size: 20,
  });

  const [mcpList, setMcpList] = useState<any>([]);
  // const [modalState, setModalState] = useState<any>(true); // Unused
  const [formData, setFormData] = useState<any>({});
  const router = useRouter();

  const { loading, run: runGetMPCList } = useRequest(
    async (
      params = {
        filter: '',
      },
      other = {
        page: 1,
        page_size: 20,
      },
    ): Promise<any> => {
      return await apiInterceptors(getMCPList(params, other));
    },
    {
      manual: false,
      onSuccess: data => {
        const [, res] = data;
        setMcpList(res?.items || []);
      },
      debounceWait: 300,
    },
  );

  const { run: runStartMCP } = useRequest(
    async (params): Promise<any> => {
      return await apiInterceptors(startMCP(params));
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          message.success(t('start_mcp_success'));
          runGetMPCList(queryParams, paginationParams);
        } else {
          message.error('Failed to start MCP');
        }
      },
      onError: (error) => {
        message.error('Failed to start MCP');
        console.error('Start MCP error:', error);
      },
      throttleWait: 300,
    },

  );
  const confirm = (item: FieldType) => {
    // 检查必要的字段是否存在
    if (!item.name || !item.mcp_code) {
      message.error('缺少必要的参数');
      return;
    }

    modalConfirm({
      title: t('delete_task'),
      content: t('delete_task_confirm'),
      okText: t('Yes'),
      cancelText: t('No'),
      onOk() {
        const params: Record<string, string> = {
          name: item.name || '',
          mcp_code: item.mcp_code || '',
        }
        return apiInterceptors(deleteMCP(params)).then(() => {
          message.success('删除成功');
          onSearch();
        });
      },
      onCancel() {},
    });
  };

  const cancel = (e: any) => {
    console.log(e);
    // message.error('Click on No');
  };
  const { run: runOfflineMCP } = useRequest(
    async (params): Promise<any> => {
      return await apiInterceptors(offlineMCP(params));
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          message.success(t('stop_mcp_success'));
          runGetMPCList(queryParams, paginationParams);
        }
      },
      throttleWait: 300,
    },
  );

  const goMcpDetail = (mcp_code: string, name: string) => {
    // 改为使用动态路由格式
    router.push(`/mcp/detail/?id=${mcp_code}&name=${name}`);
  };
  const onShowSizeChange: PaginationProps['onShowSizeChange'] = (current: number, pageSize: number) => {
    setPaginationParams(pre => ({ ...pre, page: current, page_size: pageSize }));
    runGetMPCList(queryParams, { page: current, page_size: pageSize });
  };

  const onStopTheMCP = (item: any) => {
    const params = {
      id: item?.id,
    };
    runOfflineMCP(params);
  };

  const onStartTheMCP = (item: any) => {

    const params = {
      name: item?.name,
      sse_header: item?.sse_headers,
    };
    runStartMCP(params);
  };

  const onSearch = () => {
    runGetMPCList(queryParams, paginationParams);
  };

  const editMcp = (item: any) => {
    setFormData(item);
    // setModalState(true);
  };

  return (
    <Spin spinning={loading}>
      <div className='page-body p-4 md:p-6 h-[90vh] overflow-auto bg-[#FAFAFA] dark:bg-[#111]'>
        <div className='max-w-6xl mx-auto'>
          {/* Header */}
          <div className='flex justify-between items-center mb-6'>
            <div>
              <h1 className='text-2xl font-bold tracking-tight'>AIOps MCP Servers</h1>
              <p className='text-muted-foreground'>Explore our curated collection of MCP servers to connect AI to your favorite tools.</p>
            </div>
            <div className='flex gap-2 items-center'>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => runGetMPCList(queryParams, paginationParams)}
              >
                Refresh
              </Button>
              <CreatMcpModel formData={formData} setFormData={setFormData} onSuccess={() => runGetMPCList(queryParams, paginationParams)}></CreatMcpModel>
            </div>
          </div>

          {/* Search */}
          <div className='mb-6'>
            <Search
              placeholder="Search for MCP servers..."
              allowClear
              style={{ width: 300 }}
              value={queryParams?.filter}
              onChange={e => setQueryparams((pre: any) => ({ ...pre, filter: e.target.value }))}
              onSearch={onSearch}
            />
          </div>

          {/* List */}
          {mcpList?.length ? (
            <div className='grid gap-6 md:grid-cols-2 lg:grid-cols-3'>
              {mcpList?.map((item: any, index: number) => {
                return (
                  <div
                    key={index}
                    className='bg-white dark:bg-[#1f1f1f] rounded-lg shadow p-4 relative hover:shadow-md transition-all cursor-pointer border border-gray-100 dark:border-gray-800'
                    onClick={() => goMcpDetail(item?.mcp_code, item?.name)}
                  >
                    <div className='flex items-start justify-between mb-2'>
                      <div className='flex items-center gap-3'>
                        {/* Icon */}
                        <div className='h-10 w-10 rounded-lg shrink-0 overflow-hidden flex items-center justify-center bg-blue-50 dark:bg-blue-900/20'>
                          {item?.icon ? (
                            <img
                              loading='lazy'
                              className='w-full h-full object-cover'
                              src={item?.icon}
                              alt={item?.name}
                            />
                          ) : (
                            <span className='text-blue-500 font-bold text-xs'>
                              MCP
                            </span>
                          )}
                        </div>
                        {/* Title & Status */}
                        <div>
                          <h3 className='font-medium text-base line-clamp-1'>{item?.name}</h3>
                          <div className="flex gap-1 mt-1">
                            {item?.type && <Tag className="mr-0 text-[10px] scale-90 origin-left">{item?.type}</Tag>}
                            {item?.available ? (
                              <Tag color="#87d068" className="mr-0 text-[10px] scale-90 origin-left">{t('mcp_online')}</Tag>
                            ) : (
                              <Tag className="mr-0 text-[10px] scale-90 origin-left">{t('mcp_offline')}</Tag>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Dropdown Menu */}
                      <div onClick={e => e.stopPropagation()}>
                        <InnerDropdown
                          menu={{
                            items: [
                              item?.available ? {
                                key: 'stop_mcp',
                                label: (
                                  <span className='text-red-400' onClick={() => onStopTheMCP(item)}>
                                    {t('stop_mcp')}
                                  </span>
                                ),
                              } : {
                                key: 'start_mcp',
                                label: (
                                  <span className='text-green-400' onClick={() => onStartTheMCP(item)}>
                                    {t('start_mcp')}
                                  </span>
                                ),
                              },
                              {
                                key: 'edit',
                                label: t('Edit'),
                                onClick: () => editMcp(item),
                              },
                              {
                                key: 'delete',
                                label: <span className="text-red-500">{t('Delete')}</span>,
                                onClick: () => {
                                  // Confirm handled by InnerDropdown item or we need to wrap it?
                                  // InnerDropdown items usually are just clickable. 
                                  // We can use a custom Render for the menu item if we want Popconfirm, 
                                  // or just use Modal.confirm style. 
                                  // For now let's just use the confirm function which (doesn't) show a dialog but deletes?
                                  // The original code used Popconfirm on the button.
                                  // Since this is in a dropdown, we might want to just call confirm(item) but 
                                  // ideally we should show a confirmation.
                                  // Let's use Modal.confirm logic or simple confirm() for now to match the "clean" style,
                                  // or we can rely on `confirm` function to just do it (original code had Popconfirm).
                                  // Let's stick to simple click for now, maybe add a confirm dialog later if needed.
                                  confirm(item);
                                },
                              },
                            ].filter(Boolean) as any,
                          }}
                        />
                      </div>
                    </div>

                    {/* Description */}
                    <p className='text-sm text-gray-500 dark:text-gray-400 line-clamp-2 mb-4 h-10'>
                      {item?.description}
                    </p>

                    {/* Footer Info */}
                    <div className='flex justify-between items-center text-xs text-gray-400 border-t border-gray-100 dark:border-gray-800 pt-3'>
                      <div className="flex gap-2">
                        <span>{item?.author || 'Unknown'}</span>
                      </div>
                      <span>{item?.version || 'v1.0.0'}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className='flex items-center justify-center h-64'>
              <Result
                status='info'
                icon={<FolderOpenFilled className='text-gray-300' />}
                title={<div className='text-gray-300'>No MCP Servers Found</div>}
              />
            </div>
          )}

          {/* Pagination */}
          <div className='flex justify-end mt-6'>
            <Pagination
              current={paginationParams?.page}
              pageSize={paginationParams?.page_size}
              showSizeChanger
              onChange={onShowSizeChange}
            />
          </div>
        </div>
      </div>
    </Spin>
  );
};

export default memo(Mpc);