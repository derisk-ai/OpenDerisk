import { POST, GET } from '..';

export const createPlaybook = (data: any) => POST('/api/v1/serve_playbook_service/playbooks/create', data);
export const listPlaybooks = (data: any) => POST('/api/v1/serve_playbook_service/playbooks/list', data);
export const getPlaybookInfo = (playbook_id: number) => GET(`/api/v1/serve_playbook_service/playbooks/info?playbook_id=${playbook_id}`);
export const updatePlaybook = (data: any) => POST('/api/v1/serve_playbook_service/playbooks/update', data);
export const deletePlaybook = (playbook_id: number) => POST(`/api/v1/serve_playbook_service/playbooks/${playbook_id}/delete`, {});
export const validatePlaybook = (data: any) => POST('/api/v1/serve_playbook_service/playbooks/validate', data);
export const listPlaybookVersions = (playbook_id: number) => POST(`/api/v1/serve_playbook_service/playbooks/${playbook_id}/versions`, {});
export const seedBuiltinPlaybooks = (workspace_id: number) => POST(`/api/v1/serve_playbook_service/playbooks/seed_builtin?workspace_id=${workspace_id}`, {});
