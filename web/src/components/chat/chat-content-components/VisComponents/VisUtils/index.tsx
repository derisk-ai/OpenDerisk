import React, { useEffect, useMemo, useState } from 'react';
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
    tool_result?: string | object;
    markdown?: string;
  };
}

const VisUtils = ({ data }: IProps) => {
  const { tool_args, tool_result, markdown } = data || {};
  
  const isJsonResult = useMemo(() => {
    if (!tool_result) return false;
    if (typeof tool_result === 'object') return true;
    try {
      const o = JSON.parse(tool_result);
      if (o && typeof o === 'object') return true;
    } catch (e) {
      // ignore
    }
    return false;
  }, [tool_result]);

  const [formatType, setFormatType] = useState<'markdown' | 'json'>(
    isJsonResult ? 'json' : 'markdown',
  );

  useEffect(() => {
    setFormatType(isJsonResult ? 'json' : 'markdown');
  }, [isJsonResult]);

  const formatedJSON = useMemo(() => {
    if (formatType !== 'json') return '';
    if (!tool_result) return '';
    
    if (typeof tool_result === 'object') {
      return JSON.stringify(tool_result, null, 2);
    }
    
    const obj = safeJsonParse(tool_result || '', tool_result);
    // 如果解析结果与原字符串不相等（说明解析成功且内容不同，或者是对象），则格式化
    // 注意：safeJsonParse 失败返回 default (tool_result)
    // 如果 tool_result 是 "{}"，解析出 {}，不全等。
    if (typeof obj === 'object' && obj !== null) {
        return JSON.stringify(obj, null, 2);
    }
    return String(tool_result);
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
                        copyable={{ text: typeof tool_result === 'string' ? tool_result : JSON.stringify(tool_result) }}
                      />
                      {/* @ts-ignore */}
                      <GPTVis
                        className="whitespace-normal inner-chat-gpt-vis"
                        components={codeComponents}
                        {...markdownPlugins}
                      >
                        {(markdown || (typeof tool_result === 'string' ? tool_result?.replaceAll?.('~', '&#126;') : JSON.stringify(tool_result))) ?? ''}
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
