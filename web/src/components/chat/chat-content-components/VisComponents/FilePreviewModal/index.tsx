import React, { FC, useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Modal, Image, Typography, Tabs, Button, ConfigProvider, Tooltip } from 'antd';
import {
  CodeOutlined,
  EyeOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  DownloadOutlined,
  FileTextOutlined,
  FileImageOutlined,
  GlobalOutlined,
  CloseOutlined,
  FormatPainterOutlined,
} from '@ant-design/icons';
import { CodePreview } from '../../code-preview';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { GPTVis } from '@antv/gpt-vis';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import styles from './FilePreviewModal.module.css';

const { Text } = Typography;

interface FilePreviewModalProps {
  visible: boolean;
  file: {
    file_name: string;
    file_type?: string;
    object_path?: string;
    oss_url?: string;
    preview_url?: string;
    mime_type?: string;
  } | null;
  onClose: () => void;
}

const FILE_TYPES = {
  IMAGE: 'image',
  HTML: 'html',
  CODE: 'code',
  MARKDOWN: 'markdown',
  TEXT: 'text',
  UNKNOWN: 'unknown',
};

const getFileExtension = (fileName: string): string => {
  const parts = fileName.split('.');
  return parts.length > 1 ? parts.pop()!.toLowerCase() : '';
};

const getFileType = (fileName: string, mimeType?: string): string => {
  const ext = getFileExtension(fileName);

  const imageExts = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'];
  const htmlExts = ['html', 'htm', 'xhtml'];
  const codeExts = ['js', 'jsx', 'ts', 'tsx', 'py', 'java', 'go', 'rs', 'c', 'cpp', 'h', 'css', 'scss', 'less', 'xml', 'json', 'yaml', 'yml', 'sql', 'sh', 'bash', 'php', 'rb', 'swift', 'kt', 'scala'];
  const markdownExts = ['md', 'markdown'];

  if (imageExts.includes(ext)) return FILE_TYPES.IMAGE;
  if (htmlExts.includes(ext)) return FILE_TYPES.HTML;
  if (markdownExts.includes(ext)) return FILE_TYPES.MARKDOWN;
  if (codeExts.includes(ext)) return FILE_TYPES.CODE;

  if (mimeType) {
    if (mimeType.startsWith('image/')) return FILE_TYPES.IMAGE;
    if (mimeType === 'text/html' || mimeType.includes('html')) return FILE_TYPES.HTML;
    if (mimeType.includes('markdown') || mimeType.includes('md')) return FILE_TYPES.MARKDOWN;
    if (mimeType.includes('json') || mimeType.includes('javascript') || mimeType.includes('typescript') || mimeType.includes('python')) return FILE_TYPES.CODE;
    if (mimeType.startsWith('text/')) return FILE_TYPES.TEXT;
  }

  return FILE_TYPES.TEXT;
};

const getLanguage = (fileName: string): string => {
  const ext = getFileExtension(fileName);
  const languageMap: Record<string, string> = {
    js: 'javascript', jsx: 'jsx', ts: 'typescript', tsx: 'tsx',
    py: 'python', java: 'java', go: 'go', rs: 'rust',
    c: 'c', cpp: 'cpp', h: 'c', css: 'css', scss: 'scss', less: 'less',
    xml: 'xml', json: 'json', yaml: 'yaml', yml: 'yaml', sql: 'sql',
    sh: 'bash', bash: 'bash', php: 'php', rb: 'ruby',
    swift: 'swift', kt: 'kotlin', scala: 'scala',
    md: 'markdown', markdown: 'markdown', txt: 'text',
    html: 'html', htm: 'html',
  };
  return languageMap[ext] || ext || 'text';
};

const getFileTypeIcon = (fileType: string) => {
  switch (fileType) {
    case FILE_TYPES.IMAGE: return <FileImageOutlined />;
    case FILE_TYPES.HTML: return <GlobalOutlined />;
    case FILE_TYPES.CODE: return <CodeOutlined />;
    case FILE_TYPES.MARKDOWN: return <FileTextOutlined />;
    default: return <FileTextOutlined />;
  }
};

const FilePreviewModal: FC<FilePreviewModalProps> = ({ visible, file, onClose }) => {
  const [loading, setLoading] = useState(false);
  const [content, setContent] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [actualPreviewUrl, setActualPreviewUrl] = useState<string | null>(null);
  const [useDirectOssContent, setUseDirectOssContent] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview');
  const [animating, setAnimating] = useState(false);
  const [closing, setClosing] = useState(false);
  const [shouldRender, setShouldRender] = useState(false);
  const [jsonFormatted, setJsonFormatted] = useState(true);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const fileType = useMemo(() => {
    if (!file) return FILE_TYPES.UNKNOWN;
    return getFileType(file.file_name, file.mime_type);
  }, [file]);

  const fallbackUrl = file?.preview_url || file?.oss_url;

  // Build a preview URL for this backend: derisk-fs:// URIs go through the
  // /files/preview endpoint (uri parameter); object_path files use the legacy
  // /api/oss/getFileByFileName endpoint.
  const buildPreviewUrl = (fileUri: string): string => {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
    if (fileUri.startsWith('derisk-fs://')) {
      return `${apiBaseUrl}/api/v2/serve/file/files/preview?uri=${encodeURIComponent(fileUri)}`;
    }
    if (fileUri.startsWith('/')) {
      return `${apiBaseUrl}${fileUri}`;
    }
    return fileUri;
  };

  const buildObjectPathUrl = (objectPath: string): string => {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
    return `${apiBaseUrl}/api/oss/getFileByFileName?fileName=${encodeURIComponent(objectPath)}`;
  };

  const parsedHtmlContent = useMemo(() => {
    if (!content || fileType !== FILE_TYPES.HTML) return '';
    
    if (content.includes('<!DOCTYPE') || content.includes('<html')) {
      return content;
    }
    
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { 
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.6;
      padding: 24px;
      margin: 0;
      color: #1e293b;
      background: #ffffff;
    }
    pre, code { 
      background: #f1f5f9; 
      padding: 2px 6px; 
      border-radius: 4px;
      font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
    }
    pre { padding: 16px; overflow-x: auto; }
    a { color: #6366f1; }
    img { max-width: 100%; height: auto; border-radius: 8px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #e2e8f0; padding: 8px 12px; }
    th { background: #f8fafc; }
  </style>
</head>
<body>
${content}
</body>
</html>`;
  }, [content, fileType]);

  const toggleFullscreen = () => {
    if (!iframeRef.current) return;
    
    if (!isFullscreen) {
      iframeRef.current.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  useEffect(() => {
    if (visible && !shouldRender) {
      setShouldRender(true);
      setClosing(false);
    }
  }, [visible, shouldRender]);

  useEffect(() => {
    if (shouldRender && !animating && !closing) {
      const timer = setTimeout(() => {
        setAnimating(true);
      }, 30);
      return () => clearTimeout(timer);
    }
  }, [shouldRender, animating, closing]);

  const handleClose = useCallback(() => {
    setClosing(true);
    setAnimating(false);
    setTimeout(() => {
      setShouldRender(false);
      setClosing(false);
      onClose();
    }, 250);
  }, [onClose]);

  useEffect(() => {
    if (!visible && shouldRender && animating && !closing) {
      handleClose();
    }
  }, [visible, shouldRender, animating, closing, handleClose]);

  const handleDownloadHtml = () => {
    if (!content) return;
    const blob = new Blob([parsedHtmlContent], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = file?.file_name || 'preview.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    if (!visible || !file) {
      setContent('');
      setError('');
      setActualPreviewUrl(null);
      setUseDirectOssContent(false);
      return;
    }

    const resolvePreviewUrl = async () => {
      // 优先使用 derisk-fs:// oss_url 走 /files/preview 接口（支持 inline 预览）
      const fileUri = file.oss_url || file.object_path;
      if (fileUri) {
        const previewUrl = file.object_path && !file.oss_url
          ? buildObjectPathUrl(file.object_path)
          : buildPreviewUrl(fileUri);
        console.log('[FilePreview] 使用 preview 接口预览:', previewUrl);

        try {
          const response = await fetch(previewUrl, { method: 'GET' });
          if (response.ok) {
            // 对于非图片文件，先获取内容，再设置 URL（避免触发第二个 useEffect 时标志位还是 false）
            if (fileType !== FILE_TYPES.IMAGE) {
              setLoading(true);
              try {
                const textContent = await response.text();
                setContent(textContent);
                // 同时设置 URL 和标志位，确保第二个 useEffect 检查时标志位已更新
                setActualPreviewUrl(previewUrl);
                setUseDirectOssContent(true);
              } catch {
                // 获取内容失败，降级使用代理接口
                setActualPreviewUrl(previewUrl);
                setUseDirectOssContent(false);
              } finally {
                setLoading(false);
              }
            } else {
              // 图片文件直接设置 URL
              setActualPreviewUrl(previewUrl);
            }
            return;
          }
        } catch (err) {
          console.warn('[FilePreview] preview 接口请求失败，尝试降级:', err);
        }
      } else {
        console.warn('[FilePreview] 缺少可预览 URL。文件:', file.file_name, '可用字段:', {
          oss_url: file.oss_url ? '✓' : '✗',
          preview_url: file.preview_url ? '✓' : '✗',
          object_path: file.object_path ? '✓' : '✗',
        });
      }

      // 降级使用 fallbackUrl（preview_url 或 oss_url）
      if (fallbackUrl) {
        console.log('[FilePreview] 使用降级 URL 预览:', fallbackUrl);
        setActualPreviewUrl(buildPreviewUrl(fallbackUrl));
        return;
      }

      console.warn('[FilePreview] 无可用预览 URL，文件:', file.file_name);
      setActualPreviewUrl(null);
    };

    resolvePreviewUrl();
  }, [visible, file, fallbackUrl]);

  useEffect(() => {
    if (!visible || !actualPreviewUrl || !file) {
      setContent('');
      setError('');
      return;
    }

    if (fileType === FILE_TYPES.IMAGE) return;

    // 如果已经通过 OSS 接口直接获取了内容，跳过代理接口
    if (useDirectOssContent) return;

    const fetchContent = async () => {
      setLoading(true);
      setError('');

      try {
        // actualPreviewUrl 已经是 /files/preview?uri=... 可直接获取内容
        const response = await fetch(actualPreviewUrl);
        if (!response.ok) {
          throw new Error(`Failed to fetch file: ${response.statusText}`);
        }

        setContent(await response.text());
      } catch (err) {
        console.error('Failed to fetch file content:', err);
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        setLoading(false);
      }
    };

    fetchContent();
  }, [visible, file, actualPreviewUrl, fileType, useDirectOssContent]);

  const renderLoadingState = () => (
    <div className={styles.loadingContainer}>
      <div className={styles.loadingContent}>
        <div className={styles.loadingIcon}>
          <FileTextOutlined />
        </div>
        <div className={styles.loadingText}>加载中...</div>
        <div className={styles.loadingProgress}>
          <div className={styles.loadingBar} />
        </div>
      </div>
    </div>
  );

  const renderContent = () => {
    if (!file) return null;

    if (error) {
      return (
        <div className={styles.errorContainer}>
          <div className={styles.errorIcon}>⚠️</div>
          <Text type="danger">{error}</Text>
        </div>
      );
    }

    if (loading) {
      return renderLoadingState();
    }

    switch (fileType) {
      case FILE_TYPES.IMAGE: {
        if (!actualPreviewUrl) return null;
        // actualPreviewUrl 已经是 /files/preview?uri=... 可直接展示
        return (
          <div className={styles.imageContainer}>
            <Image
              src={actualPreviewUrl}
              alt={file.file_name}
              className={styles.previewImage}
              fallback={actualPreviewUrl}
              placeholder={
                <div className={styles.imagePlaceholder}>
                  <FileTextOutlined spin style={{ fontSize: 32, color: '#6366f1' }} />
                </div>
              }
            />
          </div>
        );
      }

      case FILE_TYPES.HTML: {
        const htmlTabItems = [
          {
            key: 'preview',
            label: (
              <span className={styles.tabLabel}>
                <EyeOutlined /> 预览
              </span>
            ),
            children: (
              <div className={styles.htmlPreviewContainer}>
                <iframe
                  ref={iframeRef}
                  srcDoc={parsedHtmlContent}
                  className={styles.htmlPreviewFrame}
                  sandbox="allow-scripts allow-same-origin"
                  title="HTML Preview"
                />
                <div className={styles.htmlActions}>
                  <Button
                    size="small"
                    icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                    onClick={toggleFullscreen}
                    className={styles.actionButton}
                  >
                    {isFullscreen ? '退出全屏' : '全屏'}
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    onClick={handleDownloadHtml}
                    className={styles.actionButton}
                  >
                    下载
                  </Button>
                </div>
              </div>
            ),
          },
          {
            key: 'code',
            label: (
              <span className={styles.tabLabel}>
                <CodeOutlined /> 源码
              </span>
            ),
            children: (
              <div className={styles.codeContainer}>
                <CodePreview code={content} language="html" />
              </div>
            ),
          },
        ];

        return (
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as 'preview' | 'code')}
            items={htmlTabItems}
            className={styles.previewTabs}
          />
        );
      }

      case FILE_TYPES.MARKDOWN:
        return (
          <div className={styles.markdownContainer}>
            <GPTVis
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeRaw, rehypeKatex]}
            >
              {content}
            </GPTVis>
          </div>
        );

      case FILE_TYPES.CODE:
      case FILE_TYPES.TEXT:
      default: {
        const lang = getLanguage(file.file_name);
        let isJson = false;
        let formattedContent = content;
        // 尝试解析 JSON
        if (lang === 'json' || lang === 'text') {
          try {
            const parsed = JSON.parse(content);
            formattedContent = JSON.stringify(parsed, null, 2);
            isJson = true;
          } catch {
            // 不是合法 JSON
          }
        }
        const displayContent = isJson && jsonFormatted ? formattedContent : content;
        const displayLang = isJson ? 'json' : lang;

        return (
          <div>
            <div className={styles.codeToolbar}>
              {isJson && (
                <Tooltip title={jsonFormatted ? '显示原始内容' : '格式化 JSON'}>
                  <Button
                    type="text"
                    size="small"
                    icon={<FormatPainterOutlined />}
                    onClick={() => setJsonFormatted(!jsonFormatted)}
                    className={`${styles.toolbarBtn} ${jsonFormatted ? styles.toolbarBtnActive : ''}`}
                  >
                    格式化
                  </Button>
                </Tooltip>
              )}
            </div>
            <CodePreview
              code={displayContent}
              language={displayLang}
              light={oneLight}
            />
          </div>
        );
      }
    }
  };

  return (
    <ConfigProvider
      theme={{
        token: {
          borderRadiusLG: 12,
        },
      }}
    >
      <Modal
        open={shouldRender}
        onCancel={handleClose}
        width={fileType === FILE_TYPES.IMAGE || fileType === FILE_TYPES.HTML ? '90%' : 900}
        footer={null}
        destroyOnClose
        closable={false}
        className={styles.previewModal}
        centered
        maskClosable
        transitionName=""
        maskTransitionName=""
      >
        <div className={`${styles.modalWrapper} ${animating ? styles.animateIn : ''} ${closing ? styles.animateOut : ''}`}>
          <div className={styles.modalHeader}>
            <div className={styles.headerLeft}>
              <span className={styles.fileIconWrap}>{getFileTypeIcon(fileType)}</span>
              <div className={styles.headerInfo}>
                <Text strong className={styles.fileName}>
                  {file?.file_name || '文件预览'}
                </Text>
                {file?.file_type && (
                  <Text type="secondary" className={styles.fileType}>
                    {file.file_type}
                  </Text>
                )}
              </div>
            </div>
            <Button
              type="text"
              icon={<CloseOutlined />}
              onClick={handleClose}
              className={styles.closeButton}
            />
          </div>
          
          <div className={styles.modalBody}>
            {renderContent()}
          </div>
        </div>
      </Modal>
    </ConfigProvider>
  );
};

export default FilePreviewModal;