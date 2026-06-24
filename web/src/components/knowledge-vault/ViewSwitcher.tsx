'use client';

import { useSpace, type View } from './SpaceContext';
import { Segmented } from 'antd';
import {
  ApartmentOutlined,
  BookOutlined,
  FileOutlined,
  FileSearchOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons';

const OPTIONS = [
  { value: 'raw', label: 'Raw', icon: <FileOutlined /> },
  { value: 'wiki', label: 'Wiki', icon: <BookOutlined /> },
  { value: 'graph', label: 'Graph', icon: <ApartmentOutlined /> },
  { value: 'schema', label: 'Schema', icon: <FileSearchOutlined /> },
  { value: 'lint', label: 'Lint', icon: <ToolOutlined /> },
  { value: 'settings', label: 'Settings', icon: <SettingOutlined /> },
];

export default function ViewSwitcher() {
  const { view, setView } = useSpace();

  return (
    <Segmented
      value={view}
      onChange={(v) => setView(v as View)}
      options={OPTIONS.map((o) => ({
        value: o.value,
        label: (
          <span className="flex items-center gap-1">
            {o.icon}
            {o.label}
          </span>
        ),
      }))}
      className="bg-gray-100/70"
    />
  );
}
