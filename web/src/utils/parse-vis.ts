/* eslint-disable @typescript-eslint/no-use-before-define */
import { find, keyBy } from 'lodash';
// @ts-ignore
import { Root } from 'mdast';
import remarkParse from 'remark-parse';
import remarkStringify from 'remark-stringify';
import remarkRehype from 'remark-rehype';
import {Processor, unified } from 'unified';
import { VFile } from 'vfile';

// 用于承载Vis Markdown字符串的容器
// 可以视作一个胶水层
// derisk中使用的Vis协议，实际上是 json + markdown

interface VisItem {
  type: 'incr' | 'all'; // 增量或全量
  uid: string; // 唯一标识符
  dynamic?: boolean; // dynamic=true时，模型正在输出内容，不一定是合法markdown
  markdown?: string; // 嵌套markdown
  items?: VisItem[]; // 平铺markdown
}
const emptyPlugins: any[] = [];
const emptyRemarkRehypeOptions = { allowDangerousHtml: true };

function createString2TreeProcessor(options?: any) {
  // const remarkPlugins =
  //   options?.remarkPlugins || emptyPlugins
  //     ? { ...options?.remarkRehypeOptions, ...emptyRemarkRehypeOptions }
  //     : emptyRemarkRehypeOptions;

  const remarkPlugins = options?.remarkPlugins || [];
  const remarkRehypeOptions = {
    allowDangerousHtml: true,
    ...options?.remarkRehypeOptions,
  };

  const processor = unified()
    // markdown文本转ast解析器
    .use(remarkParse)
    // 自定义扩展插件
    .use(remarkPlugins) // ✅ 传插件数组
    .use(remarkRehype, remarkRehypeOptions); // ✅ 传配置对象给 remark-rehype
  return processor;
}

function createTree2StringProcessor() {
  // AST转MD文本的管道处理器
  const processor = unified().use(remarkStringify);
  return processor;
}

function createFile(options: { children: string }) {
  const children = options.children || '';
  const file = new VFile();

  if (typeof children === 'string') {
    file.value = children;
  } else {
    console.error(
      'Unexpected value `' +
      children +
      '` for `children` prop, expected `string`',
    );
  }
  return file;
}

// 解析单层级markdown，并返回AST树
export const parseVis2AST = (markdown: string, options?: any) => {
  const processor = createString2TreeProcessor(options);
  const AST = processor.parse(createFile({ children: markdown }));
  return AST;
};

// 将当前AST树转化为markdown字符串
export const parseAST2Vis = (AST: Root) => {
  const processor = createTree2StringProcessor();
  const markdownString = processor.stringify(AST);
  // 去除末尾的换行符
  return markdownString.trimEnd();
};

export const combineVisItem = (
  baseItem: VisItem,
  incrItem: VisItem,
  defaultIncrMap?: Map<string, VisItem>,
) => {
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
  
  // Debug log
  console.log(`[combineVisItem] baseUid=${baseUid}, incrUid=${incrUid}, baseType=${baseType}, incrType=${incrType}`);
  console.log(`[combineVisItem] baseMarkdown length=${baseMarkdown.length}, incrMarkdown length=${incrMarkdown.length}`);
  
  if (baseUid !== incrUid) {
    console.log(`[combineVisItem] UIDs don't match, returning baseItem`);
    return baseItem;
  }

  // dynamic 字段由前一个chunk的值决定
  // dynamic=true时，模型正在输出内容，不一定是合法markdown，做字符串拼接
  const combinedMarkdown = baseDynamic
    ? baseMarkdown + incrMarkdown
    : combineMarkdownString(baseMarkdown, incrMarkdown, defaultIncrMap);

  // type = all/incr 由后一个chunk的值决定，实现跳变
  let newMarkdown;
  if (incrType === 'all') newMarkdown = incrMarkdown;
  else if (baseType === 'incr' || incrMarkdown) newMarkdown = combinedMarkdown;
  else newMarkdown = baseMarkdown;

  // 处理列表vis - 区分incr/all模式
  const safeBaseItemList = baseItemList || [];
  const safeIncrItemList = incrItemList || [];
  
  let newItems;
  if (incrType === 'all') {
    // all模式：items全量替换
    newItems = safeIncrItemList;
  } else {
    // incr模式：items追加合并
    if (safeIncrItemList.length !== 0) {
      // 存储新增uid的item
      const newListItems = safeIncrItemList.filter(
        (i) => !find(safeBaseItemList, { uid: i.uid }),
      );
      const incrListMap = keyBy(safeIncrItemList, 'uid');
      const combinedListItems: VisItem[] = safeBaseItemList.map((baseI) => {
        if (incrListMap[baseI.uid])
          return combineVisItem(baseI, incrListMap[baseI.uid], defaultIncrMap);
        else return baseI;
      });
      newItems = [...combinedListItems, ...newListItems];
    } else {
      newItems = safeBaseItemList;
    }
  }

  return {
    ...baseItem,
    ...incrItem, //其他业务字段可能在增量中同样有更新
    markdown: newMarkdown || undefined,
    uid: baseUid,
    dynamic: incrDynamic,
    type: incrType,
    items: newItems,
  };
};

// 遍历AST, 获取uid + content的增量MAP
// 带业务语义：incr和uid
export const getIncrContent = (node: Root & { value?: string }) => {
  const incrNodes: Map<string, VisItem> = new Map<string, VisItem>();

  const traverseAST = (node: Root & { value?: string }) => {
    const collect = (item: VisItem) => {
      incrNodes.set(item.uid, item);
      if (item.markdown) {
        const subTree = parseVis2AST(item.markdown);
        traverseAST(subTree);
      }
      if(item.items) {
        item.items.forEach((subItem) => {
          if (subItem.markdown) {
            const subTree = parseVis2AST(subItem.markdown);
            traverseAST(subTree);
          }
        })
      }
    };

    if (node.hasOwnProperty('children')) {
      if (node.children) {
        //@ts-ignore
        node.children.forEach((child) => traverseAST(child));
      }
    } else if (node.hasOwnProperty('lang') && node.value) {
      try {
        const json = JSON.parse(node.value) as VisItem;
        const items = json.items || [];
        items.forEach((item: VisItem) => {
          collect(item);
        });
        collect(json);
      } catch (e) {
        // console.error('Parse AST node json error', node);
      }
    }
  };
  traverseAST(node);
  return incrNodes;
};

// 合并两个AST
export const combineAST = (
  baseAST: Root,
  addAST: Root,
  defaultIncrMap?: Map<string, VisItem>,
) => {
  const incrMap = defaultIncrMap || getIncrContent(addAST);

  const traverseAST = (node: Root & { value?: string }) => {
    if (node.hasOwnProperty('children')) {
      //@ts-ignore
      node.children.map((child) => traverseAST(child));
      // 自定义tag会有lang属性，node type为code
    } else if (node.hasOwnProperty('lang')) {
      if (node.value) {
        try {
          const json = JSON.parse(node.value) as VisItem;
          const incrNode = incrMap.get(json.uid);
          const newValue = incrNode ? combineVisItem(json, incrNode) : json;
          node.value = JSON.stringify(newValue);
        } catch (e) {
          // console.error('Parse AST node json error', node, e);
        }
      }
    }
    return node;
  };
  traverseAST(baseAST);
  // console.debug(baseAST, 'combined AST');
  return baseAST;
};

// 该函数用于处理AST的结构新增
const combineNodeWithChildren = (
  node1: Root,
  node2: Root,
  defaultIncrMap?: Map<string, VisItem>,
) => {
  console.log(`[combineNodeWithChildren] node1 children=${(node1 as any).children?.length}, node2 children=${(node2 as any).children?.length}`);
  
  if (node1.hasOwnProperty('children') && node2.hasOwnProperty('children')) {
    const node1String = JSON.stringify(node1);
    // @ts-ignore
    node2.children.forEach((node: any) => {
      if (node.hasOwnProperty('lang')) {
        //@ts-ignore
        if (node.value) {
          try {
            //@ts-ignore
            const json = JSON.parse(node.value) as VisItem;
            const uid = json.uid;
            console.log(`[combineNodeWithChildren] Processing node uid=${uid}, tag=${node.lang}`);

            if (!node1String.includes(uid)) {
              // 该节点为新增节点
              console.log(`[combineNodeWithChildren] New node, pushing to node1.children`);
              node1.children.push(node);
            } else {
              // 该节点为存在节点，需要合并增量数据
              console.log(`[combineNodeWithChildren] Existing node, merging...`);
              // @ts-ignore
              const existNode = node1.children.find((child: any) => {
                try {
                  if (child.value) {
                    const childJson = JSON.parse(child.value);
                    return childJson.uid === uid;
                  }
                  return false;
                } catch {
                  return child.value?.includes(uid);
                }
              });
              if (existNode) {
                // @ts-ignore
                const existJson = JSON.parse(existNode.value) as VisItem;
                const incrJson = json;
                
                // 递归处理嵌套在 markdown 中的组件
                if (existJson.markdown && incrJson.markdown) {
                  console.log(`[combineNodeWithChildren] Recursively merging nested markdown for uid=${uid}`);
                  const mergedMarkdown = combineMarkdownString(
                    existJson.markdown,
                    incrJson.markdown,
                    defaultIncrMap
                  );
                  existJson.markdown = mergedMarkdown;
                } else if (incrJson.markdown) {
                  // 增量有 markdown，基础没有，直接使用增量的
                  existJson.markdown = incrJson.markdown;
                }
                
                // 使用增量映射或直接合并节点数据
                const incrNode = defaultIncrMap?.get(uid) || incrJson;
                const mergedValue = combineVisItem(existJson, incrNode, defaultIncrMap);
                // @ts-ignore
                existNode.value = JSON.stringify(mergedValue);
                console.log(`[combineNodeWithChildren] Node merged successfully`);
              } else {
                console.log(`[combineNodeWithChildren] Warning: Could not find existing node for uid=${uid}`);
              }
            }
          } catch (e) {
            console.error(`[combineNodeWithChildren] Error parsing node:`, e);
          }
        }
      }
    });
  }

  const result = parseAST2Vis(node1);
  console.log(`[combineNodeWithChildren] Returning result, length=${result.length}`);
  return result;
};

const isPartialTag = (markdownString: string) => {
  const matches = markdownString.match(/`/g);
  return matches ? matches.length < 6 : true;
};

// 合并增量的markdown字符串
// eslint-disable-next-line @typescript-eslint/no-use-before-define
export const combineMarkdownString = (
  baseMarkdownString: string | null | undefined,
  incrMarkdownString: string | null | undefined,
  defaultIncrMap?: Map<string, VisItem>,
) => {
  console.log(`[combineMarkdownString] base length=${baseMarkdownString?.length}, incr length=${incrMarkdownString?.length}`);
  
  // 处理空chunk
  if (!baseMarkdownString || !incrMarkdownString) {
    console.log(`[combineMarkdownString] Empty chunk, returning single value`);
    return baseMarkdownString || incrMarkdownString || undefined;
  }
  // 处理非闭合标签
  if (isPartialTag(baseMarkdownString) || isPartialTag(incrMarkdownString)) {
    console.log(`[combineMarkdownString] Partial tag, concatenating`);
    return baseMarkdownString + incrMarkdownString;
  }

  // 纯文本合并
  if (
    !baseMarkdownString.includes('```') &&
    !incrMarkdownString.includes('```')
  ) {
    console.log(`[combineMarkdownString] Plain text, concatenating`);
    return baseMarkdownString + incrMarkdownString;
  }
  
  // children合并
  console.log(`[combineMarkdownString] Parsing AST...`);
  const baseAST = parseVis2AST(baseMarkdownString);
  const incrAST = parseVis2AST(incrMarkdownString);
  console.log(`[combineMarkdownString] baseAST has children=${baseAST.hasOwnProperty('children')}, incrAST has children=${incrAST.hasOwnProperty('children')}`);
  
  if (
    baseAST.hasOwnProperty('children') &&
    incrAST.hasOwnProperty('children')
  ) {
    console.log(`[combineMarkdownString] Using combineNodeWithChildren`);
    const result = combineNodeWithChildren(baseAST, incrAST, defaultIncrMap);
    console.log(`[combineMarkdownString] Result length=${result.length}`);
    return result;
  }
  const finalAST = combineAST(baseAST, incrAST, defaultIncrMap);
  const finalMarkdownString = parseAST2Vis(finalAST);
  console.log(`[combineMarkdownString] Using combineAST, result length=${finalMarkdownString.length}`);
  return finalMarkdownString;
};

export class VisBaseParser {
  // 存储Ast树，避免二次解析
  private incrNodesMap: Map<string, VisItem>;
  private string2TreeProcessor: Processor<any, any>;
  private tree2StringProcessor: Processor<any, any>;
  
  // 全局 UID 索引：uid -> { node, parent, depth }
  private uidIndex: Map<string, { node: any; parent: any; depth: number; path: string[] }>;
  
  // AST 根节点引用
  private astRoot: Root | null;

  public currentVis: string;

  constructor() {
    this.incrNodesMap = new Map<string, VisItem>();
    this.string2TreeProcessor = this.createString2TreeProcessor() as unknown as Processor<any, any>;
    this.tree2StringProcessor = this.createTree2StringProcessor() as unknown as Processor<any, any>;
    this.currentVis = '';
    this.uidIndex = new Map();
    this.astRoot = null;
  }

  destroy() {
    this.incrNodesMap?.clear();
    this.uidIndex?.clear();
    this.astRoot = null;
  }
  
  // 构建全局 UID 索引
  private buildUIDIndex(node: any, parent: any = null, depth: number = 0, path: string[] = []) {
    if (!node) return;
    
    if (node.hasOwnProperty('lang') && node.value) {
      try {
        const json = JSON.parse(node.value) as VisItem;
        if (json.uid) {
          this.uidIndex.set(json.uid, {
            node,
            parent,
            depth,
            path: [...path, json.uid]
          });
          
          // 递归索引嵌套在 markdown 中的节点
          if (json.markdown) {
            const nestedAST = this.parseVis2AST(json.markdown);
            if (nestedAST.hasOwnProperty('children')) {
              // @ts-ignore
              nestedAST.children.forEach((child: any) => {
                this.buildUIDIndex(child, node, depth + 1, [...path, json.uid]);
              });
            }
          }
          
          // 递归索引 items 数组中的节点
          if (json.items && Array.isArray(json.items)) {
            json.items.forEach((item: VisItem) => {
              if (item.uid) {
                this.uidIndex.set(item.uid, {
                  node: item,
                  parent: json,
                  depth: depth + 1,
                  path: [...path, json.uid, item.uid]
                });
              }
            });
          }
        }
      } catch (e) {
        // 非 JSON 节点，忽略
      }
    }
    
    // 递归处理子节点
    if (node.hasOwnProperty('children')) {
      // @ts-ignore
      node.children.forEach((child: any) => {
        this.buildUIDIndex(child, node, depth, path);
      });
    }
  }
  
  // 根据 UID 查找节点（O(1) 复杂度）
  private findNodeByUID(uid: string): { node: any; parent: any; depth: number; path: string[] } | undefined {
    return this.uidIndex.get(uid);
  }
  
  // 更新索引（在每次合并后调用）
  private updateIndex() {
    this.uidIndex.clear();
    if (this.astRoot) {
      this.buildUIDIndex(this.astRoot);
    }
  }

  createFile(options: { children: string }) {
    const children = options.children || '';
    const file = new VFile();

    if (typeof children === 'string') {
      file.value = children;
    } else {
      console.error(
        'Unexpected value `' +
        children +
        '` for `children` prop, expected `string`',
      );
    }
    return file;
  }

  createTree2StringProcessor() {
    // AST转MD文本的管道处理器
    const processor = unified().use(remarkStringify);
    return processor;
  }


  createString2TreeProcessor(options?: any) {
     const remarkPlugins = options?.remarkPlugins || [];
  const remarkRehypeOptions = {
    allowDangerousHtml: true,
    ...options?.remarkRehypeOptions,
  };

    const processor = unified()
      // markdown文本转ast解析器
      .use(remarkParse)
      // 自定义扩展插件
      .use(remarkPlugins) // ✅ 传插件数组
      .use(remarkRehype, remarkRehypeOptions); // ✅ 传配置对象给 remark-rehype
    return processor;
  }


  parseVis2AST(markdown: string) {
    return this.string2TreeProcessor.parse(this.createFile({ children: markdown }));;
  };

  parseAST2Vis(AST: Root) {
    // 性能不确定
    const markdownString = this.tree2StringProcessor.stringify(AST);
    // 去除末尾的换行符
    // @ts-ignore
    return markdownString.trimEnd();
  };

  combineVisItem(
    baseItem: VisItem,
    incrItem: VisItem,
  ) {
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
    if (baseUid !== incrUid) return baseItem;

    // dynamic 字段由前一个chunk的值决定
    // dynamic=true时，模型正在输出内容，不一定是合法markdown，做字符串拼接
    const combinedMarkdown = baseDynamic
      ? baseMarkdown + incrMarkdown
      : this.combineMarkdownString(baseMarkdown, incrMarkdown);

    // type = all/incr 由后一个chunk的值决定，实现跳变
    let newMarkdown;
    if (incrType === 'all') newMarkdown = incrMarkdown;
    else if (baseType === 'incr' || incrMarkdown) newMarkdown = combinedMarkdown;
    else newMarkdown = baseMarkdown;

    // 处理列表vis - 区分incr/all模式
    let newItems;
    if (incrType === 'all') {
      // all模式：items全量替换
      newItems = incrItemList;
    } else {
      // incr模式：items追加合并
      // 存储新增uid的item
      const newListItems = incrItemList.filter(
        (i) => !find(baseItemList, { uid: i.uid }),
      );
      const incrListMap = keyBy(incrItemList, 'uid');
      const combinedListItems: VisItem[] = baseItemList.map((baseI) => {
        if (incrListMap[baseI.uid])
          return this.combineVisItem(baseI, incrListMap[baseI.uid]);
        else return baseI;
      });
      newItems = [...combinedListItems, ...newListItems];
    }

    return {
      ...baseItem,
      ...incrItem, //其他业务字段可能在增量中同样有更新
      markdown: newMarkdown || undefined,
      uid: baseUid,
      dynamic: incrDynamic,
      type: incrType,
      items: newItems,
    };

  };

  // 遍历AST, 获取uid + content的增量MAP
  // 带业务语义：incr和uid
  getIncrContent(node: Root & { value?: string }) {
    this.incrNodesMap.clear();
    const traverseAST = (node: Root & { value?: string }) => {
      const collect = (item: VisItem) => {
        this.incrNodesMap.set(item.uid, item);
        if (item.markdown) {
          const subTree = this.parseVis2AST(item.markdown);
          traverseAST(subTree);
        }
        if(item.items) {
          item.items.forEach((subItem) => {
            if (subItem.markdown) {
              const subTree = this.parseVis2AST(subItem.markdown);
              traverseAST(subTree);
            }
          })
        }
      };

      if (node.hasOwnProperty('children')) {
        if (node.children) {
          //@ts-ignore
          node.children.forEach((child) => traverseAST(child));
        }
      } else if (node.hasOwnProperty('lang') && node.value) {
        try {
          const json = JSON.parse(node.value) as VisItem;
          const items = json.items || [];
          items.forEach((item: VisItem) => {
            collect(item);
          });
          collect(json);
        } catch (e) {
          // console.error('Parse AST node json error', node);
        }
      }
    };
    traverseAST(node);
  };

  // 更新AST
  updateAST(
    baseAST: Root,
  ) {
    const traverseAST = (node: Root & { value?: string }) => {
      if (node.hasOwnProperty('children')) {
        //@ts-ignore
        node.children.map((child) => traverseAST(child));
        // 自定义tag会有lang属性，node type为code
      } else if (node.hasOwnProperty('lang')) {
        if (node.value) {
          try {
            const json = JSON.parse(node.value) as VisItem;
            const incrNode = this.incrNodesMap.get(json.uid);
            const newValue = incrNode ? this.combineVisItem(json, incrNode) : json;
            node.value = JSON.stringify(newValue);
          } catch (e) {
            // console.error('Parse AST node json error', node, e);
          }
        }
      }
      return node;
    };
    traverseAST(baseAST);
    // console.debug(baseAST, 'combined AST');
    return baseAST;
  };

  isPartialTag(markdownString: string) {
    const matches = markdownString.match(/`/g);
    return matches ? matches.length < 6 : true;
  };

  // 智能合并节点 - 支持任意位置
  combineNodeWithChildren(
    baseNode: Root,
    incrNode: Root,
  ) {
    console.log(`[VisBaseParser.combineNodeWithChildren] Starting merge, base children=${(baseNode as any).children?.length}, incr children=${(incrNode as any).children?.length}`);
    
    // 使用全局索引查找和合并节点
    if (incrNode.hasOwnProperty('children')) {
      // @ts-ignore
      incrNode.children.forEach((incrChild: any) => {
        if (incrChild.hasOwnProperty('lang') && incrChild.value) {
          try {
            const incrJson = JSON.parse(incrChild.value) as VisItem;
            const uid = incrJson.uid;
            
            console.log(`[VisBaseParser.combineNodeWithChildren] Processing uid=${uid}`);
            
            // 使用全局索引查找已存在的节点（O(1) 复杂度）
            const existInfo = this.findNodeByUID(uid);
            
            if (existInfo) {
              // 节点已存在，合并数据
              console.log(`[VisBaseParser.combineNodeWithChildren] Found existing node at depth=${existInfo.depth}, path=${existInfo.path.join(' -> ')}`);
              const existNode = existInfo.node;
              const existJson = JSON.parse(existNode.value) as VisItem;
              
              // 递归处理嵌套在 markdown 中的组件
              if (existJson.markdown && incrJson.markdown) {
                const mergedMarkdown = this.combineMarkdownString(
                  existJson.markdown,
                  incrJson.markdown
                );
                existJson.markdown = mergedMarkdown;
              } else if (incrJson.markdown) {
                existJson.markdown = incrJson.markdown;
              }
              
              // 合并数据
              const mergedValue = this.combineVisItem(existJson, incrJson);
              existNode.value = JSON.stringify(mergedValue);
              console.log(`[VisBaseParser.combineNodeWithChildren] Merged successfully`);
            } else {
              // 节点不存在，智能挂载
              console.log(`[VisBaseParser.combineNodeWithChildren] New node, smart mounting...`);
              this.smartMountNode(baseNode, incrChild, incrJson);
            }
          } catch (e) {
            console.error(`[VisBaseParser.combineNodeWithChildren] Error processing node:`, e);
          }
        }
      });
    }
    
    // 更新索引
    this.updateIndex();
    
    const newVisString = this.parseAST2Vis(baseNode);
    console.log(`[VisBaseParser.combineNodeWithChildren] Merge complete, result length=${newVisString.length}`);
    return newVisString;
  }
  
  // 智能挂载节点
  private smartMountNode(baseNode: Root, newNode: any, newJson: VisItem) {
    // 策略1：如果有 parent_uid，尝试挂载到父节点下
    const parentUid = (newJson as any).parent_uid;
    if (parentUid) {
      const parentInfo = this.findNodeByUID(parentUid);
      if (parentInfo) {
        console.log(`[smartMountNode] Mounting to parent uid=${parentUid}`);
        // 挂载到父节点的 markdown 中
        if (!parentInfo.node.value) {
          parentInfo.node.value = JSON.stringify({ ...newJson, uid: parentUid });
        }
        
        const parentJson = JSON.parse(parentInfo.node.value) as VisItem;
        if (!parentJson.markdown) {
          parentJson.markdown = '';
        }
        
        // 将新节点添加到父节点的 markdown
        parentJson.markdown += '\n' + this.parseAST2Vis({
          type: 'root',
          children: [newNode]
        } as Root);
        
        parentInfo.node.value = JSON.stringify(parentJson);
        return;
      }
    }
    
    // 策略2：作为新根节点的子节点
    console.log(`[smartMountNode] Adding as new root child`);
    if (baseNode.hasOwnProperty('children')) {
      // @ts-ignore
      baseNode.children.push(newNode);
    }
  }

  // 合并增量的markdown字符串 - 使用全局索引
  combineMarkdownString(
    baseMarkdownString: string | null | undefined,
    incrMarkdownString: string | null | undefined,
  ) {
    console.log(`[VisBaseParser.combineMarkdownString] base length=${baseMarkdownString?.length}, incr length=${incrMarkdownString?.length}`);
    
    // 处理空chunk
    if (!baseMarkdownString || !incrMarkdownString) {
      return baseMarkdownString || incrMarkdownString || undefined;
    }
    // 处理非闭合标签
    if (this.isPartialTag(baseMarkdownString) || this.isPartialTag(incrMarkdownString)) {
      return baseMarkdownString + incrMarkdownString;
    }

    // 纯文本合并
    if (
      !baseMarkdownString.includes('```') &&
      !incrMarkdownString.includes('```')
    ) {
      return baseMarkdownString + incrMarkdownString;
    }

    // 使用全局索引合并
    const baseAST = this.parseVis2AST(baseMarkdownString);
    const incrAST = this.parseVis2AST(incrMarkdownString);
    
    if (
      baseAST.hasOwnProperty('children') &&
      incrAST.hasOwnProperty('children')
    ) {
      // 临时设置根节点并构建索引
      const prevRoot = this.astRoot;
      this.astRoot = baseAST;
      this.updateIndex();
      
      const result = this.combineNodeWithChildren(baseAST, incrAST);
      
      // 恢复状态
      this.astRoot = prevRoot;
      if (prevRoot) {
        this.updateIndex();
      }
      
      return result;
    }
    
    const finalAST = this.updateAST(baseAST);
    const finalMarkdownString = this.parseAST2Vis(finalAST);
    return finalMarkdownString;
  }

  updateCurrentMarkdown(incrMarkdownString: string) {
    // 处理初始化
    if (!this.currentVis) {
      this.currentVis = incrMarkdownString;
      // 构建初始索引
      this.astRoot = this.parseVis2AST(incrMarkdownString);
      this.updateIndex();
      return this.currentVis;
    }

    console.log(`[updateCurrentMarkdown] Updating...`);
    const incrAST = this.parseVis2AST(incrMarkdownString);
    this.getIncrContent(incrAST);

    // 使用全局索引合并
    const baseAST = this.parseVis2AST(this.currentVis);
    this.astRoot = baseAST; // 设置根节点引用
    this.updateIndex(); // 预构建索引
    
    const finalMarkdownString = this.combineNodeWithChildren(baseAST, incrAST);
    this.currentVis = finalMarkdownString || '';
    
    // 更新根节点和索引
    this.astRoot = this.parseVis2AST(this.currentVis);
    this.updateIndex();
    
    console.log(`[updateCurrentMarkdown] Update complete, index size=${this.uidIndex.size}`);
    return this.currentVis;
  }
}

export class VisParser {
  public current: string;
  private parsers: Map<string, VisParser>;
  private defaultParser: VisBaseParser;

  constructor() {
    this.current = '';
    this.parsers = new Map<string, VisParser>();
    this.defaultParser = new VisBaseParser();
  }

  getCurrent(key?: string) {
    return key ? (this.parsers.get(key)?.current || '') : this.defaultParser.currentVis;
  }

  update(vis: string) {
    try {
      const json = JSON.parse(vis);
      Object.keys(json).forEach((key) => {
        const parser = this.parsers.get(key);
        if (!parser) {
          const newParser = new VisParser();
          newParser.update(json[key]);
          this.parsers.set(key, newParser);
        } else {
          parser.update(json[key]);
          json[key] = parser.current;
        }
      })
      this.current = JSON.stringify(json);
    } catch {
      this.defaultParser.updateCurrentMarkdown(vis);
      this.current = this.defaultParser.currentVis;
    }
    return this.current;
  }

  destroy() {
    this.parsers.clear();
  }
}

