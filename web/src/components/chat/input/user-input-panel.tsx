'use client';

import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Input, Tooltip, Badge, Tag, message } from 'antd';
import {
  SendOutlined,
  MessageOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import classNames from 'classnames';
import useUserInput from '@/hooks/use-user-input';

interface UserInputPanelProps {
  sessionId: string | undefined;
  isExecuting: boolean;
  onInputSubmitted?: () => void;
  compact?: boolean;
}

const UserInputPanel: React.FC<UserInputPanelProps> = ({
  sessionId,
  isExecuting,
  onInputSubmitted,
  compact = false,
}) => {
  const { t } = useTranslation();
  const [inputValue, setInputValue] = useState('');
  const [isZhInput, setIsZhInput] = useState(false);
  
  const {
    submitUserInput,
    isSubmitting,
    hasPendingInput,
    pendingCount,
    queueState,
  } = useUserInput(sessionId);

  const handleSubmit = useCallback(async () => {
    if (!inputValue.trim()) return;
    
    const success = await submitUserInput(inputValue.trim());
    
    if (success) {
      setInputValue('');
      onInputSubmitted?.();
    }
  }, [inputValue, submitUserInput, onInputSubmitted]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !isZhInput) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit, isZhInput]);

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <Input
          placeholder={t('user_input_placeholder', '输入补充信息...')}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => setIsZhInput(true)}
          onCompositionEnd={() => setIsZhInput(false)}
          className="flex-1"
          size="small"
          disabled={!isExecuting}
        />
        <Tooltip title={hasPendingInput ? t('pending_inputs', `${pendingCount} 条待处理输入`) : ''}>
          <Badge count={pendingCount} size="small">
            <Button
              type="primary"
              size="small"
              icon={isSubmitting ? <LoadingOutlined /> : <SendOutlined />}
              onClick={handleSubmit}
              disabled={!inputValue.trim() || !isExecuting || isSubmitting}
            />
          </Badge>
        </Tooltip>
      </div>
    );
  }

  return (
    <div className={classNames(
      'w-full rounded-xl border transition-all duration-300',
      isExecuting
        ? 'bg-indigo-50/50 dark:bg-indigo-900/20 border-indigo-200 dark:border-indigo-800'
        : 'bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700'
    )}>
      <div className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <MessageOutlined className="text-indigo-500" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {t('user_input_title', '主动输入')}
          </span>
          {isExecuting && (
            <Tag color="blue" className="ml-auto">
              {t('agent_executing', '执行中')}
            </Tag>
          )}
          {hasPendingInput && (
            <Tag color="green" className="ml-auto">
              <CheckCircleOutlined className="mr-1" />
              {t('pending_count', `${pendingCount} 条待处理`)}
            </Tag>
          )}
        </div>
        
        <div className="flex gap-2">
          <Input.TextArea
            placeholder={t('user_input_placeholder', '在 Agent 执行过程中输入补充信息，当前步骤完成后会处理...')}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => setIsZhInput(true)}
            onCompositionEnd={() => setIsZhInput(false)}
            autoSize={{ minRows: 2, maxRows: 4 }}
            className="flex-1"
            disabled={!isExecuting}
          />
          <Button
            type="primary"
            icon={isSubmitting ? <LoadingOutlined /> : <SendOutlined />}
            onClick={handleSubmit}
            disabled={!inputValue.trim() || !isExecuting || isSubmitting}
            className="self-end"
          >
            {t('submit_input', '提交')}
          </Button>
        </div>
        
        {!isExecuting && (
          <p className="text-xs text-gray-400 mt-2">
            {t('input_disabled_hint', 'Agent 执行过程中才能提交输入')}
          </p>
        )}
      </div>
    </div>
  );
};

export default UserInputPanel;