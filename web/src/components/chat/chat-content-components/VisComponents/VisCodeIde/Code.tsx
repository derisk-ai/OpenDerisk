import React from 'react';
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { GPTVis } from '@antv/gpt-vis';
import { Space, Tabs } from 'antd';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { CodePreview } from '../../code-preview';
import { codeComponents, markdownPlugins } from '../../config';

interface CodeItem {
  language?: string;
  markdown?: string;
  path?: string;
  console?: string;
  cost?: number;
  exit_success?: boolean;
  env?: string;
  pureCode?: boolean;
}

interface Props extends CodeItem {
  showType?: 'code-with-console' | 'html-preview' | 'code';
}

function Code(props: Props) {
  const {
    language,
    markdown,
    showType = 'code',
    cost,
    exit_success,
    env,
    console: consoleOutput,
  } = props;

  switch (showType) {
    case 'code':
      return (
        <div style={{ width: '100%' }} className="vis-codeide-code">
          <CodePreview
            language={language || 'text'}
            code={markdown || ''}
            light={oneLight}
          />
        </div>
      );
    case 'html-preview':
      return (
        <div
          style={{ width: '100%' }}
          className="vis-codeide-code-html-preview"
        >
          <iframe
            title="html-preview"
            srcDoc={markdown}
            style={{ width: '100%', minHeight: 200, border: 'none' }}
            sandbox="allow-scripts"
          />
        </div>
      );
    case 'code-with-console':
      return (
        <>
          <div
            style={{ width: '100%' }}
            className="vis-codeide-code-with-console"
          >
            <CodePreview
              language={language || 'text'}
              code={markdown || ''}
              light={oneLight}
            />
            <Tabs
              tabBarStyle={{ marginBottom: 10 }}
              type="card"
              size="small"
              defaultActiveKey="1"
              tabBarExtraContent={{
                right: (
                  <Space>
                    <div>
                      <span>耗时: {cost}s</span>
                    </div>
                    <div>
                      <span>执行状态: </span>
                      {exit_success ? (
                        <CheckCircleOutlined style={{ color: 'green' }} />
                      ) : (
                        <CloseCircleOutlined style={{ color: 'red' }} />
                      )}
                    </div>
                  </Space>
                ),
              }}
              items={[
                {
                  label: env ? `输出(${env})` : '输出',
                  key: '1',
                  children: (
                    <div>
                      {consoleOutput && (
                        //@ts-ignore
                        <GPTVis
                          components={codeComponents}
                          {...markdownPlugins}
                        >
                          {`\`\`\`shell
${consoleOutput}
\`\`\``}
                        </GPTVis>
                      )}
                    </div>
                  ),
                },
              ]}
            />
          </div>
        </>
      );
    default:
      return null;
  }
}

export default React.memo(Code);
