import { useState, useEffect } from 'react';

const POLL_INTERVAL = 100;
const MAX_ATTEMPTS = 50;

/**
 * 监听指定 DOM 元素的高度变化，自动重试直到元素出现。
 */
export function useElementHeight(
  selector: string,
  fallbackSelector: string,
): number {
  const [height, setHeight] = useState<number>(0);

  useEffect(() => {
    if (!selector) return;

    let observer: ResizeObserver | null = null;
    let retryTimer: ReturnType<typeof setInterval> | null = null;
    let attempts = 0;

    const updateHeight = (): boolean => {
      const el =
        document.querySelector<HTMLElement>(selector) ||
        document.querySelector<HTMLElement>(fallbackSelector);
      if (el) {
        if (retryTimer) {
          clearInterval(retryTimer);
          retryTimer = null;
        }
        setHeight(el.getBoundingClientRect().height);
        observer = new ResizeObserver((entries) => {
          const newHeight = entries[0]?.contentRect?.height ?? 0;
          setHeight(newHeight);
        });
        observer.observe(el);
        return true;
      }
      return false;
    };

    if (!updateHeight()) {
      retryTimer = setInterval(() => {
        if (updateHeight() || ++attempts >= MAX_ATTEMPTS) {
          if (retryTimer) clearInterval(retryTimer);
        }
      }, POLL_INTERVAL);
    }

    return () => {
      observer?.disconnect();
      if (retryTimer) clearInterval(retryTimer);
    };
  }, [selector, fallbackSelector]);

  return height;
}
