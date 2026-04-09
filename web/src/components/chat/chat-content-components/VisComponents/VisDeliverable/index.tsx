import React, { useCallback } from 'react';
import { DesktopOutlined, FolderOpenOutlined, FileTextOutlined, FileImageOutlined, FilePdfOutlined, CodeOutlined } from '@ant-design/icons';
import { ee, EVENTS } from '@/utils/event-emitter';

interface DeliverableFile {
  file_id: string;
  file_name: string;
  render_type?: 'iframe' | 'markdown' | 'code' | 'image' | 'pdf' | 'text';
}

interface DeliverableData {
  uid?: string;
  deliverable_files?: DeliverableFile[];
  task_files_count?: number;
}

const renderTypeConfig: Record<string, { icon: React.ReactNode; label: string }> = {
  iframe: { icon: <DesktopOutlined style={{ fontSize: 20, color: '#1677ff' }} />, label: '网页报告' },
  markdown: { icon: <FileTextOutlined style={{ fontSize: 20, color: '#52c41a' }} />, label: 'Markdown 文档' },
  code: { icon: <CodeOutlined style={{ fontSize: 20, color: '#722ed1' }} />, label: '代码文件' },
  image: { icon: <FileImageOutlined style={{ fontSize: 20, color: '#fa8c16' }} />, label: '图片' },
  pdf: { icon: <FilePdfOutlined style={{ fontSize: 20, color: '#f5222d' }} />, label: 'PDF 文档' },
  text: { icon: <FileTextOutlined style={{ fontSize: 20, color: '#8c8c8c' }} />, label: '文本文件' },
};

const VisDeliverable: React.FC<{  DeliverableData }> = ({ data }) => {
  const { deliverable_files = [], task_files_count = 0 } = data;

  const handleDeliverableClick = useCallback((fileId: string) => {
    ee.emit(EVENTS.SWITCH_TAB, { tab: `deliverable_${fileId}` });
    ee.emit(EVENTS.OPEN_PANEL);
  }, []);

  const handleTaskFilesClick = useCallback(() => {
    ee.emit(EVENTS.SWITCH_TAB, { tab: 'task_files' });
    ee.emit(EVENTS.OPEN_PANEL);
  }, []);

  if (deliverable_files.length === 0 && task_files_count === 0) {
    return null;
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, padding: '4px 0' }}>
      {deliverable_files.map((f) => {
        const config = renderTypeConfig[f.render_type || 'iframe'] || renderTypeConfig.iframe;
        return (
          <button
            key={f.file_id}
            onClick={() => handleDeliverableClick(f.file_id)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '14px 20px',
              borderRadius: 12,
              background: 'rgba(255,255,255,0.9)',
              border: '1px solid rgba(226,232,240,0.7)',
              cursor: 'pointer',
              textAlign: 'left',
              minWidth: 200,
              transition: 'all 0.15s ease',
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#93c5fd';
              e.currentTarget.style.background = 'rgba(255,255,255,1)';
              e.currentTarget.style.boxShadow = '0 2px 6px rgba(0,0,0,0.06)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(226,232,240,0.7)';
              e.currentTarget.style.background = 'rgba(255,255,255,0.9)';
              e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)';
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 10,
                background: '#eff6ff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              {config.icon}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <span
                style={{
                  fontSize: 14,
                  fontWeight: 500,
                  color: '#1e293b',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  maxWidth: 220,
                }}
              >
                {f.file_name}
              </span>
              <span style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>{config.label}</span>
            </div>
          </button>
        );
      })}
      {task_files_count > 0 && (
        <button
          onClick={handleTaskFilesClick}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '14px 20px',
            borderRadius: 12,
            background: 'rgba(255,255,255,0.9)',
            border: '1px solid rgba(226,232,240,0.7)',
            cursor: 'pointer',
            textAlign: 'left',
            minWidth: 240,
            transition: 'all 0.15s ease',
            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = '#fcd34d';
            e.currentTarget.style.background = 'rgba(255,255,255,1)';
            e.currentTarget.style.boxShadow = '0 2px 6px rgba(0,0,0,0.06)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'rgba(226,232,240,0.7)';
            e.currentTarget.style.background = 'rgba(255,255,255,0.9)';
            e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)';
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 10,
              background: '#fffbeb',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <FolderOpenOutlined style={{ fontSize: 20, color: '#f59e0b' }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span style={{ fontSize: 14, fontWeight: 500, color: '#1e293b' }}>
              查看此任务中的所有文件
            </span>
          </div>
        </button>
      )}
    </div>
  );
};

export default React.memo(VisDeliverable);
