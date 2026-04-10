'use client';

import React, { FC, useMemo, useState, useCallback } from 'react';
import { Tooltip } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  CaretDownOutlined,
  CaretRightOutlined,
  FileOutlined,
  DownloadOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import type {
  ManusLeftPanelData,
  ManusThinkingSection,
  ManusExecutionStep,
  ManusArtifactItem,
  ManusStepType,
  ManusStepStatus,
} from '@/types/manus';
import { STEP_TYPE_CONFIG } from '@/types/manus';

interface IProps {
  data: ManusLeftPanelData;
  onStepClick?: (stepId: string) => void;
  onArtifactClick?: (artifact: ManusArtifactItem) => void;
}

/** Status icon component */
const StatusIcon: FC<{ status: ManusStepStatus }> = ({ status }) => {
  switch (status) {
    case 'running':
      return <LoadingOutlined className="text-blue-500" spin />;
    case 'completed':
      return <CheckCircleOutlined className="text-emerald-500" />;
    case 'error':
      return <ExclamationCircleOutlined className="text-red-500" />;
    case 'pending':
    default:
      return <ClockCircleOutlined className="text-slate-400" />;
  }
};

/** Step card component */
const StepCard: FC<{
  step: ManusExecutionStep;
  isActive: boolean;
  thought?: string;
  onClick?: () => void;
}> = ({ step, isActive, thought, onClick }) => {
  const config = STEP_TYPE_CONFIG[step.type] || STEP_TYPE_CONFIG.other;
  const [thoughtExpanded, setThoughtExpanded] = useState(false);

  return (
    <div
      className={`
        group flex items-start gap-2 px-2.5 py-1.5 rounded-lg cursor-pointer
        transition-all duration-200 border
        ${isActive
          ? 'bg-blue-50 border-blue-200 shadow-sm'
          : 'bg-white border-transparent hover:bg-slate-50 hover:border-slate-200'
        }
      `}
      onClick={onClick}
    >
      {/* Step type icon */}
      <div
        className="flex-shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-xs mt-0.5"
        style={{ backgroundColor: `${config.color}15`, color: config.color }}
      >
        {config.icon}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-slate-500">{config.label}</span>
          <StatusIcon status={step.status} />
        </div>
        <div className="text-sm font-medium text-slate-800 truncate mt-0.5">
          {step.title}
        </div>
        {step.subtitle && (
          <div className="text-xs text-slate-500 truncate mt-0.5">
            {step.subtitle}
          </div>
        )}

        {/* Thought bubble */}
        {thought && (
          <div className="mt-1.5">
            <button
              className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1"
              onClick={(e) => {
                e.stopPropagation();
                setThoughtExpanded(!thoughtExpanded);
              }}
            >
              {thoughtExpanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
              Agent 思考
            </button>
            {thoughtExpanded && (
              <div className="mt-1 text-xs text-slate-500 bg-slate-50 rounded p-2 leading-relaxed whitespace-pre-wrap">
                {thought}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

/** Section block component */
const SectionBlock: FC<{
  section: ManusThinkingSection;
  activeStepId?: string;
  stepThoughts: Record<string, string>;
  onStepClick?: (stepId: string) => void;
}> = ({ section, activeStepId, stepThoughts, onStepClick }) => {
  const [expanded, setExpanded] = useState(true);

  const completedCount = section.steps.filter(
    (s) => s.status === 'completed' || s.status === 'error'
  ).length;
  const totalCount = section.steps.length;

  return (
    <div className="mb-1">
      {/* Section header */}
      <button
        className="flex items-center gap-2 w-full px-2 py-1 text-left rounded-md hover:bg-slate-100 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <CaretDownOutlined className="text-xs text-slate-400" />
        ) : (
          <CaretRightOutlined className="text-xs text-slate-400" />
        )}
        <span className="text-sm font-semibold text-slate-700 flex-1">
          {section.title}
        </span>
        <span className="text-xs text-slate-400">
          {completedCount}/{totalCount}
        </span>
        {section.is_completed && (
          <CheckCircleOutlined className="text-emerald-500 text-xs" />
        )}
      </button>

      {/* Steps list */}
      {expanded && (
        <div className="ml-1 mt-0.5 space-y-0.5">
          {section.steps.map((step) => (
            <StepCard
              key={step.id}
              step={step}
              isActive={step.id === activeStepId}
              thought={stepThoughts[step.id]}
              onClick={() => onStepClick?.(step.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

/** Artifact card component */
const ArtifactCard: FC<{
  artifact: ManusArtifactItem;
  onClick?: () => void;
}> = ({ artifact, onClick }) => {
  const typeIcons: Record<string, string> = {
    file: '📄',
    table: '📊',
    chart: '📈',
    image: '🖼️',
    code: '💻',
    markdown: '📝',
    summary: '📋',
    html: '🌐',
  };

  return (
    <div
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white border border-slate-200 hover:border-blue-300 hover:shadow-sm cursor-pointer transition-all"
      onClick={onClick}
    >
      <span className="text-base">{typeIcons[artifact.type] || '📄'}</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-slate-700 truncate">
          {artifact.name}
        </div>
      </div>
      {artifact.downloadable && (
        <Tooltip title="下载">
          <DownloadOutlined className="text-slate-400 hover:text-blue-500 text-xs" />
        </Tooltip>
      )}
    </div>
  );
};

/** Main left panel component */
const VisManusLeftPanel: FC<IProps> = ({ data, onStepClick, onArtifactClick }) => {
  const {
    sections = [],
    active_step_id,
    is_working,
    step_thoughts = {},
    artifacts = [],
  } = data;

  return (
    <div className="flex flex-col h-full">
      {/* Working indicator */}
      {is_working && (
        <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 border-b border-blue-100">
          <LoadingOutlined className="text-blue-500" spin />
          <span className="text-xs text-blue-600 font-medium">正在执行中...</span>
        </div>
      )}

      {/* Sections */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-0.5">
        {sections.length > 0 ? (
          sections.map((section) => (
            <SectionBlock
              key={section.id}
              section={section}
              activeStepId={active_step_id}
              stepThoughts={step_thoughts}
              onStepClick={onStepClick}
            />
          ))
        ) : (
          <div className="flex items-center justify-center h-32 text-slate-400 text-sm">
            等待执行...
          </div>
        )}
      </div>

      {/* Artifacts */}
      {artifacts.length > 0 && (
        <div className="border-t border-slate-200 px-3 py-3">
          <div className="text-xs font-semibold text-slate-500 mb-2 flex items-center gap-1">
            <FileOutlined /> 产物 ({artifacts.length})
          </div>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {artifacts.map((artifact) => (
              <ArtifactCard
                key={artifact.id}
                artifact={artifact}
                onClick={() => onArtifactClick?.(artifact)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default VisManusLeftPanel;
