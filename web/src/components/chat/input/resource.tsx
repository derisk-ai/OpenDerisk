import { apiInterceptors, postChatModeParamsFileLoad } from '@/client/api';
import { getChatInputConfigParams } from '@/client/api/app';
import { ChatContentContext } from '@/contexts';
import { IDB } from '@/types/chat';
import { ExperimentOutlined, FolderAddOutlined } from '@ant-design/icons';
import { useAsyncEffect, useRequest } from 'ahooks';
import type { UploadFile } from 'antd';
import { Select, Tooltip, Upload } from 'antd';
import classNames from 'classnames';
import { useSearchParams } from 'next/navigation';
import React, { memo, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

const upLoadList = [
    "excel_file", "text_file", "image_file"
];

const getAcceptTypes = (type: string) => {
  switch (type) {
    case 'excel_file':
      return '.csv,.xlsx,.xls';
    case 'text_file':
      return '.txt,.doc,.docx,.pdf,.md';
    case 'image_file':
      return '.jpg,.jpeg,.png,.gif,.bmp,.webp';
    case 'audio_file':
      return '.mp3,.wav,.ogg,.aac';
    case 'video_file':
      return '.mp4,.wav,.wav';
    default:
      return ''; // 空字符串表示支持所有文件类型
  }
};

const Resource: React.FC<{
  fileList: UploadFile[];
  setFileList: React.Dispatch<React.SetStateAction<UploadFile<any>[]>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  fileName: string;
}> = ({ fileList, setFileList, setLoading, fileName }) => {
  const { setResourceValue, appInfo, chatInParams, setChatInParams, refreshHistory, refreshDialogList, modelValue, resourceValue } =
    useContext(ChatContentContext);
  const { temperatureValue, maxNewTokensValue } = useContext(ChatContentContext);
  const searchParams = useSearchParams();
  const scene = searchParams?.get('scene') ?? '';
  const chatId = (searchParams?.get('conv_uid') || searchParams?.get('chatId')) ?? '';
  const { t } = useTranslation();
  // dataBase or knowledge
  const [dbs, setDbs] = useState<IDB[]>([]);

  // 左边工具栏动态可用key
  const paramKey: string[] = useMemo(() => {
    return appInfo?.layout?.chat_in_layout?.map(i => i.param_type) || [];
  }, [appInfo?.layout?.chat_in_layout]);

  const isResourceItem = useMemo(() => {
    return (
      paramKey.includes('resource') &&
      !upLoadList.includes(appInfo?.layout?.chat_in_layout?.filter(i => i.param_type === 'resource')[0]?.sub_type) 
    );
  }, [appInfo?.layout?.chat_in_layout, paramKey]);

  const extendedChatInParams = useMemo(() => {
    return chatInParams?.filter(i => i.param_type !== 'resource') || [];
  }, [chatInParams]);

  const resource = useMemo(
    () => appInfo?.layout?.chat_in_layout?.find(i => i.param_type === 'resource'),
    [appInfo?.layout?.chat_in_layout],
  );

  const { run, loading } = useRequest(async data => await apiInterceptors(getChatInputConfigParams([data])), {
    manual: true,
    onSuccess: data => {
      const [, res] = data;
      const resourceData = res?.find(
        (item: any) => item.param_type === 'resource' && item.sub_type === resource?.sub_type,
      );
      if (!resourceData) return;
      setDbs(resourceData?.param_type_options ?? []);
    },
  });

  useAsyncEffect(async () => {
    if (isResourceItem && resource) {
      await run(resource);
    }
  }, [isResourceItem, resource]);

  const dbOpts = useMemo(
    () =>
      dbs.map?.((db: any) => {
        return {
          label: db.label,
          value: db.key,
        };
      }),
    [dbs],
  );
  // resource 特殊处理
  useEffect(() => {
    if (chatInParams?.length > 0 && resource && dbs.length > 0) {
      const chatInParamsResource = chatInParams.find(i => i.param_type === 'resource');
      if (chatInParamsResource && chatInParamsResource?.param_value) {
        if (!chatInParamsResource?.param_value.trim().startsWith('{')) {
          const resourceItem = dbs.find((i: any) => i.key === resourceValue);
          const chatInParam = [
            ...extendedChatInParams,
            {
              param_type: 'resource',
              param_value: JSON.stringify(resourceItem),
              sub_type: resource?.sub_type,
            },
          ];
          setChatInParams(chatInParam);
        }
      } else {
      }
    }
  }, [chatInParams, resource, dbs, setChatInParams, resourceValue]);

  const handleChatInParamChange = (val: any) => {
    if (val) {
      setResourceValue(val);
      const resourceItem = dbs.find((i:any) => i.key === val);
      const chatInParam = [
        ...extendedChatInParams,
        {
          param_type: 'resource',
          param_value: JSON.stringify(resourceItem),
          sub_type: resource?.sub_type,
        },
      ];
      setChatInParams(chatInParam);
    }
  };

  // 上传
  const onUpload = useCallback(async () => {
    const formData = new FormData();
    formData.append('doc_files', fileList?.[0] as any);

    setLoading(true);
    const [_, res] = await apiInterceptors(
      postChatModeParamsFileLoad({
        convUid: chatId || '',
        chatMode: scene || 'chat_normal',
        data: formData,
        model: modelValue,
        temperatureValue,
        maxNewTokensValue,
        config: {
          timeout: 1000 * 60 * 60,
        },
      }),
    ).finally(() => {
      setLoading(false);
    });
    if (res) {
      const chatInParam = [
        ...extendedChatInParams,
        {
          param_type: 'resource',
          param_value: JSON.stringify(res),
          sub_type: resource?.sub_type,
        },
      ];
      setChatInParams(chatInParam);
      setResourceValue(res);
      await refreshHistory();
      refreshDialogList && (await refreshDialogList());
    }
  }, [chatId, fileList, modelValue, refreshDialogList, refreshHistory, scene, setLoading, setResourceValue]);

  if (!paramKey.includes('resource')) {
    return (
      <Tooltip title={t('extend_tip')}>
        <div className='flex w-8 h-8 items-center justify-center rounded-md hover:bg-[rgb(221,221,221,0.6)]'>
          <ExperimentOutlined className='text-lg cursor-not-allowed opacity-30' />
        </div>
      </Tooltip>
    );
  }

  switch (resource?.sub_type) {
    case 'excel_file':
    case 'text_file':
    case 'image_file':
    case 'common_file':
      return (
        <Upload
          name='file'
          accept={getAcceptTypes(resource?.sub_type)}
          fileList={fileList}
          showUploadList={false}
          beforeUpload={(_, fileList) => {
            setFileList?.(fileList);
          }}
          customRequest={onUpload}
          disabled={!!fileName}
        >
          <Tooltip title={t('file_tip')} arrow={false} placement='bottom'>
            <div className='flex w-8 h-8 items-center justify-center rounded-md hover:bg-[rgb(221,221,221,0.6)]'>
              <FolderAddOutlined
                className={classNames('text-xl', { 'cursor-pointer': !(!!fileName || !!fileList[0]?.name) })}
              />
            </div>
          </Tooltip>
        </Upload>
      );
     default:
      return (
        <Select
          value={resourceValue}
          className='w-30 h-8 rounded-3xl'
          onChange={val => {
            handleChatInParamChange(val);
          }}
          disabled={!!resource?.bind_value}
          loading={loading}
          options={dbOpts}
        />
      );
  }
};

export default memo(Resource);
