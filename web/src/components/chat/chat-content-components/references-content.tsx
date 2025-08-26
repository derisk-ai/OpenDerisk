import MarkDownContext from './markdown-context';
import { LinkOutlined } from '@ant-design/icons';
import type { TabsProps } from 'antd';
import { Divider, Drawer, Tabs, Typography } from 'antd';
import React, { useMemo, useState } from 'react';

const ReferencesContentView: React.FC<{ references: any }> = ({ references }) => {
  const [open, setOpen] = useState<boolean>(false);

  const items: TabsProps['items'] = useMemo(() => {
    return references?.knowledge?.map((reference: any) => {
      return {
        label: (
          <div style={{ maxWidth: '120px' }}>
            <Typography.Text
              ellipsis={{
                tooltip: reference.name,
              }}
            >
              {decodeURIComponent(reference.name).split('_')[0]}
            </Typography.Text>
          </div>
        ),
        key: reference.name,
        children: (
          <div className='h-full overflow-y-auto'>
            {reference?.chunks?.map((chunk: any) => <MarkDownContext key={chunk.id}>{chunk.content}</MarkDownContext>)}
          </div>
        ),
      };
    });
  }, [references]);

  return (
    <div>
      <Divider className='mb-1 mt-0' dashed />
      <div className='flex text-sm gap-2 text-blue-400' onClick={() => setOpen(true)}>
        <LinkOutlined />
        <span className='text-sm'>查看回复引用</span>
      </div>
      <Drawer
        open={open}
        title='回复引用'
        placement={'right'}
        onClose={() => setOpen(false)}
        destroyOnHidden={true}
        className='p-0'
      >
        <Tabs items={items} size='small' />
      </Drawer>
    </div>
  );
};

const ReferencesContent: React.FC<{ references: any }> = ({ references }) => {
  try {
    const data = JSON.parse(references);
    return <ReferencesContentView references={data} />;
  } catch {
    return null;
  }
};

export default ReferencesContent;
