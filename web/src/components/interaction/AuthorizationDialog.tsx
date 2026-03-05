/**
 * AuthorizationDialog - Tool Authorization Popup Modal
 *
 * Displays authorization requests for tool execution.
 * Shows tool details, risk level, arguments, and allows user to approve/deny.
 */

'use client';

import React, { useState, useCallback, useMemo } from 'react';
import {
  Modal,
  Button,
  Space,
  Tag,
  Typography,
  Descriptions,
  Checkbox,
  Alert,
  Tooltip,
  Collapse,
} from 'antd';
import {
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  LockOutlined,
  UnlockOutlined,
  ToolOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useInteraction } from './InteractionManager';
import type { InteractionRequest, GrantScope } from '@/types/interaction';
import { GrantScope as GrantScopeEnum } from '@/types/interaction';
import type { RiskLevel } from '@/types/tool';

const { Text, Title, Paragraph } = Typography;
const { Panel } = Collapse;

// ========== Types ==========

export interface AuthorizationDialogProps {
  /** Custom request to display (overrides context) */
  request?: InteractionRequest;
  /** Whether dialog is open (overrides context) */
  open?: boolean;
  /** Callback when dialog closes */
  onClose?: () => void;
  /** Callback when authorization is granted */
  onAuthorize?: (grantScope: GrantScope) => void;
  /** Callback when authorization is denied */
  onDeny?: () => void;
}

// ========== Helper Functions ==========

/**
 * Get risk level color for Tag.
 */
function getRiskLevelColor(riskLevel?: string): string {
  switch (riskLevel?.toLowerCase()) {
    case 'safe':
      return 'success';
    case 'low':
      return 'blue';
    case 'medium':
      return 'warning';
    case 'high':
      return 'orange';
    case 'critical':
      return 'error';
    default:
      return 'default';
  }
}

/**
 * Get risk level icon.
 */
function getRiskLevelIcon(riskLevel?: string): React.ReactNode {
  switch (riskLevel?.toLowerCase()) {
    case 'safe':
      return <CheckCircleOutlined />;
    case 'low':
      return <InfoCircleOutlined />;
    case 'medium':
      return <WarningOutlined />;
    case 'high':
    case 'critical':
      return <ExclamationCircleOutlined />;
    default:
      return <InfoCircleOutlined />;
  }
}

/**
 * Get risk level display name.
 */
function getRiskLevelLabel(riskLevel?: string): string {
  switch (riskLevel?.toLowerCase()) {
    case 'safe':
      return 'Safe';
    case 'low':
      return 'Low Risk';
    case 'medium':
      return 'Medium Risk';
    case 'high':
      return 'High Risk';
    case 'critical':
      return 'Critical Risk';
    default:
      return 'Unknown';
  }
}

/**
 * Format argument value for display.
 */
function formatArgumentValue(value: unknown): string {
  if (value === null || value === undefined) {
    return 'null';
  }
  if (typeof value === 'string') {
    // Truncate long strings
    if (value.length > 200) {
      return value.substring(0, 200) + '...';
    }
    return value;
  }
  if (typeof value === 'object') {
    const str = JSON.stringify(value, null, 2);
    if (str.length > 500) {
      return str.substring(0, 500) + '...';
    }
    return str;
  }
  return String(value);
}

// ========== Component ==========

export function AuthorizationDialog({
  request: externalRequest,
  open: externalOpen,
  onClose,
  onAuthorize,
  onDeny,
}: AuthorizationDialogProps) {
  const {
    activeRequest: contextRequest,
    isDialogOpen: contextOpen,
    authorize,
    cancelRequest,
    hideDialog,
  } = useInteraction();

  // Use external props if provided, otherwise use context
  const request = externalRequest ?? contextRequest;
  const isOpen = externalOpen ?? contextOpen;

  // Local state
  const [grantScope, setGrantScope] = useState<GrantScope>(GrantScopeEnum.ONCE);
  const [loading, setLoading] = useState(false);

  // Extract authorization context
  const authContext = request?.authorization_context;
  const toolName = authContext?.tool_name ?? 'Unknown Tool';
  const toolArgs = authContext?.arguments ?? {};
  const riskLevel = authContext?.risk_level;
  const riskFactors = authContext?.risk_factors ?? [];

  // Check if session grant is allowed
  const allowSessionGrant = request?.allow_session_grant ?? true;

  // Handlers
  const handleClose = useCallback(() => {
    onClose?.();
    hideDialog();
  }, [onClose, hideDialog]);

  const handleAuthorize = useCallback(async () => {
    setLoading(true);
    try {
      const success = await authorize(true, grantScope);
      if (success) {
        onAuthorize?.(grantScope);
      }
    } finally {
      setLoading(false);
    }
  }, [authorize, grantScope, onAuthorize]);

  const handleDeny = useCallback(async () => {
    setLoading(true);
    try {
      const success = await cancelRequest('User denied authorization');
      if (success) {
        onDeny?.();
      }
    } finally {
      setLoading(false);
    }
  }, [cancelRequest, onDeny]);

  // Check if this is a high-risk operation
  const isHighRisk = useMemo(() => {
    const level = riskLevel?.toLowerCase();
    return level === 'high' || level === 'critical';
  }, [riskLevel]);

  // Don't render if no request
  if (!request) {
    return null;
  }

  return (
    <Modal
      title={
        <Space>
          <LockOutlined />
          <span>Tool Authorization Required</span>
        </Space>
      }
      open={isOpen}
      onCancel={handleClose}
      footer={null}
      width={600}
      centered
      maskClosable={!isHighRisk}
      keyboard={!isHighRisk}
      className="authorization-dialog"
    >
      {/* Risk Alert for High Risk */}
      {isHighRisk && (
        <Alert
          type="warning"
          showIcon
          icon={<ExclamationCircleOutlined />}
          message="High Risk Operation"
          description="This operation has been identified as high risk. Please review carefully before authorizing."
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Main Message */}
      <Paragraph style={{ marginBottom: 16 }}>
        {request.message}
      </Paragraph>

      {/* Tool Information */}
      <Descriptions
        column={1}
        size="small"
        bordered
        style={{ marginBottom: 16 }}
      >
        <Descriptions.Item
          label={
            <Space>
              <ToolOutlined />
              <span>Tool</span>
            </Space>
          }
        >
          <Text strong>{toolName}</Text>
        </Descriptions.Item>

        <Descriptions.Item label="Risk Level">
          <Tag color={getRiskLevelColor(riskLevel)} icon={getRiskLevelIcon(riskLevel)}>
            {getRiskLevelLabel(riskLevel)}
          </Tag>
        </Descriptions.Item>

        {request.timeout && (
          <Descriptions.Item
            label={
              <Space>
                <ClockCircleOutlined />
                <span>Timeout</span>
              </Space>
            }
          >
            {request.timeout} seconds
          </Descriptions.Item>
        )}
      </Descriptions>

      {/* Risk Factors */}
      {riskFactors.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            Risk Factors:
          </Text>
          <Space wrap>
            {riskFactors.map((factor, index) => (
              <Tag key={index} color="orange">
                {factor}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {/* Tool Arguments */}
      {Object.keys(toolArgs).length > 0 && (
        <Collapse
          ghost
          style={{ marginBottom: 16 }}
          items={[
            {
              key: 'arguments',
              label: (
                <Text strong>
                  Tool Arguments ({Object.keys(toolArgs).length})
                </Text>
              ),
              children: (
                <div
                  style={{
                    maxHeight: 200,
                    overflow: 'auto',
                    backgroundColor: '#f5f5f5',
                    padding: 12,
                    borderRadius: 4,
                    fontFamily: 'monospace',
                    fontSize: 12,
                  }}
                >
                  {Object.entries(toolArgs).map(([key, value]) => (
                    <div key={key} style={{ marginBottom: 8 }}>
                      <Text type="secondary">{key}:</Text>
                      <pre
                        style={{
                          margin: '4px 0 0 16px',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-all',
                        }}
                      >
                        {formatArgumentValue(value)}
                      </pre>
                    </div>
                  ))}
                </div>
              ),
            },
          ]}
        />
      )}

      {/* Grant Scope Options */}
      {allowSessionGrant && (
        <div style={{ marginBottom: 24 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Checkbox
              checked={grantScope === GrantScopeEnum.SESSION}
              onChange={(e) =>
                setGrantScope(e.target.checked ? GrantScopeEnum.SESSION : GrantScopeEnum.ONCE)
              }
            >
              <Space>
                <UnlockOutlined />
                <span>Allow this tool for the entire session</span>
              </Space>
            </Checkbox>
            {grantScope === GrantScopeEnum.SESSION && (
              <Text type="secondary" style={{ marginLeft: 24 }}>
                You won&apos;t be asked again for this tool during this session.
              </Text>
            )}
          </Space>
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        {request.allow_skip && (
          <Button onClick={() => handleClose()}>
            Skip
          </Button>
        )}

        <Button
          danger
          icon={<CloseCircleOutlined />}
          onClick={handleDeny}
          loading={loading}
        >
          Deny
        </Button>

        <Button
          type="primary"
          icon={<CheckCircleOutlined />}
          onClick={handleAuthorize}
          loading={loading}
        >
          {grantScope === GrantScopeEnum.SESSION ? 'Allow (Session)' : 'Allow Once'}
        </Button>
      </div>
    </Modal>
  );
}

export default AuthorizationDialog;
