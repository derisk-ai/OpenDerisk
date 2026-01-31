import React, { useMemo, useState } from 'react';
import { CodePreview } from '../../code-preview';
import { codeComponents, markdownPlugins } from '../../config';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { safeJsonParse } from '@/utils/json';
import { GPTVis } from '@antv/gpt-vis';
import { Collapse, Descriptions, Segmented, Space, Typography } from 'antd';
import { VisUitilDiv } from './style';

const { Text } = Typography;

interface IProps {
  data: {
    tool_name?: string;
    tool_desc?: string;
    tool_cost?: number;
    tool_version?: string;
    tool_author?: string;
    run_env?: string;
    tool_args?: unknown;
    tool_result?: string;
    markdown?: string;
  };
}

const VisUtils = ({ data }: IProps) => {
  const { tool_args, tool_result, markdown } = data || {};
  const [formatType, setFormatType] = useState<'markdown' | 'json'>('markdown');
  const formatedJSON = useMemo(() => {
    if (formatType !== 'json') return '';
    const obj = safeJsonParse(tool_result || '', tool_result);
    return obj !== tool_result ? JSON.stringify(obj, null, 2) : tool_result;
  }, [tool_result, formatType]);

  return (
    <VisUitilDiv>
      <Space style={{ width: '100%' }} direction="vertical">
        <Descriptions
          size="small"
          title={
            <>
              <div>{data?.tool_name}</div>
              <Typography.Text
                style={{ fontWeight: 'normal' }}
                type="secondary"
              >
                {data?.tool_desc}
              </Typography.Text>
            </>
          }
          items={[
            { key: '1', label: '耗时', children: data?.tool_cost ? `${data.tool_cost}s` : '-' },
            { key: '2', label: '工具版本', children: data?.tool_version || '-' },
            { key: '3', label: '工具作者', children: data?.tool_author || '-' },
            {
              key: '4',
              label: '运行环境',
              children: (
                <Typography.Text
                  ellipsis={{ tooltip: data?.run_env }}
                >
                  {data?.run_env || '-'}
                </Typography.Text>
              ),
            },
          ]}
        />
        <Collapse
          style={{ width: '100%' }}
          bordered={false}
          defaultActiveKey={['in', 'out']}
          items={[
            {
              key: 'in',
              label: '输入参数',
              children: (
                <CodePreview
                  language="json"
                  code={JSON.stringify(tool_args ?? {}, null, 2)}
                  light={oneLight}
                />
              ),
            },
          ]}
        />
        <Collapse
          style={{ width: '100%' }}
          bordered={false}
          defaultActiveKey={['out']}
          items={[
            {
              key: 'out',
              label: '输出参数',
              extra: (
                <Segmented
                  value={formatType}
                  options={[
                    { label: 'markdown', value: 'markdown' },
                    { label: 'json', value: 'json' },
                  ]}
                  onChange={(v) =>
                    setFormatType((v as 'markdown' | 'json') ?? 'markdown')
                  }
                />
              ),
              children: (
                <>
                  {formatType === 'markdown' && (
                    <div className="vis-utils-markdown">
                      <Text
                        className="code-copy-btn"
                        copyable={{ text: tool_result }}
                      />
                      {/* @ts-ignore */}
                      <GPTVis
                        className="whitespace-normal inner-chat-gpt-vis"
                        components={codeComponents}
                        {...markdownPlugins}
                      >
                        {markdown || (tool_result?.replaceAll?.('~', '&#126;') ?? '')}
                      </GPTVis>
                    </div>
                  )}
                  {formatType === 'json' && (
                    <CodePreview
                      language="json"
                      code={formatedJSON || ''}
                      light={oneLight}
                    />
                  )}
                </>
              ),
            },
          ]}
        />
      </Space>
    </VisUitilDiv>
  );
};

export default React.memo(VisUtils);
