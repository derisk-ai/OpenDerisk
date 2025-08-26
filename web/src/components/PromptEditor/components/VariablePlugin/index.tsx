import {
  Decoration,
  DecorationSet,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  ViewUpdate,
} from '@codemirror/view';
import { VariablePluginWidget } from './VariablePluginWidget';
// const regex = /\{\{([^}]+)?\}\}/;
// const regex = /\{\{((?:(?!\{\{|}}).)+)\}\}/;
const regex = /{{([^{}]+)}}/;

/**
 * 用于匹配指定规则的文本并自定义渲染
 */
export default (params: {
  variableList: any[];
  clickChangeVariable: (
    range: { from: number; to: number },
    varInfo: any,
  ) => void;
  reasoningArgSuppliers: string[];
  readonly?: boolean;
}) => {
  const { variableList, clickChangeVariable, reasoningArgSuppliers, readonly } =
    params;
  // 匹配标签
  const placeholderMatcherBlue = new MatchDecorator({
    regexp: /{{([^{}]+)}}/g,
    decoration: (match, view, matchPos) => {
      // 是否为文本中第一个变量
      let isFirst = false;
      // 匹配文本中第一个符合规则的
      const currentText = view?.state?.doc?.toString();
      const matchContentIndex = currentText.match(regex)?.index;
      if (matchContentIndex === matchPos) {
        isFirst = true;
      }
      let selectedList = variableList;
      // 找出已选择的变量list，即在reasoningArgSuppliers中存在的name
      if (reasoningArgSuppliers?.length > 0) {
        selectedList = variableList?.filter((item) =>
          reasoningArgSuppliers?.includes(item.name),
        );
      }
      const widgetName = match[1];
      // 一个arg可能对应多个name，所以优先以reasoningArgSuppliers中的name为准，如果匹配不到，就使用全量的匹配
      const varInfo =
        selectedList?.find((item) => item?.arg === widgetName) ||
        variableList?.find((item) => item?.arg === widgetName) ||
        {};

      const { description, arg, script } = varInfo || {};
      const params = {
        name: match[1],
        description,
        script,
        renderName: arg,
        isFirst,
        matchPos,
        readonly,
      };

      const handleClickChangeVariable = () => {
        clickChangeVariable(
          {
            from: matchPos,
            to: matchPos + match[0].length,
          },
          varInfo,
        );
      };

      return Decoration.replace({
        widget: new VariablePluginWidget(params, handleClickChangeVariable),
      });
    },
  });

  //蓝色
  const placeholdersVarTag = ViewPlugin.fromClass(
    class {
      placeholders: DecorationSet;
      constructor(view: EditorView) {
        this.placeholders = placeholderMatcherBlue.createDeco(view);
      }
      update(update: ViewUpdate) {
        this.placeholders = placeholderMatcherBlue.updateDeco(
          update,
          this.placeholders,
        );
      }
    },
    {
      decorations: (instance) => instance.placeholders,
      provide: (plugin) =>
        EditorView.atomicRanges.of((view) => {
          return view.plugin(plugin)?.placeholders || Decoration.none;
        }),
    },
  );
  return placeholdersVarTag;
};
