import React, { FC } from 'react';
import { Tag, Space, Typography, Tooltip } from 'antd';
import {
  DownloadOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { AttachWrap, AttachItemWrap } from './style';
import { formatFileSize, getFileIcon, canPreview } from './utils';

const { Text } = Typography;

interface AttachItem {
  name?: string;
  url?: string;
  link?: string;
  ref_name?: string;
  ref_link?: string;
  // 新增字段支持
  file_name?: string;
  file_size?: number;
  mime_type?: string;
  preview_url?: string;
  download_url?: string;
  oss_url?: string;
  [key: string]: unknown;
}

interface IProps {
  data: AttachItem[] | { items?: AttachItem[]; [key: string]: unknown };
}

const VisDAttach: FC<IProps> = ({ data }) => {
  const items = Array.isArray(data)
    ? data
    : (data && (data as { items?: AttachItem[] }).items) ?? [];

  if (!items?.length) {
    return null;
  }

  const handlePreview = (item: AttachItem) => {
    const previewUrl =
      (item as any).preview_url ??
      (item as any).oss_url ??
      item?.url ??
      item?.link ??
      item?.ref_link;
    if (previewUrl) {
      window.open(previewUrl, '_blank');
    }
  };

  const handleDownload = (item: AttachItem) => {
    const downloadUrl =
      (item as any).download_url ??
      (item as any).oss_url ??
      item?.url ??
      item?.link ??
      item?.ref_link;
    if (downloadUrl) {
      window.open(downloadUrl, '_blank');
    }
  };

  return (
    <AttachWrap>
      <Space wrap style={{ width: '100%' }}>
        <span>附件：</span>
        {items.map((item: AttachItem, index: number) => {
          const fileName =
            item.file_name ?? item.name ?? item.ref_name ?? `附件 ${index + 1}`;
          const href = item?.url ?? item?.link ?? item?.ref_link;
          const Icon = getFileIcon(
            fileName,
            (item as any).mime_type
          );
          const showPreview = canPreview((item as any).mime_type);
          const fileSize = (item as any).file_size;
          const canShowActions = fileSize !== undefined || (item as any).download_url || (item as any).preview_url;

          if (canShowActions) {
            // 显示增强版附件项（带图标和操作按钮）
            return (
              <AttachItemWrap key={href ?? index}>
                <Space size={4}>
                  <Icon className="attachIcon" />
                  <Text className="attachName">{fileName}</Text>
                  {fileSize && (
                    <Text type="secondary" className="attachSize">
                      {formatFileSize(fileSize)}
                    </Text>
                  )}
                  {showPreview && ((item as any).preview_url || (item as any).oss_url || href) && (
                    <Tooltip title="预览">
                      <span className="attachAction" onClick={() => handlePreview(item)}>
                        <EyeOutlined />
                      </span>
                    </Tooltip>
                  )}
                  <Tooltip title="下载">
                    <span className="attachAction" onClick={() => handleDownload(item)}>
                      <DownloadOutlined />
                    </span>
                  </Tooltip>
                </Space>
              </AttachItemWrap>
            );
          }

          // 显示原版 Tag 样式
          return (
            <Tag
              key={href ?? index}
              className="attachItem"
              onClick={() => href && window.open(href)}
            >
              <Space size={4}>
                <Icon className="attachIcon" />
                {fileName}
              </Space>
            </Tag>
          );
        })}
      </Space>
    </AttachWrap>
  );
};

export default VisDAttach;