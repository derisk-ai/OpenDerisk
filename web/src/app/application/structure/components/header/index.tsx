import { publishAppNew } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleOutlined, ExclamationCircleFilled, CloudUploadOutlined, LeftOutlined, DownOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Dropdown, Modal, Button, Tag, Space, Divider } from 'antd';
import { useRouter } from 'next/navigation';
import { useContext, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Image from 'next/image';

function Header() {
  const { t } = useTranslation();
  const { modal } = App.useApp();
  const [publishModalOpen, setPublishModalOpen] = useState(false);
  const { appInfo, queryAppInfo, refreshAppInfo, fetchUpdateAppLoading, refreshAppInfoLoading, setAppInfo, refetchVersionData, versionData } = useContext(AppContext);
  const router = useRouter();

  // 发布应用
  const { runAsync: fetchPublishApp, loading: fetchPublishAppLoading } = useRequest(
    async params => await publishAppNew(params),
    {
      manual: true,
      onSuccess: async () => {
        modal.success({
          content: t('header_publish_success'),
        });
        if (typeof refreshAppInfo === 'function') {
          await refreshAppInfo();
        }
        if (typeof refetchVersionData === 'function') {
          await refetchVersionData();
        }
      },
      onError: () => {
        modal.error({
          content: t('header_publish_failed'),
        });
      }
    },
  );

  const handlePublishOk = async () => {
    if (typeof refreshAppInfo === 'function') {
      await fetchPublishApp(appInfo);
      setPublishModalOpen(false);
    }
  };

  const versionItems = useMemo(() => {
    // @ts-ignore
    return (
      versionData?.data?.data?.items?.map((option: any, index: number) => {
        return {
          ...option,
          key: option.version_info,
          label: (
            <div className="flex items-center justify-between min-w-[150px]">
              <span className={option.version_info === appInfo?.config_version ? 'font-medium text-blue-600' : 'text-gray-700'}>
                {option.version_info}
              </span>
              {option.version_info === appInfo?.config_version && <CheckCircleOutlined className='ml-2 text-green-500' />}
            </div>
          ),
        };
      }) || [{}]
    );
  }, [versionData, appInfo?.config_version]);

  const handleMenuClick = async (event: any) => {
    const versionInfo = versionData?.data?.data?.items.find((item: any) => item.version_info === event.key);
    if (versionInfo) {
      if (typeof queryAppInfo === 'function') {
        queryAppInfo(appInfo.app_code, versionInfo.code);
      }
    }
  };

  const menuProps = {
    items: versionItems,
    onClick: handleMenuClick,
  };

  return (
    <div className='flex items-center justify-between w-full h-16 px-4 border-b border-gray-200 bg-white shadow-sm z-20'>
      <div className='flex items-center gap-4'>
        <Button 
          type="text" 
          icon={<LeftOutlined />} 
          onClick={() => router.replace('/application/app')}
          className="text-gray-500 hover:text-gray-800"
        />
        
        <Divider type="vertical" className="h-6 bg-gray-300 mx-0" />
        
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg overflow-hidden border border-gray-100 shadow-sm">
            <Image 
              src={appInfo.icon || '/agents/agent1.jpg'} 
              alt='App Icon' 
              width={40} 
              height={40}
              className="object-cover"
            />
          </div>
          
          <div className="flex flex-col">
            <div className='font-bold text-gray-800 text-base leading-tight flex items-center gap-2'>
              {appInfo?.app_name || '--'}
              {appInfo?.config_version && (
                <Dropdown menu={menuProps} trigger={['click']}>
                  <Tag className="cursor-pointer m-0 border-0 bg-gray-100 hover:bg-gray-200 text-gray-500 rounded px-2 py-0 text-xs font-normal flex items-center gap-1 transition-colors">
                    {appInfo?.config_version} <DownOutlined className="text-[10px]" />
                  </Tag>
                </Dropdown>
              )}
            </div>
            
            <div className='text-xs text-gray-400 flex items-center mt-1'>
               {fetchUpdateAppLoading ? (
                  <span className="flex items-center gap-1 text-blue-500">
                     <ClockCircleOutlined spin /> Saving...
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-green-600">
                    <CheckCircleOutlined /> Saved
                  </span>
                )}
                <span className="mx-2 text-gray-300">|</span>
                <span>{appInfo?.updated_at ? `Last updated: ${appInfo.updated_at}` : '--'}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Can add more header actions here like Debug Mode switch etc. */}
        <Button
          type="primary"
          icon={<CloudUploadOutlined />}
          className='bg-gradient-to-r from-blue-500 to-indigo-600 border-none shadow-md hover:shadow-lg transition-all'
          onClick={() => setPublishModalOpen(true)}
          loading={fetchPublishAppLoading}
        >
          {t('header_publish')}
        </Button>
      </div>

      <Modal
        title={
          <div className='flex items-center gap-2 text-amber-500'>
            <ExclamationCircleFilled />
            <span className="text-gray-800 font-medium">{t('header_publish_app')}</span>
          </div>
        }
        open={publishModalOpen}
        onCancel={() => setPublishModalOpen(false)}
        okButtonProps={{ loading: refreshAppInfoLoading || fetchUpdateAppLoading || fetchPublishAppLoading }}
        onOk={handlePublishOk}
        centered
        width={400}
      >
        <div className='py-4 text-gray-600'>{t('header_publish_confirm')}</div>
      </Modal>
    </div>
  );
}

export default Header;
