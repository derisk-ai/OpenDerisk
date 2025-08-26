import {
  AppListResponse,
  CreateAppParams,
  IAgent,
  IApp,
  NativeAppScenesResponse,
  StrategyResponse,
  TeamMode,
} from '@/types/app';
import { ConfigurableParams } from '@/types/common';
import { GET, POST } from '../index';
import { Key } from '@mui/icons-material';

/**
 * 查询team_mode模式
 */
export const getTeamMode = () => {
  return GET<null, TeamMode[]>('/api/v1/team-mode/list');
};
/**
 *  创建应用
 */
export const addApp = (data: CreateAppParams) => {
  return POST<CreateAppParams, IApp>('/api/v1/app/building/create', data);
};
/**
 *  更新应用
 */
export const updateApp = (data: CreateAppParams) => {
  return POST<CreateAppParams, IApp>('/api/v1/app/building/edit', data, {
    headers: {
      'Cache-Control': 'no-cache', // 添加清除缓存的头部
      Pragma: 'no-cache',
      Expires: '0',
    },
  });
};
/**
 *  应用列表
 */
export const getAppList = (data: Record<string, any>) => {
  return POST<Record<string, any>, AppListResponse>(
    `/api/v1/app/list?page=${data.page || 1}&page_size=${data.page_size || 12}`,
    data,
  );
};
/**
 *  获取创建应用agents
 */
export const getAgents = () => {
  return GET<object, IAgent[]>('/api/v1/agents/list', {});
};
/**
 *  创建auto_plan应用
 *  获取模型策略
 */
export const getAppStrategy = () => {
  return GET<null, StrategyResponse[]>(`/api/v1/llm-strategy/list`);
};
/**
 *  创建native_app应用
 *  获取资源参数
 */
export const getResource = (data: Record<string, string>) => {
  return GET<Record<string, string>, Record<string, any>[]>(`/api/v1/app/resources/list?type=${data.type}`);
};

export const getResourceV2 = (data: Record<string, string>) => {
  return GET<Record<string, string>, ConfigurableParams[]>(`/api/v1/app/resources/list?type=${data.type}&version=v2`);
};

/**
 *  创建native_app应用
 *  获取应用类型
 */
export const getNativeAppScenes = () => {
  return GET<null, NativeAppScenesResponse[]>('/api/v1/native_scenes');
};
/**
 *  创建native_app应用
 *  获取模型列表
 */
export const getAppStrategyValues = (type: string) => {
  return GET<string, string[]>(`/api/v1/llm-strategy/value/list?type=${type}`);
};

/**
 * 查询应用权限
 */
export const getAppAdmins = (appCode: string) => {
  return GET<null, string[]>(`/api/v1/app/${appCode}/admins`);
};
/**
 * 更新应用权限
 */
export const updateAppAdmins = (data: { app_code: string; admins: string[] }) => {
  return POST<{ app_code: string; admins: string[] }, null>(`/api/v1/app/admins/update`, data);
};

/**
 * 对话页面布局
 */
export const getChatLayout = () => {
  return GET<null, any>(`/api/v1/serve/building/config/chat/out/modes`);
};

/**
 * 对话配置
 */
export const getChatInputConfig = () => {
  return GET<null, any>(`/api/v1/serve/building/config/chat/in/params/all`);
};

/**
 * 对话配置
 */
export const getChatInputConfigParams = (data:[{
  param_type: string;
  sub_type?: string;
  param_default_value?: string | number;
  param_description?: string;
  [key: string]: any;
}]) => {
  return POST<[{
    param_type: string;
    sub_type?: string;
    param_default_value?: string | number;
    param_description?: string;
    [key: string]: any;
  }], any
  >(`/api/v1/serve/building/config/chat/in/params/render`,data);
};

/**
 * 版本信息
 */
export const getAppVersion = (data: Record<string, string>) => {
  return GET<null, any>(`/api/v1/serve/building/config/list?app_code=${data.app_code}&page=${1}&page_size=${100}`);
};
// /api/v1/serve/app/publish
export const publishAppNew = (data: Record<string, string>) => {
  return POST<Record<string, string>, any>(`/api/v1/serve/app/publish`, data);
};
