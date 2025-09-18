"use client"
import { ChatContext } from '@/contexts';
import { apiInterceptors, getMCPListQuery, mcpToolList, mcpToolRun } from '@/client/api';
import { DiffOutlined, RedoOutlined } from '@ant-design/icons';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import JsonView from '@uiw/react-json-view';
import { githubDarkTheme } from '@uiw/react-json-view/githubDark';
import { githubLightTheme } from '@uiw/react-json-view/githubLight';
import { useRequest } from 'ahooks';
import { Button, Card, Form, Input, Select, Spin, App } from 'antd';
import classNames from 'classnames';
import { useSearchParams } from 'next/navigation';
import React, { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import '../index.css';

export default function MpcDetail() {
  const searchParams = useSearchParams();
  const { mode } = useContext(ChatContext);
  const { t } = useTranslation();
  const { message } = App.useApp();
  const titleOption = [
    {
      label: t('mcp_tools'),
      value: 'Tools',
    },
  ];
  const [alignment, setAlignment] = useState<string | null>('Tools');
  const [requestType, setRequestType] = useState<string>('HTTP');
  const [mcpInfo, setMcpInfo] = useState<any>({});
  const [selectUrl, setSelectUrl] = useState<any>('');
  const [connect, setConnect] = useState<any>('');
  const [toolList, setToolList] = useState<Array<{ name: string; description: string; param_schema: any }>>([]);
  const theme = mode === 'dark' ? githubDarkTheme : githubLightTheme;
  const queryParams = {
    id: searchParams.get('id') || '',
    name: searchParams.get('name') || ''
  };
  const [form] = Form.useForm();

  const {
    loading: runLoading,
    run: runMcpToolRun,
    data: runData,
  } = useRequest(
    async (params: any): Promise<any> => {
      return await apiInterceptors(mcpToolRun(params));
    },
    {
      manual: true,
      onSuccess: data => {
        const [, , res] = data;

        if (res?.success) {
          message.success(t('success'));
          if (res?.data !== null && typeof res?.data === 'object') {
            try {
              setConnect(res || '');
            } catch (error) {
              console.log(error);
              setConnect('');
            }
          }
        }
      },
      debounceWait: 300,
    },
  );

  const { loading: mcpQueryLoading } = useRequest(
    async (): Promise<any> => {
      // 确保 name 参数存在再发起请求
      if (!queryParams.name) {
        console.error('Missing name parameter');
        return Promise.reject('Missing name parameter');
      }
      return await apiInterceptors(
        getMCPListQuery({
          name: queryParams.name,
        }),
      );
    },
    {
      manual: false,
      onSuccess: data => {
        const [, res] = data;
        setMcpInfo(res || {});
      },
      debounceWait: 300,
    },
  );

  const { loading: listLoading, run: runToolList } = useRequest(
    async (
      params = {
        name: queryParams.name,
      },
    ): Promise<any> => {
      // 确保 name 参数存在再发起请求
      if (!params.name) {
        console.error('Missing name parameter for tool list');
        return Promise.reject('Missing name parameter');
      }
      return await apiInterceptors(mcpToolList(params));
    },
    {
      manual: false,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.data) {
          setToolList(res?.data || []);
        }
      },
      debounceWait: 300,
    },
  );

  const handleAlignment = (event: React.MouseEvent<HTMLElement>, newAlignment: string | null) => {
    console.log(event);
    if (newAlignment === alignment || !newAlignment) return false;
    setAlignment(newAlignment);
  };

  const handleCopy = () => {
    navigator.clipboard
      .writeText(connect)
      .then(() => {
        message.success(t('success'));
      })
      .catch(err => message.error(err));
  };

  const handleRefparams = async () => {
    let params = {};
    await form
      .validateFields()
      .then(values => {
        params = values;
      })
      .catch(() => {
        params = false;
      });
    return params;
  };

  const handleSelectUsrl = async (key: string) => {
    if (key === selectUrl) return;
    setSelectUrl(key);
    const _params = await handleRefparams();
  };

  const handleRefresh = async () => {
    await runToolList({ name: queryParams?.name });
  };

  const onGoRun = async () => {
    if (!selectUrl) return message.warning(t('please_select_mcp'));
    const _params = await handleRefparams();
    if (!_params) {
      message.error(t('form_required'));
      return;
    }

    await runMcpToolRun({
      name: queryParams?.name,
  
      params:{
        name: selectUrl,
        arguments: {
          ..._params,
        },
      }
     
    });
  };

  const formData: any = useMemo(() => {
    return toolList?.find(item => item?.name === selectUrl)?.param_schema || {};
  }, [selectUrl]);

  // 如果参数还未就绪，显示加载状态
  if (!queryParams.name || !queryParams.id) {
    return (
      <div className='page-body p-4 md:p-6 h-[90vh] overflow-auto flex items-center justify-center'>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <Spin spinning={listLoading || runLoading || mcpQueryLoading}>
      <div className='page-body p-4 md:p-6 h-[90vh] overflow-auto'>
        <header className='mb-8 pb-6 border-b'>
          <div className='flex items-center gap-3 mb-3'>
            <div className='relative h-8 w-8 overflow-hidden rounded-full'>
              {mcpInfo?.icon ? (
                <img
                  decoding='async'
                  data-nimg='fill'
                  className='object-contain'
                  src={mcpInfo?.icon}
                  style={{ position: 'absolute', height: '100%', width: '100%', inset: '0px', color: 'transparent' }}
                />
              ) : (
                <span
                  style={{ borderRadius: '50%', lineHeight: '27px' }}
                  className='inline-block w-[32px] h-[32px] text-white text-center rounded-full'
                >
                  <span className='ant-avatar-string text-[10px]'>derisk22</span>
                </span>
              )}
            </div>
            <h1 className='text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight break-words'>{mcpInfo?.name}</h1>
          </div>

          <p className='text-base md:text-lg text-muted-foreground max-w-prose'>{mcpInfo?.description}</p>
        </header>
        <div className='mb-3 flex flex-nowrap'>
          <Input
            size='large'
            addonBefore={
              <Select
                placeholder={requestType}
                style={{ width: 150 }}
                value={requestType}
                options={[{ label: 'HTTP', value: 'HTTP' }]}
                onChange={e => setRequestType(e)}
              />
            }
            value={mcpInfo?.sse_url}
            disabled
          />
        </div>
        <div className='grid grid-cols-1 md:grid-cols-5 gap-6 md:gap-8'>
          <div className='md:col-span-3'>
            <Card dir='ltr' data-orientation='horizontal' className='w-full'>
              <div className='flex items-center justify-between mb-1 flex-wrap'>
                <ToggleButtonGroup
                  value={alignment}
                  exclusive
                  onChange={handleAlignment}
                  aria-label='text alignment'
                  className='p-1 h-12  '
                >
                  {titleOption?.map(item => (
                    <ToggleButton
                      key={item.value}
                      className={`border-0 rounded-[6px] ${mode === 'light' ? 'text-black' : 'text-white'}`}
                      value={item?.value}
                    >
                      {item?.label}
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>

                <div className='flex items-center gap-2'>
                  <Button type='text' icon={<RedoOutlined className='text-2xl' onClick={handleRefresh} />}></Button>
                </div>
              </div>
              {/* body left */}
              <div className='ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 mt-6'>
                <div className='rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden'>
                  {alignment === 'Tools' && (
                    <div className='p-5 pt-6 space-y-8'>
                      {toolList?.map((item, index) => {
                        return (
                          <div
                            key={index}
                            onClick={() => handleSelectUsrl(item?.name)}
                            style={{
                              backgroundColor: selectUrl === item?.name ? '#0069fe' : '#fff',
                              color: selectUrl === item?.name ? '#fff' : '#000',
                            }} 
                            className={`cursor-pointer transition-all p-2 rounded-lg ${
                              selectUrl === item?.name ? '' : 'hover:text-[#0069fe]'
                            }`}
                            
                          >
                            <div className='p-4 rounded-lg border transition-all hover:shadow-md' 
                               style={{
                               backgroundColor: selectUrl === item?.name ? '#0069fe' : '#f9f9f9',
                               color: selectUrl === item?.name ? '#fff' : '#333',
                               }}>
                              <h2 
                              className='text-lg md:text-xl font-bold mb-2 p-2 rounded' 
                              style={{
                                backgroundColor: selectUrl === item?.name ? '#0056d2' : '#e6f7ff',
                                color: selectUrl === item?.name ? '#fff' : '#0056d2',
                              }}>
                              {item.name}
                              </h2>
                              <p 
                              className='text-sm md:text-base leading-relaxed' 
                              style={{
                                color: selectUrl === item?.name ? '#d1eaff' : '#888',
                              }}>
                              {item?.description}
                              </p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            </Card>
          </div>
          <div className='space-y-6 md:col-span-2'>
            <Card
              title={
                <div className='flex'>
                  <div className='flex-1'>{t('mcp_parameter_name')}</div>
                  <div className='flex-1'>{t('mcp_parameter_value')}</div>
                </div>
              }
            >
              <div className='flex'>
                <div className='w-full'>
                  <Form className='font-[400]' style={{ width: '100%' }} form={form}>
                    {Object.keys(formData || {})?.map((item, index) => {
                      return (
                        <Form.Item
                          key={item + index}
                          label={formData?.[item]?.title}
                          name={item}
                          className='w-full'
                          rules={[{ required: formData?.[item]?.required, message: `${t('please_enter')}${item}` }]}
                        >
                          <div className='flex w-full'>
                            <Input
                              className='flex-1'
                              placeholder={formData?.[item]?.description}
                              defaultValue={formData?.[item]?.default}
                            />
                          </div>
                        </Form.Item>
                      );
                    })}

                    <Form.Item>
                      <Button type='primary' htmlType='submit' className='w-full' onClick={onGoRun}>
                        {t('mcp_trial_run')}
                      </Button>
                    </Form.Item>
                  </Form>
                </div>
              </div>
            </Card>

            <Card
              title={
                <div className='flex justify-between'>
                  {t('mcp_run_results')}{' '}
                  <Button type='text' icon={<DiffOutlined className='text-[18px]' />} onClick={handleCopy} />
                </div>
              }
            >
              {runData?.[3]?.data?.success ? (
                <JsonView
                  style={{ ...theme, width: '100%', padding: 10, overflow: 'auto' }}
                  className={classNames({
                    'bg-[#fafafa]': mode === 'light',
                  })}
                  value={connect}
                  enableClipboard={false}
                  displayDataTypes={false}
                  objectSortKeys={false}
                />
              ) : (
                <div className='text-red-500'>{runData?.[3]?.data?.err_msg}</div>
              )}
            </Card>
          </div>
        </div>
      </div>
    </Spin>
  );
};