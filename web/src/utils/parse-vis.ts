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
  if (baseUid !== incrUid) return baseItem;

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

  // 处理列表vis
  if (incrItemList.length !== 0) {
    // 存储新增uid的item
    const newListItems = incrItemList.filter(
      (i) => !find(baseItemList, { uid: i.uid }),
    );
    const incrListMap = keyBy(incrItemList, 'uid');
    const combinedListItems: VisItem[] = baseItemList.map((baseI) => {
      if (incrListMap[baseI.uid])
        return combineVisItem(baseI, incrListMap[baseI.uid], defaultIncrMap);
      else return baseI;
    });
    return {
      ...baseItem,
      ...incrItem, //其他业务字段可能在增量中同样有更新
      markdown: newMarkdown || undefined,
      uid: baseUid,
      dynamic: incrDynamic,
      type: incrType,
      items: [...combinedListItems, ...newListItems],
    };
  }

  return {
    ...baseItem,
    ...incrItem, //其他业务字段可能在增量中同样有更新
    markdown: newMarkdown,
    uid: baseUid,
    dynamic: incrDynamic,
    type: incrType,
    items: baseItemList,
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
  if (node1.hasOwnProperty('children') && node2.hasOwnProperty('children')) {
    const node1String = JSON.stringify(node1);
    node2.children.forEach((node:any) => {
      if (node.hasOwnProperty('lang')) {
        //@ts-ignore
        if (node.value) {
          try {
            //@ts-ignore
            const json = JSON.parse(node.value);
            const uid = json.uid;

            if (!node1String.includes(uid)) {
              // 该节点为新增节点
              node1.children.push(node);
            } else {
              // 该节点为存在节点
              // @ts-ignore
              const existNode = node1.children.find((child) =>
                // @ts-ignore
                child.value?.includes(uid),
              );
              if (existNode) {
                // @ts-ignore
                const newNode = combineAST(existNode, node, defaultIncrMap);
                // @ts-ignore
                existNode.value = newNode.value;
              }
            }
          } catch (e) {
            // console.error('Parse AST node json error', node, e);
          }
        }
      }
    });
  }

  return parseAST2Vis(node1);
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
  // 处理空chunk
  if (!baseMarkdownString || !incrMarkdownString) {
    return baseMarkdownString || incrMarkdownString || undefined;
  }
  // 处理非闭合标签
  if (isPartialTag(baseMarkdownString) || isPartialTag(incrMarkdownString)) {
    return baseMarkdownString + incrMarkdownString;
  }

  // 纯文本合并
  if (
    !baseMarkdownString.includes('```') &&
    !incrMarkdownString.includes('```')
  ) {
    return baseMarkdownString + incrMarkdownString;
  }
  // children合并
  const baseAST = parseVis2AST(baseMarkdownString);
  const incrAST = parseVis2AST(incrMarkdownString);
  if (
    baseAST.hasOwnProperty('children') &&
    incrAST.hasOwnProperty('children')
  ) {
    return combineNodeWithChildren(baseAST, incrAST, defaultIncrMap);
  }
  const finalAST = combineAST(baseAST, incrAST, defaultIncrMap);
  const finalMarkdownString = parseAST2Vis(finalAST);
  return finalMarkdownString;
};

export class VisBaseParser {
  // 存储Ast树，避免二次解析
  private incrNodesMap: Map<string, VisItem>;
  private string2TreeProcessor: Processor<any, any>;
  private tree2StringProcessor: Processor<any, any>;

  public currentVis: string;

  constructor() {
    this.incrNodesMap = new Map<string, VisItem>();
    this.string2TreeProcessor = this.createString2TreeProcessor() as unknown as Processor<any, any>;
    this.tree2StringProcessor = this.createTree2StringProcessor() as unknown as Processor<any, any>;
    this.currentVis = '';
  }

  destroy() {
    this.incrNodesMap?.clear();
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

    // 处理列表vis
    if (incrItemList.length !== 0) {
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
      return {
        ...baseItem,
        ...incrItem, //其他业务字段可能在增量中同样有更新
        markdown: newMarkdown || undefined,
        uid: baseUid,
        dynamic: incrDynamic,
        type: incrType,
        items: [...combinedListItems, ...newListItems],
      };
    }

    return {
      ...baseItem,
      ...incrItem, //其他业务字段可能在增量中同样有更新
      markdown: newMarkdown,
      uid: baseUid,
      dynamic: incrDynamic,
      type: incrType,
      items: baseItemList,
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

  // 该函数用于处理AST的结构新增
  combineNodeWithChildren(
    baseNode: Root,
    incrNode: Root,
  ) {
    if (baseNode.hasOwnProperty('children') && incrNode.hasOwnProperty('children')) {
      const baseMarkdown = JSON.stringify(baseNode);
      // @ts-ignore
      incrNode.children.forEach((node: { hasOwnProperty: (arg0: string) => any; value: string; }) => {
        if (node.hasOwnProperty('lang')) {
          //@ts-ignore
          if (node.value) {
            try {
              //@ts-ignore
              const json = JSON.parse(node.value);
              const uid = json.uid;

              if (!baseMarkdown.includes(uid)) {
                // 该节点为新增节点
                // @ts-ignore
                baseNode.children.push(node);
              } else {
                // 该节点为存在节点
                // @ts-ignore
                const existNode = baseNode.children.find((child) =>
                  // @ts-ignore
                  child.value?.includes(uid),
                );
                if (existNode) {
                  // @ts-ignore
                  const newNode = this.updateAST(existNode);
                  // @ts-ignore
                  existNode.value = newNode.value;
                }
              }
            } catch (e) {
              // console.error('Parse AST node json error', node, e);
            }
          }
        }
      });
    }
    const newVisString = this.parseAST2Vis(baseNode);

    return newVisString;
  };

  // 合并增量的markdown字符串
  // eslint-disable-next-line @typescript-eslint/no-use-before-define
  combineMarkdownString(
    baseMarkdownString: string | null | undefined,
    incrMarkdownString: string | null | undefined,
  ) {
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

    // children合并
    const baseAST = this.parseVis2AST(baseMarkdownString);
    const incrAST = this.parseVis2AST(incrMarkdownString);
    if (
      baseAST.hasOwnProperty('children') &&
      incrAST.hasOwnProperty('children')
    ) {
      return this.combineNodeWithChildren(baseAST, incrAST);
    }
    const finalAST = this.updateAST(baseAST);
    const finalMarkdownString = this.parseAST2Vis(finalAST);
    return finalMarkdownString;
  };

  updateCurrentMarkdown(incrMarkdownString: string) {
    // 处理初始化
    if (!this.currentVis) {
      this.currentVis = incrMarkdownString;
      return this.currentVis;
    }

    const incrAST = this.parseVis2AST(incrMarkdownString);
    this.getIncrContent(incrAST);

    const finalMarkdownString = this.combineMarkdownString(this.currentVis, incrMarkdownString);
    this.currentVis = finalMarkdownString || '';
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

