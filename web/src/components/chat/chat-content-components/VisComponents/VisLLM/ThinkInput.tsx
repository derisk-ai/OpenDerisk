import React, { useEffect, useState } from "react"
import { Collapse, Flex, Segmented } from 'antd';
import { GPTVisLite } from "@antv/gpt-vis";
import { codeComponents, markdownPlugins } from '../../config';
import { safeJsonParse } from "@/utils/json";
import { GET } from '@/client/api';


interface ModelDetail {
  title?: string
  outputType?: string
  content?: string
}



export default function ({ url = '' }: { url: string }) {
  const [showType, setShowType] = useState('');
  const [collapseOpen, setCollapseOpen] = useState<string[]>(['1']);
  const [details, setDetails] = useState<ModelDetail[]>([]);



  useEffect(() => {
    GET(url).then(res => {
      const data = res.data?.data?.items ? [...res.data.data.items] : [];
      if (!res.data?.success || !data.length) {
        return
      }
      let max = data.length;
      const result: ModelDetail[] = []
      for (let i = 0; i < max; i++) {
        const cur = data[i]
        if (Array.isArray(cur.items) && cur.items.length > 0) {
          data.push(...cur.items)
          max += cur.items.length
          continue
        }
        result.push({
          title: cur.title,
          outputType: cur.outputType,
          content: cur.content,
        })
      }
      setShowType(result?.[0]?.title || '');
      setDetails(result);
    })
  }, [url])

  const detail = details.find(i => i.title === showType)

  return <Collapse
    bordered={false}
    style={{
      padding: 0,
    }}
    size="small"
    defaultActiveKey={collapseOpen}
    expandIcon={({ }) => <></>}
    onChange={v => setCollapseOpen(v)}
    destroyOnHidden
    ghost
    items={[
      {
        headerClass: 'vis-llm-coll-header',
        key: '1',
        className: 'vis-llm-col-content',
        children: <Flex gap={8} vertical justify="flex-start" align="flex-start" >
          <h4>模型输入</h4>
          {!!collapseOpen.length && <Segmented
            value={showType}
            onChange={(v) => setShowType(v || '')}
            onClick={e => e.stopPropagation()}
            options={
              details.map(i => {
                return {
                  label: i.title,
                  value: i.title,
                }
              })
            }
          />}
          {detail?.content && (
            <GPTVisLite
              className="whitespace-normal"
              components={{
                ...codeComponents,
              }}
              {...markdownPlugins}
            >
              {detail.outputType?.toLowerCase() === 'json' ?
                `\`\`\`json\n${JSON.stringify(safeJsonParse(detail?.content), null, 2)}\n\`\`\`` :
                detail?.content
              }
            </GPTVisLite>
          )}

        </Flex>,
      },
    ]}
  />


}
