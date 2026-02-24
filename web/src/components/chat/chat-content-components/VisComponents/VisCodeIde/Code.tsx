import { CodePreview } from '../../code-preview';
import { codeComponents } from '../../config';

import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { GPTVisLite } from '@antv/gpt-vis';
import { Space, Tabs } from 'antd';
import { isEqual } from 'lodash';
import React from 'react';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';

interface Props extends TS.CodeIde {
  pureCode?: boolean;
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
    console: _console,
  } = props;

  switch (showType) {
    case 'code':
      return (
        <div style={{ width: '100%' }} className="vis-codeide-code">
          <CodePreview lang={language} code={markdown || ''} style={oneLight} />
        </div>
      );
    case 'html-preview':
      return (
        <div
          style={{ width: '100%' }}
          className="vis-codeide-code-html-preview"
        >
          <iframe
            srcDoc={markdown}
            style={{ width: '100%', height: '100%', border: 'none' }}
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
              lang={language}
              code={markdown || ''}
              style={oneLight}
            />
            <Tabs
              tabBarStyle={{
                marginBottom: 10,
              }}
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
                      {_console && (
                        <GPTVisLite
                          components={codeComponents}
                          rehypePlugins={[rehypeRaw]}
                          remarkPlugins={[remarkGfm]}
                        >
                          {`\`\`\`shell
${_console}
\`\`\``}
                        </GPTVisLite>
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
      return <></>;
  }
}

export default React.memo(Code, isEqual);
