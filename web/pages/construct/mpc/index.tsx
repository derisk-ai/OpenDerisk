import { apiInterceptors, postDbgptsMy } from '@/client/api';
import { IAgentPlugin } from '@/types/agent';
import { useRequest } from 'ahooks';
import { Spin } from 'antd';
import React, { useState } from 'react';
import { useRouter } from 'next/router';

const Mpc: React.FC = () => {
  const [searchValue, setSearchValue] = useState<string>('');
  const router  = useRouter();
  const {
    data: mcpList = [
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
      {},
    ],
    refresh,
    loading,
  } = useRequest<IAgentPlugin[], []>(
    async (): Promise<any> => {
      return await apiInterceptors(postDbgptsMy());
    },
    {
      manual: true,
    },
  );

  const handleSubmit = e => {
    e.preventDefault(); //
    console.log('Search');
  };

  const goMpcDetail = (id: string) => {
    return () => {
      router.push(`/construct/mpc/${id}`);
    };
  };

  return (
    <Spin spinning={loading}>
      <div className='page-body p-4 md:p-6 h-[90vh] overflow-auto'>
        <section className='py-12 md:py-14 pb-8 md:pb-10 bg-gradient-to-b from-primary/5 to-background'>
          <div className='container mx-auto px-4 md:px-6 max-w-6xl'>
            <div className='flex flex-col items-center space-y-4 text-center'>
              <h1 className='text-2xl font-bold tracking-tighter sm:text-3xl md:text-4xl lg:text-5xl'>
                Find DeRisk MCP Servers For DevOps
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
                    stroke-width='2'
                    stroke-linecap='round'
                    stroke-linejoin='round'
                    className='absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground'
                  >
                    <circle cx='11' cy='11' r='8'></circle>
                    <path d='m21 21-4.3-4.3'></path>
                  </svg>
                  <input
                    type='text'
                    className='flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 pl-9 pr-9 [&amp;::-webkit-search-cancel-button]:hidden [&amp;::-webkit-search-decoration]:hidden [&amp;::-ms-clear]:hidden'
                    placeholder='Search for MCP servers...'
                    autocomplete='off'
                    name='search'
                    value={searchValue}
                    onChange={e => {
                      setSearchValue(e?.target?.value);
                    }}
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
          <div className='container mx-auto px-4 md:px-6 max-w-6xl'>
            {/* top */}
            <div className='flex flex-col md:flex-row md:items-center justify-between mb-6'>
              <div>
                <h2 className='text-2xl font-bold tracking-tight mb-2'>Official MCP Servers</h2>
              </div>
            </div>

            {/* body */}

            <div className='grid gap-6 md:grid-cols-2 lg:grid-cols-3'>
              {mcpList?.map(item => {
                return (
                  <div className='block group cursor-pointer' onClick={goMpcDetail('dsadsa')}>
                    <div className='rounded-lg bg-card text-card-foreground shadow-sm h-full hover:shadow-md transition-all border overflow-hidden'>
                      <div className='p-4'>
                        {/* box top */}
                        <div className='flex items-center gap-3 mb-3'>
                          {/* top img */}
                          <div className='h-8 w-8 rounded-full overflow-hidden shrink-0'>
                            <img
                              alt='Firecrawl icon'
                              loading='lazy'
                              width='32'
                              height='32'
                              decoding='async'
                              data-nimg='1'
                              className='object-cover'
                              style={{ color: 'transparent' }}
                              src='https://avatars.githubusercontent.com/u/135057108?v=4'
                            />
                          </div>
                          {/* top title */}
                          <h3 className='font-medium text-base line-clamp-1'>Firecrawl</h3>

                          {/* top collection */}
                          <div className='flex items-center ml-auto text-xs text-muted-foreground'>
                            <svg
                              xmlns='http://www.w3.org/2000/svg'
                              viewBox='0 0 24 24'
                              fill='currentColor'
                              className='w-4 h-4 mr-1'
                            >
                              <path
                                fill-rule='evenodd'
                                d='M10.788 3.21c.448-1.077 1.976-1.077 2.424 0l2.082 5.007 5.404.433c1.164.093 1.636 1.545.749 2.305l-4.117 3.527 1.257 5.273c.271 1.136-.964 2.033-1.96 1.425L12 18.354 7.373 21.18c-.996.608-2.231-.29-1.96-1.425l1.257-5.273-4.117-3.527c-.887-.76-.415-2.212.749-2.305l5.404-.433 2.082-5.006z'
                                clip-rule='evenodd'
                              ></path>
                            </svg>
                            2,221
                          </div>
                        </div>
                        {/* box body */}
                        <p className='text-sm text-muted-foreground line-clamp-2 mb-3'>
                          Empowers LLMs with advanced web scraping capabilities for content extraction, crawling, and
                          search functionalities.
                        </p>
                        {/* box bottom */}
                        <div className='inline-flex items-center rounded-full border px-2.5 py-0.5 font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 text-foreground text-xs'>
                          Official
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </div>
    </Spin>
  );
};

export default Mpc;
