'use client';

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import type { ContextMetrics, ContextMetricsEvent } from '@/types/context-metrics';

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
  const wsRef = useRef<WebSocket | null>(null);

  const updateMetrics = useCallback((newMetrics: ContextMetrics) => {
    setMetrics(newMetrics);
  }, []);

  const clearMetrics = useCallback(() => {
    setMetrics(null);
  }, []);

  // WebSocket 连接 (如果 convId 存在)
  useEffect(() => {
    if (!convId) return;

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/context/${convId}`;
    
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as ContextMetricsEvent;
          if (data.event_type === 'context_metrics_update' || data.event_type === 'context_metrics_full') {
            setMetrics(data.data);
          }
        } catch (e) {
          console.warn('[ContextMetrics] Failed to parse WebSocket message:', e);
        }
      };

      ws.onerror = (error) => {
        console.warn('[ContextMetrics] WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('[ContextMetrics] WebSocket closed');
      };
    } catch (e) {
      console.warn('[ContextMetrics] Failed to create WebSocket:', e);
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [convId]);

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