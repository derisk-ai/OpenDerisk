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
  file_name?: string;
  file_size?: number;
  mime_type?: string;
  preview_url?: string;
  download_url?: string;
  oss_url?: string;
  object_path?: string;
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

  const buildPreviewUrl = (item: AttachItem): string | null => {
    if (item.object_path) {
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
      return `${apiBaseUrl}/api/oss/getFileByFileName?fileName=${encodeURIComponent(item.object_path)}`;
    }
    return null;
  };

  const handlePreview = async (item: AttachItem) => {
    // Try API proxy URL first (for object_path based files)
    const apiPreviewUrl = buildPreviewUrl(item);
    if (apiPreviewUrl) {
      try {
        const response = await fetch(apiPreviewUrl, { method: 'HEAD' });
        if (response.ok) {
          window.open(apiPreviewUrl, '_blank', 'noopener,noreferrer');
          return;
        }
      } catch {
        // Fallback to direct URLs
      }
    }

    const fallbackUrl =
      item.preview_url ??
      item.oss_url ??
      item?.url ??
      item?.link ??
      item?.ref_link;
    if (fallbackUrl) {
      window.open(fallbackUrl, '_blank', 'noopener,noreferrer');
    }
  };

  const handleDownload = (item: AttachItem) => {
    const downloadUrl =
      item.download_url ??
      item.oss_url ??
      item?.url ??
      item?.link ??
      item?.ref_link;

    if (!downloadUrl) {
      console.warn('No download URL available');
      return;
    }

    const fileName = item.file_name ?? item.name ?? item.ref_name ?? 'download';

    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = fileName;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const hasPreviewUrl = (item: AttachItem): boolean => {
    return !!(item.object_path ?? item.preview_url ?? item.oss_url ?? item?.url ?? item?.link ?? item?.ref_link);
  };

  const hasDownloadUrl = (item: AttachItem): boolean => {
    return !!(item.download_url ?? item.oss_url ?? item?.url ?? item?.link ?? item?.ref_link);
  };

  const getFileSizeDisplay = (size?: number): string | null => {
    if (size === undefined || size === null || size <= 0) return null;
    return formatFileSize(size);
  };

  return (
    <AttachWrap>
      <Space wrap style={{ width: '100%' }}>
        <span className="attachLabel">Attachments:</span>
        {items.map((item: AttachItem, index: number) => {
          const fileName =
            item.file_name ?? item.name ?? item.ref_name ?? `Attachment ${index + 1}`;
          const Icon = getFileIcon(fileName, item.mime_type);
          const sizeDisplay = getFileSizeDisplay(item.file_size);
          const canShowPreview = hasPreviewUrl(item);
          const canShowDownload = hasDownloadUrl(item);

          if (item.file_size !== undefined || item.download_url || item.preview_url || item.oss_url || item.object_path) {
            return (
              <AttachItemWrap key={index}>
                <div className="attachItemContent">
                  <Icon className="attachIcon" />
                  <Text className="attachName" ellipsis={{ tooltip: fileName }}>
                    {fileName}
                  </Text>
                  {sizeDisplay && (
                    <Text type="secondary" className="attachSize">
                      {sizeDisplay}
                    </Text>
                  )}
                </div>
                <div className="attachActions">
                  {canShowPreview && (
                    <Tooltip title="Preview">
                      <span className="attachAction previewAction" onClick={() => handlePreview(item)}>
                        <EyeOutlined />
                      </span>
                    </Tooltip>
                  )}
                  {canShowDownload && (
                    <Tooltip title="Download">
                      <span className="attachAction downloadAction" onClick={() => handleDownload(item)}>
                        <DownloadOutlined />
                      </span>
                    </Tooltip>
                  )}
                </div>
              </AttachItemWrap>
            );
          }

          const href = item?.url ?? item?.link ?? item?.ref_link;
          return (
            <Tag
              key={index}
              className="attachItem"
              onClick={() => {
                if (href) window.open(href, '_blank', 'noopener,noreferrer');
              }}
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
