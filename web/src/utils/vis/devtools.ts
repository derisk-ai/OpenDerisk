/**
 * VIS Protocol V2 - DevTools (TypeScript)
 *
 * Debugging and development tools for VIS components.
 * Provides component tree visualization, update tracing, and performance profiling.
 */

import { VisJsonLinesParser, VisComponent, VisJsonLine } from './jsonlines-parser';
import { IncrementalIndexManager, IndexEntry, IndexStats } from './incremental-index';

/**
 * Snapshot of VIS state at a point in time
 */
export interface VisSnapshot {
  timestamp: number;
  components: Map<string, VisComponent>;
  indexStats: IndexStats;
}

/**
 * Update trace record
 */
export interface UpdateTrace {
  timestamp: number;
  uid: string;
  type: 'add' | 'update' | 'remove';
  changes?: Record<string, { old: any; new: any }>;
  duration?: number;
}

/**
 * Performance metrics
 */
export interface PerformanceMetrics {
  parseTime: number;
  renderTime: number;
  memoryUsage: number;
  componentCount: number;
  updateCount: number;
  averageUpdateTime: number;
}

/**
 * DevTools configuration
 */
export interface DevToolsConfig {
  enabled: boolean;
  maxHistorySize: number;
  trackUpdates: boolean;
  trackPerformance: boolean;
  logToConsole: boolean;
}

/**
 * VIS DevTools
 *
 * Usage:
 * ```typescript
 * // Enable in development
 * if (process.env.NODE_ENV === 'development') {
 *   window.__VIS_DEVTOOLS__ = new VisDevTools(parser);
 * }
 *
 * // Access from console
 * __VIS_DEVTOOLS__.inspectTree()
 * __VIS_DEVTOOLS__.getHistory()
 * __VIS_DEVTOOLS__.profile()
 * ```
 */
export class VisDevTools {
  private parser: VisJsonLinesParser;
  private config: DevToolsConfig;
  private history: VisSnapshot[] = [];
  private updateTraces: UpdateTrace[] = [];
  private performanceMetrics: PerformanceMetrics = {
    parseTime: 0,
    renderTime: 0,
    memoryUsage: 0,
    componentCount: 0,
    updateCount: 0,
    averageUpdateTime: 0,
  };
  private startTime: number = 0;
  private updateTimes: number[] = [];

  constructor(parser: VisJsonLinesParser, config?: Partial<DevToolsConfig>) {
    this.parser = parser;
    this.config = {
      enabled: true,
      maxHistorySize: 100,
      trackUpdates: true,
      trackPerformance: true,
      logToConsole: false,
      ...config,
    };

    if (this.config.enabled) {
      this.setupIndexTracking();
    }
  }

  /**
   * Get component tree visualization
   */
  inspectTree(): VisComponentTreeNode[] {
    const components = this.parser.getAllComponents();
    const index = this.parser.getIndex();
    const roots: VisComponentTreeNode[] = [];

    // Find root components (no parent)
    for (const [uid, component] of components) {
      const entry = index.get(uid);
      if (!entry?.parentUid) {
        roots.push(this.buildTreeNode(uid, components, index));
      }
    }

    return roots;
  }

  /**
   * Get update history
   */
  getHistory(limit?: number): VisSnapshot[] {
    const history = [...this.history].reverse();
    return limit ? history.slice(0, limit) : history;
  }

  /**
   * Get update traces
   */
  getTraces(limit?: number): UpdateTrace[] {
    const traces = [...this.updateTraces].reverse();
    return limit ? traces.slice(0, limit) : traces;
  }

  /**
   * Get current performance metrics
   */
  getMetrics(): PerformanceMetrics {
    this.updateMetrics();
    return { ...this.performanceMetrics };
  }

  /**
   * Take a snapshot of current state
   */
  takeSnapshot(): VisSnapshot {
    const snapshot: VisSnapshot = {
      timestamp: Date.now(),
      components: new Map(this.parser.getAllComponents()),
      indexStats: this.parser.getIndex().getStats(),
    };

    this.history.push(snapshot);

    // Trim history
    if (this.history.length > this.config.maxHistorySize) {
      this.history.shift();
    }

    return snapshot;
  }

  /**
   * Compare two snapshots
   */
  diff(before: VisSnapshot, after: VisSnapshot): VisDiff {
    const added: string[] = [];
    const removed: string[] = [];
    const changed: string[] = [];

    for (const [uid] of after.components) {
      if (!before.components.has(uid)) {
        added.push(uid);
      }
    }

    for (const [uid] of before.components) {
      if (!after.components.has(uid)) {
        removed.push(uid);
      } else {
        const beforeComp = before.components.get(uid)!;
        const afterComp = after.components.get(uid)!;

        if (JSON.stringify(beforeComp.props) !== JSON.stringify(afterComp.props)) {
          changed.push(uid);
        }
      }
    }

    return { added, removed, changed };
  }

  /**
   * Time travel to a specific snapshot
   */
  timeTravel(index: number): VisSnapshot | null {
    if (index < 0 || index >= this.history.length) {
      return null;
    }

    return this.history[index];
  }

  /**
   * Profile current parsing performance
   */
  profile(): PerformanceProfile {
    const start = performance.now();
    const memoryBefore = this.getMemoryUsage();

    // Force garbage collection if available
    if (typeof (globalThis as any).gc === 'function') {
      (globalThis as any).gc();
    }

    const parseStart = performance.now();

    // Simulate parse operation
    const stats = this.parser.getIndex().getStats();

    const parseEnd = performance.now();
    const memoryAfter = this.getMemoryUsage();

    const end = performance.now();

    return {
      duration: end - start,
      parseTime: parseEnd - parseStart,
      memoryBefore,
      memoryAfter,
      memoryDelta: memoryAfter - memoryBefore,
      componentCount: stats.totalEntries,
      maxDepth: stats.maxDepth,
      indexStats: stats,
    };
  }

  /**
   * Validate component state
   */
  validate(): ValidationResult {
    const issues: ValidationIssue[] = [];
    const index = this.parser.getIndex();
    const components = this.parser.getAllComponents();

    // Check index integrity
    const indexIssues = index.validate();
    for (const issue of indexIssues) {
      issues.push({ type: 'error', component: 'index', message: issue });
    }

    // Check component state
    for (const [uid, component] of components) {
      if (!component.tag) {
        issues.push({ type: 'error', component: uid, message: 'Missing tag' });
      }

      if (!uid) {
        issues.push({ type: 'error', component: uid, message: 'Missing uid' });
      }

      if (component.state === 'error' && !component.error) {
        issues.push({ type: 'warning', component: uid, message: 'Error state without error message' });
      }
    }

    // Check for orphan components
    const stats = index.getStats();
    if (stats.orphanCount > 0) {
      issues.push({
        type: 'warning',
        component: 'index',
        message: `${stats.orphanCount} orphan components detected`,
      });
    }

    return {
      valid: issues.filter((i) => i.type === 'error').length === 0,
      issues,
    };
  }

  /**
   * Export state for debugging
   */
  export(): VisExport {
    return {
      version: '2.0',
      timestamp: Date.now(),
      components: Array.from(this.parser.getAllComponents().entries()).map(([uid, comp]) => ({
        uid,
        ...comp,
      })),
      indexStats: this.parser.getIndex().getStats(),
      history: this.history.map((s) => ({
        timestamp: s.timestamp,
        componentCount: s.components.size,
        indexStats: s.indexStats,
      })),
      traces: this.updateTraces.slice(-100),
    };
  }

  /**
   * Clear all tracking data
   */
  clear(): void {
    this.history = [];
    this.updateTraces = [];
    this.updateTimes = [];
    this.performanceMetrics = {
      parseTime: 0,
      renderTime: 0,
      memoryUsage: 0,
      componentCount: 0,
      updateCount: 0,
      averageUpdateTime: 0,
    };
  }

  /**
   * Enable/disable tracking
   */
  setEnabled(enabled: boolean): void {
    this.config.enabled = enabled;
  }

  /**
   * Log to console
   */
  log(message: string, data?: any): void {
    if (this.config.logToConsole) {
      console.log(`[VIS DevTools] ${message}`, data);
    }
  }

  private setupIndexTracking(): void {
    const index = this.parser.getIndex();

    index.onChange((uid, entry) => {
      if (!this.config.trackUpdates) return;

      const trace: UpdateTrace = {
        timestamp: Date.now(),
        uid,
        type: entry ? (this.parser.getComponent(uid) ? 'update' : 'add') : 'remove',
      };

      this.updateTraces.push(trace);

      // Trim traces
      if (this.updateTraces.length > this.config.maxHistorySize) {
        this.updateTraces.shift();
      }

      this.log(`Component ${trace.type}: ${uid}`, entry);
    });
  }

  private buildTreeNode(
    uid: string,
    components: Map<string, VisComponent>,
    index: IncrementalIndexManager
  ): VisComponentTreeNode {
    const component = components.get(uid);
    const children = index.findByParent(uid);

    return {
      uid,
      tag: component?.tag || 'unknown',
      state: component?.state || 'unknown',
      props: component?.props,
      children: children.map((c) => this.buildTreeNode(c.uid, components, index)),
    };
  }

  private getMemoryUsage(): number {
    if (typeof (performance as any).memory !== 'undefined') {
      return (performance as any).memory.usedJSHeapSize;
    }
    return 0;
  }

  private updateMetrics(): void {
    const stats = this.parser.getIndex().getStats();
    this.performanceMetrics.componentCount = stats.totalEntries;
    this.performanceMetrics.updateCount = this.updateTraces.length;

    if (this.updateTimes.length > 0) {
      this.performanceMetrics.averageUpdateTime =
        this.updateTimes.reduce((a, b) => a + b, 0) / this.updateTimes.length;
    }

    this.performanceMetrics.memoryUsage = this.getMemoryUsage();
  }
}

/**
 * Component tree node for visualization
 */
export interface VisComponentTreeNode {
  uid: string;
  tag: string;
  state: string;
  props?: Record<string, any>;
  children: VisComponentTreeNode[];
}

/**
 * Diff result between snapshots
 */
export interface VisDiff {
  added: string[];
  removed: string[];
  changed: string[];
}

/**
 * Validation result
 */
export interface ValidationResult {
  valid: boolean;
  issues: ValidationIssue[];
}

/**
 * Validation issue
 */
export interface ValidationIssue {
  type: 'error' | 'warning' | 'info';
  component: string;
  message: string;
}

/**
 * Performance profile
 */
export interface PerformanceProfile {
  duration: number;
  parseTime: number;
  memoryBefore: number;
  memoryAfter: number;
  memoryDelta: number;
  componentCount: number;
  maxDepth: number;
  indexStats: IndexStats;
}

/**
 * Export data format
 */
export interface VisExport {
  version: string;
  timestamp: number;
  components: Array<VisComponent & { uid: string }>;
  indexStats: IndexStats;
  history: Array<{
    timestamp: number;
    componentCount: number;
    indexStats: IndexStats;
  }>;
  traces: UpdateTrace[];
}

// Expose to global for console access
declare global {
  interface Window {
    __VIS_DEVTOOLS__?: VisDevTools;
  }
}

export default VisDevTools;