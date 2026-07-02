import React from 'react';

export const MessageTokenBadge: React.FC<{
  stepTokens: number;
  stepState: string;
}> = ({ stepTokens, stepState }) => {
  return (
    <span className="message-token-badge" title={`${stepState} · ${stepTokens} tokens`}>
      <span className="badge-state">{stepState}</span>
      <span className="badge-tokens">{stepTokens > 0 ? stepTokens : '—'}</span>
    </span>
  );
};