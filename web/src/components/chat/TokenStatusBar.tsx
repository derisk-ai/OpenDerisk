import React from 'react';

export interface UsageMetrics {
  total: number;
  prompt: number;
  completion: number;
  context_window: number;
  ratio: number;
  step_state?: string;
}

export const TokenStatusBar: React.FC<{ usageMetrics: UsageMetrics | null }> = ({ usageMetrics }) => {
  if (!usageMetrics) return null;
  const { total, context_window, ratio, step_state } = usageMetrics;
  const ratioPct = context_window > 0 ? (ratio * 100).toFixed(1) + '%' : '—';
  return (
    <div className="token-status-bar" role="status" aria-live="polite">
      <span className="token-count">{total.toLocaleString()} tokens</span>
      {context_window > 0 && (
        <span className="token-context">/ {context_window.toLocaleString()} ctx</span>
      )}
      <span className="token-ratio">{ratioPct}</span>
      {step_state && <span className="step-state">{step_state}</span>}
    </div>
  );
};