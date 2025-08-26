"use client"
import { ChatContext } from '@/contexts';
import {
  apiInterceptors,
  delApp,
  getAppAdmins,
  getAppList,
  newDialogue,
  publishAppNew,
  unPublishApp,
  updateAppAdmins,
} from '@/client/api';
import BlurredCard, { ChatButton, InnerDropdown } from '@/components/blurred-card';
import { IApp } from '@/types/app';
import { BulbOutlined, PlusOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons';
import { useDebounceFn, useRequest } from 'ahooks';
import { App as AntdApp, Button, Input, Pagination, Popover, Segmented, SegmentedProps, Spin, Tag, message } from 'antd';
import moment from 'moment';
import { useSearchParams, useRouter } from 'next/navigation';
import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import CreateAppModal from '@/components/create-app-modal';

type TabKey = 'all' | 'published' | 'unpublished';
type ModalType = 'edit' | 'add';

export default function App() {
  const { modal, notification } = AntdApp.useApp();
  const router = useRouter();
  const { t } = useTranslation();
  const [open, setOpen] = useState<boolean>(false);
  const [spinning, setSpinning] = useState<boolean>(false);
  const [activeKey, setActiveKey] = useState<TabKey>('all');
  const [apps, setApps] = useState<IApp[]>([]);
  const [modalType, setModalType] = useState<ModalType>('add');
  const { model, setAgent: setAgentToChat, setCurrentDialogInfo } = useContext(ChatContext);
  const searchParams = useSearchParams();
  const openModal = searchParams?.get('openModal') ?? '';
  const [filterValue, setFilterValue] = useState('');
  const [curApp] = useState<IApp>();
  const [adminOpen, setAdminOpen] = useState<boolean>(false);
  const [admins, setAdmins] = useState<string[]>([]);
  // 分页信息
  const totalRef = useRef<{
    current_page: number;
    total_count: number;
    total_page: number;
    page_size:number;
  } | null>(null);

  const handleCreate = () => {
    setModalType('add');
    setOpen(true);
    localStorage.removeItem('new_app_info');
  };

  const handleEdit = (app: any) => {
    localStorage.setItem('new_app_info', JSON.stringify({ ...app, isEdit: true }));
    router.replace(`/application/structure/?app_code=${app.app_code}`);
  };

  const getListFiltered = useCallback(() => {
    let published = undefined;
    if (activeKey === 'published') {
      published = 'true';
    }
    if (activeKey === 'unpublished') {
      published = 'false';
    }
    initData({ name_filter: filterValue, published });
  }, [activeKey, filterValue]);

  const handleTabChange = (activeKey: string) => {
    setActiveKey(activeKey as TabKey);
  };

  // 发布或取消发布应用
  const { run: operate } = useRequest(
    async (app: IApp) => {
      if (app.published === 'true') {

        return await apiInterceptors(unPublishApp(app.app_code));
      } else {
        return await apiInterceptors(publishAppNew({ app_code: app.app_code }));
      }
    },
    {
      manual: true,
      onSuccess: data => {
        if (data[2]?.success) {
          message.success('操作成功');
        }
        getListFiltered();
      },
    },
  );

  const initData = useDebounceFn(
    async params => {
      setSpinning(true);
      const obj: any = {
        page: 1,
        page_size: 12,
        ...params,
      };
      const [error, data] = await apiInterceptors(getAppList(obj), notification);
      if (error) {
        setSpinning(false);
        return;
      }
      if (!data) return;
      setApps(data?.app_list || []);
      totalRef.current = {
        current_page: data?.current_page || 1,
        total_count: data?.total_count || 0,
        total_page: data?.total_page || 0,
        page_size: 12,
      };
      setSpinning(false);
    },
    {
      wait: 500,
    },
  ).run;

  const showDeleteConfirm = (app: IApp) => {
    modal.confirm({
      title: t('Tips'),
      icon: <WarningOutlined />,
      content: `do you want delete the application?`,
      okText: 'Yes',
      okType: 'danger',
      cancelText: 'No',
      async onOk() {
        await apiInterceptors(delApp({ app_code: app.app_code }));
        getListFiltered();
      },
    });
  };

  useEffect(() => {
    if (openModal) {
      setModalType('add');
      setOpen(true);
    }
  }, [openModal]);

  const languageMap = {
    en: t('English'),
    zh: t('Chinese'),
  };
  const handleChat = async (app: IApp) => {
    // 不区分 原生应用跳转 和 自定义应用
    const [, res] = await apiInterceptors(newDialogue({ app_code: app.app_code }));
    if (res) {
      setAgentToChat?.(app.app_code);
      router.push(`/chat/?app_code=${app.app_code}&conv_uid=${res.conv_uid}`);
    }
  };
  const items: SegmentedProps['options'] = [
    {
      value: 'all',
      label: t('apps'),
    },
    {
      value: 'published',
      label: t('published'),
    },
    {
      value: 'unpublished',
      label: t('unpublished'),
    },
  ];

  const onSearch = async (e: any) => {
    const v = e.target.value;
    setFilterValue(v);
  };

  // 获取应用权限列表
  const { run: getAdmins, loading } = useRequest(
    async (appCode: string) => {
      const [, res] = await apiInterceptors(getAppAdmins(appCode));

      return res ?? [];
    },
    {
      manual: true,
      onSuccess: data => {
        setAdmins(data);
      },
    },
  );

  // 更新应用权限
  const { run: updateAdmins, loading: adminLoading } = useRequest(
    async (params: { app_code: string; admins: string[] }) => await apiInterceptors(updateAppAdmins(params)),
    {
      manual: true,
      onSuccess: () => {
        message.success('更新成功');
      },
    },
  );

  useEffect(() => {
    if (curApp) {
      getAdmins(curApp.app_code);
    }
  }, [curApp, getAdmins]);

  useEffect(() => {
    getListFiltered();
  }, [getListFiltered]);

  return (
    <Spin spinning={spinning}>
      <div className='h-screen w-full p-4 md:p-6 flex flex-col'>
        <div className='flex justify-between items-center mb-4 sticky'>
          <div className='flex items-center gap-4'>
            <Segmented
              className='backdrop-filter backdrop-blur-lg bg-white/30 border border-white rounded-lg shadow p-1 dark:border-[#6f7f95] dark:bg-[#6f7f95]/60 [&_.ant-segmented-item-selected]:bg-[#0c75fc]/80 [&_.ant-segmented-item-selected]:text-white'
              options={items as any}
              onChange={handleTabChange}
              value={activeKey}
            />
            <Input
              variant='filled'
              value={filterValue}
              prefix={<SearchOutlined />}
              placeholder={t('please_enter_the_keywords')}
              onChange={onSearch}
              onPressEnter={onSearch}
              allowClear
              className='w-[230px] h-[40px] border-1 border-white backdrop-filter backdrop-blur-lg bg-white/30  dark:border-[#6f7f95] dark:bg-[#6f7f95]/60'
            />
          </div>

          <Button
            className='border-none text-white bg-button-gradient flex items-center'
            icon={<PlusOutlined className='text-base' />}
            onClick={handleCreate}
          >
            {t('create_app')}
          </Button>
        </div>
        <div className='flex-1 flex-col w-full pb-12 mx-[-8px] overflow-y-auto'>
          <div className='flex flex-wrap flex-1 overflow-y-auto'>
            {apps.map(item => {
              return (
                <BlurredCard
                  key={item.app_code}
                  code={item.app_code}
                  name={item.app_name}
                  description={item.app_describe}
                  logo={item.icon || '/icons/colorful-plugin.png'}
                  RightTop={
                    <div className='flex items-center gap-2'>
                      <Popover
                        content={
                          <div className='flex flex-col gap-2'>
                            <div className='flex items-center gap-2'>
                              <BulbOutlined
                                style={{
                                  color: 'rgb(252,204,96)',
                                  fontSize: 12,
                                }}
                              />
                              <span className='text-sm text-gray-500'>{t('copy_url')}</span>
                            </div>
                            <div className='flex items-center gap-2'>
                              <BulbOutlined
                                style={{
                                  color: 'rgb(252,204,96)',
                                  fontSize: 12,
                                }}
                              />
                              <span className='text-sm text-gray-500'>{t('double_click_open')}</span>
                            </div>
                          </div>
                        }
                      ></Popover>
                      <InnerDropdown
                        menu={{
                          items: [
                            {
                              key: 'publish',
                              label: (
                                <span
                                  onClick={e => {
                                    e.stopPropagation();
                                    operate(item);
                                  }}
                                >
                                  {item.published === 'true' ? t('unpublish') : t('publish')}
                                </span>
                              ),
                            },
                            {
                              key: 'del',
                              label: (
                                <span
                                  className='text-red-400'
                                  onClick={e => {
                                    e.stopPropagation();
                                    showDeleteConfirm(item);
                                  }}
                                >
                                  {t('Delete')}
                                </span>
                              ),
                            },
                          ],
                        }}
                      />
                    </div>
                  }
                  Tags={
                    <div>
                      <Tag>{languageMap[item.language]}</Tag>
                      <Tag>{item.team_mode}</Tag>
                      <Tag>{item.published ? t('published') : t('unpublished')}</Tag>
                    </div>
                  }
                  rightTopHover={false}
                  LeftBottom={
                    <div className='flex gap-2'>
                      <span>{item.owner_name}</span>
                      <span>•</span>
                      {item?.updated_at && <span>{moment(item?.updated_at).fromNow() + ' ' + t('update')}</span>}
                    </div>
                  }
                  RightBottom={
                    <ChatButton
                      onClick={() => {
                        handleChat(item);
                      }}
                    />
                  }
                  onClick={() => {
                    handleEdit(item);
                  }}
                  scene={item?.team_context?.chat_scene || 'chat_agent'}
                />
              );
            })}
          </div>
          <div className='w-full flex justify-end shrink-0 pb-12 pt-1'>
            <Pagination
              showSizeChanger={false}
              total={totalRef.current?.total_count || 0}
              pageSize={12}
              current={totalRef.current?.current_page}
              onChange={async (page, _page_size) => {
                await initData({ page });
              }}
            />
          </div>
        </div>
        {open && (
          <CreateAppModal
            open={open}
            onCancel={() => {
              setOpen(false);
            }}
            refresh={initData}
            type={modalType}
          />
        )}
      </div>
    </Spin>
  );
}
