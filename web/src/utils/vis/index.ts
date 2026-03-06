/**
 * VIS Protocol V2 - Entry Point
 *
 * Provides optimized incremental indexing, JSON Lines parsing,
 * type-safe components, and DevTools for debugging.
 *
 * @example
 * ```typescript
 * import { VisJsonLinesParser, visBuilder, VisDevTools } from '@/utils/vis';
 *
 * // Create parser
 * const parser = new VisJsonLinesParser();
 *
 * // Parse JSON Lines
 * parser.parse('{"type":"component","tag":"vis-thinking","uid":"xxx","props":{"markdown":"..."}}');
 *
 * // Use builder
 * const output = visBuilder()
 *   .thinking('think-1', 'Analyzing...')
 *   .message('msg-1', 'Hello!')
 *   .toJsonl();
 *
 * // Enable DevTools in development
 * if (process.env.NODE_ENV === 'development') {
 *   window.__VIS_DEVTOOLS__ = new VisDevTools(parser);
 * }
 * ```
 */

// Incremental Index
export {
  IncrementalIndexManager,
  DependencyGraph,
  type IndexEntry,
  type IndexStats,
  type ChangeCallback,
} from './incremental-index';

// JSON Lines Parser
export {
  VisJsonLinesParser,
  VisJsonLinesBuilder,
  JsonPatch,
  VisMessageType,
  visBuilder,
  type VisJsonLine,
  type JsonPatchOp,
  type VisComponent,
  type ParseResult,
} from './jsonlines-parser';

// DevTools
export {
  VisDevTools,
  type VisSnapshot,
  type UpdateTrace,
  type PerformanceMetrics,
  type VisComponentTreeNode,
  type VisDiff,
  type ValidationResult,
  type ValidationIssue,
  type PerformanceProfile,
  type VisExport,
  type DevToolsConfig,
} from './devtools';

// Component Types
export {
  VisComponentRegistry,
  type VisUpdateType,
  type VisComponentState,
  type VisBaseProps,
  type VisThinkingProps,
  type VisMessageProps,
  type VisTextProps,
  type VisToolProps,
  type VisPlanProps,
  type VisChartProps,
  type VisCodeProps,
  type VisConfirmProps,
  type VisSelectProps,
  type VisDashboardProps,
  type VisAttachProps,
  type VisTodoProps,
  type VisComponentTag,
  type VisComponentProps,
  type VisComponentDefinition,
  type ValidationResult as ComponentValidationResult,
  VisThinkingTag,
  VisMessageTag,
  VisTextTag,
  VisToolTag,
  VisPlanTag,
  VisChartTag,
  VisCodeTag,
  VisConfirmTag,
  VisSelectTag,
  VisDashboardTag,
  VisAttachTag,
  VisTodoTag,
} from './component-types';

// Re-export for backward compatibility
export { VisBaseParser, VisParser } from '../parse-vis';

// Version info
export const VIS_VERSION = '2.0.0';