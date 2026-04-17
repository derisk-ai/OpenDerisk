'use client';

import React, { createContext, useContext, useState, useCallback } from 'react';
import type { ContextMetrics } from '@/types/context-metrics';

interface ContextMetricsContextValue {
  metrics: ContextMetrics | null;
  updateMetrics: (newMetrics: ContextMetrics) => void;
  clearMetrics: () => void;
}

const ContextMetricsContext = createContext<ContextMetricsContextValue | null>(null);

interface ContextMetricsProviderProps {
  children: React.ReactNode;
  convId?: string;
}

export const ContextMetricsProvider: React.FC<ContextMetricsProviderProps> = ({
  children,
  convId,
}) => {
  const [metrics, setMetrics] = useState<ContextMetrics | null>(null);

  const updateMetrics = useCallback((newMetrics: ContextMetrics) => {
    setMetrics(newMetrics);
  }, []);

  const clearMetrics = useCallback(() => {
    setMetrics(null);
  }, []);

  // WebSocket 连接已禁用 - 后端未实现 /ws/context endpoint
  // 如需启用，请确保后端已实现该 WebSocket endpoint

  const value: ContextMetricsContextValue = {
    metrics,
    updateMetrics,
    clearMetrics,
  };

  return (
    <ContextMetricsContext.Provider value={value}>
      {children}
    </ContextMetricsContext.Provider>
  );
};

export const useContextMetrics = (): ContextMetricsContextValue => {
  const context = useContext(ContextMetricsContext);
  if (!context) {
    return {
      metrics: null,
      updateMetrics: () => {},
      clearMetrics: () => {},
    };
  }
  return context;
};

export default ContextMetricsContext;