'use client';

import { Empty } from 'antd';

export default function DeepResearchPanel() {
  return (
    <div className="flex flex-col items-center justify-center h-full p-4 text-center">
      <Empty description="Deep Research 即将上线" imageStyle={{ height: 40 }} />
      <p className="text-xs text-gray-400 mt-2">未来将支持多轮研究任务。</p>
    </div>
  );
}
