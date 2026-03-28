'use client';

import React, { FC, useState } from 'react';

interface RingDataItem {
  name: string;
  value: number;
  color: string;
  description?: string;
}

interface SystemEvent {
  event_id: string;
  event_type: string;
  title: string;
  description?: string;
  timestamp?: string;
  duration_ms?: number;
  status?: 'done' | 'running' | 'failed';
  metadata?: {
    ring_data?: RingDataItem[];
    [key: string]: unknown;
  };
}

interface SystemEventsData {
  is_running: boolean;
  current_action?: string;
  current_phase: 'preparation' | 'execution' | 'completion';
  recent_events: SystemEvent[];
  total_count: number;
  has_more: boolean;
  total_duration_ms?: number;
}

interface VisSystemEventsProps {
  data: SystemEventsData;
}

const formatDuration = (ms?: number): string => {
  if (!ms) return '';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${((ms % 60000) / 1000).toFixed(0)}s`;
};

const MiniRingChart: FC<{ data: RingDataItem[]; size?: number }> = ({ data, size = 24 }) => {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  if (total === 0) return null;

  const strokeWidth = 3;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  let currentOffset = 0;
  const segments = data.map((item) => {
    const percentage = item.value / total;
    const segmentLength = circumference * percentage;
    const segment = {
      color: item.color,
      offset: currentOffset,
      length: segmentLength,
      item: item,
    };
    currentOffset += segmentLength;
    return segment;
  });

  const formatValue = (value: number) => {
    if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
    if (value >= 1000) return `${(value / 1000).toFixed(0)}K`;
    return value.toString();
  };

  const tooltipText = segments
    .filter(s => s.item.value > 0)
    .map(s => s.item.description || `${s.item.name}: ${formatValue(s.item.value)}`)
    .join('\n');

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ cursor: 'help' }}>
      <title>{tooltipText}</title>
      {segments.map((segment, index) => (
        <circle
          key={index}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={segment.color}
          strokeWidth={strokeWidth}
          strokeDasharray={`${segment.length} ${circumference}`}
          strokeDashoffset={-segment.offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      ))}
    </svg>
  );
};

export const VisSystemEvents: FC<VisSystemEventsProps> = ({ data }) => {
  const { is_running, current_phase, recent_events, total_count, total_duration_ms } = data;
  const [isExpanded, setIsExpanded] = useState(false);

// 只有在非运行状态下且有失败事件时，才显示整体错误状态
  // 运行中时，即使有失败事件（如重试中），也显示运行状态
  const hasError = !is_running && (recent_events?.some(e => e.status === 'failed') ?? false);

  // 统计失败事件数量（用于展开列表中显示）
  const failedCount = recent_events?.filter(e => e.status === 'failed').length ?? 0;

  const getAccentColor = () => {
    if (hasError) return '#ef4444';
    if (!is_running) return '#22c55e';
    switch (current_phase) {
      case 'preparation': return '#f59e0b';
      case 'execution': return '#6366f1';
      case 'completion': return '#22c55e';
      default: return '#6366f1';
    }
  };

  const getStatusText = () => {
    if (hasError) {
      // 如果有多个失败事件，显示数量
      if (failedCount > 1) {
        return `执行出错 (${failedCount}个)`;
      }
      return '执行出错';
    }
    if (!is_running) return '执行完成';

    const latestEvent = recent_events?.[0];
    if (latestEvent) {
      if (data.current_action) return data.current_action;
      return latestEvent.title;
    }
    return '初始化中...';
  };

  if (!is_running && (!recent_events || recent_events.length === 0) && !total_duration_ms) {
    return null;
  }

  const accentColor = getAccentColor();
  const statusText = getStatusText();
  const displayEvents = isExpanded ? (recent_events || []) : (recent_events?.slice(0, 1) || []);

  return (
    <div
      style={{
        padding: '10px 14px',
        background: '#ffffff',
        borderRadius: '8px',
        border: '1px solid #e5e7eb',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
        display: 'flex',
        alignItems: isExpanded ? 'flex-start' : 'center',
        gap: '12px',
      }}
    >
      {/* Loading 图标 */}
      <div
        style={{
          width: '22px',
          height: '22px',
          borderRadius: '50%',
          background: `${accentColor}15`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          marginTop: isExpanded ? '2px' : '0',
        }}
      >
        {is_running ? (
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            style={{ animation: 'sysSpin 1s linear infinite' }}
          >
            <circle
              cx="12"
              cy="12"
              r="10"
              stroke={accentColor}
              strokeWidth="2.5"
              strokeDasharray="31.4 31.4"
              strokeLinecap="round"
            />
          </svg>
        ) : hasError ? (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
            <path d="M18 6L6 18M6 6l12 12" stroke={accentColor} strokeWidth="2.5" strokeLinecap="round" />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
            <path d="M5 12l4 4 10-10" stroke={accentColor} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>

      {/* 主要内容区域 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              fontSize: '13px',
              color: accentColor,
              fontWeight: 500,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {statusText}
          </span>

          {is_running && (
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: accentColor,
                animation: 'sysPulse 1.5s ease-in-out infinite',
                flexShrink: 0,
              }}
            />
          )}

          {total_count > 0 && (
            <span style={{ fontSize: '12px', color: '#9ca3af', flexShrink: 0 }}>
              ({total_count})
            </span>
          )}
        </div>

        {/* 展开的事件列表 - 固定高度，最多6行 */}
        {isExpanded && displayEvents.length > 0 && (
          <div
            style={{
              marginTop: '8px',
              maxHeight: '180px',  // 约6行高度
              overflowY: 'auto',
              paddingRight: '4px',
            }}
          >
            {displayEvents.map((event, index) => {
              const eventHasError = event.status === 'failed';
              const eventColor = eventHasError ? '#dc2626' : '#6b7280';
              const hasDescription = event.description && event.description.trim();
              const hasRingData = event.metadata?.ring_data && event.metadata.ring_data.length > 0;
              const isTokenBudget = event.event_type === 'token_budget_summary';

              return (
                <div
                  key={event.event_id}
                  title={hasDescription ? event.description : undefined}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '12px',
                    padding: '5px 0',
                    fontSize: '12px',
                    color: eventColor,
                    borderBottom: index < displayEvents.length - 1 ? '1px solid #f3f4f6' : 'none',
                    cursor: hasDescription ? 'help' : 'default',
                  }}
                >
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: isTokenBudget ? 500 : 400 }}>
                      {event.title}
                    </span>
                    {hasDescription && (
                      <span style={{
                        color: '#9ca3af',
                        fontSize: '11px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        flexShrink: 1,
                      }}>
                        {event.description}
                      </span>
                    )}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                    {event.duration_ms !== undefined && (
                      <span style={{ color: '#9ca3af' }}>
                        {formatDuration(event.duration_ms)}
                      </span>
                    )}
                    {hasRingData && (
                      <MiniRingChart data={event.metadata!.ring_data!} size={24} />
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 右侧操作区域 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
        {!is_running && total_duration_ms && (
          <span style={{ fontSize: '12px', color: '#6b7280' }}>
            {formatDuration(total_duration_ms)}
          </span>
        )}

        {total_count > 1 && (
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            style={{
              background: '#f3f4f6',
              border: 'none',
              borderRadius: '4px',
              fontSize: '11px',
              color: '#6b7280',
              cursor: 'pointer',
              padding: '4px 8px',
              display: 'flex',
              alignItems: 'center',
              gap: '3px',
              transition: 'background 0.2s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#e5e7eb'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = '#f3f4f6'; }}
          >
            {isExpanded ? '收起' : `${total_count}个`}
            <svg
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              style={{
                transform: isExpanded ? 'rotate(180deg)' : 'rotate(0)',
                transition: 'transform 0.2s',
              }}
            >
              <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </div>

      <style>
        {`
          @keyframes sysSpin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
          @keyframes sysPulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.3); }
          }
        `}
      </style>
    </div>
  );
};

export default VisSystemEvents;
