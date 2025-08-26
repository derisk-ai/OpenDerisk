import { styled } from 'styled-components';

export const PromptEditorWrapper = styled.div`
  font-weight: 400;
  font-size: 14px;
  line-height: 24px;
  transition: all 0.2s;
  word-break: break-all;
  height: 100%;
  cursor: text;
  flex: 1;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-gutter: stable;
  .cm-editor {
    background: transparent;
  }

  .cm-content {
    white-space: pre-wrap !important;
    width: 100% !important;
    line-height: 24px !important;
    font-size: 14px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
      'Helvetica Neue', Arial, 'Noto Sans', sans-serif, 'Apple Color Emoji',
      'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji';
  }

  .cm-placeholder {
    color: rgba(0, 10, 26, 26%) !important;
  }

  .cm-focused {
    outline: none !important;
  }
`;
