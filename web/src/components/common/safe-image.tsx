'use client';

import React, { useState } from 'react';

interface SafeImageProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  /** Fallback image URL to try if the primary src fails. */
  fallbackSrc?: string;
  /** Fallback ReactNode to render when both src and fallbackSrc fail or src is absent. */
  fallback?: React.ReactNode;
}

/**
 * SafeImage: img wrapper that gracefully handles load failures.
 *
 * - If src fails, tries fallbackSrc (once).
 * - If fallbackSrc also fails or is absent, renders fallback node.
 * - Prevents infinite retry loops by tracking failed URLs.
 */
const SafeImage: React.FC<SafeImageProps> = ({
  src,
  fallbackSrc,
  fallback,
  onError,
  ...rest
}) => {
  const [failedSrcs, setFailedSrcs] = useState<Set<string>>(new Set());

  const markFailed = (url: string) => {
    setFailedSrcs((prev) => new Set(prev).add(url));
  };

  const primaryUrl = typeof src === 'string' ? src : '';
  const fallbackUrl = typeof fallbackSrc === 'string' ? fallbackSrc : '';

  if (primaryUrl && !failedSrcs.has(primaryUrl)) {
    return (
      <img
        src={primaryUrl}
        onError={(e) => {
          markFailed(primaryUrl);
          onError?.(e);
        }}
        {...rest}
      />
    );
  }

  if (fallbackUrl && !failedSrcs.has(fallbackUrl)) {
    return (
      <img
        src={fallbackUrl}
        onError={(e) => {
          markFailed(fallbackUrl);
          onError?.(e);
        }}
        {...rest}
      />
    );
  }

  return fallback || null;
};

export default SafeImage;
