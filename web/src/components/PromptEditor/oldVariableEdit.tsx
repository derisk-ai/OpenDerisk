import { Rect } from '@codemirror/view';
import { createTheme } from '@uiw/codemirror-themes';
import CodeMirror, { EditorView } from '@uiw/react-codemirror';
import type { FC } from 'react';
import React, { useEffect, useRef, useState } from 'react';
import VariableChangeModal from './components/VariableChangeModal';
import VariableChooseModal from './components/VariableChooseModal';
import VariablePlugin from './components/VariablePlugin';
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
  setReasoningArgSuppliers: (
    value: string[] | ((string: []) => string[]),
  ) => void;
  reasoningArgSuppliers: string[];
};

interface Range {
  from: number;
  to: number;
}

const CommandPromptInput: FC<IPromptInputProps> = (props) => {
  const {
    value,
    readonly,
    placeholder,
    onChange,
    variableList = [],
    style,
    setReasoningArgSuppliers,
    reasoningArgSuppliers,
  } = props;
  // 选区信息
  const [selectionRange, setSelectionRange] = useState<Range | undefined>();
  // 光标位置信息，用于定位浮层位置
  const [cursorPosition, setCursorPosition] = useState<Rect | null>(null);
  const editorRef = useRef<EditorView | null>(null);
  // 触发的对应指令
  // 变量选择浮层
  const [showVarChooseModalOpen, setShowVarChooseModalOpen] = useState(false);
  // 保存下{{}}中的指令内容，用于检索匹配
  const [variableMatchContent, setVariableMatchContent] = useState<string>('');

  // 变量切换弹窗
  const [showVarChangeModalOpen, setShowVarChangeModalOpen] = useState(false);

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
    if (!curRange?.from || !curRange?.to) return;
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
  const handleClickChangeVariable = (range: { from: number; to: number }) => {
    setShowVarChangeModalOpen(true);
    setSelectionRange({
      from: range?.from,
      to: range?.to,
    });
  };
  // 扩展插件
  const basicExtensions = [
    VariablePlugin({
      variableList,
      clickChangeVariable: handleClickChangeVariable,
      reasoningArgSuppliers,
    }),
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
  const handleKeyDown = () => {
    const view = editorRef.current;
    if (!view) return;
    setTimeout(() => {
      const selection = getCursorSelection(view);
      let matchResult = null;
      const currentText = view?.state?.doc?.toString()?.slice(0, selection.to);
      const reg = /{{[^{}]*$/;
      matchResult = currentText?.match(reg);
      // 匹配到双花括号规则
      if (matchResult?.index || matchResult?.index === 0) {
        // 保存下匹配到变量符合规则的内容
        setVariableMatchContent(matchResult[0]);
        // 将选区范围替换为匹配到的内容范围，用于替换内容使用
        setSelectionRange({ ...selection, from: matchResult?.index });
        const position = getCursorPosition(view);
        // 保存下光标位置
        setCursorPosition(position);
        setShowVarChooseModalOpen(true);
        // 匹配到单花括号规则
      } else {
        setShowVarChooseModalOpen(false);
        setVariableMatchContent('');
        setSelectionRange(selection);
      }
    });
  };

  /**
   * 监听全局鼠标抬起
   */
  const handleMouseUp = (event: any) => {
    const view = editorRef.current;
    if (!view) return;
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
  const handleChangeVar = (params: { arg: string; name: string }) => {
    const { arg, name } = params;
    handleReplace(`{{${arg}}}`);
    setReasoningArgSuppliers((prev: string[]) => {
      // 已经存在了当前的name，直接返回
      if (prev.includes(name)) {
        return prev;
      } else {
        // 不存在的变量，则添加，添加时需要判断下是否存在相同arg的变量，如果有则去掉之前的，保证不会有重复的arg
        // 找到相同arg所有的name
        const argNames = variableList
          ?.filter((item) => item.arg === arg)
          ?.map((item) => item.name);
        // 过滤掉相同arg的变量
        const newPrev = prev.filter((item) => {
          return !argNames.includes(item);
        });
        return [...newPrev, name];
      }
    });
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
      {showVarChangeModalOpen && (
        <VariableChangeModal
          open={showVarChangeModalOpen}
          setOpen={setShowVarChangeModalOpen}
          handleChangeVar={handleChangeVar}
          variableList={variableList}
        />
      )}
      <PromptEditorWrapper style={style}>
        {/* 变量选择浮层 */}
        <div className="custom-choose">
          {showVarChooseModalOpen && (
            <VariableChooseModal
              cursorPosition={cursorPosition}
              variableMatchContent={variableMatchContent}
              variableList={variableList}
              getPopPosition={getPopPosition}
              setOpen={setShowVarChooseModalOpen}
              handleChangeVar={handleChangeVar}
            />
          )}
        </div>
        <CodeMirror
          theme={theme}
          className={'InputCodeMirror'}
          readOnly={readonly}
          value={value}
          onChange={(curValue) => {
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
            closeBrackets: false,
            indentOnInput: false,
            highlightActiveLine: false,
            //自动突出显示与当前选中内容相匹配的其它部分
            highlightSelectionMatches: false,
          }}
          extensions={[basicExtensions]}
          height="100%"
          style={{
            fontSize: 14,
            height: '100%',
          }}
        />
      </PromptEditorWrapper>
    </>
  );
};

export default React.memo(CommandPromptInput);
