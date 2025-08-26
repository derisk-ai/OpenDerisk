import { ChatContentContext, ChatContext } from '@/contexts';
import { SettingOutlined } from '@ant-design/icons';
import { Select, Tooltip } from 'antd';
import React, { memo, useContext, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import ModelIcon from '../content/model-icon';

const ModelSwitcher: React.FC = () => {
  const { modelList } = useContext(ChatContext);
  const { appInfo, modelValue, setModelValue, chatInParams, setChatInParams } = useContext(ChatContentContext);
  const { t } = useTranslation();

  const extendedChatInParams = useMemo(() => {
    return chatInParams?.filter(i => i.param_type !== 'model') || [];
  }, [chatInParams]);

  const model = useMemo(
    () => appInfo?.layout?.chat_in_layout?.find(i => i.param_type === 'model'),
    [appInfo?.layout?.chat_in_layout],
  );

  // 左边工具栏动态可用key
  const paramKey: string[] = useMemo(() => {
    return appInfo?.layout?.chat_in_layout?.map(i => i.param_type) || [];
  }, [appInfo?.layout?.chat_in_layout]);

  if (!paramKey.includes('model')) {
    return (
      <Tooltip title={t('model_tip')}>
        <div className='flex w-8 h-8 items-center justify-center rounded-md hover:bg-[rgb(221,221,221,0.6)]'>
          <SettingOutlined className='text-xl cursor-not-allowed opacity-30' />
        </div>
      </Tooltip>
    );
  }

  const handleChatInParamChange = (val: any) => {
    if (val) {
      setModelValue(val);
      const chatInParam = [
        ...extendedChatInParams,
        {
          param_type: 'model',
          param_value: val,
          sub_type: model?.sub_type,
        },
      ];
      setChatInParams(chatInParam);
    }
  };


  return (
    <Select
      value={modelValue}
      placeholder={t('choose_model')}
      className='h-8 w-42 rounded-1xl'
      onChange={val => {
        handleChatInParamChange(val);
      }}
      popupMatchSelectWidth={300}
    >
      {modelList.map(item => (
        <Select.Option key={item} >
          <div className='flex items-center'>
            <ModelIcon model={item} />
            <span className='ml-2 overflow-hidden text-ellipsis whitespace-nowrap'>{item}</span>
          </div>
        </Select.Option>
      ))}
    </Select>
  );
};

export default memo(ModelSwitcher);
