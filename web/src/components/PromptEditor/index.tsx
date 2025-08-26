import { Rect } from '@codemirror/view';
import { createTheme } from '@uiw/codemirror-themes';
import CodeMirror, { EditorView } from '@uiw/react-codemirror';
import type { FC } from 'react';
import React, { useEffect, useRef, useState } from 'react';
import CommonPlugin from './components/CommonPlugin';
// import HighlightTitlePlugin from './components/HighlightTitlePlugin';
// import MentionPanel from './components/MentionPanel';
// import VariableChangeModal from './components/VariableChangeModal';
// import VariablePlugin from './components/VariablePlugin';
import { PromptEditorWrapper } from './style';
import { getCursorPosition, getCursorSelection } from './utils';

export type IPromptInputProps = {
  readonly?: boolean;
  maxLength?: number;
  placeholder?: string;
  value?: any;
  onChange?: (val: any) => void;
  variableList?: any[];
  style?: React.CSSProperties;
  setReasoningArgSuppliers?: (value: string[] | ((string: []) => string[])) => void;
  reasoningArgSuppliers?: string[];
  skillList?: any[];
  agentList?: any[];
  knowledgeList?: any[];
  className?: string;
  teamMode?: boolean;
};

interface Range {
  from: number;
  to: number;
}

const CommandPromptInput: FC<IPromptInputProps> = props => {
  const {
    value,
    readonly,
    placeholder,
    onChange,
    variableList = [],
    style,
    setReasoningArgSuppliers,
    reasoningArgSuppliers = [],
    skillList = [],
    agentList = [],
    knowledgeList = [],
    className,
    teamMode,
  } = props;
  // 选区信息
  const [selectionRange, setSelectionRange] = useState<Range | undefined>();
  // 光标位置信息，用于定位浮层位置
  const [cursorPosition, setCursorPosition] = useState<Rect | null>(null);
  const editorRef = useRef<EditorView | null>(null);
  // 触发的对应指令
  // 变量选择浮层
  const [showVarChooseModalOpen, setShowVarChooseModalOpen] = useState(false);

  // 变量切换弹窗
  const [showVarChangeModalOpen, setShowVarChangeModalOpen] = useState(false);

  const getJoinText = (params: { title?: string; mentionType?: string }) => {
    const { title, mentionType } = params;
    if (!title || !mentionType) return '';
    return `{#LibraryBlock type="${mentionType}" #}${title}{#/LibraryBlock#}`;
  };
  // 当前切换变量的信息
  const [changeVarInfo, setChangeVarInfo] = useState<{
    title?: string;
    mentionType?: string;
  }>({});

  /**
   * 获取浮窗实际位置
   */
  const getPopPosition = (elementRef: any, cursorPosition: Rect) => {
    if (!elementRef.current) {
      return;
    }
    const popRect = elementRef.current?.getBoundingClientRect();
    const popPosition = {
      top: cursorPosition.bottom + 10,
      left: cursorPosition.left,
    };
    const windowHeight = window.innerHeight;
    if (popPosition.top + popRect.height > windowHeight) {
      // 如果超出，则将浮窗往上移动
      popPosition.top = windowHeight - popRect.height;
    }
    return popPosition;
  };

  /**
   * 替换选区内容
   * @param text 替换内容
   * @param range 替换内容所在选区
   */
  const handleReplace = (text: string, range?: Range) => {
    if (!editorRef.current || (!selectionRange && !range)) return;
    let newText = text || '';
    // 默认使用传入的范围进行替换操作
    const curRange = {
      from: range?.from ?? selectionRange?.from,
      to: range?.to ?? selectionRange?.to,
    };
    // curRange?.from可能为0，0的时候也可以进行替换
    if ((!curRange?.from && curRange?.from !== 0) || !curRange?.to) return;
    const transaction = editorRef.current.state.update({
      changes: {
        from: curRange?.from,
        to: curRange?.to,
        insert: newText,
      },
    });
    // 应用更改
    editorRef.current?.dispatch(transaction);
  };
  const handleClickChangeVariable = (range: { from: number; to: number }, varInfo: any) => {
    setChangeVarInfo(varInfo);
    setShowVarChangeModalOpen(true);
    setSelectionRange({
      from: range?.from,
      to: range?.to,
    });
  };
  // 扩展插件
  const basicExtensions = [
    // 变量插件
    // VariablePlugin({
    //   variableList,
    //   clickChangeVariable: handleClickChangeVariable,
    //   reasoningArgSuppliers,
    //   readonly,
    // }),
    // 通用插件（技能/知识/agent）
    CommonPlugin({
      skillList,
      agentList,
      knowledgeList,
    }),
    // 高亮标题插件
    // HighlightTitlePlugin,
  ];

  const theme = createTheme({
    theme: 'light',
    settings: {
      background: '#ffffff',
      backgroundImage: '',
      caret: '#000',
      selection: '#afd1ff',
      gutterBackground: '#fff',
      gutterForeground: '#8a919966',
      fontSize: 14,
    },
    styles: [],
  });

  /**
   * 编辑器中键盘按下
   */
  const handleKeyDown = (event: any) => {
    const view = editorRef.current;
    if (!view || readonly) return;
    setTimeout(() => {
      const selection = getCursorSelection(view);
      const nextStr = view?.state?.doc?.toString()?.slice(selection.from, selection.to + 1);
      if (event?.key === '{') {
        // 将选区范围替换为匹配到的内容范围，用于替换内容使用
        setSelectionRange({
          ...selection,
          // 当前光标位置在{}的中间，保存替换范围时，向后一位替换{
          from: selection.from - 1,
          // 编辑器如果能够顺利补全括号，就向后加1保存范围用于替换{}
          // 不能顺利补全{}就只需要替换左括号{则不需要加1
          to: nextStr === '}' ? selection.to + 1 : selection.to,
        });
        const position = getCursorPosition(view);
        // 保存下光标位置
        setCursorPosition(position);
        setShowVarChooseModalOpen(true);
      } else {
        setShowVarChooseModalOpen(false);
        setSelectionRange(selection);
      }
    });
  };

  /**
   * 监听全局鼠标抬起
   */
  const handleMouseUp = (event: any) => {
    const view = editorRef.current;
    if (!view || readonly) return;
    const selection = getCursorSelection(view);
    const position = getCursorPosition(view);
    // 点击这些区域时不关闭浮层
    const modalDom = document.querySelector('.ant-modal-root');
    const customModalDom = document.querySelector('.custom-command-modal');
    const customChooseModalDom = document.querySelector('.custom-choose-modal');
    let flag = false;
    // 是否在浮层内进行的点击
    if (
      (customModalDom && customModalDom?.contains(event?.target)) ||
      (modalDom && modalDom?.contains(event?.target)) ||
      (customChooseModalDom && customChooseModalDom?.contains(event?.target))
    ) {
      flag = true;
    }
    if (!flag) {
      setShowVarChooseModalOpen(false);
      setCursorPosition(position);
      setSelectionRange(selection);
    }
  };

  /**
   * 创建编辑器
   * @param view
   */
  const handleCreateEditor = (view: EditorView) => {
    editorRef.current = view;
    // 监听键盘按下事件
    view?.dom?.addEventListener('keydown', handleKeyDown);
    // 这里监听全局的鼠标抬起事件，获取选区信息，避免鼠标在编辑器外部时不触发
    document.addEventListener('mouseup', handleMouseUp);
  };

  /**
   * 切换变量
   */
  const handleChangeVar = (params: { arg: string; name: string; mentionType?: string; title?: string }) => {
    const { arg, name, mentionType, title } = params;
    if (mentionType === 'variable') {
      handleReplace(`{{${arg}}}`);
      setChangeVarInfo(params);
      // @ts-ignore
      setReasoningArgSuppliers((prev: string[]) => {
        // 已经存在了当前的name，直接返回
        if (prev.includes(name)) {
          return prev;
        } else {
          // 不存在的变量，则添加，添加时需要判断下是否存在相同arg的变量，如果有则去掉之前的，保证不会有重复的arg
          // 找到相同arg所有的name
          const argNames = variableList?.filter(item => item.arg === arg)?.map(item => item.name);
          // 过滤掉相同arg的变量
          const newPrev = prev.filter(item => {
            return !argNames.includes(item);
          });
          return [...newPrev, name];
        }
      });
    } else {
      // 其他类型的替换，拼接固定格式
      const text = getJoinText({ title, mentionType });
      handleReplace(text);
    }
  };

  useEffect(() => {
    return () => {
      // 移除监听事件
      document.removeEventListener('mouseup', handleMouseUp);
      if (editorRef.current) {
        editorRef.current?.dom?.removeEventListener('keydown', handleKeyDown);
      }
    };
  }, []);
  return (
    <>
      {/* {showVarChangeModalOpen && (
        <VariableChangeModal
          open={showVarChangeModalOpen}
          setOpen={setShowVarChangeModalOpen}
          handleChangeVar={handleChangeVar}
          variableList={variableList}
          changeVarInfo={changeVarInfo}
        />
      )} */}

      <PromptEditorWrapper style={style} className={className}>
        {/* 变量选择浮层 */}
        <div className='custom-choose'>
          {/* {showVarChooseModalOpen && (
            <MentionPanel
              skillList={skillList || []}
              agentList={agentList || []}
              variableList={variableList || []}
              knowledgeList={knowledgeList || []}
              cursorPosition={cursorPosition}
              getPopPosition={getPopPosition}
              setOpen={setShowVarChooseModalOpen}
              handleChangeVar={handleChangeVar}
              teamMode={teamMode}
            />
          )} */}
        </div>
        <CodeMirror
          theme={theme}
          className={'InputCodeMirror'}
          readOnly={readonly}
          value={value}
          onChange={curValue => {
            if (onChange) {
              onChange(curValue);
            }
          }}
          onCreateEditor={handleCreateEditor}
          placeholder={placeholder}
          basicSetup={{
            lineNumbers: false,
            highlightActiveLineGutter: false,
            foldGutter: false,
            autocompletion: false,
            //关闭自己显示另一开括号
            // closeBrackets: false,
            indentOnInput: false,
            highlightActiveLine: false,
            //自动突出显示与当前选中内容相匹配的其它部分
            highlightSelectionMatches: false,
          }}
          extensions={[basicExtensions]}
          height='100%'
          style={{
            fontSize: 14,
            height: '100%',
            minHeight: '200px',
          }}
        />
      </PromptEditorWrapper>
    </>
  );
};

export default React.memo(CommandPromptInput);
