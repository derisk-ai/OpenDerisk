/**
 * VIS Protocol V2 - Incremental Index Manager (TypeScript)
 *
 * Provides O(1) incremental index updates instead of O(n) full rebuilds.
 * Compatible with existing VisBaseParser but with better performance.
 */

/**
 * Index entry for tracking VIS components
 */
export interface IndexEntry {
  uid: string;
  node: any;
  nodeType: 'ast' | 'item' | 'nested';
  parentUid: string | null;
  depth: number;
  path: string[];
  
  // Dependency tracking
  dependencies: Set<string>;
  dependents: Set<string>;
  
  // Host references
  markdownHostUid?: string;
  itemsHostUid?: string;
  itemIndex?: number;
}

/**
 * Index statistics
 */
export interface IndexStats {
  totalEntries: number;
  maxDepth: number;
  byType: Record<string, number>;
  orphanCount: number;
  circularCount: number;
}

/**
 * Change event type
 */
export type ChangeCallback = (uid: string, entry: IndexEntry | null) => void;

/**
 * Dependency Graph for tracking component relationships
 */
export class DependencyGraph {
  private edges: Map<string, Set<string>> = new Map();
  private reverseEdges: Map<string, Set<string>> = new Map();

  /**
   * Add a dependency edge: fromUid depends on toUid
   */
  addEdge(fromUid: string, toUid: string): void {
    if (!this.edges.has(fromUid)) {
      this.edges.set(fromUid, new Set());
    }
    this.edges.get(fromUid)!.add(toUid);

    if (!this.reverseEdges.has(toUid)) {
      this.reverseEdges.set(toUid, new Set());
    }
    this.reverseEdges.get(toUid)!.add(fromUid);
  }

  /**
   * Remove a dependency edge
   */
  removeEdge(fromUid: string, toUid: string): void {
    this.edges.get(fromUid)?.delete(toUid);
    this.reverseEdges.get(toUid)?.delete(fromUid);
  }

  /**
   * Remove a node and all its edges
   */
  removeNode(uid: string): void {
    // Remove outgoing edges
    for (const dep of this.edges.get(uid) || []) {
      this.removeEdge(uid, dep);
    }

    // Remove incoming edges
    for (const dependent of this.reverseEdges.get(uid) || []) {
      this.removeEdge(dependent, uid);
    }

    this.edges.delete(uid);
    this.reverseEdges.delete(uid);
  }

  /**
   * Get all nodes this node depends on
   */
  getDependencies(uid: string): Set<string> {
    return new Set(this.edges.get(uid) || []);
  }

  /**
   * Get all nodes that depend on this node
   */
  getDependents(uid: string): Set<string> {
    return new Set(this.reverseEdges.get(uid) || []);
  }

  /**
   * Get all transitive dependents (descendants)
   */
  getAllDependents(uid: string): Set<string> {
    const result = new Set<string>();
    const queue = Array.from(this.getDependents(uid));

    while (queue.length > 0) {
      const current = queue.shift()!;
      if (result.has(current)) continue;
      result.add(current);
      queue.push(...this.getDependents(current));
    }

    return result;
  }

  /**
   * Detect cycle involving a node
   */
  detectCycle(uid: string): string[] | null {
    const visited = new Set<string>();
    const path: string[] = [];

    const dfs = (node: string): string[] | null => {
      if (path.includes(node)) {
        const cycleStart = path.indexOf(node);
        return [...path.slice(cycleStart), node];
      }

      if (visited.has(node)) return null;

      visited.add(node);
      path.push(node);

      for (const dep of this.edges.get(node) || []) {
        const cycle = dfs(dep);
        if (cycle) return cycle;
      }

      path.pop();
      return null;
    };

    return dfs(uid);
  }
}

/**
 * Incremental Index Manager
 *
 * Key improvements over VisBaseParser's rebuildIndex():
 * - O(1) single-node updates vs O(n) full rebuild
 * - Dependency tracking for efficient invalidation
 * - Circular reference detection
 * - Memory-efficient with change notifications
 */
export class IncrementalIndexManager {
  private index: Map<string, IndexEntry> = new Map();
  private dependencyGraph = new DependencyGraph();
  private changeCallbacks: ChangeCallback[] = [];
  private bulkMode = false;
  private pendingChanges = new Set<string>();

  readonly MAX_DEPTH = 100;

  /**
   * Get index entry by UID - O(1) lookup
   */
  get(uid: string): IndexEntry | undefined {
    return this.index.get(uid);
  }

  /**
   * Check if UID exists in index - O(1)
   */
  has(uid: string): boolean {
    return this.index.has(uid);
  }

  /**
   * Add or update an index entry - O(1) amortized
   */
  add(entry: IndexEntry): void {
    if (entry.path.length > this.MAX_DEPTH) {
      console.warn(`Entry depth ${entry.path.length} exceeds max ${this.MAX_DEPTH}`);
      return;
    }

    const existing = this.index.get(entry.uid);

    if (existing) {
      this.updateExistingEntry(existing, entry);
    } else {
      this.addNewEntry(entry);
    }

    if (this.bulkMode) {
      this.pendingChanges.add(entry.uid);
    } else {
      this.notifyChange(entry.uid, entry);
    }
  }

  /**
   * Remove an entry and clean up dependencies - O(d) where d is dependent count
   */
  remove(uid: string): IndexEntry | undefined {
    const entry = this.index.get(uid);
    if (!entry) return undefined;

    this.index.delete(uid);
    this.dependencyGraph.removeNode(uid);

    // Clean up dependency references
    for (const depUid of entry.dependencies) {
      const depEntry = this.index.get(depUid);
      if (depEntry) {
        depEntry.dependents.delete(uid);
      }
    }

    for (const dependentUid of entry.dependents) {
      const dependentEntry = this.index.get(dependentUid);
      if (dependentEntry) {
        dependentEntry.dependencies.delete(uid);
      }
    }

    if (this.bulkMode) {
      this.pendingChanges.add(uid);
    } else {
      this.notifyChange(uid, null);
    }

    return entry;
  }

  /**
   * Update specific fields of an entry - O(1)
   */
  update(uid: string, updates: Partial<IndexEntry>): IndexEntry | undefined {
    const entry = this.index.get(uid);
    if (!entry) return undefined;

    Object.assign(entry, updates);

    if (this.bulkMode) {
      this.pendingChanges.add(uid);
    } else {
      this.notifyChange(uid, entry);
    }

    return entry;
  }

  /**
   * Get all UIDs affected by a change
   */
  getAffectedUids(uid: string): Set<string> {
    const result = new Set<string>([uid]);
    const dependents = this.dependencyGraph.getAllDependents(uid);
    result.forEach(r => result.add(r));
    dependents.forEach(d => result.add(d));
    return result;
  }

  /**
   * Find all entries with a given parent - O(n) scan
   */
  findByParent(parentUid: string): IndexEntry[] {
    const results: IndexEntry[] = [];
    for (const entry of this.index.values()) {
      if (entry.parentUid === parentUid) {
        results.push(entry);
      }
    }
    return results;
  }

  /**
   * Find entries within a depth range - O(n) scan
   */
  findByDepth(minDepth: number, maxDepth: number): IndexEntry[] {
    const results: IndexEntry[] = [];
    for (const entry of this.index.values()) {
      if (entry.depth >= minDepth && entry.depth <= maxDepth) {
        results.push(entry);
      }
    }
    return results;
  }

  /**
   * Find entries by node type - O(n) scan
   */
  findByType(nodeType: string): IndexEntry[] {
    const results: IndexEntry[] = [];
    for (const entry of this.index.values()) {
      if (entry.nodeType === nodeType) {
        results.push(entry);
      }
    }
    return results;
  }

  /**
   * Add a dependency relationship - O(1)
   * Returns false if it would create a circular dependency
   */
  addDependency(uid: string, dependsOnUid: string): boolean {
    if (!this.index.has(uid) || !this.index.has(dependsOnUid)) {
      return false;
    }

    this.dependencyGraph.addEdge(uid, dependsOnUid);

    const cycle = this.dependencyGraph.detectCycle(uid);
    if (cycle) {
      this.dependencyGraph.removeEdge(uid, dependsOnUid);
      console.warn(`Detected circular dependency: ${cycle.join(' -> ')}`);
      return false;
    }

    this.index.get(uid)!.dependencies.add(dependsOnUid);
    this.index.get(dependsOnUid)!.dependents.add(uid);

    return true;
  }

  /**
   * Remove a dependency relationship - O(1)
   */
  removeDependency(uid: string, dependsOnUid: string): void {
    this.dependencyGraph.removeEdge(uid, dependsOnUid);

    this.index.get(uid)?.dependencies.delete(dependsOnUid);
    this.index.get(dependsOnUid)?.dependents.delete(uid);
  }

  /**
   * Begin bulk operation mode - defer change notifications
   */
  beginBulk(): void {
    this.bulkMode = true;
    this.pendingChanges.clear();
  }

  /**
   * End bulk mode and return all changed UIDs
   */
  endBulk(): Set<string> {
    this.bulkMode = false;
    const changed = new Set(this.pendingChanges);
    this.pendingChanges.clear();

    for (const uid of changed) {
      const entry = this.index.get(uid);
      if (entry) {
        this.notifyChange(uid, entry);
      }
    }

    return changed;
  }

  /**
   * Register a change callback
   */
  onChange(callback: ChangeCallback): () => void {
    this.changeCallbacks.push(callback);
    return () => {
      const index = this.changeCallbacks.indexOf(callback);
      if (index >= 0) {
        this.changeCallbacks.splice(index, 1);
      }
    };
  }

  /**
   * Clear all entries
   */
  clear(): void {
    this.index.clear();
    this.dependencyGraph = new DependencyGraph();
    this.pendingChanges.clear();
  }

  /**
   * Get index statistics
   */
  getStats(): IndexStats {
    const stats: IndexStats = {
      totalEntries: this.index.size,
      maxDepth: 0,
      byType: {},
      orphanCount: 0,
      circularCount: 0,
    };

    const orphanUids = new Set<string>();

    for (const entry of this.index.values()) {
      stats.byType[entry.nodeType] = (stats.byType[entry.nodeType] || 0) + 1;
      stats.maxDepth = Math.max(stats.maxDepth, entry.depth);

      if (entry.parentUid && !this.index.has(entry.parentUid)) {
        orphanUids.add(entry.uid);
      }
    }

    stats.orphanCount = orphanUids.size;

    // Detect cycles
    const checked = new Set<string>();
    for (const uid of this.index.keys()) {
      if (!checked.has(uid)) {
        const cycle = this.dependencyGraph.detectCycle(uid);
        if (cycle) {
          stats.circularCount++;
          cycle.forEach(c => checked.add(c));
        }
      }
    }

    return stats;
  }

  /**
   * Validate index integrity
   */
  validate(): string[] {
    const issues: string[] = [];

    for (const entry of this.index.values()) {
      if (entry.path.length > this.MAX_DEPTH) {
        issues.push(`Entry ${entry.uid} exceeds max depth`);
      }

      for (const depUid of entry.dependencies) {
        if (!this.index.has(depUid)) {
          issues.push(`Entry ${entry.uid} depends on non-existent ${depUid}`);
        }
      }

      if (entry.parentUid && !this.index.has(entry.parentUid)) {
        issues.push(`Entry ${entry.uid} has non-existent parent ${entry.parentUid}`);
      }
    }

    // Detect cycles
    const checked = new Set<string>();
    for (const uid of this.index.keys()) {
      if (!checked.has(uid)) {
        const cycle = this.dependencyGraph.detectCycle(uid);
        if (cycle) {
          issues.push(`Circular dependency detected: ${cycle.join(' -> ')}`);
          cycle.forEach(c => checked.add(c));
        }
      }
    }

    return issues;
  }

  private addNewEntry(entry: IndexEntry): void {
    this.index.set(entry.uid, entry);

    if (entry.parentUid) {
      this.addDependency(entry.uid, entry.parentUid);
    }
  }

  private updateExistingEntry(existing: IndexEntry, newEntry: IndexEntry): void {
    // Update parent dependency if changed
    if (existing.parentUid !== newEntry.parentUid) {
      if (existing.parentUid) {
        this.removeDependency(existing.uid, existing.parentUid);
      }
      if (newEntry.parentUid) {
        this.addDependency(existing.uid, newEntry.parentUid);
      }
    }

    // Update fields
    existing.node = newEntry.node;
    existing.nodeType = newEntry.nodeType;
    existing.parentUid = newEntry.parentUid;
    existing.depth = newEntry.depth;
    existing.path = newEntry.path;
    existing.markdownHostUid = newEntry.markdownHostUid;
    existing.itemsHostUid = newEntry.itemsHostUid;
    existing.itemIndex = newEntry.itemIndex;
  }

  private notifyChange(uid: string, entry: IndexEntry | null): void {
    for (const callback of this.changeCallbacks) {
      try {
        callback(uid, entry);
      } catch (e) {
        console.error('Change callback error:', e);
      }
    }
  }

  get size(): number {
    return this.index.size;
  }

  [Symbol.iterator](): Iterator<[string, IndexEntry]> {
    return this.index.entries();
  }
}

export default IncrementalIndexManager;