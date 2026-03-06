import React, { useState, useCallback } from 'react';
import { VisAuthorizationCardWrap } from './style';
import {
  Button,
  Divider,
  Tag,
  Space,
  Checkbox,
  Collapse,
  Typography,
} from 'antd';
import {
  LockOutlined,
  ToolOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useInteraction } from '@/components/interaction';
import { GrantScope } from '@/types/interaction';

const { Text } = Typography;

// ========== Types ==========

export interface VisAuthorizationCardData {
  request_id: string;
  message: string;
  tool_name: string;
  risk_level?: 'safe' | 'low' | 'medium' | 'high' | 'critical';
  risk_factors?: string[];
  arguments?: Record<string, unknown>;
  allow_session_grant?: boolean;
  timeout?: number;
  disabled?: boolean;
}

interface VisAuthorizationCardProps {
  data: VisAuthorizationCardData;
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

const VisAuthorizationCard: React.FC<VisAuthorizationCardProps> = ({ data }) => {
  const { authorize, cancelRequest, showRequest } = useInteraction();
  const [disabled, setDisabled] = useState<boolean>(!!data.disabled);
  const [grantScope, setGrantScope] = useState<GrantScope>(GrantScope.ONCE);
  const [loading, setLoading] = useState(false);

  const toolArgs = data.arguments ?? {};
  const riskFactors = data.risk_factors ?? [];
  const allowSessionGrant = data.allow_session_grant ?? true;

  const handleAuthorize = useCallback(async () => {
    setLoading(true);
    try {
      // Show the request in the interaction manager first
      showRequest(data.request_id);
      const success = await authorize(true, grantScope);
      if (success) {
        setDisabled(true);
      }
    } finally {
      setLoading(false);
    }
  }, [authorize, grantScope, data.request_id, showRequest]);

  const handleDeny = useCallback(async () => {
    setLoading(true);
    try {
      showRequest(data.request_id);
      const success = await cancelRequest('User denied authorization');
      if (success) {
        setDisabled(true);
      }
    } finally {
      setLoading(false);
    }
  }, [cancelRequest, data.request_id, showRequest]);

  return (
    <VisAuthorizationCardWrap className="VisAuthorizationCardClass">
      <div className="card-content">
        {/* Header */}
        <div className="auth-header">
          <LockOutlined className="auth-icon" />
          <span className="auth-title">Tool Authorization Required</span>
        </div>

        <Divider
          style={{
            margin: '8px 0px 8px 0px',
            borderWidth: '1px',
            borderColor: 'rgba(0, 0, 0, 0.06)',
          }}
        />

        {/* Message */}
        <div className="whitespace-normal" style={{ marginBottom: 12 }}>
          <Text>{data.message}</Text>
        </div>

        {/* Tool Info */}
        <div className="tool-info">
          <ToolOutlined />
          <span className="tool-name">{data.tool_name}</span>
          <Tag
            color={getRiskLevelColor(data.risk_level)}
            icon={getRiskLevelIcon(data.risk_level)}
          >
            {getRiskLevelLabel(data.risk_level)}
          </Tag>
        </div>

        {/* Risk Factors */}
        {riskFactors.length > 0 && (
          <div className="risk-factors">
            {riskFactors.map((factor, index) => (
              <Tag key={index} color="orange">
                {factor}
              </Tag>
            ))}
          </div>
        )}

        {/* Tool Arguments */}
        {Object.keys(toolArgs).length > 0 && (
          <Collapse
            ghost
            size="small"
            className="arguments-section"
            items={[
              {
                key: 'arguments',
                label: (
                  <Text strong style={{ fontSize: 12 }}>
                    Tool Arguments ({Object.keys(toolArgs).length})
                  </Text>
                ),
                children: (
                  <div className="arguments-content">
                    {Object.entries(toolArgs).map(([key, value]) => (
                      <div key={key} className="arg-item">
                        <span className="arg-key">{key}:</span>
                        <pre className="arg-value">
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

        {/* Session Grant Option */}
        {allowSessionGrant && !disabled && (
          <div className="session-grant-option">
            <Checkbox
              checked={grantScope === GrantScope.SESSION}
              onChange={(e) =>
                setGrantScope(e.target.checked ? GrantScope.SESSION : GrantScope.ONCE)
              }
            >
              <Text style={{ fontSize: 12 }}>Allow this tool for the entire session</Text>
            </Checkbox>
          </div>
        )}

        <Divider
          style={{
            margin: '8px 0px 8px 0px',
            borderWidth: '1px',
            borderColor: 'rgba(0, 0, 0, 0.06)',
          }}
        />

        {/* Footer with Buttons */}
        <div className="auth-footer">
          <Button
            disabled={disabled}
            danger
            icon={<CloseCircleOutlined />}
            onClick={handleDeny}
            loading={loading}
          >
            Deny
          </Button>
          <Button
            disabled={disabled}
            type="primary"
            icon={<CheckCircleOutlined />}
            style={
              !disabled
                ? {
                    backgroundImage:
                      'linear-gradient(104deg, #3595ff 13%, #185cff 99%)',
                    color: '#ffffff',
                  }
                : undefined
            }
            onClick={handleAuthorize}
            loading={loading}
          >
            {grantScope === GrantScope.SESSION ? 'Allow (Session)' : 'Allow Once'}
          </Button>
        </div>
      </div>
    </VisAuthorizationCardWrap>
  );
};

export default VisAuthorizationCard;
