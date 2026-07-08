'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { SmartPluginIcon } from '@/components/icons/smart-plugin-icon';

interface AgentAvatarProps {
  /** Agent icon URL. Empty values and the magic value `smart-plugin` are treated as unset. */
  icon?: string | null;
  /** Agent name, used for the initial-letter fallback and image alt text. */
  name?: string | null;
  /** Rendered size in pixels. */
  size?: number;
  /** Additional classes for the avatar container (e.g. rounded shapes, borders). */
  className?: string;
}

/** Legacy default images that should be treated as "no custom icon". */
const DEFAULT_AVATAR_PATHS = new Set([
  '/agents/default_avatar.png',
  '/agents/chat_avatar_default.png',
]);

const AVATAR_COLORS = [
  '#1677ff',
  '#00b96b',
  '#722ed1',
  '#eb2f96',
  '#fa8c16',
  '#13c2c2',
  '#2f54eb',
  '#52c41a',
  '#f5222d',
  '#faad14',
  '#9254de',
  '#08979c',
];

function hashCode(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function getAvatarColor(name: string): string {
  return AVATAR_COLORS[hashCode(name) % AVATAR_COLORS.length];
}

function getInitial(name: string): string {
  if (!name) return '?';
  const trimmed = name.trim();
  const first = trimmed[0];
  if (!first) return '?';
  // For CJK characters, take the first char directly
  if (first.charCodeAt(0) > 0x4e00) {
    return first;
  }
  // For ASCII, uppercase first letter
  return first.toUpperCase();
}

/**
 * Renders an agent icon with a system-style fallback:
 * 1. The provided icon URL.
 * 2. A colored circle with the agent's initial letter (matching the system avatar pattern).
 * 3. The SmartPlugin SVG icon if no name is available.
 */
export const AgentAvatar: React.FC<AgentAvatarProps> = ({
  icon,
  name,
  size = 36,
  className = '',
}) => {
  const [error, setError] = useState(false);

  useEffect(() => {
    setError(false);
  }, [icon]);

  const rawIcon = icon?.trim();
  const isDefaultOrEmpty =
    !rawIcon || rawIcon === 'smart-plugin' || DEFAULT_AVATAR_PATHS.has(rawIcon);

  const displayName = name || '';
  const initial = useMemo(() => getInitial(displayName), [displayName]);
  const bgColor = useMemo(() => getAvatarColor(displayName), [displayName]);

  if (isDefaultOrEmpty || error) {
    if (!displayName) {
      return (
        <div
          className={`flex items-center justify-center overflow-hidden ${className}`}
          style={{ width: size, height: size }}
        >
          <SmartPluginIcon size={Math.round(size * 0.75)} />
        </div>
      );
    }

    return (
      <div
        className={`flex items-center justify-center overflow-hidden text-white font-medium ${className}`}
        style={{
          width: size,
          height: size,
          backgroundColor: bgColor,
          fontSize: size * 0.45,
        }}
      >
        {initial}
      </div>
    );
  }

  return (
    <div
      className={`flex items-center justify-center overflow-hidden ${className}`}
      style={{ width: size, height: size }}
    >
      <img
        src={rawIcon}
        alt={name || 'Agent'}
        className="w-full h-full object-cover"
        onError={() => setError(true)}
      />
    </div>
  );
};

export default AgentAvatar;
