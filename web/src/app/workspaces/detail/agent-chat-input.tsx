'use client';

import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { Button, Input } from 'antd';
import { ReloadOutlined, SendOutlined } from '@ant-design/icons';

export interface AgentChatInputProps {
  placeholder?: string;
  onSend: (text: string) => void;
  loading?: boolean;
  disabled?: boolean;
  lastInput?: string | null;
  onRetry?: () => void;
}

export interface AgentChatInputHandle {
  focus: () => void;
}

export const AgentChatInput = forwardRef<AgentChatInputHandle, AgentChatInputProps>(function AgentChatInput(
  { placeholder = '输入指令给 Agent...', onSend, loading, disabled, lastInput, onRetry },
  ref
) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    focus: () => inputRef.current?.focus(),
  }));

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="ws-agent-chat-input">
      <Input.TextArea
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoSize={{ minRows: 1, maxRows: 6 }}
        disabled={disabled || loading}
      />
      {lastInput && onRetry && !loading && (
        <Button
          icon={<ReloadOutlined />}
          onClick={onRetry}
          disabled={disabled}
          title="Retry last input"
        />
      )}
      <Button
        type="primary"
        icon={<SendOutlined />}
        onClick={handleSend}
        loading={loading}
        disabled={!text.trim() || disabled || loading}
      />
    </div>
  );
});
