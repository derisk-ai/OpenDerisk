'use client';

import React, { FC, useMemo, useState, useEffect } from 'react';
import classNames from 'classnames';
import {
  LoadingOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  GlobalOutlined,
  CaretDownOutlined,
  CaretUpOutlined,
  FileSearchOutlined,
  EditOutlined,
  ConsoleSqlOutlined,
  SearchOutlined,
  CodeOutlined,
  PlayCircleOutlined,
  FileTextOutlined,
  DesktopOutlined,
  FileOutlined,
  ProfileOutlined,
} from '@ant-design/icons';
import { GPTVisLite } from '@antv/gpt-vis';
import { markdownComponents } from '../../config';
import type {
  ManusRightPanelData,
  ManusActiveStepInfo,
  ManusExecutionOutput,
  ManusStepType,
  ManusStepStatus,
  ManusArtifactItem,
  ManusPanelView,
} from '@/types/manus';
import {
  OutputRenderer,
  TerminalRenderer,
  CodeExecutionRenderer,
  HtmlTabbedRenderer,
  SkillScriptRenderer,
  SkillCardRenderer,
} from './renderers';

interface IProps {
  data: ManusRightPanelData;
}

/** Get Ant Design icon for step type (matching DB-GPT original) */
const getStepTypeIcon = (type: ManusStepType) => {
  switch (type) {
    case 'read':
      return <FileSearchOutlined className="text-emerald-500" />;
    case 'edit':
    case 'write':
      return <EditOutlined className="text-amber-500" />;
    case 'bash':
      return <ConsoleSqlOutlined className="text-purple-500" />;
    case 'grep':
    case 'glob':
      return <SearchOutlined className="text-cyan-500" />;
    case 'python':
      return <CodeOutlined className="text-blue-500" />;
    case 'html':
      return <CodeOutlined className="text-orange-500" />;
    case 'task':
    case 'skill':
      return <PlayCircleOutlined className="text-indigo-500" />;
    case 'sql':
      return <ConsoleSqlOutlined className="text-emerald-600" />;
    default:
      return <FileTextOutlined className="text-gray-500" />;
  }
};

/** Get icon background class based on step type */
const getIconBgClass = (type: ManusStepType): string => {
  const map: Record<string, string> = {
    read: 'bg-emerald-50',
    edit: 'bg-amber-50',
    write: 'bg-amber-50',
    bash: 'bg-purple-50',
    grep: 'bg-cyan-50',
    glob: 'bg-cyan-50',
    python: 'bg-blue-50',
    html: 'bg-orange-50',
    task: 'bg-indigo-50',
    skill: 'bg-indigo-50',
    sql: 'bg-emerald-50',
  };
  return map[type] || 'bg-gray-50';
};

/** Status badge component (matching DB-GPT original) */
const StatusBadge: FC<{ status: ManusStepStatus; isRunning?: boolean }> = ({ status, isRunning }) => {
  if (isRunning || status === 'running') {
    return (
      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-blue-100 text-blue-600 text-[10px] font-medium">
        <LoadingOutlined spin className="text-xs" />
        <span>Running</span>
      </div>
    );
  }
  if (status === 'completed') {
    return (
      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-600 text-[10px] font-medium">
        <CheckCircleFilled className="text-xs" />
        <span>Completed</span>
      </div>
    );
  }
  if (status === 'error') {
    return (
      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-red-100 text-red-600 text-[10px] font-medium">
        <CloseCircleFilled className="text-xs" />
        <span>Error</span>
      </div>
    );
  }
  return null;
};

/** Detect if a bash command is actually executing code */
function detectCodeLanguageInBash(command?: string): string | null {
  if (!command) return null;
  const cmd = command.toLowerCase();
  if (/(?:^|\s)python[23]?\s/.test(cmd) || /\.py\b/.test(cmd) || /(?:^|\s)pip\s/.test(cmd)) return 'python';
  if (/(?:^|\s)node\s/.test(cmd) || /(?:^|\s)npx?\s/.test(cmd) || /\.(?:js|ts)\b/.test(cmd)) return 'javascript';
  return null;
}

/** Select the appropriate renderer based on step type */
const StepRenderer: FC<{
  activeStep: ManusActiveStepInfo;
  outputs: ManusExecutionOutput[];
}> = ({ activeStep, outputs }) => {
  const { type, action, action_input, status } = activeStep;

  const command = useMemo(() => {
    if (!action_input) return undefined;
    if (typeof action_input === 'string') {
      try {
        const parsed = JSON.parse(action_input);
        return parsed.command || parsed.cmd;
      } catch {
        return action_input;
      }
    }
    return action_input?.command || action_input?.cmd;
  }, [action_input]);

  const codeLanguage = useMemo(
    () => (type === 'bash' ? detectCodeLanguageInBash(command) : null),
    [type, command]
  );

  switch (type) {
    case 'bash':
      if (codeLanguage) return <CodeExecutionRenderer outputs={outputs} language={codeLanguage} />;
      return <TerminalRenderer command={command} outputs={outputs} status={status} title={`Terminal - ${activeStep.title}`} />;
    case 'python':
      return <CodeExecutionRenderer outputs={outputs} language="python" />;
    case 'sql':
      return <CodeExecutionRenderer outputs={outputs} language="sql" />;
    case 'html':
      return <HtmlTabbedRenderer outputs={outputs} title={activeStep.title} />;
    case 'skill':
      if (action === 'execute_skill_script_file') return <SkillScriptRenderer outputs={outputs} skillName={activeStep.title} />;
      if (action === 'get_skill_resource' || action === 'load_skill') return <SkillCardRenderer outputs={outputs} skillName={activeStep.title} />;
      return <OutputRenderer outputs={outputs} />;
    default:
      return <OutputRenderer outputs={outputs} />;
  }
};

/** Tab button component (matching DB-GPT style) */
const TabButton: FC<{
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}> = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    className={classNames(
      'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
      active
        ? 'bg-white text-gray-800 shadow-sm border border-gray-200'
        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
    )}
  >
    {icon}
    <span>{label}</span>
  </button>
);

/** Summary view - renders final summary content with markdown */
const SummaryView: FC<{ content: string }> = ({ content }) => (
  <div className="p-4">
    <div className="text-sm leading-normal max-w-none [&_h1]:text-lg [&_h1]:font-bold [&_h1]:mt-3 [&_h1]:mb-1.5 [&_h2]:text-base [&_h2]:font-bold [&_h2]:mt-2.5 [&_h2]:mb-1 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1 [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5 [&_hr]:my-2">
      <GPTVisLite components={markdownComponents}>{content}</GPTVisLite>
    </div>
  </div>
);

/** Artifacts view - shows deliverable files */
const ArtifactsView: FC<{ artifacts: ManusArtifactItem[] }> = ({ artifacts }) => {
  const typeIcons: Record<string, string> = {
    file: '📄', table: '📊', chart: '📈', image: '🖼️',
    code: '💻', markdown: '📝', summary: '📋', html: '🌐',
  };

  return (
    <div className="p-4 space-y-2">
      {artifacts.map((artifact) => (
        <div
          key={artifact.id}
          className="flex items-center gap-3 px-4 py-3 rounded-lg bg-white border border-gray-200 hover:border-blue-300 hover:shadow-sm transition-all"
        >
          <span className="text-lg">{typeIcons[artifact.type] || '📄'}</span>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-700 truncate">{artifact.name}</div>
            {artifact.size && (
              <div className="text-xs text-gray-400">{(artifact.size / 1024).toFixed(1)} KB</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

type ActiveTab = 'execution' | 'summary' | 'artifacts';

/**
 * VisManusRightPanel - content-only component (no outer header).
 * Header is provided by ManusRightPanelContainer in manus-chat-content.tsx.
 * Renders tab navigation + active step info card + step output renderer.
 */
const VisManusRightPanel: FC<IProps> = ({ data }) => {
  const {
    active_step,
    outputs = [],
    is_running,
    summary_content,
    panel_view,
    artifacts = [],
  } = data;

  const [activeTab, setActiveTab] = useState<ActiveTab>('execution');
  const [inputCollapsed, setInputCollapsed] = useState(false);

  const hasSummary = !!summary_content;
  const hasArtifacts = artifacts.length > 0;

  // Auto-switch to summary tab when task completes
  useEffect(() => {
    if (panel_view === 'summary' && hasSummary) {
      setActiveTab('summary');
    }
  }, [panel_view, hasSummary]);

  // No data at all
  if (!active_step && !hasSummary) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-gray-400">
        <GlobalOutlined className="text-3xl text-gray-300 mb-3" />
        <div className="text-xs text-gray-400">等待执行...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar - always visible */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-gray-100 bg-white/50">
          <TabButton
            active={activeTab === 'execution'}
            onClick={() => setActiveTab('execution')}
            icon={<DesktopOutlined className="text-xs" />}
            label="执行步骤"
          />
          {hasSummary && (
            <TabButton
              active={activeTab === 'summary'}
              onClick={() => setActiveTab('summary')}
              icon={<ProfileOutlined className="text-xs" />}
              label="摘要"
            />
          )}
          {hasArtifacts && (
            <TabButton
              active={activeTab === 'artifacts'}
              onClick={() => setActiveTab('artifacts')}
              icon={<FileOutlined className="text-xs" />}
              label={`交付文件 (${artifacts.length})`}
            />
          )}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'summary' && hasSummary ? (
          <SummaryView content={summary_content!} />
        ) : activeTab === 'artifacts' && hasArtifacts ? (
          <ArtifactsView artifacts={artifacts} />
        ) : (
          /* Execution tab - active step renderer */
          active_step ? (
            active_step.type === 'bash' ? (
              <StepRenderer activeStep={active_step} outputs={outputs} />
            ) : (
              <div className="p-4">
                <div className="rounded-xl border border-gray-200 bg-white overflow-hidden flex flex-col">
                  {/* Step info header (collapsible) */}
                  <div
                    className="flex items-center justify-between px-4 py-3 cursor-pointer select-none hover:bg-gray-50 transition-colors"
                    onClick={() => setInputCollapsed(prev => !prev)}
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className={classNames('w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0', getIconBgClass(active_step.type))}>
                        {getStepTypeIcon(active_step.type)}
                      </div>
                      <div className="text-sm font-semibold text-gray-800 truncate">
                        {active_step.title}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <StatusBadge status={active_step.status} isRunning={is_running} />
                      <span className="text-gray-400 text-xs">
                        {inputCollapsed ? <CaretDownOutlined /> : <CaretUpOutlined />}
                      </span>
                    </div>
                  </div>

                  {/* Expanded content */}
                  {!inputCollapsed && (
                    <div className="border-t border-gray-100 p-4">
                      <StepRenderer activeStep={active_step} outputs={outputs} />
                    </div>
                  )}
                </div>
              </div>
            )
          ) : (
            <div className="flex flex-col items-center justify-center h-48 text-gray-400">
              <GlobalOutlined className="text-3xl text-gray-300 mb-3" />
              <div className="text-xs text-gray-400">等待执行...</div>
            </div>
          )
        )}
      </div>
    </div>
  );
};

export default VisManusRightPanel;
