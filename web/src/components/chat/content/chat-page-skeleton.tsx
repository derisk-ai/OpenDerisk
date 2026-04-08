'use client';

import React, { memo } from 'react';

const ChatPageSkeleton: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center h-full w-full">
      <div className="flex flex-col items-center gap-3 animate-pulse">
        <div className="w-12 h-12 rounded-2xl bg-gray-300/40 dark:bg-gray-600/40" />
        <div className="h-3 w-24 bg-gray-300/30 dark:bg-gray-600/30 rounded" />
      </div>
    </div>
  );
};

export default memo(ChatPageSkeleton);
