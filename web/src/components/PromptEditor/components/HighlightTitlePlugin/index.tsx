import {
  Decoration,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  ViewUpdate,
} from '@codemirror/view';

// 创建装饰器
const highlightMark = Decoration.mark({
  attributes: {
    style: 'color: #08979c; font-weight: 500;',
    // style: 'color: #1b62ff; font-weight: 500;',
  },
});

// 匹配指定规则的文本并高亮显示
const createMatchDecorator = new MatchDecorator({
  // regexp: /^#{1,6}\s+.+$/gm,
  regexp: /^#{1,6}\s+(.*)$/gm, // 匹配标题格式
  decoration: () => highlightMark,
});

/**
 * 动态高亮插件
 * 用于匹配指定规则的文本并高亮显示
 */
const HighlightTitlePlugin = ViewPlugin.fromClass(
  class {
    decorations;
    constructor(view: EditorView) {
      this.decorations = createMatchDecorator.createDeco(view);
    }
    update(update: ViewUpdate) {
      if (update.docChanged) {
        this.decorations = createMatchDecorator.updateDeco(
          update,
          this.decorations,
        ); // 重新生成装饰器
      }
    }
  },
  {
    decorations: (instance) => instance.decorations, // 返回装饰器集合
  },
);

export default HighlightTitlePlugin;
