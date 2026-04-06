/**
 * VIS Protocol V2 - Type-Safe Component System
 *
 * Auto-generated types from schema definitions.
 * This file provides complete type safety for VIS components.
 */

// ============== Base Types ==============

export type VisUpdateType = 'incr' | 'all' | 'delete';

export type VisComponentState = 'pending' | 'streaming' | 'complete' | 'error';

export interface VisBaseProps {
  uid: string;
  type: VisUpdateType;
  dynamic?: boolean;
}

// ============== Thinking Component ==============

export interface VisThinkingProps extends VisBaseProps {
  markdown: string;
  think_link?: string;
}

export const VisThinkingTag = 'vis-thinking';

// ============== Message Component ==============

export interface VisMessageProps extends VisBaseProps {
  markdown: string;
  role?: string;
  name?: string;
  avatar?: string;
  model?: string;
  start_time?: string;
  task_id?: string;
}

export const VisMessageTag = 'drsk-msg';

// ============== Text/Content Component ==============

export interface VisTextProps extends VisBaseProps {
  markdown: string;
}

export const VisTextTag = 'drsk-content';

// ============== Tool Component ==============

export type VisToolStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface VisToolProps extends VisBaseProps {
  name: string;
  args?: Record<string, any>;
  status: VisToolStatus;
  output?: string;
  error?: string;
  start_time?: string;
  end_time?: string;
  progress?: number;
}

export const VisToolTag = 'vis-tool';

// ============== Plan Component ==============

export type VisTaskStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface VisTask {
  task_id?: string;
  task_uid?: string;
  task_name?: string;
  task_content?: string;
  agent_name?: string;
  status?: VisTaskStatus;
}

export interface VisPlanProps extends VisBaseProps {
  round_title?: string;
  round_description?: string;
  tasks: VisTask[];
}

export const VisPlanTag = 'drsk-plan';

// ============== Chart Component ==============

export type VisChartType = 'line' | 'bar' | 'pie' | 'scatter' | 'area';

export interface VisChartProps extends VisBaseProps {
  chart_type: VisChartType;
  data: Record<string, any>;
  config?: Record<string, any>;
  title?: string;
}

export const VisChartTag = 'vis-chart';

// ============== Code Component ==============

export interface VisCodeProps extends VisBaseProps {
  language?: string;
  code: string;
  filename?: string;
  executable?: boolean;
}

export const VisCodeTag = 'vis-code';

// ============== Confirm Component ==============

export interface VisConfirmProps extends VisBaseProps {
  markdown: string;
  disabled?: boolean;
  extra?: Record<string, any>;
}

export const VisConfirmTag = 'vis-confirm';

// ============== Select Component ==============

export interface VisSelectOption {
  markdown: string;
  confirm_message?: string;
  extra?: Record<string, any>;
}

export interface VisSelectProps extends VisBaseProps {
  options: VisSelectOption[];
}

export const VisSelectTag = 'vis-select';

// ============== Dashboard Component ==============

export type VisDashboardLayout = 'grid' | 'flex' | 'custom';

export interface VisDashboardProps extends VisBaseProps {
  layout?: VisDashboardLayout;
  columns?: number;
}

export const VisDashboardTag = 'vis-dashboard';

// ============== Attach Component ==============

export interface VisAttachProps extends VisBaseProps {
  file_id: string;
  file_name: string;
  file_type: string;
  file_size?: number;
  oss_url?: string;
  preview_url?: string;
  download_url?: string;
}

export const VisAttachTag = 'd-attach';

// ============== Todo Component ==============

export type VisTodoStatus = 'pending' | 'working' | 'completed' | 'failed';

export interface VisTodoItem {
  id: string;
  title: string;
  status: VisTodoStatus;
  index: number;
}

export interface VisTodoProps extends VisBaseProps {
  mission?: string;
  items: VisTodoItem[];
  current_index?: number;
}

export const VisTodoTag = 'vis-todo';

// ============== Status Notification Component ==============

export type VisNotificationLevel = 'info' | 'success' | 'warning' | 'error' | 'progress';

export interface VisStatusNotificationProps extends VisBaseProps {
  title: string;
  message: string;
  level?: VisNotificationLevel;
  progress?: number;
  icon?: string;
  dismissible?: boolean;
  auto_dismiss?: number;
  actions?: Array<{
    label: string;
    action: string;
    [key: string]: any;
  }>;
}

export const VisStatusNotificationTag = 'd-status-notification';

// ============== Union Types ==============

export type VisComponentTag =
  | typeof VisThinkingTag
  | typeof VisMessageTag
  | typeof VisTextTag
  | typeof VisToolTag
  | typeof VisPlanTag
  | typeof VisChartTag
  | typeof VisCodeTag
  | typeof VisConfirmTag
  | typeof VisSelectTag
  | typeof VisDashboardTag
  | typeof VisAttachTag
  | typeof VisTodoTag
  | typeof VisStatusNotificationTag;

export type VisComponentProps =
  | VisThinkingProps
  | VisMessageProps
  | VisTextProps
  | VisToolProps
  | VisPlanProps
  | VisChartProps
  | VisCodeProps
  | VisConfirmProps
  | VisSelectProps
  | VisDashboardProps
  | VisAttachProps
  | VisTodoProps
  | VisStatusNotificationProps;

// ============== Component Registry ==============

export interface VisComponentDefinition<T extends VisComponentProps = VisComponentProps> {
  tag: string;
  category: string;
  description: string;
  validate: (props: Partial<T>) => ValidationResult;
  defaultProps?: Partial<T>;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

/**
 * Component registry for type-safe component access
 */
export class VisComponentRegistry {
  private static definitions: Map<string, VisComponentDefinition> = new Map();

  static register<T extends VisComponentProps>(definition: VisComponentDefinition<T>): void {
    this.definitions.set(definition.tag, definition);
  }

  static get(tag: string): VisComponentDefinition | undefined {
    return this.definitions.get(tag);
  }

  static has(tag: string): boolean {
    return this.definitions.has(tag);
  }

  static validate(tag: string, props: Record<string, any>): ValidationResult {
    const definition = this.definitions.get(tag);
    if (!definition) {
      return { valid: false, errors: [`Unknown component tag: ${tag}`], warnings: [] };
    }
    return definition.validate(props);
  }

  static list(): string[] {
    return Array.from(this.definitions.keys());
  }
}

// ============== Validators ==============

function createValidator<T extends VisBaseProps>(
  tag: string,
  requiredFields: (keyof T)[]
): (props: Partial<T>) => ValidationResult {
  return (props: Partial<T>): ValidationResult => {
    const errors: string[] = [];
    const warnings: string[] = [];

    if (!props.uid) {
      errors.push('uid is required');
    }

    if (!props.type) {
      errors.push('type is required');
    }

    for (const field of requiredFields) {
      if (props[field] === undefined || props[field] === null) {
        errors.push(`${String(field)} is required`);
      }
    }

    return { valid: errors.length === 0, errors, warnings };
  };
}

// Register built-in components
VisComponentRegistry.register({
  tag: VisThinkingTag,
  category: 'reasoning',
  description: 'Displays the agent thinking/reasoning process',
  validate: createValidator<VisThinkingProps>(VisThinkingTag, ['markdown']),
});

VisComponentRegistry.register({
  tag: VisMessageTag,
  category: 'message',
  description: 'A complete message from an agent',
  validate: createValidator<VisMessageProps>(VisMessageTag, ['markdown']),
});

VisComponentRegistry.register({
  tag: VisTextTag,
  category: 'content',
  description: 'Text content with incremental update support',
  validate: createValidator<VisTextProps>(VisTextTag, ['markdown']),
});

VisComponentRegistry.register({
  tag: VisToolTag,
  category: 'action',
  description: 'Tool execution display',
  validate: createValidator<VisToolProps>(VisToolTag, ['name', 'status']),
});

VisComponentRegistry.register({
  tag: VisPlanTag,
  category: 'planning',
  description: 'Task plan visualization',
  validate: createValidator<VisPlanProps>(VisPlanTag, ['tasks']),
});

VisComponentRegistry.register({
  tag: VisChartTag,
  category: 'visualization',
  description: 'Data visualization chart',
  validate: createValidator<VisChartProps>(VisChartTag, ['chart_type', 'data']),
});

VisComponentRegistry.register({
  tag: VisCodeTag,
  category: 'content',
  description: 'Code display with syntax highlighting',
  validate: createValidator<VisCodeProps>(VisCodeTag, ['code']),
});

VisComponentRegistry.register({
  tag: VisConfirmTag,
  category: 'interaction',
  description: 'User confirmation dialog',
  validate: createValidator<VisConfirmProps>(VisConfirmTag, ['markdown']),
});

VisComponentRegistry.register({
  tag: VisSelectTag,
  category: 'interaction',
  description: 'User selection options',
  validate: createValidator<VisSelectProps>(VisSelectTag, ['options']),
});

VisComponentRegistry.register({
  tag: VisDashboardTag,
  category: 'layout',
  description: 'Dashboard layout for multiple widgets',
  validate: createValidator<VisDashboardProps>(VisDashboardTag, []),
});

VisComponentRegistry.register({
  tag: VisAttachTag,
  category: 'content',
  description: 'File attachment display',
  validate: createValidator<VisAttachProps>(VisAttachTag, ['file_id', 'file_name', 'file_type']),
});

VisComponentRegistry.register({
  tag: VisTodoTag,
  category: 'planning',
  description: 'Todo list display',
  validate: createValidator<VisTodoProps>(VisTodoTag, ['items']),
});

VisComponentRegistry.register({
  tag: VisStatusNotificationTag,
  category: 'notification',
  description: 'Status notification display for system messages',
  validate: createValidator<VisStatusNotificationProps>(VisStatusNotificationTag, ['title', 'message']),
});

export default VisComponentRegistry;