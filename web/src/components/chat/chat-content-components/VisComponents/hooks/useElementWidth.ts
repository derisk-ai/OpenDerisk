import { useState, useEffect } from 'react';

const POLL_INTERVAL = 100;
const MAX_ATTEMPTS = 50;

/**
 * 监听指定 DOM 元素的宽度变化，自动重试直到元素出现。
 */
export function useElementWidth(
  selector: string,
  fallbackSelector: string,
): number {
  const [width, setWidth] = useState<number>(0);

  useEffect(() => {
    if (!selector) return;

    let observer: ResizeObserver | null = null;
    let retryTimer: ReturnType<typeof setInterval> | null = null;
    let attempts = 0;

    const updateWidth = (): boolean => {
      const el =
        document.querySelector<HTMLElement>(selector) ||
        document.querySelector<HTMLElement>(fallbackSelector);
      if (el) {
        if (retryTimer) {
          clearInterval(retryTimer);
          retryTimer = null;
        }
        setWidth(el.getBoundingClientRect().width);
        observer = new ResizeObserver((entries) => {
          const newWidth = entries[0]?.contentRect?.width ?? 0;
          setWidth(newWidth);
        });
        observer.observe(el);
        return true;
      }
      return false;
    };

    if (!updateWidth()) {
      retryTimer = setInterval(() => {
        if (updateWidth() || ++attempts >= MAX_ATTEMPTS) {
          if (retryTimer) clearInterval(retryTimer);
        }
      }, POLL_INTERVAL);
    }

    return () => {
      observer?.disconnect();
      if (retryTimer) clearInterval(retryTimer);
    };
  }, [selector, fallbackSelector]);

  return width;
}
