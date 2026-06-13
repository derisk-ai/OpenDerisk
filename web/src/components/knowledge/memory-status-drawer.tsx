import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Tabs, Input, Button, Table, Empty, Spin, Tag, message } from 'antd';
import { SearchOutlined, SendOutlined, BarChartOutlined } from '@ant-design/icons';
import {
  apiInterceptors,
  getMemoryStatus,
  getMemoryWings,
  searchMemory,
  addMemory,
} from '@/client/api';

const { TextArea } = Input;

interface MemoryStatusDrawerProps {
  knowledgeId: string;
  spaceName: string;
}

type TabKey = 'overview' | 'search' | 'write';

// The /wings endpoint may return either a list ([{name,count}]) or a
// record ({wing: count}); normalise both into [name, count] pairs.
function normalizeWings(data: any): Array<[string, number]> {
  if (!data) return [];
  if (Array.isArray(data)) {
    return data.map((w) => [w?.name ?? '', Number(w?.count ?? 0)]);
  }
  return Object.entries(data).map(([k, v]) => [k, Number(v)]);
}

export default function MemoryStatusDrawer(props: MemoryStatusDrawerProps) {
  const { knowledgeId, spaceName } = props;
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  // Overview state
  const [statusData, setStatusData] = useState<Record<string, any> | null>(null);
  const [wingsData, setWingsData] = useState<any>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Array<{ id: string; content: string; wing: string; room: string; score: number; created_at: string }>>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Write state
  const [writeContent, setWriteContent] = useState('');
  const [writeWing, setWriteWing] = useState('default');
  const [writeRoom, setWriteRoom] = useState('general');
  const [writeLoading, setWriteLoading] = useState(false);

  const loadStatus = async () => {
    setLoadingStatus(true);
    const [statusErr, statusData] = await apiInterceptors(getMemoryStatus(knowledgeId));
    if (!statusErr) setStatusData(statusData as any);
    const [wingsErr, wingsData] = await apiInterceptors(getMemoryWings(knowledgeId));
    if (!wingsErr) setWingsData(wingsData as any);
    setLoadingStatus(false);
  };

  // Auto-load the overview when the drawer mounts (it is re-created on each
  // open via destroyOnHidden, so this fires every time it is shown).
  useEffect(() => {
    loadStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [knowledgeId]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    const [err, data] = await apiInterceptors(
      searchMemory(knowledgeId, { query: searchQuery, top_k: 10 }),
    );
    setSearchLoading(false);
    if (!err) setSearchResults(data || []);
  };

  const handleWrite = async () => {
    if (!writeContent.trim()) return;
    setWriteLoading(true);
    const [err, data] = await apiInterceptors(
      addMemory(knowledgeId, { content: writeContent, wing: writeWing, room: writeRoom }),
    );
    setWriteLoading(false);
    if (!err && data) {
      message.success(t('Memory_Write_Success'));
      setWriteContent('');
      loadStatus();
    }
  };

  const handleTabChange = (key: string) => {
    setActiveTab(key as TabKey);
    if (key === 'overview') loadStatus();
  };

  const memoryColumns = [
    {
      title: t('Memory_Content'),
      dataIndex: 'content',
      key: 'content',
      render: (text: string) => (
        <div className="max-w-[400px] truncate" title={text}>
          {text}
        </div>
      ),
    },
    {
      title: t('Wing'),
      dataIndex: 'wing',
      key: 'wing',
      width: 100,
      render: (text: string) => <Tag color="blue">{text}</Tag>,
    },
    {
      title: t('Room'),
      dataIndex: 'room',
      key: 'room',
      width: 100,
      render: (text: string) => <Tag color="green">{text}</Tag>,
    },
    {
      title: t('Score'),
      dataIndex: 'score',
      key: 'score',
      width: 90,
      render: (score: number) => <span className="font-mono">{score?.toFixed(3)}</span>,
    },
  ];

  const wingPairs = normalizeWings(wingsData);

  const tabItems = [
    {
      key: 'overview',
      label: (
        <span className="flex items-center gap-1">
          <BarChartOutlined /> {t('Memory_Overview')}
        </span>
      ),
      children: (
        <div className="space-y-4">
          <Spin spinning={loadingStatus}>
            <div className="grid grid-cols-2 gap-4">
              <StatCard
                label={t('Total_Entries')}
                value={statusData?.total_entries ?? '-'}
              />
              <StatCard
                label={t('Wings')}
                value={wingPairs.length || '-'}
              />
            </div>
            {wingPairs.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                  {t('Wings')}
                </h4>
                <div className="flex flex-wrap gap-2">
                  {wingPairs.map(([wing, count]) => (
                    <Tag key={wing} color="blue" className="px-3 py-1 text-sm">
                      {wing}: {count}
                    </Tag>
                  ))}
                </div>
              </div>
            )}
            {(statusData?.total_entries ?? 0) === 0 && !loadingStatus && (
              <Empty description={t('Memory_Store_Empty')} />
            )}
          </Spin>
        </div>
      ),
    },
    {
      key: 'search',
      label: (
        <span className="flex items-center gap-1">
          <SearchOutlined /> {t('Memory_Search')}
        </span>
      ),
      children: (
        <div className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder={t('Search_Memory')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onPressEnter={handleSearch}
              prefix={<SearchOutlined />}
              className="flex-1"
            />
            <Button type="primary" onClick={handleSearch} loading={searchLoading}>
              {t('Search')}
            </Button>
          </div>
          <Spin spinning={searchLoading}>
            {searchResults.length > 0 ? (
              <Table
                columns={memoryColumns}
                dataSource={searchResults}
                rowKey="id"
                pagination={false}
                size="small"
              />
            ) : (
              <Empty description={searchQuery ? t('No_Memory_Found') : ''} />
            )}
          </Spin>
        </div>
      ),
    },
    {
      key: 'write',
      label: (
        <span className="flex items-center gap-1">
          <SendOutlined /> {t('Memory_Write')}
        </span>
      ),
      children: (
        <div className="space-y-4">
          <TextArea
            placeholder={t('Memory_Content_Placeholder')}
            value={writeContent}
            onChange={(e) => setWriteContent(e.target.value)}
            rows={4}
            maxLength={2000}
            showCount
          />
          <div className="flex gap-2">
            <Input
              placeholder={t('Wing')}
              value={writeWing}
              onChange={(e) => setWriteWing(e.target.value)}
              className="w-32"
            />
            <Input
              placeholder={t('Room')}
              value={writeRoom}
              onChange={(e) => setWriteRoom(e.target.value)}
              className="w-32"
            />
            <Button
              type="primary"
              onClick={handleWrite}
              loading={writeLoading}
              disabled={!writeContent.trim()}
              className="ml-auto"
            >
              {t('Memory_Write')}
            </Button>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="memory-drawer">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-500 flex items-center justify-center">
          <span className="text-white text-sm font-bold">M</span>
        </div>
        <div>
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200">{spaceName}</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">Memory Store</p>
        </div>
      </div>
      <Tabs activeKey={activeTab} onChange={handleTabChange} items={tabItems} />
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
      <div className="text-2xl font-bold text-gray-800 dark:text-gray-200">{value}</div>
      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">{label}</div>
    </div>
  );
}
