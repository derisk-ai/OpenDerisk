'use client';

import { useRef, useState } from 'react';
import VerticalNav from './VerticalNav';

const LEFT_WIDTH_KEY = 'kv_left_width';
const RIGHT_WIDTH_KEY = 'kv_right_width';

export default function SpaceLayout({
  left,
  center,
  right,
}: {
  left: React.ReactNode;
  center: React.ReactNode;
  right: React.ReactNode;
}) {
  const [leftWidth, setLeftWidth] = useState<number>(() => {
    const s = typeof window !== 'undefined' ? localStorage.getItem(LEFT_WIDTH_KEY) : null;
    return s ? Number(s) : 260;
  });
  const [rightWidth, setRightWidth] = useState<number>(() => {
    const s = typeof window !== 'undefined' ? localStorage.getItem(RIGHT_WIDTH_KEY) : null;
    return s ? Number(s) : 320;
  });

  const dragState = useRef<{ pane: 'left' | 'right' | null; startX: number; startW: number }>({
    pane: null,
    startX: 0,
    startW: 0,
  });

  function startDrag(pane: 'left' | 'right', e: React.MouseEvent) {
    e.preventDefault();
    dragState.current = {
      pane,
      startX: e.clientX,
      startW: pane === 'left' ? leftWidth : rightWidth,
    };
    document.body.setAttribute('data-panel-resizing', 'true');
    window.addEventListener('mousemove', onDrag);
    window.addEventListener('mouseup', stopDrag);
  }

  function onDrag(e: MouseEvent) {
    const st = dragState.current;
    if (!st.pane) return;
    const delta = e.clientX - st.startX;
    if (st.pane === 'left') {
      const next = Math.max(200, Math.min(400, st.startW + delta));
      setLeftWidth(next);
    } else {
      const next = Math.max(240, Math.min(480, st.startW - delta));
      setRightWidth(next);
    }
  }

  function stopDrag() {
    if (dragState.current.pane === 'left') {
      localStorage.setItem(LEFT_WIDTH_KEY, String(leftWidth));
    } else if (dragState.current.pane === 'right') {
      localStorage.setItem(RIGHT_WIDTH_KEY, String(rightWidth));
    }
    dragState.current.pane = null;
    document.body.removeAttribute('data-panel-resizing');
    window.removeEventListener('mousemove', onDrag);
    window.removeEventListener('mouseup', stopDrag);
  }

  return (
    <div className="flex h-full w-full bg-gray-50 overflow-hidden">
      <VerticalNav />
      <div
        className="flex-shrink-0 bg-white border-r border-gray-200 overflow-hidden flex flex-col"
        style={{ width: leftWidth }}
      >
        {left}
      </div>
      <div
        onMouseDown={(e) => startDrag('left', e)}
        className="w-1 cursor-col-resize bg-gray-200 hover:bg-violet-300 transition-colors flex-shrink-0"
      />
      <div className="flex-1 min-w-0 min-h-0 overflow-hidden flex flex-col">{center}</div>
      <div
        onMouseDown={(e) => startDrag('right', e)}
        className="w-1 cursor-col-resize bg-gray-200 hover:bg-violet-300 transition-colors flex-shrink-0"
      />
      <div
        className="flex-shrink-0 bg-white border-l border-gray-200 overflow-hidden flex flex-col"
        style={{ width: rightWidth }}
      >
        {right}
      </div>
    </div>
  );
}
