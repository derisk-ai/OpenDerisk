import { POST, GET } from '..';

export const createTrigger = (data: any) => POST('/api/v1/serve_trigger_service/triggers/create', data);
export const listTriggers = (data: any) => POST('/api/v1/serve_trigger_service/triggers/list', data);
export const getTriggerInfo = (trigger_id: number) => GET(`/api/v1/serve_trigger_service/triggers/info?trigger_id=${trigger_id}`);
export const updateTrigger = (data: any) => POST('/api/v1/serve_trigger_service/triggers/update', data);
export const deleteTrigger = (trigger_id: number) => POST(`/api/v1/serve_trigger_service/triggers/${trigger_id}/delete`, {});
export const fireTrigger = (data: any) => POST('/api/v1/serve_trigger_service/triggers/fire', data);
