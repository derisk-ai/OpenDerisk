/**
 * InteractionHandler - Unified Handler for Different Interaction Types
 *
 * A switch component that renders the appropriate UI based on interaction type:
 * - CONFIRMATION: Yes/No dialog
 * - AUTHORIZATION: Tool authorization dialog
 * - TEXT_INPUT: Text input dialog
 * - SINGLE_SELECT / MULTI_SELECT: Selection dialog
 * - NOTIFICATION: Toast/Alert display
 * - PROGRESS: Progress indicator
 */

'use client';

import React, { useState, useCallback, useMemo } from 'react';
import {
  Modal,
  Button,
  Space,
  Input,
  Select,
  Checkbox,
  Radio,
  Progress,
  Alert,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  UploadOutlined,
  InfoCircleOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { useInteraction } from './InteractionManager';
import { AuthorizationDialog } from './AuthorizationDialog';
import type { InteractionRequest, InteractionOption } from '@/types/interaction';
import { InteractionType, InteractionPriority } from '@/types/interaction';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

// ========== Types ==========

export interface InteractionHandlerProps {
  /** Custom request to handle (overrides context) */
  request?: InteractionRequest;
  /** Whether to show as modal (default: true) */
  asModal?: boolean;
  /** Callback when interaction is completed */
  onComplete?: (success: boolean) => void;
}

// ========== Helper Components ==========

/**
 * Confirmation Dialog Component
 */
function ConfirmationContent({
  request,
  onConfirm,
  onCancel,
  loading,
}: {
  request: InteractionRequest;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const confirmLabel = request.options.find(o => o.value === 'yes')?.label ?? 'Confirm';
  const cancelLabel = request.options.find(o => o.value === 'no')?.label ?? 'Cancel';

  return (
    <div>
      <Paragraph>{request.message}</Paragraph>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 24 }}>
        {request.allow_cancel && (
          <Button onClick={onCancel} loading={loading}>
            {cancelLabel}
          </Button>
        )}
        <Button type="primary" onClick={onConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </div>
    </div>
  );
}

/**
 * Text Input Dialog Component
 */
function TextInputContent({
  request,
  onSubmit,
  onCancel,
  loading,
}: {
  request: InteractionRequest;
  onSubmit: (value: string) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const [value, setValue] = useState(request.default_value ?? '');
  const placeholder = (request.metadata?.placeholder as string) ?? 'Enter your response...';
  const multiline = (request.metadata?.multiline as boolean) ?? false;

  const handleSubmit = useCallback(() => {
    if (value.trim()) {
      onSubmit(value.trim());
    }
  }, [value, onSubmit]);

  return (
    <div>
      <Paragraph>{request.message}</Paragraph>
      {multiline ? (
        <TextArea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          rows={4}
          style={{ marginBottom: 16 }}
        />
      ) : (
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          onPressEnter={handleSubmit}
          style={{ marginBottom: 16 }}
        />
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        {request.allow_cancel && (
          <Button onClick={onCancel} loading={loading}>
            Cancel
          </Button>
        )}
        <Button
          type="primary"
          onClick={handleSubmit}
          loading={loading}
          disabled={!value.trim()}
        >
          Submit
        </Button>
      </div>
    </div>
  );
}

/**
 * Single Select Dialog Component
 */
function SingleSelectContent({
  request,
  onSelect,
  onCancel,
  loading,
}: {
  request: InteractionRequest;
  onSelect: (value: string) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const [selected, setSelected] = useState<string | undefined>(
    request.default_value ?? request.options.find(o => o.default)?.value
  );

  const handleSubmit = useCallback(() => {
    if (selected) {
      onSelect(selected);
    }
  }, [selected, onSelect]);

  return (
    <div>
      <Paragraph>{request.message}</Paragraph>
      <Radio.Group
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        style={{ width: '100%', marginBottom: 16 }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          {request.options.map((option) => (
            <Radio
              key={option.value}
              value={option.value}
              disabled={option.disabled}
              style={{ display: 'block', marginBottom: 8 }}
            >
              <Space direction="vertical" size={0}>
                <Text>{option.label}</Text>
                {option.description && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {option.description}
                  </Text>
                )}
              </Space>
            </Radio>
          ))}
        </Space>
      </Radio.Group>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        {request.allow_cancel && (
          <Button onClick={onCancel} loading={loading}>
            Cancel
          </Button>
        )}
        <Button
          type="primary"
          onClick={handleSubmit}
          loading={loading}
          disabled={!selected}
        >
          Select
        </Button>
      </div>
    </div>
  );
}

/**
 * Multi Select Dialog Component
 */
function MultiSelectContent({
  request,
  onSelect,
  onCancel,
  loading,
}: {
  request: InteractionRequest;
  onSelect: (values: string[]) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const [selected, setSelected] = useState<string[]>(
    request.default_values ?? request.options.filter(o => o.default).map(o => o.value)
  );

  const handleChange = useCallback((value: string, checked: boolean) => {
    setSelected(prev =>
      checked ? [...prev, value] : prev.filter(v => v !== value)
    );
  }, []);

  const handleSubmit = useCallback(() => {
    if (selected.length > 0) {
      onSelect(selected);
    }
  }, [selected, onSelect]);

  return (
    <div>
      <Paragraph>{request.message}</Paragraph>
      <Space direction="vertical" style={{ width: '100%', marginBottom: 16 }}>
        {request.options.map((option) => (
          <Checkbox
            key={option.value}
            checked={selected.includes(option.value)}
            disabled={option.disabled}
            onChange={(e) => handleChange(option.value, e.target.checked)}
          >
            <Space direction="vertical" size={0}>
              <Text>{option.label}</Text>
              {option.description && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {option.description}
                </Text>
              )}
            </Space>
          </Checkbox>
        ))}
      </Space>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        {request.allow_cancel && (
          <Button onClick={onCancel} loading={loading}>
            Cancel
          </Button>
        )}
        <Button
          type="primary"
          onClick={handleSubmit}
          loading={loading}
          disabled={selected.length === 0}
        >
          Submit ({selected.length} selected)
        </Button>
      </div>
    </div>
  );
}

/**
 * File Upload Dialog Component
 */
function FileUploadContent({
  request,
  onUpload,
  onCancel,
  loading,
}: {
  request: InteractionRequest;
  onUpload: (fileIds: string[]) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const [fileList, setFileList] = useState<string[]>([]);
  const acceptedTypes = request.accepted_file_types?.join(',') ?? '*';
  const multiple = request.allow_multiple_files ?? false;

  // TODO: Implement actual file upload logic
  const handleUpload = useCallback((info: any) => {
    if (info.file.status === 'done') {
      const fileId = info.file.response?.file_id ?? info.file.uid;
      setFileList(prev => [...prev, fileId]);
      message.success(`${info.file.name} uploaded successfully`);
    } else if (info.file.status === 'error') {
      message.error(`${info.file.name} upload failed`);
    }
  }, []);

  const handleSubmit = useCallback(() => {
    if (fileList.length > 0) {
      onUpload(fileList);
    }
  }, [fileList, onUpload]);

  return (
    <div>
      <Paragraph>{request.message}</Paragraph>
      <Upload.Dragger
        accept={acceptedTypes}
        multiple={multiple}
        onChange={handleUpload}
        style={{ marginBottom: 16 }}
      >
        <p className="ant-upload-drag-icon">
          <UploadOutlined />
        </p>
        <p className="ant-upload-text">Click or drag files to upload</p>
        {request.max_file_size && (
          <p className="ant-upload-hint">
            Max file size: {Math.round(request.max_file_size / 1024 / 1024)}MB
          </p>
        )}
      </Upload.Dragger>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        {request.allow_cancel && (
          <Button onClick={onCancel} loading={loading}>
            Cancel
          </Button>
        )}
        <Button
          type="primary"
          onClick={handleSubmit}
          loading={loading}
          disabled={fileList.length === 0}
        >
          Submit
        </Button>
      </div>
    </div>
  );
}

/**
 * Progress Display Component (non-modal)
 */
function ProgressContent({ request }: { request: InteractionRequest }) {
  const percent = (request.progress_value ?? 0) * 100;
  const progressMessage = request.progress_message ?? request.message;

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" style={{ width: '100%' }}>
        <Text>{progressMessage}</Text>
        <Progress percent={Math.round(percent)} status="active" />
      </Space>
    </div>
  );
}

/**
 * Notification Display Component (non-modal)
 */
function NotificationContent({ request }: { request: InteractionRequest }) {
  const getAlertType = () => {
    switch (request.type) {
      case InteractionType.SUCCESS:
        return 'success';
      case InteractionType.WARNING:
        return 'warning';
      case InteractionType.ERROR:
        return 'error';
      default:
        return 'info';
    }
  };

  return (
    <Alert
      type={getAlertType()}
      message={request.title ?? 'Notification'}
      description={request.message}
      showIcon
      closable
    />
  );
}

// ========== Main Component ==========

export function InteractionHandler({
  request: externalRequest,
  asModal = true,
  onComplete,
}: InteractionHandlerProps) {
  const {
    activeRequest: contextRequest,
    isDialogOpen,
    hideDialog,
    confirm,
    submitTextInput,
    submitSelection,
    cancelRequest,
  } = useInteraction();

  const request = externalRequest ?? contextRequest;
  const [loading, setLoading] = useState(false);

  // Handlers
  const handleComplete = useCallback((success: boolean) => {
    onComplete?.(success);
    hideDialog();
  }, [onComplete, hideDialog]);

  const handleConfirm = useCallback(async () => {
    setLoading(true);
    try {
      const success = await confirm(true);
      handleComplete(success);
    } finally {
      setLoading(false);
    }
  }, [confirm, handleComplete]);

  const handleCancel = useCallback(async () => {
    setLoading(true);
    try {
      const success = await cancelRequest();
      handleComplete(!success); // Cancel means not successful completion
    } finally {
      setLoading(false);
    }
  }, [cancelRequest, handleComplete]);

  const handleTextSubmit = useCallback(async (value: string) => {
    setLoading(true);
    try {
      const success = await submitTextInput(value);
      handleComplete(success);
    } finally {
      setLoading(false);
    }
  }, [submitTextInput, handleComplete]);

  const handleSingleSelect = useCallback(async (value: string) => {
    setLoading(true);
    try {
      const success = await submitSelection(value);
      handleComplete(success);
    } finally {
      setLoading(false);
    }
  }, [submitSelection, handleComplete]);

  const handleMultiSelect = useCallback(async (values: string[]) => {
    setLoading(true);
    try {
      const success = await submitSelection(values);
      handleComplete(success);
    } finally {
      setLoading(false);
    }
  }, [submitSelection, handleComplete]);

  const handleFileUpload = useCallback(async (fileIds: string[]) => {
    // TODO: Implement file upload submission
    handleComplete(true);
  }, [handleComplete]);

  // Don't render if no request
  if (!request) {
    return null;
  }

  // Render content based on type
  const renderContent = () => {
    switch (request.type) {
      case InteractionType.AUTHORIZATION:
        return <AuthorizationDialog />;

      case InteractionType.CONFIRMATION:
        return (
          <ConfirmationContent
            request={request}
            onConfirm={handleConfirm}
            onCancel={handleCancel}
            loading={loading}
          />
        );

      case InteractionType.TEXT_INPUT:
        return (
          <TextInputContent
            request={request}
            onSubmit={handleTextSubmit}
            onCancel={handleCancel}
            loading={loading}
          />
        );

      case InteractionType.SINGLE_SELECT:
      case InteractionType.PLAN_SELECTION:
        return (
          <SingleSelectContent
            request={request}
            onSelect={handleSingleSelect}
            onCancel={handleCancel}
            loading={loading}
          />
        );

      case InteractionType.MULTI_SELECT:
        return (
          <MultiSelectContent
            request={request}
            onSelect={handleMultiSelect}
            onCancel={handleCancel}
            loading={loading}
          />
        );

      case InteractionType.FILE_UPLOAD:
        return (
          <FileUploadContent
            request={request}
            onUpload={handleFileUpload}
            onCancel={handleCancel}
            loading={loading}
          />
        );

      case InteractionType.PROGRESS:
        return <ProgressContent request={request} />;

      case InteractionType.INFO:
      case InteractionType.WARNING:
      case InteractionType.ERROR:
      case InteractionType.SUCCESS:
        return <NotificationContent request={request} />;

      default:
        return (
          <div>
            <Paragraph>{request.message}</Paragraph>
            <Button onClick={handleCancel}>Close</Button>
          </div>
        );
    }
  };

  // Non-modal types
  const nonModalTypes = [
    InteractionType.PROGRESS,
    InteractionType.INFO,
    InteractionType.WARNING,
    InteractionType.ERROR,
    InteractionType.SUCCESS,
  ];

  // Authorization has its own modal
  if (request.type === InteractionType.AUTHORIZATION) {
    return <AuthorizationDialog />;
  }

  // Render as non-modal for certain types
  if (nonModalTypes.includes(request.type as any) || !asModal) {
    return renderContent();
  }

  // Render as modal
  return (
    <Modal
      title={request.title ?? getDefaultTitle(request.type)}
      open={isDialogOpen}
      onCancel={handleCancel}
      footer={null}
      centered
      maskClosable={request.allow_cancel}
    >
      {renderContent()}
    </Modal>
  );
}

/**
 * Get default title based on interaction type.
 */
function getDefaultTitle(type: string): string {
  switch (type) {
    case InteractionType.CONFIRMATION:
      return 'Confirmation Required';
    case InteractionType.TEXT_INPUT:
      return 'Input Required';
    case InteractionType.SINGLE_SELECT:
      return 'Select an Option';
    case InteractionType.MULTI_SELECT:
      return 'Select Options';
    case InteractionType.FILE_UPLOAD:
      return 'Upload Files';
    case InteractionType.PLAN_SELECTION:
      return 'Select a Plan';
    default:
      return 'Interaction';
  }
}

export default InteractionHandler;
