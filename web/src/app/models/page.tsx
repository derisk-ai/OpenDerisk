'use client';
import { apiInterceptors, getModelList, newDialogue, startModel, stopModel } from '@/client/api';
import BlurredCard, { ChatButton, InnerDropdown } from '@/components/blurred-card';
import ModelForm from '@/components/model/model-form';
import { ChatContext } from '@/contexts';
import { IModelData } from '@/types/model';
import { getModelIcon } from '@/utils/constants';
import { PlusOutlined } from '@ant-design/icons';
import { Button, Modal, Tag, message } from 'antd';
import moment from 'moment';
import { useRouter } from 'next/navigation';
import { useContext, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

export default function ModelManage() {
  const { t } = useTranslation();
  const { setCurrentDialogInfo, setModel } = useContext(ChatContext);

  const [models, setModels] = useState<Array<IModelData>>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState<boolean>(false);
  const router = useRouter();

  async function getModels() {
    const [, res] = await apiInterceptors(getModelList());
    setModels(res ?? []);
  }

  async function startTheModel(info: IModelData) {
    if (loading) return;
    const content = t(`confirm_start_model`) + info.model_name;

    showConfirm(t('start_model'), content, async () => {
      setLoading(true);
      const [, , res] = await apiInterceptors(
        startModel({
          host: info.host,
          port: info.port,
          model: info.model_name,
          worker_type: info.worker_type,
          delete_after: false,
          params: {},
        }),
      );
      setLoading(false);
      if (res?.success) {
        message.success(t('start_model_success'));
        await getModels();
      }
    });
  }

  async function stopTheModel(info: IModelData, delete_after = false) {
    if (loading) return;

    const action = delete_after ? 'stop_and_delete' : 'stop';
    const content = t(`confirm_${action}_model`) + info.model_name;
    showConfirm(t(`${action}_model`), content, async () => {
      setLoading(true);
      const [, , res] = await apiInterceptors(
        stopModel({
          host: info.host,
          port: info.port,
          model: info.model_name,
          worker_type: info.worker_type,
          delete_after: delete_after,
          params: {},
        }),
      );
      setLoading(false);
      if (res?.success === true) {
        message.success(t(`${action}_model_success`));
        await getModels();
      }
    });
  }

  const showConfirm = (title: string, content: string, onOk: () => Promise<void>) => {
    Modal.confirm({
      title,
      content,
      onOk: async () => {
        await onOk();
      },
      okButtonProps: {
        className: 'bg-button-gradient',
      },
    });
  };

  const handleChat = async (info: IModelData) => {
    const [_, data] = await apiInterceptors(
      newDialogue({
        app_code: 'chat_normal',
        model: info.model_name,
      }),
    );
    if (data?.conv_uid) {
      setModel(info.model_name);
      router.push(`/chat?app_code=chat_normal&conv_uid=${data?.conv_uid}&model=${info.model_name}`);
    }
  };

  useEffect(() => {
    getModels();
  }, []);

  const returnLogo = (name: string) => {
    return getModelIcon(name);
  };

  return (
    <div className='h-screen w-full p-4 md:p-6 '>
      <div className='flex justify-end items-center mb-6'>
        <div className='flex items-center gap-4'>
          <Button
            className='border-none text-white bg-button-gradient'
            icon={<PlusOutlined />}
            onClick={() => {
              setIsModalOpen(true);
            }}
          >
            {t('create_model')}
          </Button>
        </div>
      </div>

      <div className='mx-[-8px] overflow-y-auto h-full pb-12'>
       <div className='flex flex-wrap'>
        {models.map(item => (
          <BlurredCard
            logo={returnLogo(item.model_name)}
            description={
              <div className='flex flex-col gap-1 relative text-xs bottom-4'>
                <div className='flex overflow-hidden'>
                  <p className='w-28 text-gray-500 mr-2'>Host:</p>
                  <p className='flex-1 text-ellipsis'>{item.host}</p>
                </div>
                <div className='flex overflow-hidden'>
                  <p className='w-28 text-gray-500 mr-2'>Manage Host:</p>
                  <p className='flex-1 text-ellipsis'>
                    {item.manager_host}:{item.manager_port}
                  </p>
                </div>
                <div className='flex overflow-hidden'>
                  <p className='w-28 text-gray-500 mr-2'>Last Heart Beat:</p>
                  <p className='flex-1 text-ellipsis'>{moment(item.last_heartbeat).format('YYYY-MM-DD HH:mm:ss')}</p>
                </div>
              </div>
            }
            name={item.model_name}
            key={item.model_name}
            RightTop={
              <InnerDropdown
                menu={{
                  items: [
                    {
                      key: 'stop_model',
                      label: (
                        <span className='text-red-400' onClick={() => stopTheModel(item)}>
                          {t('stop_model')}
                        </span>
                      ),
                    },
                    {
                      key: 'start_model',
                      label: (
                        <span className='text-green-400' onClick={() => startTheModel(item)}>
                          {t('start_model')}
                        </span>
                      ),
                    },
                    {
                      key: 'stop_and_delete_model',
                      label: (
                        <span className='text-red-400' onClick={() => stopTheModel(item, true)}>
                          {t('stop_and_delete_model')}
                        </span>
                      ),
                    },
                  ],
                }}
              />
            }
            rightTopHover={false}
            Tags={
              <div>
                <Tag color={item.healthy ? 'green' : 'red'}>{item.healthy ? 'Healthy' : 'Unhealthy'}</Tag>
                <Tag>{item.worker_type}</Tag>
              </div>
            }
            RightBottom={
              <ChatButton
                text={t('start_chat')}
                onClick={() => {
                  handleChat(item);
                }}
              />
            }
          />
        ))}
        </div>
      </div>
      <Modal
        width={800}
        open={isModalOpen}
        title={t('create_model')}
        onCancel={() => {
          setIsModalOpen(false);
        }}
        footer={null}
      >
        <ModelForm
          onCancel={() => {
            setIsModalOpen(false);
          }}
          onSuccess={() => {
            setIsModalOpen(false);
            getModels();
          }}
        />
      </Modal>
    </div>
  );
}
