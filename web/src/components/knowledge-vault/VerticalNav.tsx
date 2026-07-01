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
import VaultSeal from './VaultSeal';
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
    <div className="w-16 flex-shrink-0 bg-white border-r border-[#ECEAE3] flex flex-col items-center py-3 h-full">
      <Link
        href="/knowledge-vault"
        className="w-10 h-10 rounded-lg text-[#B5462E] flex items-center justify-center mb-4 hover:bg-[#FBF3F1] transition-colors"
        title="Knowledge Vault"
      >
        <VaultSeal className="w-6 h-6" />
      </Link>
      <div className="h-px w-6 bg-[#ECEAE3] mb-3" />
      <div className="flex-1 flex flex-col gap-1 w-full px-2 items-center">
        {ITEMS.map((item) => {
          const active = view === item.value;
          return (
            <button
              key={item.value}
              onClick={() => setView(item.value)}
              title={item.label}
              className={[
                'relative w-full flex flex-col items-center justify-center gap-1 rounded-md py-2 px-1 transition-colors',
                active
                  ? 'text-[#0C75FC] bg-[#0C75FC]/5'
                  : 'text-[#8A8F98] hover:text-[#151622] hover:bg-[#F4F2EC]',
              ].join(' ')}
            >
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[2px] rounded-r bg-[#0C75FC]" />
              )}
              <span className="text-lg leading-none">{item.icon}</span>
              <span className="text-[10px] font-medium leading-none">{item.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
