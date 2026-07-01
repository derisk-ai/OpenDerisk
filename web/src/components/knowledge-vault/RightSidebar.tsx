'use client';

import { Tabs } from 'antd';
import { ApartmentOutlined, ExperimentOutlined, SearchOutlined } from '@ant-design/icons';
import GraphSearchPanel from './GraphSearchPanel';
import SearchPanel from './SearchPanel';
import DeepResearchPanel from './DeepResearchPanel';
import { useSpace } from './SpaceContext';

export default function RightSidebar() {
  const { view } = useSpace();

  if (view === 'graph') {
    return (
      <Tabs
        defaultActiveKey="graph-search"
        size="small"
        className="h-full flex flex-col kv-tabs"
        items={[
          {
            key: 'graph-search',
            label: (
              <span className="flex items-center gap-1 px-2">
                <ApartmentOutlined className="text-sm" />
                Graph
              </span>
            ),
            children: <GraphSearchPanel />,
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
