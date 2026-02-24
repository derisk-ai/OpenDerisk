import {
  FileOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  FileImageOutlined,
  FileExcelOutlined,
  FilePptOutlined,
  FileZipOutlined,
  FileMarkdownOutlined,
  PlayCircleFilled,  // 视频
  AudioOutlined,      // 音频
  FileUnknownOutlined,
  CodeOutlined,
  FileGifOutlined,
  FileJpgOutlined,
  PictureOutlined,
} from '@ant-design/icons';

export type FileIconType = React.ElementType;

// 文件扩展名到图标的映射
const EXTENSION_TO_ICON: Record<string, FileIconType> = {
  // 文本文件
  txt: FileTextOutlined,
  md: FileMarkdownOutlined,
  json: FileTextOutlined,
  xml: FileTextOutlined,
  html: FileTextOutlined,
  css: FileTextOutlined,
  js: CodeOutlined,
  ts: CodeOutlined,
  tsx: CodeOutlined,
  jsx: CodeOutlined,
  py: CodeOutlined,
  java: CodeOutlined,
  c: CodeOutlined,
  cpp: CodeOutlined,
  h: CodeOutlined,
  go: CodeOutlined,
  rs: CodeOutlined,
  sql: CodeOutlined,
  yaml: FileTextOutlined,
  yml: FileTextOutlined,
  csv: FileExcelOutlined,

  // PDF
  pdf: FilePdfOutlined,

  // Word
  doc: FileWordOutlined,
  docx: FileWordOutlined,

  // Excel
  xls: FileExcelOutlined,
  xlsx: FileExcelOutlined,

  // PPT
  ppt: FilePptOutlined,
  pptx: FilePptOutlined,

  // 图片
  jpg: FileJpgOutlined,
  jpeg: FileJpgOutlined,
  png: FileJpgOutlined,
  gif: FileGifOutlined,
  svg: FileImageOutlined,
  bmp: FileImageOutlined,
  webp: FileImageOutlined,
  ico: FileImageOutlined,

  // 视频
  mp4: PlayCircleFilled,
  avi: PlayCircleFilled,
  mkv: PlayCircleFilled,
  mov: PlayCircleFilled,
  wmv: PlayCircleFilled,
  flv: PlayCircleFilled,
  webm: PlayCircleFilled,

  // 音频
  mp3: AudioOutlined,
  wav: AudioOutlined,
  flac: AudioOutlined,
  aac: AudioOutlined,
  ogg: AudioOutlined,
  m4a: AudioOutlined,

  // 压缩文件
  zip: FileZipOutlined,
  rar: FileZipOutlined,
  '7z': FileZipOutlined,
  tar: FileZipOutlined,
  gz: FileZipOutlined,
  bz2: FileZipOutlined,
};

// MIME 类型到图标的映射
const MIME_TYPE_TO_ICON: Record<string, FileIconType> = {
  // 文本
  'text/plain': FileTextOutlined,
  'text/html': FileTextOutlined,
  'text/css': FileTextOutlined,
  'text/javascript': CodeOutlined,
  'text/markdown': FileMarkdownOutlined,
  'application/json': FileTextOutlined,
  'application/xml': FileTextOutlined,

  // PDF
  'application/pdf': FilePdfOutlined,

  // Word
  'application/msword': FileWordOutlined,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': FileWordOutlined,

  // Excel
  'application/vnd.ms-excel': FileExcelOutlined,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': FileExcelOutlined,

  // PPT
  'application/vnd.ms-powerpoint': FilePptOutlined,
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': FilePptOutlined,

  // 图片
  'image/jpeg': FileJpgOutlined,
  'image/png': FileJpgOutlined,
  'image/gif': FileGifOutlined,
  'image/svg+xml': FileImageOutlined,
  'image/webp': FileImageOutlined,
  'image/bmp': FileImageOutlined,
  'image/ico': FileImageOutlined,

  // 视频
  'video/mp4': PlayCircleFilled,
  'video/avi': PlayCircleFilled,
  'video/webm': PlayCircleFilled,
  'video/quicktime': PlayCircleFilled,

  // 音频
  'audio/mpeg': AudioOutlined,
  'audio/wav': AudioOutlined,
  'audio/ogg': AudioOutlined,
  'audio/flac': AudioOutlined,

  // 压缩
  'application/zip': FileZipOutlined,
  'application/x-rar-compressed': FileZipOutlined,
  'application/x-7z-compressed': FileZipOutlined,
  'application/x-tar': FileZipOutlined,
  'application/gzip': FileZipOutlined,
  'application/x-gzip': FileZipOutlined,
};

/**
 * 根据文件扩展名获取对应的图标组件
 * @param filename 文件名
 * @returns React 组件
 */
export function getFileIconByExtension(filename: string): FileIconType {
  if (!filename) return FileUnknownOutlined;

  const ext = filename.split('.').pop()?.toLowerCase() || '';
  return EXTENSION_TO_ICON[ext] || FileOutlined;
}

/**
 * 根据 MIME 类型获取对应的图标组件
 * @param mimeType MIME 类型
 * @returns React 组件
 */
export function getFileIconByMimeType(mimeType: string): FileIconType {
  if (!mimeType) return FileUnknownOutlined;
  return MIME_TYPE_TO_ICON[mimeType.toLowerCase()] || getFileByMimeCategory(mimeType);
}

/**
 * 根据 MIME 类别获取图标
 * @param mimeType MIME 类型
 * @returns React 组件
 */
function getFileByMimeCategory(mimeType: string): FileIconType {
  const category = mimeType.split('/')[0].toLowerCase();

  switch (category) {
    case 'image':
      return PictureOutlined;
    case 'video':
      return PlayCircleFilled;
    case 'audio':
      return AudioOutlined;
    case 'text':
      return FileTextOutlined;
    default:
      return FileUnknownOutlined;
  }
}

/**
 * 根据文件名或 MIME 类型获取对应的图标组件
 * @param filename 文件名（可选）
 * @param mimeType MIME 类型（可选）
 * @returns React 组件
 */
export function getFileIcon(filename?: string, mimeType?: string): FileIconType {
  // 优先使用扩展名
  if (filename) {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    if (ext && EXTENSION_TO_ICON[ext]) {
      return EXTENSION_TO_ICON[ext];
    }
  }

  // 其次使用 MIME 类型
  if (mimeType) {
    return getFileIconByMimeType(mimeType);
  }

  return FileUnknownOutlined;
}

/**
 * 格式化文件大小
 * @param bytes 文件大小（字节）
 * @param options 配置选项
 * @returns 格式化后的字符串
 */
interface FormatFileSizeOptions {
  decimals?: number;
  unit?: 'B' | 'KB' | 'MB' | 'GB' | 'TB' | 'auto';
}

export function formatFileSize(
  bytes: number | null | undefined,
  options?: FormatFileSizeOptions,
): string {
  if (bytes === null || bytes === undefined || bytes === 0) {
    return '0 B';
  }

  const { decimals = 2, unit = 'auto' } = options;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];

  if (unit !== 'auto') {
    const unitIndex = units.indexOf(unit);
    if (unitIndex >= 0) {
      const value = bytes / Math.pow(1024, unitIndex);
      return `${value.toFixed(decimals)} ${unit}`;
    }
  }

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${(bytes / Math.pow(k, i)).toFixed(dm)} ${units[i]}`;
}

/**
 * 判断文件是否可预览
 * @param mimeType MIME 类型
 * @returns 是否可预览
 */
export function isPreviewable(mimeType?: string): boolean {
  if (!mimeType) return false;

  const previewableTypes = [
    // 图片
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/bmp',
    'image/webp',
    'image/svg+xml',
    // PDF
    'application/pdf',
    // 文本
    'text/plain',
    'text/html',
    'text/css',
    'text/javascript',
    'application/json',
    'application/xml',
  ];

  return previewableTypes.includes(mimeType.toLowerCase());
}

/**
 * 获取文件扩展名
 * @param filename 文件名
 * @returns 扩展名（不含点）
 */
export function getFileExtension(filename: string): string {
  const parts = filename.split('.');
  return parts.length > 1 ? parts.pop()?.toLowerCase() || '' : '';
}