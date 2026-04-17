 
import { find, keyBy } from 'lodash';
// @ts-ignore
import { Root } from 'mdast';
import remarkParse from 'remark-parse';
import remarkStringify from 'remark-stringify';
import remarkRehype from 'remark-rehype';
import { Processor, unified } from 'unified';
import { VFile } from 'vfile';

/**
 * VIS协议解析器 - 修复版本
 *
 * 修复的问题：
 * 1. planning_window区域agent类型和task类型chunk丢失
 * 2. running_window区域d-llm增量数据只渲染第一个chunk
 *
 * 核心修复点：
 * 1. 字段合并时保留非null值，避免null覆盖有效数据
 * 2. items数组中元素的markdown字段递归合并
 * 3. 深层嵌套组件的完整索引和合并
 * 4. markdown合并时追加新组件而不是替换
 */

// ============== 类型定义 ==============

interface VisItem {
  type: 'incr' | 'all' | 'delete';
  uid: string;
  dynamic?: boolean;
  markdown?: string;
  items?: VisItem[];
  parent_uid?: string;
  [key: string]: any;
}

interface NodeIndexEntry {
  node: any;
  nodeType: 'ast' | 'item' | 'nested';
  parentUid: string | null;
  parentNode: any;
  depth: number;
  path: string[];
  markdownHost?: any;
  itemsHost?: VisItem;
  itemsHostNode?: any;  // 新增：存储items宿主的AST节点引用
  itemIndex?: number;
}

interface QueryResult {
  found: boolean;
  entry?: NodeIndexEntry;
  visItem?: VisItem;
}

// ============== 工具函数 ==============

/**
 * Maximum size for JSON string parsing (10MB)
 * Prevents browser crash from parsing extremely large VIS data
 */
const MAX_JSON_PARSE_SIZE = 10_000_000;

/**
 * 安全解析 JSON，处理非法转义字符（如 \$）
 * 关键修复：后端可能生成包含非法转义字符的 JSON
 */
function safeJsonParse<T>(jsonString: string | null | undefined): T {
  if (!jsonString) {
    throw new Error('Empty or null JSON string');
  }

  // Size check: prevent parsing extremely large JSON that could cause browser crash
  if (jsonString.length > MAX_JSON_PARSE_SIZE) {
    console.warn(`[safeJsonParse] JSON string too large (${jsonString.length} chars), skipping parse`);
    throw new Error(`JSON too large: ${jsonString.length} characters exceeds limit of ${MAX_JSON_PARSE_SIZE}`);
  }

  try {
    // 首先尝试直接解析
    return JSON.parse(jsonString);
  } catch (e) {
    // 如果失败，尝试修复常见的非法转义字符
    // JSON 标准不允许 \$ 转义，将其替换为普通 $
    const sanitized = jsonString.replace(/\\\$/g, '$');
    return JSON.parse(sanitized);
  }
}

/**
 * 检测markdown字符串是否包含未闭合的代码块标签
 */
function isPartialTag(markdownString: string): boolean {
  if (!markdownString) return true;

  // 计算```的数量，奇数表示未闭合
  const matches = markdownString.match(/```/g);
  return matches ? matches.length % 2 !== 0 : false;
}

/**
 * 创建VFile对象
 */
function createFile(content: string): VFile {
  const file = new VFile();
  file.value = content || '';
  return file;
}

/**
 * 合并两个对象，只用非null/undefined的值覆盖
 * 关键修复：避免null值覆盖有效数据
 */
function mergeNonNull<T extends Record<string, any>>(base: T, incr: Partial<T>): T {
  const result = { ...base };

  for (const key of Object.keys(incr)) {
    const value = incr[key];
    // 只有当增量值不是null且不是undefined时才覆盖
    if (value !== null && value !== undefined) {
      (result as any)[key] = value;
    }
  }

  return result;
}

// ============== VisBaseParser 类 ==============

export class VisBaseParser {
  private string2TreeProcessor: Processor<any, any>;
  private tree2StringProcessor: Processor<any, any>;
  private incrNodesMap: Map<string, VisItem>;
  private uidIndex: Map<string, NodeIndexEntry>;
  private astRoot: Root | null;
  public currentVis: string;

  constructor(options?: any) {
    this.string2TreeProcessor = this.createString2TreeProcessor(options);
    this.tree2StringProcessor = this.createTree2StringProcessor();
    this.incrNodesMap = new Map();
    this.uidIndex = new Map();
    this.astRoot = null;
    this.currentVis = '';
  }

  destroy(): void {
    this.incrNodesMap.clear();
    this.uidIndex.clear();
    this.astRoot = null;
    this.currentVis = '';
  }

  /**
   * 更新当前VIS内容（主入口）
   */
  updateCurrentMarkdown(incrMarkdownString: string | null): string {
    // 关键修复：允许空字符串作为有效的更新内容，用于清空数据
    if (incrMarkdownString === undefined || incrMarkdownString === null) {
      return this.currentVis;
    }
    
    // 处理空字符串：清空所有数据
    if (incrMarkdownString === '') {
      this.currentVis = '';
      this.astRoot = null;
      this.uidIndex.clear();
      this.incrNodesMap.clear();
      return this.currentVis;
    }

    // 初始化场景
    if (!this.currentVis) {
      this.currentVis = incrMarkdownString;
      this.astRoot = this.parseVis2AST(incrMarkdownString);
      this.rebuildIndex();
      return this.currentVis;
    }

    // 增量合并场景
    const incrAST = this.parseVis2AST(incrMarkdownString);
    this.extractIncrContent(incrAST);

    // 确保有根AST
    if (!this.astRoot) {
      this.astRoot = this.parseVis2AST(this.currentVis);
      this.rebuildIndex();
    }

    // 执行增量合并
    this.mergeIncrementalChunk(incrAST);

    // 更新currentVis
    this.currentVis = this.parseAST2Vis(this.astRoot);

    return this.currentVis;
  }

  /**
   * 通过UID快速查询组件
   */
  queryByUID(uid: string): QueryResult {
    const entry = this.uidIndex.get(uid);
    if (!entry) {
      return { found: false };
    }

    let visItem: VisItem | undefined;
    try {
      if (entry.nodeType === 'ast' && entry.node.value) {
        visItem = safeJsonParse<VisItem>(entry.node.value);
      } else if (entry.nodeType === 'item') {
        visItem = entry.node as VisItem;
      } else if (entry.nodeType === 'nested' && entry.node.value) {
        visItem = safeJsonParse<VisItem>(entry.node.value);
      }
    } catch (e) {
      // 解析失败
    }

    return { found: true, entry, visItem };
  }

  getComponentPath(uid: string): string[] {
    const entry = this.uidIndex.get(uid);
    return entry ? entry.path : [];
  }

  getChildrenUIDs(uid: string): string[] {
    const children: string[] = [];
    this.uidIndex.forEach((entry, childUid) => {
      if (entry.parentUid === uid) {
        children.push(childUid);
      }
    });
    return children;
  }

  getIndexStats(): { total: number; byType: Record<string, number>; maxDepth: number } {
    const stats = {
      total: this.uidIndex.size,
      byType: { ast: 0, item: 0, nested: 0 } as Record<string, number>,
      maxDepth: 0
    };

    this.uidIndex.forEach((entry) => {
      stats.byType[entry.nodeType] = (stats.byType[entry.nodeType] || 0) + 1;
      stats.maxDepth = Math.max(stats.maxDepth, entry.depth);
    });

    return stats;
  }

  // ========== 核心合并逻辑 ==========

  /**
   * 执行增量合并
   */
  private mergeIncrementalChunk(incrAST: Root): void {
    if (!this.astRoot) return;

    // 遍历增量AST中的所有节点
    this.traverseASTNodes(incrAST, (incrNode, incrJson) => {
      const uid = incrJson.uid;
      if (!uid) return;

      // DELETE 类型：从组件树中移除该节点
      if (incrJson.type === 'delete') {
        this.removeNodeByUid(uid);
        return;
      }

      // 通过索引快速查找目标节点
      const existingEntry = this.uidIndex.get(uid);

      if (existingEntry) {
        // 节点已存在，执行合并
        this.mergeExistingNode(existingEntry, incrJson, incrNode);
      } else {
        // 节点不存在，智能挂载
        this.smartMountNewNode(incrNode, incrJson);
      }
    });

    // 重建索引
    this.rebuildIndex();
  }

  /**
   * 根据 UID 从 AST 树中移除节点
   * 支持 VIS DELETE 协议 - 删除已渲染的组件
   */
  private removeNodeByUid(uid: string): void {
    const entry = this.uidIndex.get(uid);
    if (!entry) return;

    try {
      if (entry.nodeType === 'ast') {
        // 顶层 AST 节点：从 astRoot.children 中移除
        if (this.astRoot) {
          const idx = this.astRoot.children.indexOf(entry.node);
          if (idx !== -1) {
            this.astRoot.children.splice(idx, 1);
          }
        }
      } else if (entry.nodeType === 'item') {
        // items 数组中的元素：从宿主的 items 中移除
        if (entry.itemsHostNode && entry.itemIndex !== undefined) {
          const hostJson = safeJsonParse(entry.itemsHostNode.value) as VisItem;
          if (hostJson.items) {
            hostJson.items = hostJson.items.filter((item: any) => item.uid !== uid);
            entry.itemsHostNode.value = JSON.stringify(hostJson);
          }
        } else if (entry.itemsHost && entry.itemIndex !== undefined) {
          if (entry.itemsHost.items) {
            entry.itemsHost.items = entry.itemsHost.items.filter((item: any) => item.uid !== uid);
          }
        }
      }
      // 从索引中移除
      this.uidIndex.delete(uid);
    } catch (e) {
      console.error(`[removeNodeByUid] Error removing uid=${uid}:`, e);
    }
  }

  /**
   * 合并已存在的节点
   * 关键修复：
   * 1. 正确处理items中元素的markdown递归合并
   * 2. 正确处理nested类型节点，更新其markdown宿主
   */
  private mergeExistingNode(entry: NodeIndexEntry, incrJson: VisItem, incrNode?: any): void {
    try {
      let existingJson: VisItem;

      // 根据节点类型获取现有数据
      if (entry.nodeType === 'ast' || entry.nodeType === 'nested') {
        if (!entry.node.value) return;
        existingJson = safeJsonParse<VisItem>(entry.node.value);
      } else if (entry.nodeType === 'item') {
        existingJson = entry.node as VisItem;
      } else {
        return;
      }

      // 执行合并
      const mergedJson = this.combineVisItem(existingJson, incrJson);

      // 更新节点
      if (entry.nodeType === 'ast') {
        // 顶层AST节点，直接更新
        entry.node.value = JSON.stringify(mergedJson);
      } else if (entry.nodeType === 'nested') {
        // 关键修复：嵌套在markdown中的节点
        // 需要更新其markdown宿主的markdown字段
        this.updateNestedNodeInHost(entry, mergedJson);
      } else if (entry.nodeType === 'item') {
        // 关键修复：更新items数组中的元素
        if (entry.itemsHostNode && entry.itemIndex !== undefined) {
          // 需要更新宿主节点的JSON
          const hostJson = safeJsonParse(entry.itemsHostNode.value) as VisItem;
          if (hostJson.items && hostJson.items[entry.itemIndex]) {
            hostJson.items[entry.itemIndex] = mergedJson;
            entry.itemsHostNode.value = JSON.stringify(hostJson);
          }
        } else if (entry.itemsHost && entry.itemIndex !== undefined) {
          entry.itemsHost.items![entry.itemIndex] = mergedJson;
        }
        // 同时更新索引中的引用
        Object.assign(entry.node, mergedJson);
      }

    } catch (e) {
      console.error(`[mergeExistingNode] Error merging uid=${incrJson.uid}:`, e);
    }
  }

  /**
   * 更新嵌套在markdown中的节点
   * 关键：需要沿着路径向上更新所有宿主的markdown字段
   */
  private updateNestedNodeInHost(entry: NodeIndexEntry, mergedJson: VisItem): void {
    const targetUid = mergedJson.uid;

    // 找到markdown宿主
    const hostNode = entry.markdownHost || entry.parentNode;
    if (!hostNode || !hostNode.value) {
      // 如果没有宿主，直接更新节点本身（降级处理）
      entry.node.value = JSON.stringify(mergedJson);
      return;
    }

    try {
      // 解析宿主的JSON
      const hostJson = safeJsonParse(hostNode.value) as VisItem;

      if (!hostJson.markdown) {
        // 宿主没有markdown，直接更新节点
        entry.node.value = JSON.stringify(mergedJson);
        return;
      }

      // 解析宿主的markdown为AST
      const markdownAST = this.parseVis2AST(hostJson.markdown);

      // 在AST中找到目标节点并更新
      let updated = false;
      this.traverseASTNodes(markdownAST, (node, json) => {
        if (json.uid === targetUid) {
          node.value = JSON.stringify(mergedJson);
          updated = true;
        }
      });

      if (updated) {
        // 将更新后的AST转回markdown字符串
        hostJson.markdown = this.parseAST2Vis(markdownAST);
        // 更新宿主节点
        hostNode.value = JSON.stringify(hostJson);

        // 递归向上更新：如果宿主本身也是嵌套节点，需要继续更新其宿主
        const hostEntry = this.uidIndex.get(hostJson.uid);
        if (hostEntry && hostEntry.nodeType === 'nested') {
          // 宿主也是嵌套节点，需要递归更新
          this.updateNestedNodeInHost(hostEntry, hostJson);
        }
      } else {
        // 没有在markdown中找到目标节点，直接更新节点本身
        entry.node.value = JSON.stringify(mergedJson);
      }

    } catch (e) {
      console.error(`[updateNestedNodeInHost] Error:`, e);
      // 降级处理：直接更新节点
      entry.node.value = JSON.stringify(mergedJson);
    }
  }

  /**
   * 智能挂载新节点
   */
  private smartMountNewNode(newNode: any, newJson: VisItem): void {
    if (!this.astRoot) return;

    const parentUid = newJson.parent_uid;

    if (parentUid) {
      const parentEntry = this.uidIndex.get(parentUid);
      if (parentEntry) {
        this.mountToParentMarkdown(parentEntry, newNode, newJson);
        return;
      }
    }

    // 作为根节点的子节点
    if (this.astRoot.children) {
      (this.astRoot.children as any[]).push(newNode);
    }
  }

  /**
   * 将新节点挂载到父节点的markdown中
   */
  private mountToParentMarkdown(parentEntry: NodeIndexEntry, newNode: any, newJson: VisItem): void {
    try {
      let parentJson: VisItem;
      let updateFn: (json: VisItem) => void;

      if (parentEntry.nodeType === 'ast' || parentEntry.nodeType === 'nested') {
        if (!parentEntry.node.value) return;
        parentJson = safeJsonParse(parentEntry.node.value);
        updateFn = (json) => { parentEntry.node.value = JSON.stringify(json); };
      } else if (parentEntry.nodeType === 'item') {
        parentJson = parentEntry.node as VisItem;
        updateFn = (json) => {
          Object.assign(parentEntry.node, json);
          // 同时更新宿主节点
          if (parentEntry.itemsHostNode && parentEntry.itemIndex !== undefined) {
            const hostJson = safeJsonParse(parentEntry.itemsHostNode.value) as VisItem;
            if (hostJson.items) {
              hostJson.items[parentEntry.itemIndex] = json;
              parentEntry.itemsHostNode.value = JSON.stringify(hostJson);
            }
          }
        };
      } else {
        return;
      }

      // 构建新节点的markdown字符串
      const newNodeMarkdown = this.parseAST2Vis({
        type: 'root',
        children: [newNode]
      } as Root);

      // 追加到父节点的markdown
      if (!parentJson.markdown) {
        parentJson.markdown = newNodeMarkdown;
      } else {
        parentJson.markdown += '\n' + newNodeMarkdown;
      }

      updateFn(parentJson);

    } catch (e) {
      console.error(`[mountToParentMarkdown] Error:`, e);
    }
  }

  /**
   * 合并两个VisItem
   * 关键修复：
   * 1. 使用mergeNonNull避免null覆盖有效值
   * 2. 递归合并items中元素的markdown
   */
  combineVisItem(baseItem: VisItem, incrItem: VisItem): VisItem {
    const {
      markdown: baseMarkdown = '',
      uid: baseUid,
      type: baseType,
      items: baseItemList = [],
      dynamic: baseDynamic,
    } = baseItem;

    const {
      markdown: incrMarkdown = '',
      uid: incrUid,
      type: incrType,
      items: incrItemList = [],
      dynamic: incrDynamic,
    } = incrItem;

    // UID不匹配，返回原始数据
    if (baseUid !== incrUid) {
      return baseItem;
    }

    // 合并markdown
    let combinedMarkdown: string | undefined;
    if (baseDynamic) {
      // dynamic模式：简单字符串拼接
      combinedMarkdown = (baseMarkdown || '') + (incrMarkdown || '');
    } else {
      // 正常模式：智能合并
      combinedMarkdown = this.combineMarkdownString(baseMarkdown, incrMarkdown);
    }

    // 确定最终markdown
    let newMarkdown: string | undefined;
    if (incrType === 'all') {
      // all模式：全量替换（但如果incr的markdown为空，保留base的）
      newMarkdown = incrMarkdown || baseMarkdown || undefined;
    } else {
      // incr模式：增量合并
      if (incrMarkdown) {
        newMarkdown = combinedMarkdown;
      } else {
        newMarkdown = baseMarkdown || undefined;
      }
    }

    // 合并items数组
    let newItems: VisItem[] | undefined;
    if (incrType === 'all' && incrItemList && incrItemList.length > 0) {
      // all模式且有新items：全量替换
      newItems = incrItemList;
    } else {
      // incr模式或all模式但无新items：增量合并
      newItems = this.combineItems(baseItemList || [], incrItemList || []);
    }

    // 关键修复：使用mergeNonNull合并其他字段，避免null覆盖
    const mergedFields = mergeNonNull(baseItem, incrItem);

    return {
      ...mergedFields,
      markdown: newMarkdown,
      uid: baseUid,
      dynamic: incrDynamic !== undefined ? incrDynamic : baseDynamic,
      type: incrType || baseType,
      items: newItems && newItems.length > 0 ? newItems : undefined,
    };
  }

  /**
   * 合并items数组
   * 关键修复：递归合并每个item的markdown字段
   */
  private combineItems(baseItems: VisItem[], incrItems: VisItem[]): VisItem[] {
    if (!incrItems || incrItems.length === 0) {
      return baseItems || [];
    }

    const incrMap = keyBy(incrItems, 'uid');

    // 合并已存在的items
    const merged = (baseItems || []).map(baseItem => {
      const incrItem = incrMap[baseItem.uid];
      if (incrItem) {
        // 递归合并item
        return this.combineVisItem(baseItem, incrItem);
      }
      return baseItem;
    });

    // 添加新items
    const existingUids = new Set((baseItems || []).map(i => i.uid));
    const newItems = incrItems.filter(i => !existingUids.has(i.uid));

    return [...merged, ...newItems];
  }

  /**
   * 合并两个markdown字符串
   * 关键修复：修复nested代码块导致的isPartialTag误判问题
   */
  combineMarkdownString(
    baseMarkdownString: string | null | undefined,
    incrMarkdownString: string | null | undefined
  ): string | undefined {
    // 处理空值
    if (!baseMarkdownString && !incrMarkdownString) {
      return undefined;
    }
    if (!baseMarkdownString) {
      return incrMarkdownString || undefined;
    }
    if (!incrMarkdownString) {
      return baseMarkdownString;
    }

    // 纯文本合并（不包含代码块）
    if (!baseMarkdownString.includes('```') && !incrMarkdownString.includes('```')) {
      return baseMarkdownString + incrMarkdownString;
    }

    // 关键修复：先尝试AST级别合并，正确处理nested代码块
    try {
      const baseAST = this.parseVis2AST(baseMarkdownString);
      const incrAST = this.parseVis2AST(incrMarkdownString);

      // 收集base中的所有uid
      const baseUidMap = new Map<string, { node: any; json: VisItem }>();
      this.traverseASTNodes(baseAST, (node, json) => {
        if (json.uid) {
          baseUidMap.set(json.uid, { node, json });
        }
      });

      // 处理增量AST中的每个节点
      this.traverseASTNodes(incrAST, (incrNode, incrJson) => {
        if (!incrJson.uid) return;

        const existing = baseUidMap.get(incrJson.uid);
        if (existing) {
          // 节点已存在，合并数据
          const merged = this.combineVisItem(existing.json, incrJson);
          existing.node.value = JSON.stringify(merged);
        } else {
          // 节点不存在，追加到base
          if (baseAST.children) {
            (baseAST.children as any[]).push(incrNode);
          }
        }
      });

      return this.parseAST2Vis(baseAST);
    } catch (error) {
      // AST解析失败，退回到partial tag检测逻辑
      console.warn('[combineMarkdownString] AST merge failed, falling back to partial tag check:', error);
      
      // 处理非闭合标签（流式输出中间状态）
      if (isPartialTag(baseMarkdownString) || isPartialTag(incrMarkdownString)) {
        return baseMarkdownString + incrMarkdownString;
      }

      // 其他异常情况，返回拼接结果
      return baseMarkdownString + '\n' + incrMarkdownString;
    }
  }

  // ========== 索引管理 ==========

  /**
   * 重建完整索引
   */
  private rebuildIndex(): void {
    this.uidIndex.clear();
    if (this.astRoot) {
      this.buildIndexRecursive(this.astRoot, null, null, null, 0, []);
    }
  }

  /**
   * 递归构建索引
   * 关键修复：正确索引items数组中元素的markdown嵌套，并检测循环引用
   */
  private buildIndexRecursive(
    node: any,
    parentNode: any,
    parentUid: string | null,
    itemsHostNode: any,
    depth: number,
    path: string[]
  ): void {
    if (!node) return;
    
    // 防止递归过深（最大深度限制）
    if (depth > 100) {
      console.error(`[buildIndexRecursive] 递归深度超过限制: ${depth}, path: ${path.join(' -> ')}`);
      return;
    }

    // 处理AST code节点（带lang属性）
    if (node.lang && node.value) {
      try {
        const json = safeJsonParse(node.value) as VisItem;
        if (json.uid) {
          // 检测循环引用：如果当前UID已在路径中，说明有循环引用
          if (path.includes(json.uid)) {
            // 特殊处理：如果是直接自引用（父节点和子节点使用相同 UID），
            // 这通常是合法的结构（表示子组件是父组件的渲染形式）
            const lastUid = path[path.length - 1];
            if (lastUid === json.uid) {
              // 直接自引用，跳过但不报错
              return;
            }
            // 其他情况是真正的循环引用，报错
            console.error(`[buildIndexRecursive] 检测到循环引用，跳过处理: uid=${json.uid}, path: ${path.join(' -> ')} -> ${json.uid}`);
            return;
          }
          
          const currentPath = [...path, json.uid];

          // 索引当前节点
          this.uidIndex.set(json.uid, {
            node,
            nodeType: 'ast',
            parentUid,
            parentNode,
            depth,
            path: currentPath
          });

          // 索引items数组
          if (json.items && Array.isArray(json.items)) {
            this.indexItems(json.items, node, json.uid, depth + 1, currentPath);
          }

          // 索引嵌套markdown
          if (json.markdown) {
            this.indexNestedMarkdown(json.markdown, node, json.uid, depth + 1, currentPath);
          }
        }
      } catch (e) {
        // 非JSON节点，忽略
      }
    }

    // 递归处理子节点
    if (node.children && Array.isArray(node.children)) {
      node.children.forEach((child: any) => {
        this.buildIndexRecursive(child, node, parentUid, itemsHostNode, depth, path);
      });
    }
  }

  /**
   * 索引items数组
   * 关键修复：存储宿主AST节点引用，检测循环引用
   */
  private indexItems(
    items: VisItem[],
    hostNode: any,
    hostUid: string,
    depth: number,
    path: string[]
  ): void {
    // 防止递归过深
    if (depth > 100) {
      console.error(`[indexItems] 递归深度超过限制: ${depth}, path: ${path.join(' -> ')}`);
      return;
    }
    
    items.forEach((item, index) => {
      if (item.uid) {
        // 检测循环引用：如果当前UID已在路径中，说明有循环引用
        if (path.includes(item.uid)) {
          // 特殊处理：如果是直接自引用（父节点和子节点使用相同 UID），
          // 这通常是合法的结构（表示子组件是父组件的渲染形式）
          const lastUid = path[path.length - 1];
          if (lastUid === item.uid) {
            // 直接自引用，跳过但不报错
            return;
          }
          // 其他情况是真正的循环引用，报错
          console.error(`[indexItems] 检测到循环引用，跳过处理: uid=${item.uid}, path: ${path.join(' -> ')} -> ${item.uid}`);
          return;
        }

        const currentPath = [...path, item.uid];

        // 获取宿主的VisItem对象
        let hostVisItem: VisItem | undefined;
        try {
          hostVisItem = safeJsonParse(hostNode.value);
        } catch (e) {
          // 忽略
        }

        this.uidIndex.set(item.uid, {
          node: item,
          nodeType: 'item',
          parentUid: hostUid,
          parentNode: hostNode,
          depth,
          path: currentPath,
          itemsHost: hostVisItem,
          itemsHostNode: hostNode,  // 关键：存储AST节点引用
          itemIndex: index
        });

        // 递归索引item的markdown
        if (item.markdown) {
          this.indexNestedMarkdown(item.markdown, item, item.uid, depth + 1, currentPath);
        }

        // 递归索引item的items
        if (item.items && Array.isArray(item.items)) {
          // 对于嵌套的items，需要特殊处理
          this.indexNestedItems(item.items, item, item.uid, depth + 1, currentPath);
        }
      }
    });
  }

  /**
   * 索引嵌套在VisItem中的items（非AST节点）
   * 关键修复：检测循环引用
   */
  private indexNestedItems(
    items: VisItem[],
    hostItem: VisItem,
    hostUid: string,
    depth: number,
    path: string[]
  ): void {
    // 防止递归过深
    if (depth > 100) {
      console.error(`[indexNestedItems] 递归深度超过限制: ${depth}, path: ${path.join(' -> ')}`);
      return;
    }
    
    items.forEach((item, index) => {
      if (item.uid) {
        // 检测循环引用：如果当前UID已在路径中，说明有循环引用
        if (path.includes(item.uid)) {
          // 特殊处理：如果是直接自引用（父节点和子节点使用相同 UID），
          // 这通常是合法的结构（表示子组件是父组件的渲染形式）
          const lastUid = path[path.length - 1];
          if (lastUid === item.uid) {
            // 直接自引用，跳过但不报错
            return;
          }
          // 其他情况是真正的循环引用，报错
          console.error(`[indexNestedItems] 检测到循环引用，跳过处理: uid=${item.uid}, path: ${path.join(' -> ')} -> ${item.uid}`);
          return;
        }

        const currentPath = [...path, item.uid];

        this.uidIndex.set(item.uid, {
          node: item,
          nodeType: 'item',
          parentUid: hostUid,
          parentNode: hostItem,
          depth,
          path: currentPath,
          itemsHost: hostItem,
          itemIndex: index
        });

        // 递归索引
        if (item.markdown) {
          this.indexNestedMarkdown(item.markdown, item, item.uid, depth + 1, currentPath);
        }
        if (item.items) {
          this.indexNestedItems(item.items, item, item.uid, depth + 1, currentPath);
        }
      }
    });
  }

  /**
   * 索引嵌套在markdown中的组件
   * 关键修复：检测循环引用
   */
  private indexNestedMarkdown(
    markdown: string,
    hostNode: any,
    hostUid: string,
    depth: number,
    path: string[]
  ): void {
    if (!markdown || !markdown.includes('```')) return;
    
    // 防止递归过深
    if (depth > 100) {
      console.error(`[indexNestedMarkdown] 递归深度超过限制: ${depth}, path: ${path.join(' -> ')}`);
      return;
    }

    try {
      const nestedAST = this.parseVis2AST(markdown);

      this.traverseASTNodes(nestedAST, (node, json) => {
        if (json.uid) {
          // 检测循环引用：如果当前UID已在路径中，说明有循环引用
          if (path.includes(json.uid)) {
            // 特殊处理：如果是直接自引用（父节点和子节点使用相同 UID），
            // 这通常是合法的结构（表示子组件是父组件的渲染形式）
            const lastUid = path[path.length - 1];
            if (lastUid === json.uid) {
              // 直接自引用，跳过但不报错
              return;
            }
            // 其他情况是真正的循环引用，报错
            console.error(`[indexNestedMarkdown] 检测到循环引用，跳过处理: uid=${json.uid}, path: ${path.join(' -> ')} -> ${json.uid}`);
            return;
          }

          const currentPath = [...path, json.uid];

          this.uidIndex.set(json.uid, {
            node,
            nodeType: 'nested',
            parentUid: hostUid,
            parentNode: hostNode,
            depth,
            path: currentPath,
            markdownHost: hostNode
          });

          // 递归索引更深层的嵌套
          if (json.markdown) {
            this.indexNestedMarkdown(json.markdown, node, json.uid, depth + 1, currentPath);
          }

          // 索引items
          if (json.items && Array.isArray(json.items)) {
            this.indexItems(json.items, node, json.uid, depth + 1, currentPath);
          }
        }
      });
    } catch (e) {
      // 解析失败，忽略
    }
  }

  // ========== AST操作 ==========

  parseVis2AST(markdown: string): Root {
    return this.string2TreeProcessor.parse(createFile(markdown));
  }

  parseAST2Vis(ast: Root): string {
    const result = this.tree2StringProcessor.stringify(ast);
    return (result as string).trimEnd();
  }

  private traverseASTNodes(
    node: any,
    callback: (node: any, json: VisItem) => void
  ): void {
    if (!node) return;

    if (node.lang && node.value) {
      try {
        const json = safeJsonParse(node.value) as VisItem;
        callback(node, json);
      } catch (e) {
        // 非JSON节点
      }
    }

    if (node.children && Array.isArray(node.children)) {
      node.children.forEach((child: any) => {
        this.traverseASTNodes(child, callback);
      });
    }
  }

  private extractIncrContent(incrAST: Root): void {
    this.incrNodesMap.clear();

    // 用于检测循环引用：记录当前访问路径
    // 只有检测到真正的路径闭环（A -> B -> C -> A）才报错
    // 允许同一个 uid 在不同分支路径中出现

    const collect = (item: VisItem, path: string[], depth: number = 0) => {
      // 防止递归过深
      if (depth > 100) {
        console.error(`[extractIncrContent] 递归深度超过限制: ${depth}`);
        return;
      }

      if (item.uid) {
        // 检测循环引用：只在当前路径中存在该 uid 时才认为是循环引用
        // 例如：A -> B -> C -> A（闭环）
        // 而不是：A -> B 和 D -> B（不同分支共享子节点）
        if (path.includes(item.uid)) {
          // 特殊处理：如果是直接自引用（父节点和子节点使用相同 UID），
          // 这通常是合法的结构（表示子组件是父组件的渲染形式）
          // 我们应该跳过处理，但不报错
          const lastUid = path[path.length - 1];
          if (lastUid === item.uid) {
            // 直接自引用，跳过但不报错
            return;
          }
          // 其他情况是真正的循环引用，报错
          console.error(`[extractIncrContent] 检测到循环引用，跳过处理: uid=${item.uid}, path: ${path.join(' -> ')}`);
          return;
        }

        // 将当前 uid 加入路径
        const currentPath = [...path, item.uid];
        this.incrNodesMap.set(item.uid, item);

        // 递归处理 markdown 中的组件
        if (item.markdown) {
          const subTree = this.parseVis2AST(item.markdown);
          this.traverseASTNodes(subTree, (node, json) => {
            collect(json, currentPath, depth + 1);
          });
        }

        // 递归处理 items
        if (item.items) {
          item.items.forEach((subItem) => {
            collect(subItem, currentPath, depth + 1);
          });
        }
      } else {
        // 没有 uid 的组件，继续递归处理其子元素
        if (item.markdown) {
          const subTree = this.parseVis2AST(item.markdown);
          this.traverseASTNodes(subTree, (node, json) => {
            collect(json, path, depth + 1);
          });
        }

        if (item.items) {
          item.items.forEach((subItem) => {
            collect(subItem, path, depth + 1);
          });
        }
      }
    };

    this.traverseASTNodes(incrAST, (node, json) => {
      collect(json, [], 0);
    });
  }

  private createString2TreeProcessor(options?: any): Processor<any, any> {
    const remarkPlugins = options?.remarkPlugins || [];
    const remarkRehypeOptions = {
      allowDangerousHtml: true,
      ...options?.remarkRehypeOptions,
    };

    return unified()
      .use(remarkParse)
      .use(remarkPlugins)
      .use(remarkRehype, remarkRehypeOptions) as unknown as Processor<any, any>;
  }

  private createTree2StringProcessor(): Processor<any, any> {
    return unified().use(remarkStringify) as unknown as Processor<any, any>;
  }
}

// ============== VisParser 类 ==============

export class VisParser {
  public current: string;
  private parsers: Map<string, VisParser>;
  private windowParsers: Map<string, VisBaseParser>;  // 新增：每个窗口独立的VisBaseParser
  private defaultParser: VisBaseParser;

  constructor() {
    this.current = '';
    this.parsers = new Map();
    this.windowParsers = new Map();  // 新增
    this.defaultParser = new VisBaseParser();
  }

  getCurrent(key?: string): string {
    if (key) {
      // 优先从windowParsers获取
      const windowParser = this.windowParsers.get(key);
      if (windowParser) {
        return windowParser.currentVis;
      }
      return this.parsers.get(key)?.current || '';
    }
    return this.defaultParser.currentVis;
  }

  queryByUID(uid: string, key?: string): QueryResult {
    if (key) {
      // 优先从windowParsers查询
      const windowParser = this.windowParsers.get(key);
      if (windowParser) {
        return windowParser.queryByUID(uid);
      }
      const parser = this.parsers.get(key);
      if (parser && (parser as any).defaultParser) {
        return (parser as any).defaultParser.queryByUID(uid);
      }
      return { found: false };
    }
    return this.defaultParser.queryByUID(uid);
  }

  /**
   * 更新VIS内容
   * 关键修复：当某个窗口的内容为null时，保留该窗口之前的数据
   */
  update(vis: string): string {
    try {
      const json = safeJsonParse<Record<string, string | null>>(vis);

      // 解析当前状态，获取所有窗口的历史数据
      let currentState: Record<string, string | null> = {};
      try {
        if (this.current) {
          currentState = safeJsonParse<Record<string, string | null>>(this.current);
        }
      } catch {
        currentState = {};
      }

      // 收集所有需要处理的窗口key（包括新的和历史的）
      const allKeys = new Set([...Object.keys(json), ...Object.keys(currentState)]);

      // 构建最终结果
      const result: Record<string, string | null> = {};

      allKeys.forEach((key) => {
        const windowContent = json[key];

        // 获取或创建该窗口的解析器
        let windowParser = this.windowParsers.get(key);
        if (!windowParser) {
          windowParser = new VisBaseParser();
          this.windowParsers.set(key, windowParser);
        }

        // 只有当有新内容且不是空字符串时才更新解析器
        // 关键修复：空字符串会清空数据，跳过更新以保留之前累积的数据
        // 这与测试页面的行为一致：测试页面只有当窗口有实际内容时才调用 updateCurrentMarkdown
        if (windowContent !== undefined && windowContent !== null && windowContent !== '') {
          windowParser.updateCurrentMarkdown(windowContent);
        }

        // 关键修复：始终使用解析器的当前状态（保留历史）
        // 如果解析器有内容，使用解析器的内容
        // 如果解析器没有内容但历史有内容，保留历史
        // 如果都没有，设为null
        if (windowParser.currentVis) {
          result[key] = windowParser.currentVis;
        } else if (currentState[key]) {
          result[key] = currentState[key];
        } else {
          // 如果新json中该key存在（即使是null），保留null
          // 如果新json中该key不存在，不添加到结果中
          if (key in json) {
            result[key] = null;
          }
        }
      });

      this.current = JSON.stringify(result);
    } catch {
      this.defaultParser.updateCurrentMarkdown(vis);
      this.current = this.defaultParser.currentVis;
    }

    return this.current;
  }

  /**
   * 获取指定窗口的解析器统计信息
   */
  getIndexStats(key?: string): { total: number; byType: Record<string, number>; maxDepth: number } {
    if (key) {
      const windowParser = this.windowParsers.get(key);
      if (windowParser) {
        return windowParser.getIndexStats();
      }
    }
    return this.defaultParser.getIndexStats();
  }

  /**
   * 获取所有窗口的解析器统计信息
   */
  getAllWindowStats(): Map<string, { total: number; byType: Record<string, number>; maxDepth: number }> {
    const stats = new Map();
    this.windowParsers.forEach((parser, key) => {
      stats.set(key, parser.getIndexStats());
    });
    return stats;
  }

  destroy(): void {
    this.parsers.forEach((parser) => parser.destroy());
    this.parsers.clear();
    this.windowParsers.forEach((parser) => parser.destroy());
    this.windowParsers.clear();
    this.defaultParser.destroy();
  }
}

// ============== 导出独立函数（向后兼容） ==============

const defaultParser = new VisBaseParser();

export const parseVis2AST = (markdown: string, options?: any): Root => {
  const parser = new VisBaseParser(options);
  return parser.parseVis2AST(markdown);
};

export const parseAST2Vis = (ast: Root): string => {
  return defaultParser.parseAST2Vis(ast);
};

export const combineMarkdownString = (
  baseMarkdownString: string | null | undefined,
  incrMarkdownString: string | null | undefined
): string | undefined => {
  return defaultParser.combineMarkdownString(baseMarkdownString, incrMarkdownString);
};