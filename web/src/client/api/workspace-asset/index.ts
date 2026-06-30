import { POST, GET } from '..';

export const createAsset = (data: any) => POST('/api/v1/serve_workspace_asset_service/assets/create', data);
export const listAssets = (data: any) => POST('/api/v1/serve_workspace_asset_service/assets/list', data);
export const getAssetInfo = (asset_id: number) => GET(`/api/v1/serve_workspace_asset_service/assets/info?asset_id=${asset_id}`);
export const updateAsset = (data: any) => POST('/api/v1/serve_workspace_asset_service/assets/update', data);
export const searchAssets = (data: any) => POST('/api/v1/serve_workspace_asset_service/assets/search', data);
export const listAssetVersions = (asset_id: number) => GET(`/api/v1/serve_workspace_asset_service/assets/${asset_id}/versions`);
export const linkAssetToTask = (data: any) => POST('/api/v1/serve_workspace_asset_service/assets/link_task', data);
export const listTaskAssetLinks = (task_id: number) => GET(`/api/v1/serve_workspace_asset_service/assets/task_links?task_id=${task_id}`);
