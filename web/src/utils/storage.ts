import { STORAGE_INIT_MESSAGE_KET, STORAGE_USERINFO_KEY } from './constants/storage';

export interface InitMessage {
  id: string;
  message: string;
  model?: string;
  resource?: any;
  resources?: any[];
  skills?: { skill_code: string; name: string; description?: string; type?: string; icon?: string; author?: string; version?: string; }[];
  mcps?: { id?: string; uuid?: string; name: string; description?: string; icon?: string; }[];
}

export function getInitMessage(): InitMessage | null {
  const value = localStorage.getItem(STORAGE_INIT_MESSAGE_KET) ?? '';
  try {
    const initData = JSON.parse(value) as InitMessage;
    return initData;
  } catch {
    return null;
  }
}

export function getUserId(): string | undefined {
  try {
    const id = JSON.parse(localStorage.getItem(STORAGE_USERINFO_KEY) ?? '')['user_id'];
    return id;
  } catch {
    return undefined;
  }
}
