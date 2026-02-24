import {
  FilePdfOutlined,
  FileImageOutlined,
  FileTextOutlined,
  FileZipOutlined,
  FileExcelOutlined,
  FileWordOutlined,
  FilePptOutlined,
  FileMarkdownOutlined,
  FileOutlined,
} from '@ant-design/icons';
import type { ComponentType } from 'react';

/**
 * Format file size to human readable format
 * @param bytes File size in bytes
 * @returns Formatted string (e.g., "1.5 MB")
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

/**
 * File type categories for preview support
 */
export type FilePreviewType = 'text' | 'image' | 'pdf' | 'code' | 'json' | 'csv' | 'unknown';

/**
 * Get preview type based on MIME type
 * @param mimeType MIME type string
 * @returns Preview type category
 */
export function getPreviewType(mimeType?: string): FilePreviewType {
  if (!mimeType) return 'unknown';

  const type = mimeType.toLowerCase();

  if (type.startsWith('text/')) {
    if (type === 'text/markdown' || type === 'text/x-markdown') return 'text';
    if (type === 'text/csv') return 'csv';
    return 'text';
  }

  if (type === 'application/json') return 'json';

  if (type.startsWith('image/')) return 'image';

  if (type === 'application/pdf') return 'pdf';

  if (
    type === 'application/javascript' ||
    type === 'application/typescript' ||
    type === 'text/html' ||
    type === 'text/css' ||
    type === 'text/xml'
  ) {
    return 'code';
  }

  return 'unknown';
}

/**
 * Check if file can be previewed
 * @param mimeType MIME type string
 * @returns Whether the file can be previewed
 */
export function canPreview(mimeType?: string): boolean {
  const previewType = getPreviewType(mimeType);
  return previewType !== 'unknown';
}

/**
 * Get icon component based on MIME type or file extension
 * @param fileName File name
 * @param mimeType MIME type string
 * @returns Ant Design icon component
 */
export function getFileIcon(
  fileName?: string,
  mimeType?: string
): ComponentType<{ style?: React.CSSProperties; className?: string }> {
  const type = mimeType?.toLowerCase() || '';

  // Check MIME type first
  if (type === 'application/pdf') return FilePdfOutlined;
  if (type.startsWith('image/')) return FileImageOutlined;
  if (type === 'text/markdown' || type === 'text/x-markdown') return FileMarkdownOutlined;
  if (type === 'application/json' || type === 'text/javascript' || type === 'application/typescript') {
    return FileOutlined;
  }
  if (type === 'text/csv' || type === 'application/vnd.ms-excel' || type.includes('spreadsheet')) {
    return FileExcelOutlined;
  }
  if (type === 'application/msword' || type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
    return FileWordOutlined;
  }
  if (type === 'application/vnd.ms-powerpoint' || type === 'application/vnd.openxmlformats-officedocument.presentationml.presentation') {
    return FilePptOutlined;
  }
  if (type.startsWith('text/')) return FileTextOutlined;
  if (type === 'application/zip' || type === 'application/x-rar-compressed' || type.includes('compressed')) {
    return FileZipOutlined;
  }

  // Check file extension as fallback
  if (fileName) {
    const ext = fileName.split('.').pop()?.toLowerCase();

    switch (ext) {
      case 'pdf':
        return FilePdfOutlined;
      case 'jpg':
      case 'jpeg':
      case 'png':
      case 'gif':
      case 'bmp':
      case 'webp':
      case 'svg':
        return FileImageOutlined;
      case 'md':
      case 'markdown':
        return FileMarkdownOutlined;
      case 'js':
      case 'ts':
      case 'jsx':
      case 'tsx':
      case 'py':
      case 'java':
      case 'c':
      case 'cpp':
      case 'go':
      case 'rs':
      case 'json':
      case 'yaml':
      case 'yml':
      case 'xml':
      case 'html':
      case 'css':
      case 'sql':
        return FileOutlined;
      case 'csv':
      case 'xls':
      case 'xlsx':
        return FileExcelOutlined;
      case 'doc':
      case 'docx':
        return FileWordOutlined;
      case 'ppt':
      case 'pptx':
        return FilePptOutlined;
      case 'zip':
      case 'rar':
      case '7z':
      case 'tar':
      case 'gz':
        return FileZipOutlined;
      case 'txt':
      case 'log':
        return FileTextOutlined;
      default:
        return FileOutlined;
    }
  }

  return FileOutlined;
}

/**
 * Get file type label based on file_type field or mime_type
 * @param fileType File type string (e.g., 'conclusion', 'deliverable')
 * @returns Human readable label
 */
export function getFileTypeLabel(fileType?: string): string {
  if (!fileType) return '文件';

  const labels: Record<string, string> = {
    conclusion: '结论文件',
    deliverable: '交付物',
    tool_output: '工具输出',
    write_file: '写入文件',
    temp: '临时文件',
    report: '报告',
    data: '数据文件',
    image: '图片',
    document: '文档',
    code: '代码文件',
    config: '配置文件',
  };

  return labels[fileType] || '文件';
}
