import {
  Decoration,
  DecorationSet,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  ViewUpdate,
} from '@codemirror/view';
import { CommonPluginWidget } from './CommonPluginWidget';

/**
 * 用于匹配指定规则的文本并自定义渲染
 */
export default (params: {
  skillList?: any[];
  agentList?: any[];
  knowledgeList?: any[];
}) => {
  const { skillList, agentList, knowledgeList } = params;
  // 匹配标签
  const placeholderMatcherBlue = new MatchDecorator({
    regexp:
      // @ts-ignore
      /{#LibraryBlock(?<attrs>[^#]*)#}(?<content>[^#]+){#\/LibraryBlock#}/g,
    decoration: (match) => {
      const attrs = match.groups?.attrs;
      const content: string = match.groups?.content || '';
      // 获取attrs中的type
      const type = attrs?.match(/type="([^"]+)"/)?.[1] || '';
      let params = {
        name: content,
        description: '',
        type,
      };
      if (type === 'skill') {
        const skill = skillList?.find((item) => item?.title === content);
        params.description = skill?.description;
      } else if (type === 'agent') {
        const agent = agentList?.find((item) => item?.title === content);
        params.description = agent?.description;
      } else if (type === 'knowledge') {
        const knowledge = knowledgeList?.find((item) => item?.name === content);
        params.description = knowledge?.description;
      }
      return Decoration.replace({
        // @ts-ignore
        widget: new CommonPluginWidget(params),
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
