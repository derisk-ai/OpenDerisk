import { Rect } from '@codemirror/view';
import { createTheme } from '@uiw/codemirror-themes';
import CodeMirror, { EditorView } from '@uiw/react-codemirror';
import { Segmented, Tooltip } from 'antd';
import { EditOutlined, EyeOutlined } from '@ant-design/icons';
import type { FC } from 'react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeRaw from 'rehype-raw';
import rehypeHighlight from 'rehype-highlight';
import VariablePlugin from './components/VariablePlugin';
import { PromptEditorWrapper, MarkdownPreviewWrapper } from './style';
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
  showPreview?: boolean;
};

interface Range {
  from: number;
  to: number;
}

/**
 * Custom markdown components for premium rendering
 */
const markdownComponents: Partial<Components> = {
  h1: ({ children, ...props }) => (
    <div className="prompt-md-h1">
      <h1 {...props}>{children}</h1>
    </div>
  ),
  h2: ({ children, ...props }) => (
    <div className="prompt-md-h2">
      <h2 {...props}>{children}</h2>
    </div>
  ),
  h3: ({ children, ...props }) => (
    <h3 className="prompt-md-h3" {...props}>{children}</h3>
  ),
  h4: ({ children, ...props }) => (
    <h4 className="prompt-md-h4" {...props}>{children}</h4>
  ),
  p: ({ children, ...props }) => (
    <p className="prompt-md-p" {...props}>{children}</p>
  ),
  strong: ({ children, ...props }) => (
    <strong className="prompt-md-strong" {...props}>{children}</strong>
  ),
  ul: ({ children, ...props }) => (
    <ul className="prompt-md-ul" {...props}>{children}</ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="prompt-md-ol" {...props}>{children}</ol>
  ),
  li: ({ children, ...props }) => (
    <li className="prompt-md-li" {...props}>{children}</li>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote className="prompt-md-blockquote" {...props}>{children}</blockquote>
  ),
  code: ({ className, children, ...props }) => {
    const isInline = !className;
    if (isInline) {
      return <code className="prompt-md-inline-code" {...props}>{children}</code>;
    }
    return <code className={`prompt-md-block-code ${className || ''}`} {...props}>{children}</code>;
  },
  pre: ({ children, ...props }) => (
    <pre className="prompt-md-pre" {...props}>{children}</pre>
  ),
  table: ({ children, ...props }) => (
    <div className="prompt-md-table-wrap">
      <table className="prompt-md-table" {...props}>{children}</table>
    </div>
  ),
  thead: ({ children, ...props }) => (
    <thead className="prompt-md-thead" {...props}>{children}</thead>
  ),
  th: ({ children, ...props }) => (
    <th className="prompt-md-th" {...props}>{children}</th>
  ),
  td: ({ children, ...props }) => (
    <td className="prompt-md-td" {...props}>{children}</td>
  ),
  hr: (props) => (
    <hr className="prompt-md-hr" {...props} />
  ),
  a: ({ children, ...props }) => (
    <a className="prompt-md-link" {...props} target="_blank" rel="noopener noreferrer">{children}</a>
  ),
};

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
    showPreview = false,
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

  // 内部状态控制预览显示，默认为 false
  const [isPreviewVisible, setIsPreviewVisible] = useState(false);

  const previewRef = useRef<HTMLDivElement>(null);

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
  // @ts-ignore
  const basicExtensions = [
    // 变量插件
    VariablePlugin({
      variableList,
      clickChangeVariable: handleClickChangeVariable,
      reasoningArgSuppliers,
      readonly,
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

  const handleModeChange = useCallback((val: string | number) => {
    setIsPreviewVisible(val === 'preview');
  }, []);

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
      <PromptEditorWrapper style={style} className={`${className} relative`}>
        {showPreview && (
          <div className="absolute top-3 right-5 z-30">
            <Segmented
              size="small"
              value={isPreviewVisible ? 'preview' : 'edit'}
              onChange={handleModeChange}
              options={[
                {
                  label: (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '0 2px' }}>
                      <EditOutlined style={{ fontSize: 12 }} />
                      <span style={{ fontSize: 12 }}>编辑</span>
                    </span>
                  ),
                  value: 'edit',
                },
                {
                  label: (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '0 2px' }}>
                      <EyeOutlined style={{ fontSize: 12 }} />
                      <span style={{ fontSize: 12 }}>预览</span>
                    </span>
                  ),
                  value: 'preview',
                },
              ]}
              className="prompt-mode-segmented"
            />
          </div>
        )}
        
        <div className="flex h-full w-full relative">
            <div className={`h-full w-full transition-opacity duration-200 ${isPreviewVisible ? 'opacity-0 pointer-events-none absolute' : 'opacity-100'}`}>
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
                    indentOnInput: false,
                    highlightActiveLine: false,
                    highlightSelectionMatches: false,
                  }}
                  // @ts-ignore
                  extensions={basicExtensions}
                  height='100%'
                  style={{
                    fontSize: 14,
                    height: '100%',
                    minHeight: '200px',
                  }}
                />
            </div>
            
            {showPreview && isPreviewVisible && (
              <MarkdownPreviewWrapper ref={previewRef}>
                <div className="prompt-md-content">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm, remarkBreaks]}
                    rehypePlugins={[rehypeRaw, rehypeHighlight]}
                    components={markdownComponents}
                  >
                    {value || ''}
                  </ReactMarkdown>
                </div>
              </MarkdownPreviewWrapper>
            )}
        </div>
      </PromptEditorWrapper>
    </>
  );
};

export default React.memo(CommandPromptInput);
