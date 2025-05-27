import { apiInterceptors, getMPCList, offlineMCP, startMCP } from '@/client/api';
import { InnerDropdown } from '@/new-components/common/blurredCard';
import { FolderOpenFilled } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { Form, Pagination, Result, Spin, Tooltip, message } from 'antd';
import { useRouter } from 'next/router';
import React, { memo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import CreatMpcModel from './CreatMpcModel';

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
      return await apiInterceptors(getMPCList(params, other));
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
        }
      },
      throttleWait: 300,
    },
  );

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

  const handleSubmit = e => {
    e.preventDefault();
    onSearch();
  };

  const goMpcDetail = (id: string, name: string) => {
    return () => {
      router.push(`/construct/mpc/${id}/${name}`);
    };
  };
  const onShowSizeChange: PaginationProps['onShowSizeChange'] = (current: number, pageSize: number) => {
    setPaginationParams(pre => ({ ...pre, page: current, page_size: pageSize }));

    form?.validateFields().then(values => {
      runGetMPCList(values, { page: current, page_size: pageSize });
    });
  };

  const onStopTheMCP = (item: any) => {
    const params = {
      id: item?.id,
    };
    runOfflineMCP(params);
  };

  const onStartTheMCP = (item: any) => {
    const params = {
      id: item?.id,
    };
    runStartMCP(params);
  };

  const onSearch = () => {
    runGetMPCList(queryParams, paginationParams);
  };

  return (
    <Spin spinning={loading}>
      <div className='page-body p-4 md:p-6 h-[90vh] overflow-auto'>
        <section className='py-12 md:py-14 pb-8 md:pb-10 bg-gradient-to-b from-primary/5 to-background'>
          <div className='container mx-auto px-4 md:px-6 max-w-6xl'>
            <div className='flex flex-col items-center space-y-4 text-center'>
              <h1 className='text-3xl font-bold tracking-tighter sm:text-4xl md:text-5xl lg:text-6xl'>
                Find The Best MCP Servers
              </h1>
              <p className='max-w-[700px] text-muted-foreground md:text-xl'>
                Explore our curated collection of MCP servers to connect AI to your favorite tools.
              </p>

              <form className='w-full max-w-xl mt-2' onSubmit={handleSubmit}>
                <div className='relative'>
                  <svg
                    xmlns='http://www.w3.org/2000/svg'
                    width='24'
                    height='24'
                    viewBox='0 0 24 24'
                    fill='none'
                    stroke='currentColor'
                    strokeLinecap='round'
                    strokeWidth='2'
                    strokeLinejoin='round'
                    className='absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground cursor-pointer'
                    onClick={() => onSearch()}
                  >
                    <circle cx='11' cy='11' r='8'></circle>
                    <path d='m21 21-4.3-4.3'></path>
                  </svg>
                  <input
                    type='text'
                    className='flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 pl-9 pr-9 [&amp;::-webkit-search-cancel-button]:hidden [&amp;::-webkit-search-decoration]:hidden [&amp;::-ms-clear]:hidden'
                    placeholder='Search for MCP servers...'
                    autoComplete='off'
                    name='search'
                    value={queryParams?.filter}
                    onChange={e => {
                      setQueryparams((pre: any) => ({ ...pre, filter: e.target.value }));
                    }}
                    onBlur={() => onSearch()}
                  />
                  <button type='submit' className='sr-only' aria-label='Search'>
                    Search
                  </button>
                </div>
              </form>
            </div>
          </div>
        </section>

        <section className='py-8 md:py-10'>
          <div className='container mx-auto px-4 md:px-6 '>
            {/* top */}
            <div className='flex items-center gap-4 justify-end'>
              <CreatMpcModel onSuccess={() => runGetMPCList(queryParams, paginationParams)}></CreatMpcModel>
            </div>
            <div className='flex flex-col md:flex-row md:items-center justify-between mb-6'>
              <div>
                <h2 className='text-2xl font-bold tracking-tight mb-2'>Official MCP Servers</h2>
              </div>
            </div>

            {/* body */}

            {mcpList?.length ? (
              <div className='grid gap-6 md:grid-cols-2 lg:grid-cols-3'>
                {mcpList?.map((item: any, index: number) => {
                  return (
                    <div
                      key={index}
                      className='backdrop-filter backdrop-blur-lg cursor-pointer bg-white bg-opacity-70 border-white rounded-lg shadow p-4 relative w-full h-full dark:border-[#6f7f95] dark:bg-[#6f7f95] dark:bg-opacity-60 hover:shadow-md transition-all border overflow-hidden'
                      onClick={goMpcDetail(item?.id, item?.name)}
                    >
                      <div className=' text-card-foreground  '>
                        <div className='p-4'>
                          {/* box top */}

                          <div className='flex items-center gap-3 mb-3'>
                            {/* top img */}
                            <div className='h-8 w-8 rounded-full overflow-hidden shrink-0'>
                              {item?.icon ? (
                                <img
                                  loading='lazy'
                                  width='32'
                                  height='32'
                                  className='object-cover'
                                  style={{ color: 'transparent' }}
                                  src={item?.icon}
                                />
                              ) : (
                                <span className='ant-avatar ant-avatar-circle bg-gradient-to-tr from-[#31afff] to-[#1677ff] cursor-pointer css-dev-only-do-not-override-13e4gqt'>
                                  <span className='ant-avatar-string text-[10px]'>derisk</span>
                                </span>
                              )}
                            </div>
                            {/* top title */}
                            <h3 className='font-medium text-base line-clamp-1'>{item?.name}</h3>

                            {/* top collection */}
                            <div className='flex items-center ml-auto text-xs text-muted-foreground'>
                              <svg
                                xmlns='http://www.w3.org/2000/svg'
                                viewBox='0 0 24 24'
                                fill='currentColor'
                                className='w-4 h-4 mr-1'
                              >
                                <path
                                  fillRule='evenodd'
                                  d='M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.117 3.527 1.257 5.273c.271 1.136-.964 2.033-1.96 1.425L12 18.354 7.373 21.18c-.996.608-2.231-.29-1.96-1.425l1.257-5.273-4.117-3.527c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.006z'
                                  clipRule='evenodd'
                                ></path>
                              </svg>
                              <div style={{ marginRight: '5px' }}> {item?.installed || 0}</div>

                              <div onClick={e => e.stopPropagation()}>
                                <InnerDropdown
                                  menu={{
                                    items: [
                                      {
                                        key: 'stop_mcp',
                                        label: (
                                          <span className='text-red-400' onClick={() => onStopTheMCP(item)}>
                                            {t('stop_mcp')}
                                          </span>
                                        ),
                                      },
                                      {
                                        key: 'start_mcp',
                                        label: (
                                          <span className='text-green-400' onClick={() => onStartTheMCP(item)}>
                                            {t('start_mcp')}
                                          </span>
                                        ),
                                      },
                                    ],
                                  }}
                                />
                              </div>
                            </div>
                          </div>
                          {/* box body */}
                          <Tooltip placement='top' title={item?.description}>
                            <p className='text-sm text-muted-foreground line-clamp-2 mb-3'>{item?.description}</p>
                          </Tooltip>
                          {/* box bottom */}
                          <div className='inline-flex items-center rounded-md border px-2.5 py-0.5 font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 text-foreground text-xs'>
                            {item?.type}
                          </div>
                          <div className=' rounded-lg max-w-sm mx-auto mt-2 p-1' onClick={e => e.stopPropagation()}>
                            <div className='space-y-2'>
                              <div className='flex justify-between'>
                                <div className='flex items-center'>
                                  <span className=' text-gray-500'>{`${t('mcp_version')}：`}</span>
                                  <span>{item?.version || '-'}</span>
                                </div>
                                <div className='flex items-center'>
                                  <span className=' text-gray-500'>{`${t('mcp_author')}：`}</span>
                                  <span>{item?.author || '-'}</span>
                                </div>
                              </div>
                              <div className='flex items-center'>
                                <span className=' text-gray-500'>{`${t('mcp_email')}：`}</span>
                                <span>{item?.email || '-'}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className='flex items-center justify-center '>
                <Result
                  status='info'
                  icon={<FolderOpenFilled className='text-gray-300' />}
                  title={<div className='text-gray-300'>Not Fount</div>}
                />
              </div>
            )}
          </div>
        </section>

        <section>
          <div className='container mx-auto px-4 md:px-6  flex justify-end'>
            <Pagination
              current={paginationParams?.page}
              pageSize={paginationParams?.page_size}
              showSizeChanger
              onChange={onShowSizeChange}
            ></Pagination>
          </div>
        </section>
      </div>
    </Spin>
  );
};

export default memo(Mpc);
