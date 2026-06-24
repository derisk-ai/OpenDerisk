'use client';

import { Tabs } from 'antd';
import { SearchOutlined, ExperimentOutlined } from '@ant-design/icons';
import SearchPanel from './SearchPanel';
import DeepResearchPanel from './DeepResearchPanel';

export default function RightSidebar() {
  return (
    <Tabs
      defaultActiveKey="search"
      size="small"
      className="h-full flex flex-col kv-tabs"
      items={[
        {
          key: 'search',
          label: (
            <span className="flex items-center gap-1 px-2">
              <SearchOutlined className="text-sm" />
              Search
            </span>
          ),
          children: <SearchPanel />,
        },
        {
          key: 'research',
          label: (
            <span className="flex items-center gap-1 px-2">
              <ExperimentOutlined className="text-sm" />
              Research
            </span>
          ),
          children: <DeepResearchPanel />,
        },
      ]}
    />
  );
}
