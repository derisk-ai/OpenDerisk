import { publishAppNew } from '@/client/api';
import { AppContext } from '@/contexts';
import { CheckCircleOutlined, ExclamationCircleFilled, SwapOutlined } from '@ant-design/icons';
import { useRequest } from 'ahooks';
import { App, Dropdown, Modal } from 'antd';
import { useRouter } from 'next/navigation';
import { useContext, useMemo, useState } from 'react';

function Header() {
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
          content: '应用发布成功',
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
          content: '应用发布失败，请稍后重试',
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
            <span className={option.version_info === appInfo?.config_version ? 'font-bold text-[#1677ff]' : ''}>
              {option.version_info}
              {option.version_info === appInfo?.config_version && <CheckCircleOutlined className='ml-1 text-[green]' />}
            </span>
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
    <div className='flex items-center justify-between w-full px-4 py-2 border-b border-b-[#D9D9D9]'>
      <div className='flex items-center space-x-4'>
        <button
          onClick={() => router.replace('/application/app')}
          className='p-2 rounded hover:bg-gray-200'
          aria-label='返回'
        >
          <span className='text-xl'>←</span>
        </button>
        <img src={appInfo.icon || '/agents/agent1.jpg'} alt='App Icon' className='w-10 h-10 rounded' />
        <div>
          <div className='flex flex-row items-center space-x-2'>
            <div className='font-semibold text-lg'>{appInfo?.app_name || '--'}</div>
            <div className='text-xs text-gray-500'>已自动保存：{appInfo?.updated_at ? appInfo.updated_at : '--'}</div>
          </div>
          {appInfo?.config_version && versionItems.length > 0 && (
            <Dropdown menu={menuProps}>
              <button
                onClick={e => e.preventDefault()}
                className='text-xs text-gray-500 hover:bg-[#f3f5f9] cursor-pointer rounded p-1'
              >
                <SwapOutlined className='mr-1' />
                {appInfo?.config_version}
              </button>
            </Dropdown>
          )}
          {appInfo?.config_version && versionItems.length <= 0 && (
            <button className='text-xs text-gray-500 hover:bg-[#f3f5f9]  rounded p-1'>{appInfo?.config_version}</button>
          )}
        </div>
      </div>
      <button
        className='ant-btn  ant-btn-default ant-btn-color-default ant-btn-variant-outlined border-none text-white bg-button-gradient flex items-center cursor-pointer px-5 py-1 rounded hover:bg-button-hover transition-colors duration-200'
        onClick={() => setPublishModalOpen(true)}
      >
        发布
      </button>

      <Modal
        title={
          <div className='flex gap-2'>
            <ExclamationCircleFilled style={{ color: '#faad14' }} />
            发布应用
          </div>
        }
        open={publishModalOpen}
        onCancel={() => setPublishModalOpen(false)}
        okButtonProps={{ loading: refreshAppInfoLoading || fetchUpdateAppLoading || fetchPublishAppLoading }}
        onOk={handlePublishOk}
      >
        <div className='pl-6'>确定要发布该应用吗？</div>
      </Modal>
    </div>
  );
}

export default Header;
