import { DELETE, GET, POST, PUT } from '../index';

// Types
export interface ChannelConfig {
  id?: string;
  name: string;
  channel_type: 'dingtalk' | 'feishu' | 'wechat' | 'qq';
  enabled: boolean;
  config: Record<string, any>;
}

export interface ChannelResponse extends ChannelConfig {
  id: string;
  status: string;
  last_connected?: string;
  last_error?: string;
  gmt_created?: string;
  gmt_modified?: string;
}

export interface ChannelTestResponse {
  success: boolean;
  message: string;
  details?: Record<string, any>;
}

// API endpoints
const API_PREFIX = '/api/v1/serve/channel';

/**
 * Get all channels
 */
export const getChannels = (includeDisabled = false) => {
  return GET<{ include_disabled: boolean }, ChannelResponse[]>(`${API_PREFIX}/channels`, {
    include_disabled: includeDisabled,
  });
};

/**
 * Get a specific channel
 */
export const getChannel = (channelId: string) => {
  return GET<{}, ChannelResponse>(`${API_PREFIX}/channels/${channelId}`);
};

/**
 * Create a new channel
 */
export const createChannel = (data: ChannelConfig) => {
  return POST<ChannelConfig, ChannelResponse>(`${API_PREFIX}/channels`, data);
};

/**
 * Update a channel
 */
export const updateChannel = (channelId: string, data: ChannelConfig) => {
  return PUT<ChannelConfig, ChannelResponse>(`${API_PREFIX}/channels/${channelId}`, data);
};

/**
 * Delete a channel
 */
export const deleteChannel = (channelId: string) => {
  return DELETE<{}, null>(`${API_PREFIX}/channels/${channelId}`);
};

/**
 * Test channel connection
 */
export const testChannel = (channelId: string) => {
  return POST<{}, ChannelTestResponse>(`${API_PREFIX}/channels/${channelId}/test`);
};

/**
 * Enable a channel
 */
export const enableChannel = (channelId: string) => {
  return POST<{}, { enabled: boolean; channel_id: string }>(
    `${API_PREFIX}/channels/${channelId}/enable`
  );
};

/**
 * Disable a channel
 */
export const disableChannel = (channelId: string) => {
  return POST<{}, { enabled: boolean; channel_id: string }>(
    `${API_PREFIX}/channels/${channelId}/disable`
  );
};