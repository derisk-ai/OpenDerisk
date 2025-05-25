import { ChatContext } from '@/app/chat-context';
import { apiInterceptors, getMPCListQuery, mcpToolList, mcpToolRun } from '@/client/api';
import { DiffOutlined, RedoOutlined } from '@ant-design/icons';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import JsonView from '@uiw/react-json-view';
import { githubDarkTheme } from '@uiw/react-json-view/githubDark';
import { githubLightTheme } from '@uiw/react-json-view/githubLight';
import { useRequest } from 'ahooks';
import { Button, Card, Form, Input, Select, Spin, message } from 'antd';
import classNames from 'classnames';
import { useRouter } from 'next/router';
import React, { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import './index.css';
const titleOption = [
  {
    label: 'Tools',
    value: 'Tools',
  },
];

const MpcDetail: React.FC = () => {
  const router = useRouter();
  const { mode } = useContext(ChatContext);
  const { t } = useTranslation();
  const [alignment, setAlignment] = useState<string | null>('Tools');
  const [requestType, setRequestType] = useState<string>('HTTP');
  const [mcpInfo, setMcpInfo] = useState<any>({});
  const [selectUrl, setSelectUrl] = useState<any>('');
  const [connect, setConnect] = useState<any>('');
  const [toolList, setToolList] = useState<Array<{ name: string; description: string; param_schema: any }>>([]);
  const theme = mode === 'dark' ? githubDarkTheme : githubLightTheme;
  const queryParams: any = router.query;
  const [form] = Form.useForm();

  const {
    loading: runLoading,
    run: runMcpToolRun,
    data: runData,
  } = useRequest(
    async (
      params = {
        name: queryParams.name,
      },
    ): Promise<any> => {
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
              setConnect(JSON.stringify(res) || '');
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
      return await apiInterceptors(
        getMPCListQuery({
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
      return await apiInterceptors(mcpToolList(params));
    },
    {
      manual: false,
      onSuccess: data => {
        const [, , res] = data;
        if (res?.success) {
          // res?.data ||
          setToolList([
            {
              name: 'list_servers',
              description: 'List all registered MCP servers',
              param_schema: {},
            },
            {
              name: 'fetch_fetch',
              description:
                'Fetches a URL from the internet and optionally extracts its contents as markdown.\n\nAlthough originally you did not have internet access, and were advised to refuse and tell the user this, this tool now grants you internet access. Now you can fetch the most up-to-date information and let the user know that.',
              param_schema: {
                url: {
                  type: 'string',
                  title: 'Url',
                  description: 'URL to fetch',
                  required: true,
                },
                max_length: {
                  type: 'integer',
                  title: 'Max Length',
                  description: 'Maximum number of characters to return.',
                  required: false,
                  default: 5000,
                },
                start_index: {
                  type: 'integer',
                  title: 'Start Index',
                  description:
                    'On return output starting at this character index, useful if a previous fetch was truncated and more context is required.',
                  required: false,
                },
                raw: {
                  type: 'boolean',
                  title: 'Raw',
                  description: 'Get the actual HTML content of the requested page, without simplification.',
                  required: false,
                },
              },
            },
          ]);
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

    await runMcpToolRun({ name: queryParams?.name, ..._params });
  };

  const formData: any = useMemo(() => {
    return toolList?.find(item => item?.name === selectUrl)?.param_schema || {};
  }, [selectUrl]);

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
                <span className='ant-avatar ant-avatar-circle bg-gradient-to-tr from-[#31afff] to-[#1677ff] cursor-pointer css-dev-only-do-not-override-13e4gqt'>
                  <span className='ant-avatar-string text-[10px]'>derisk</span>
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
                  {titleOption?.map(item => {
                    return (
                      <>
                        <ToggleButton
                          className={`border-0 rounded-[6px] ${mode === 'light' ? 'text-black' : 'text-white'}`}
                          value={item?.value}
                        >
                          {item?.label}
                        </ToggleButton>
                      </>
                    );
                  })}
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
                      {/* <div>
                        <h2 className='text-xl md:text-2xl font-semibold mb-3'>About</h2>
                        <p className='text-sm md:text-base leading-relaxed'>
                          Magic empowers developers to create beautiful, modern UI components instantly by using natural
                          language descriptions. It seamlessly integrates with popular IDEs like Cursor, Windsurf, and
                          VSCode (with Cline), providing an AI-powered workflow that streamlines UI development. Access
                          a vast library of pre-built, customizable components inspired by 21st.dev, and see your
                          creations in real-time with full TypeScript and SVGL support. Enhance existing components with
                          advanced features and animations to accelerate your UI development process.
                        </p>
                      </div> */}
                      {toolList?.map((item, index) => {
                        return (
                          <div
                            key={index}
                            onClick={() => handleSelectUsrl(item?.name)}
                            className='cursor-pointer hover:text-[#0069fe] transition-all'
                          >
                            <h2 className='text-xl md:text-2xl font-semibold mb-4 '>{item.name}</h2>
                            <ul>
                              <li className='flex items-start gap-3 py-1 list-disc'>
                                <span
                                  className='w-2 h-2 rounded-full  mt-2 shrink-0'
                                  style={{
                                    backgroundColor: selectUrl === item?.name ? '#0069fe' : '#000000',
                                  }}
                                ></span>
                                <span className='text-sm md:text-base'>{item?.description}</span>
                              </li>
                            </ul>
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
                  <div className='flex-1'>{t('parameter_name')}</div>
                  <div className='flex-1'>{t('parameter_value')}</div>
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
                        {t('trial_run')}
                      </Button>
                    </Form.Item>
                  </Form>
                </div>
              </div>
            </Card>

            <Card
              title={
                <div className='flex justify-between'>
                  {t('run_results')}{' '}
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

export default MpcDetail;
