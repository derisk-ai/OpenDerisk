'use client';

import { Avatar } from 'antd';
import type { AvatarProps } from 'antd';
import React, { useMemo } from 'react';

/**
 * Deterministic color palette for user avatars.
 * Each user gets a consistent color based on their name.
 */
const AVATAR_COLORS = [
  '#1677ff', // blue
  '#00b96b', // green
  '#722ed1', // purple
  '#eb2f96', // magenta
  '#fa8c16', // orange
  '#13c2c2', // cyan
  '#2f54eb', // geekblue
  '#52c41a', // lime
  '#f5222d', // red
  '#faad14', // gold
  '#9254de', // violet
  '#08979c', // teal
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
  // For CJK characters, take the first char directly
  const first = trimmed[0];
  if (first && first.charCodeAt(0) > 0x4e00) {
    return first;
  }
  // For ASCII, uppercase first letter
  return first?.toUpperCase() || '?';
}

export interface UserAvatarProps extends Omit<AvatarProps, 'src' | 'icon' | 'children'> {
  /** Avatar image URL. If falsy, shows initial letter. */
  avatarUrl?: string | null;
  /** User name — used for initial letter and color. */
  name?: string | null;
}

/**
 * UserAvatar: shows the user's avatar image, or a colored initial letter if no image.
 *
 * The background color is deterministic based on the username, so the same user
 * always gets the same color across sessions and components.
 */
const UserAvatar: React.FC<UserAvatarProps> = ({ avatarUrl, name, style, ...rest }) => {
  const displayName = name || '';
  const initial = useMemo(() => getInitial(displayName), [displayName]);
  const bgColor = useMemo(() => getAvatarColor(displayName), [displayName]);

  if (avatarUrl) {
    return <Avatar src={avatarUrl} style={style} {...rest} />;
  }

  return (
    <Avatar
      style={{
        backgroundColor: bgColor,
        color: '#fff',
        fontWeight: 500,
        fontSize: rest.size && typeof rest.size === 'number' ? rest.size * 0.45 : undefined,
        ...style,
      }}
      {...rest}
    >
      {initial}
    </Avatar>
  );
};

export default UserAvatar;
