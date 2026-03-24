import styled from 'styled-components';

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
    padding: 16px 20px;
  }

  .cm-scroller {
    padding: 0 !important;
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

  /* Segmented control style */
  .prompt-mode-segmented {
    background: rgba(0, 0, 0, 0.04);
    border-radius: 6px;
    padding: 2px;

    .ant-segmented-item {
      border-radius: 5px;
      transition: all 0.2s cubic-bezier(0.645, 0.045, 0.355, 1);
    }
    
    .ant-segmented-item-selected {
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);
    }
  }
`;

export const MarkdownPreviewWrapper = styled.div`
  position: absolute;
  inset: 0;
  z-index: 20;
  overflow-y: auto;
  background: #fff;
  scrollbar-width: thin;
  scrollbar-gutter: stable;

  .prompt-md-content {
    padding: 48px 28px 32px;
    max-width: 100%;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
      'Helvetica Neue', Arial, 'Noto Sans', sans-serif;
    color: #374151;
    font-size: 14px;
    line-height: 1.75;
    letter-spacing: 0.01em;
  }

  /* ===== Headings ===== */
  .prompt-md-h1 {
    margin: 0 0 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid #e5e7eb;
    
    h1 {
      font-size: 20px;
      font-weight: 700;
      color: #111827;
      line-height: 1.3;
      margin: 0;
      letter-spacing: -0.01em;
    }
  }

  .prompt-md-h2 {
    margin: 28px 0 12px;
    padding: 10px 14px;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-left: 3px solid #3b82f6;
    border-radius: 0 8px 8px 0;
    
    h2 {
      font-size: 15px;
      font-weight: 600;
      color: #1e293b;
      line-height: 1.4;
      margin: 0;
      letter-spacing: 0;
    }
  }

  .prompt-md-h3 {
    font-size: 14px;
    font-weight: 600;
    color: #334155;
    margin: 20px 0 8px;
    padding-left: 10px;
    border-left: 2px solid #94a3b8;
    line-height: 1.5;
  }

  .prompt-md-h4 {
    font-size: 13px;
    font-weight: 600;
    color: #475569;
    margin: 16px 0 6px;
    line-height: 1.5;
  }

  /* ===== Paragraph ===== */
  .prompt-md-p {
    margin: 6px 0;
    color: #4b5563;
    font-size: 13.5px;
    line-height: 1.8;
    word-break: break-word;
  }

  /* ===== Strong / Bold ===== */
  .prompt-md-strong {
    color: #1f2937;
    font-weight: 600;
  }

  /* ===== Lists ===== */
  .prompt-md-ul {
    margin: 6px 0;
    padding-left: 20px;
    list-style: none;

    > .prompt-md-li {
      position: relative;
      padding-left: 6px;

      &::before {
        content: '';
        position: absolute;
        left: -14px;
        top: 10px;
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: #94a3b8;
      }
    }
  }

  .prompt-md-ol {
    margin: 6px 0;
    padding-left: 20px;
    list-style: none;
    counter-reset: ol-counter;

    > .prompt-md-li {
      position: relative;
      padding-left: 6px;
      counter-increment: ol-counter;

      &::before {
        content: counter(ol-counter);
        position: absolute;
        left: -20px;
        top: 2px;
        width: 18px;
        height: 18px;
        border-radius: 50%;
        background: #eff6ff;
        color: #3b82f6;
        font-size: 11px;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: center;
        line-height: 1;
      }
    }
  }

  .prompt-md-li {
    color: #4b5563;
    font-size: 13.5px;
    line-height: 1.8;
    margin: 3px 0;
    word-break: break-word;

    /* Nested lists */
    .prompt-md-ul, .prompt-md-ol {
      margin: 2px 0;
    }
  }

  /* ===== Blockquote ===== */
  .prompt-md-blockquote {
    margin: 12px 0;
    padding: 10px 16px;
    background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%);
    border-left: 3px solid #f59e0b;
    border-radius: 0 8px 8px 0;
    color: #78350f;

    .prompt-md-p {
      color: #92400e;
      margin: 2px 0;
    }
  }

  /* ===== Inline Code ===== */
  .prompt-md-inline-code {
    font-family: 'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', Menlo, Monaco, Consolas, monospace;
    font-size: 12.5px;
    background: #f1f5f9;
    color: #0369a1;
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid #e2e8f0;
    font-weight: 500;
    white-space: pre-wrap;
    word-break: break-word;
  }

  /* ===== Code Block ===== */
  .prompt-md-pre {
    margin: 12px 0;
    background: #1e293b;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.06);

    .prompt-md-block-code,
    code {
      display: block;
      padding: 16px 20px;
      font-family: 'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', Menlo, Monaco, Consolas, monospace;
      font-size: 12.5px;
      line-height: 1.7;
      color: #e2e8f0;
      background: transparent;
      border: none;
      border-radius: 0;
      overflow-x: auto;
      white-space: pre;
    }

    /* Highlight.js overrides */
    code.hljs {
      background: transparent;
      padding: 16px 20px;
    }
  }

  /* ===== Table ===== */
  .prompt-md-table-wrap {
    margin: 12px 0;
    overflow-x: auto;
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  }

  .prompt-md-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }

  .prompt-md-thead {
    background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
  }

  .prompt-md-th {
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    color: #334155;
    font-size: 12.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-bottom: 1px solid #e2e8f0;

    &:not(:last-child) {
      border-right: 1px solid #f1f5f9;
    }
  }

  .prompt-md-td {
    padding: 9px 14px;
    color: #4b5563;
    border-bottom: 1px solid #f1f5f9;
    line-height: 1.6;
    word-break: break-word;

    &:not(:last-child) {
      border-right: 1px solid #f8fafc;
    }
  }

  .prompt-md-table tbody tr {
    transition: background 0.15s ease;

    &:nth-child(even) {
      background: #fafbfc;
    }

    &:hover {
      background: #f0f7ff;
    }

    &:last-child .prompt-md-td {
      border-bottom: none;
    }
  }

  /* ===== Horizontal Rule ===== */
  .prompt-md-hr {
    margin: 24px 0;
    border: none;
    height: 1px;
    background: linear-gradient(90deg, transparent 0%, #d1d5db 20%, #d1d5db 80%, transparent 100%);
  }

  /* ===== Link ===== */
  .prompt-md-link {
    color: #2563eb;
    text-decoration: none;
    font-weight: 500;
    border-bottom: 1px solid transparent;
    transition: all 0.15s ease;

    &:hover {
      color: #1d4ed8;
      border-bottom-color: #93c5fd;
    }
  }

  /* ===== Image ===== */
  img {
    max-width: 100%;
    border-radius: 8px;
    margin: 8px 0;
  }
`;
