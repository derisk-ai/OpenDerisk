/**
 * Manus 双面板布局类型定义
 * 对应后端 vis_manus_protocol.py 协议
 */

export type ManusStepType =
  | 'read'
  | 'edit'
  | 'write'
  | 'bash'
  | 'grep'
  | 'glob'
  | 'task'
  | 'skill'
  | 'python'
  | 'html'
  | 'sql'
  | 'other';

export type ManusStepStatus = 'pending' | 'running' | 'completed' | 'error';

export type ManusOutputType =
  | 'code'
  | 'text'
  | 'markdown'
  | 'table'
  | 'chart'
  | 'json'
  | 'error'
  | 'html'
  | 'image'
  | 'thought'
  | 'sql_query';

export type ManusArtifactType =
  | 'file'
  | 'table'
  | 'chart'
  | 'image'
  | 'code'
  | 'markdown'
  | 'summary'
  | 'html';

export type ManusPanelView =
  | 'execution'
  | 'files'
  | 'html-preview'
  | 'image-preview'
  | 'skill-preview'
  | 'summary'
  | 'deliverable';

export interface ManusExecutionStep {
  id: string;
  type: ManusStepType;
  title: string;
  subtitle?: string;
  description?: string;
  phase?: string;
  status: ManusStepStatus;
  output?: any;
}

export interface ManusThinkingSection {
  id: string;
  title: string;
  content?: string;
  is_completed: boolean;
  steps: ManusExecutionStep[];
}

export interface ManusArtifactItem {
  id: string;
  type: ManusArtifactType;
  name: string;
  content?: any;
  created_at?: number;
  downloadable?: boolean;
  mime_type?: string;
  size?: number;
  file_path?: string;
}

export interface ManusExecutionOutput {
  output_type: ManusOutputType;
  content: any;
  timestamp?: number;
}

export interface ManusActiveStepInfo {
  id: string;
  type: ManusStepType;
  title: string;
  subtitle?: string;
  status: ManusStepStatus;
  detail?: string;
  action?: string;
  action_input?: any;
}

export interface ManusLeftPanelData {
  sections: ManusThinkingSection[];
  active_step_id?: string;
  is_working: boolean;
  user_query?: string;
  assistant_text?: string;
  model_name?: string;
  step_thoughts: Record<string, string>;
  artifacts: ManusArtifactItem[];
}

export interface ManusTaskFileItem {
  file_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  mime_type?: string;
  oss_url?: string;
  preview_url?: string;
  download_url?: string;
  description?: string;
  created_at?: string;
  object_path?: string;
}

export interface ManusDeliverableFile {
  file_id: string;
  file_name: string;
  mime_type?: string;
  file_size: number;
  content_url?: string;
  download_url?: string;
  content?: string;
  object_path?: string;
  render_type: 'iframe' | 'markdown' | 'code' | 'image' | 'pdf' | 'text';
}

export interface ManusStepData {
  active_step: ManusActiveStepInfo;
  outputs: ManusExecutionOutput[];
}

export interface ManusRightPanelData {
  active_step?: ManusActiveStepInfo;
  outputs: ManusExecutionOutput[];
  is_running: boolean;
  artifacts: ManusArtifactItem[];
  panel_view: ManusPanelView;
  summary_content?: string;
  is_summary_streaming?: boolean;
  task_files: ManusTaskFileItem[];
  deliverable_files: ManusDeliverableFile[];
  /** Map from planning_window UID (action_id) to step data for click-to-switch */
  steps_map?: Record<string, ManusStepData>;
}

/** Step type display configuration */
export const STEP_TYPE_CONFIG: Record<
  ManusStepType,
  { icon: string; color: string; label: string }
> = {
  read: { icon: '📖', color: '#10b981', label: '读取' },
  edit: { icon: '✏️', color: '#f59e0b', label: '编辑' },
  write: { icon: '📝', color: '#3b82f6', label: '写入' },
  bash: { icon: '💻', color: '#8b5cf6', label: '终端' },
  grep: { icon: '🔍', color: '#06b6d4', label: '搜索' },
  glob: { icon: '📁', color: '#14b8a6', label: '查找' },
  task: { icon: '📋', color: '#6366f1', label: '任务' },
  skill: { icon: '⚡', color: '#6366f1', label: '技能' },
  python: { icon: '🐍', color: '#eab308', label: 'Python' },
  html: { icon: '🌐', color: '#f97316', label: 'HTML' },
  sql: { icon: '🗄️', color: '#ec4899', label: 'SQL' },
  other: { icon: '⚙️', color: '#64748b', label: '其他' },
};
