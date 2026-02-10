import React, { FC, useState } from 'react';
import { Space, Tag, Image, Modal, Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import {
  CloudDownloadOutlined,
  EyeOutlined,
  MoreOutlined,
} from '@ant-design/icons';
import { AttachWrap, AttachListItem, FileIconWrapper } from './style';
import {
  getFileIcon,
  formatFileSize,
  isPreviewable,
} from '@/utils/fileUtils';

interface AttachItem {
  name?: string;
  url?: string;
  link?: string;
  ref_name?: string;
  ref_link?: string;
  mime_type?: string;
  size?: number;
  [key: string]: unknown;
}

interface IProps {
  /**
   * 附件数据，可以是数组或包含 items 数组的对象
   */
  data: AttachItem[] | { items?: AttachItem[]; [key: string]: unknown };
  /**
   * 是否显示文件大小
   */
  showSize?: boolean;
  /**
   * 是否显示文件图标
   */
  showIcon?: boolean;
  /**
   * 模式：tags - 标签模式（默认），list - 列表模式
   */
  mode?: 'tags' | 'list';
}

const VisDAttach: FC<IProps> = ({
  data,
  showSize = true,
  showIcon = true,
  mode = 'tags',
}) => {
  const items = Array.isArray(data)
    ? data
    : (data && (data as { items?: AttachItem[] }).items) ?? [];

  const [previewFile, setPreviewFile] = useState<AttachItem | null>(null);
  const [isPreviewVisible, setIsPreviewVisible] = useState(false);

  // 处理下载
  const handleDownload = (item: AttachItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const href = item?.url ?? item?.link ?? item?.ref_link;
    if (href) {
      const link = document.createElement('a');
      link.href = href;
      link.download = item?.name ?? item?.ref_name ?? 'file';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  // 处理预览
  const handlePreview = (item: AttachItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const href = item?.url ?? item?.link ?? item?.ref_link;
    const mimeType = item?.mime_type;
    if (href && mimeType && isPreviewable(mimeType)) {
      setPreviewFile(item);
      setIsPreviewVisible(true);
    } else if (href) {
      window.open(href, '_blank');
    }
  };

  // 获取菜单项
  const getMenuItems = (item: AttachItem): MenuProps['items'] => {
    const href = item?.url ?? item?.link ?? item?.ref_link;
    const mimeType = item?.mime_type;

    return [
      {
        key: 'preview',
        icon: <EyeOutlined />,
        label: '预览',
        onClick: () => {
          if (href && mimeType && isPreviewable(mimeType)) {
            setPreviewFile(item);
            setIsPreviewVisible(true);
          } else if (href) {
            window.open(href, '_blank');
          }
        },
      },
      {
        key: 'download',
        icon: <CloudDownloadOutlined />,
        label: '下载',
        onClick: () => {
          const link = document.createElement('a');
          link.href = href || '';
          link.download = item?.name ?? item?.ref_name ?? 'file';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        },
      },
    ];
  };

  // 标签模式渲染
  const renderTags = () => (
    <Space wrap style={{ width: '100%' }}>
      <span>附件：</span>
      {items.map((item, index: number) => {
        const href = item?.url ?? item?.link ?? item?.ref_link;
        const label = item?.name ?? item?.ref_name ?? `附件 ${index + 1}`;
        const Icon = getFileIcon(item?.name, item?.mime_type);
        const size = item?.size ? formatFileSize(item.size) : null;
        const isPreviewableFile =
          item?.mime_type && isPreviewable(item.mime_type);

        return (
          <Tag
            key={href ?? index}
            className="attachItem"
            onClick={() => href && window.open(href)}
          >
            <Space size={4}>
              {showIcon && <Icon style={{ fontSize: '12px' }} />}
              <span>{label}</span>
              {size && <span className="fileSize">{`(${size})`}</span>}
              {isPreviewableFile && <EyeOutlined style={{ fontSize: '10px' }} />}
            </Space>
          </Tag>
        );
      })}
    </Space>
  );

  // 列表模式渲染
  const renderList = () => (
    <div className="attachList">
      {items.map((item, index) => {
        const href = item?.url ?? item?.link ?? item?.ref_link;
        const label = item?.name ?? item?.ref_name ?? `附件 ${index + 1}`;
        const Icon = getFileIcon(item?.name, item?.mime_type);
        const size = item?.size ? formatFileSize(item.size) : null;
        const mimeType = item?.mime_type;

        const isPreviewableFile = mimeType && isPreviewable(mimeType);

        return (
          <AttachListItem
            key={href ?? index}
            onClick={() => href && window.open(href)}
          >
            <FileIconWrapper>
              <Icon />
            </FileIconWrapper>
            <div className="fileInfo">
              <div className="fileName">
                <Tooltip title={label}>
                  <span className="nameText">{label}</span>
                </Tooltip>
                {mimeType && (
                  <span className="mimeType">({mimeType.split('/')[1]?.toUpperCase() || 'FILE'})</span>
                )}
              </div>
              {size && <div className="fileSize">{size}</div>}
            </div>
            <div className="fileActions">
              {isPreviewableFile && (
                <Tooltip title="预览">
                  <EyeOutlined
                    className="actionIcon"
                    onClick={(e) => handlePreview(item, e)}
                  />
                </Tooltip>
              )}
              <Tooltip title="下载">
                <CloudDownloadOutlined
                  className="actionIcon"
                  onClick={(e) => handleDownload(item, e)}
                />
              </Tooltip>
              <Dropdown menu={{ items: getMenuItems(item) }} trigger={['click']}>
                <MoreOutlined
                  className="actionIcon"
                  onClick={(e) => e.stopPropagation()}
                />
              </Dropdown>
            </div>
          </AttachListItem>
        );
      })}
    </div>
  );

  if (!items?.length) {
    return null;
  }

  return (
    <AttachWrap>
      {mode === 'tags' ? renderTags() : renderList()}

      {/* 预览弹窗 */}
      <Modal
        open={isPreviewVisible}
        title={previewFile?.name ?? previewFile?.ref_name ?? '文件预览'}
        footer={null}
        onCancel={() => setIsPreviewVisible(false)}
        width="80vw"
        centered
      >
        {previewFile && (
          <div style={{ textAlign: 'center', padding: '20px' }}>
            <Image
              src={previewFile?.url ?? previewFile?.link ?? previewFile?.ref_link}
              alt={previewFile?.name ?? previewFile?.ref_name ?? 'preview'}
              style={{ maxWidth: '100%', maxHeight: '70vh' }}
              preview={false}
            />
          </div>
        )}
      </Modal>
    </AttachWrap>
  );
};

export default VisDAttach;

// 导出类型供外部使用
export type { AttachItem };