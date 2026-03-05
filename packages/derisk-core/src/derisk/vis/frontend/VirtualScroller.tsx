/**
 * 虚拟滚动容器组件
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';

interface VirtualScrollerProps {
  itemCount: number;
  itemHeight: number;
  containerHeight: number;
  renderItem: (index: number, style: React.CSSProperties) => React.ReactNode;
  overscan?: number;
}

export const VirtualScroller: React.FC<VirtualScrollerProps> = ({
  itemCount,
  itemHeight,
  containerHeight,
  renderItem,
  overscan = 5,
}) => {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // 计算可见范围
  const calculateVisibleRange = useCallback(() => {
    const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
    const visibleCount = Math.ceil(containerHeight / itemHeight);
    const endIndex = Math.min(itemCount, startIndex + visibleCount + overscan * 2);
    
    return { startIndex, endIndex };
  }, [scrollTop, itemHeight, containerHeight, itemCount, overscan]);
  
  const { startIndex, endIndex } = calculateVisibleRange();
  
  // 处理滚动
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);
  
  // 总高度
  const totalHeight = itemCount * itemHeight;
  
  // 偏移量
  const offsetY = startIndex * itemHeight;
  
  return (
    <div
      ref={containerRef}
      className="virtual-scroller"
      style={{
        height: containerHeight,
        overflow: 'auto',
        position: 'relative',
      }}
      onScroll={handleScroll}
    >
      {/* 占位元素 */}
      <div
        style={{
          height: totalHeight,
          position: 'relative',
        }}
      >
        {/* 可见元素 */}
        <div
          style={{
            position: 'absolute',
            top: offsetY,
            left: 0,
            right: 0,
          }}
        >
          {Array.from({ length: endIndex - startIndex }, (_, i) => {
            const index = startIndex + i;
            const style: React.CSSProperties = {
              height: itemHeight,
              position: 'absolute',
              top: i * itemHeight,
              left: 0,
              right: 0,
            };
            
            return renderItem(index, style);
          })}
        </div>
      </div>
    </div>
  );
};

export default VirtualScroller;