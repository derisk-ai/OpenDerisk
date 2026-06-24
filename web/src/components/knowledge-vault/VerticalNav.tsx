'use client';

import Link from 'next/link';
import {
  ApartmentOutlined,
  BookOutlined,
  FileOutlined,
  FileSearchOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useSpace, type View } from './SpaceContext';

const ITEMS: { value: View; label: string; icon: React.ReactNode }[] = [
  { value: 'raw', label: 'Raw', icon: <FileOutlined /> },
  { value: 'wiki', label: 'Wiki', icon: <BookOutlined /> },
  { value: 'graph', label: 'Graph', icon: <ApartmentOutlined /> },
  { value: 'schema', label: 'Schema', icon: <FileSearchOutlined /> },
  { value: 'lint', label: 'Lint', icon: <ToolOutlined /> },
  { value: 'settings', label: 'Settings', icon: <SettingOutlined /> },
];

export default function VerticalNav() {
  const { view, setView, slug } = useSpace();

  return (
    <div className="w-16 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col items-center py-3 h-full">
      <Link
        href="/knowledge-vault"
        className="w-10 h-10 rounded-xl bg-violet-600 text-white flex items-center justify-center mb-6 hover:bg-violet-700 transition-colors"
        title="Knowledge Vault"
      >
        <BookOutlined className="text-lg" />
      </Link>
      <div className="flex-1 flex flex-col gap-2 w-full px-2 items-center">
        {ITEMS.map((item) => {
          const active = view === item.value;
          return (
            <button
              key={item.value}
              onClick={() => setView(item.value)}
              title={item.label}
              className={[
                'w-full flex flex-col items-center justify-center gap-1 rounded-lg py-2 px-1 transition-colors',
                active
                  ? 'bg-violet-50 text-violet-600'
                  : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700',
              ].join(' ')}
            >
              <span className={['text-lg', active ? 'text-violet-600' : ''].join(' ')}>
                {item.icon}
              </span>
              <span className="text-[10px] font-medium leading-none">{item.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
