import React, { FC } from 'react';
import { List, Tag, Typography, Space, Button, Tooltip } from 'antd';
import {
  DownloadOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { AttachListWrap, AttachListItem, FileItemContent, FileItemActions } from './style';
import { formatFileSize, getFileIcon, canPreview } from '../VisDAttach/utils';

const { Text } = Typography;

interface AttachItem {
  file_id: string;
  file_name: string;
  file_type: string;
  file_size?: number;
  oss_url?: string;
  preview_url?: string;
  download_url?: string;
  mime_type?: string;
  created_at?: string;
  task_id?: string;
  description?: string;
}

interface IProps {
  data: {
    uid?: string;
    type?: string;
    title?: string;
    description?: string;
    files?: AttachItem[];
    total_count?: number;
    total_size?: number;
    show_batch_download?: boolean;
  };
}

const VisDAttachList: FC<IProps> = ({ data }) => {
 const { title = '交付文件', description, files = [], total_count, show_batch_download = true } = data;

 if (!files?.length) {
   return null;
 }

 const FileIcon = getFileIcon(files[0]?.file_name || '', files[0]?.mime_type);

 const handlePreview = (file: AttachItem) => {
   const previewUrl = file.preview_url || file.oss_url;
   if (previewUrl) {
     window.open(previewUrl, '_blank');
   }
 };

 const handleDownload = (file: AttachItem) => {
   const downloadUrl = file.download_url || file.oss_url;
   if (downloadUrl) {
     window.open(downloadUrl, '_blank');
   }
 };

 const handleBatchDownload = () => {
   // TODO: 实现批量下载逻辑
   console.log('批量下载', files);
 };

 return (
   <AttachListWrap>
     <div className="attachListHeader">
       <Space>
         <FileIcon className="folderIcon" />
         <Text strong className="title">{title}</Text>
         {total_count !== undefined && (
           <Text type="secondary">共 {total_count} 个文件</Text>
         )}
       </Space>
       {show_batch_download && (
         <Button
           type="link"
           icon={<DownloadOutlined />}
           size="small"
           onClick={handleBatchDownload}
         >
           全部下载
         </Button>
       )}
     </div>
     {description && <Text type="secondary" className="description">{description}</Text>}
     <List
       className="attachList"
       dataSource={files}
       renderItem={(file) => {
         const Icon = getFileIcon(file.file_name, file.mime_type);
         return (
           <AttachListItem key={file.file_id}>
             <FileItemContent>
               <Space>
                 <Icon className="fileIcon" />
                 <div className="fileInfo">
                   <Text className="fileName">{file.file_name}</Text>
                   <Space size="small" className="fileMeta">
                     {file.file_size && file.file_size > 0 && (
                       <Text type="secondary" className="fileSize">
                         {formatFileSize(file.file_size)}
                       </Text>
                     )}
                     {file.task_id && (
                       <Tag className="fileTypeTag">
                         {file.file_type || '文件'}
                       </Tag>
                     )}
                   </Space>
                   {file.description && (
                     <Text type="secondary" className="fileDesc" ellipsis={{ tooltip: file.description }}>
                       {file.description}
                     </Text>
                   )}
                 </div>
               </Space>
             </FileItemContent>
             <FileItemActions>
               <Space size="small">
                 {canPreview(file.mime_type) && (file.preview_url || file.oss_url) && (
                   <Tooltip title="预览">
                     <Button
                       type="text"
                       icon={<EyeOutlined />}
                       size="small"
                       onClick={() => handlePreview(file)}
                     />
                   </Tooltip>
                 )}
                 <Tooltip title="下载">
                   <Button
                     type="text"
                     icon={<DownloadOutlined />}
                     size="small"
                     onClick={() => handleDownload(file)}
                   />
                 </Tooltip>
               </Space>
             </FileItemActions>
           </AttachListItem>
         );
       }}
     />
   </AttachListWrap>
 );
};

export default VisDAttachList;