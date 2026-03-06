import { POST, GET } from '..';

export const getSkillList = (data?: any, other?: any) => {
  return POST(`/api/v1/serve_skill_service/query_fuzzy?page=${other.page}&page_size=${other.page_size}`, data);
};

export const createSkill = (data: any) => {
  return POST('/api/v1/serve_skill_service/create', data);
};

export const updateSkill = (data: any) => {
  return POST('/api/v1/serve_skill_service/update', data);
};

export const deleteSkill = (data: any) => {
  return POST('/api/v1/serve_skill_service/delete', data);
};

export const syncSkillFromGit = (repo_url: string, branch: string = 'main', force_update: boolean = false) => {
  return POST(`/api/v1/serve_skill_service/sync_git?repo_url=${encodeURIComponent(repo_url)}&branch=${branch}&force_update=${force_update}`);
};

// Async sync task APIs
export const createSyncTask = (data: {
  repo_url: string;
  branch?: string;
  force_update?: boolean;
}) => {
  return POST('/api/v1/serve_skill_service/sync_git_async', data);
};

export const getSyncTaskStatus = (taskId: string) => {
  return GET(`/api/v1/serve_skill_service/sync_status/${taskId}`);
};

export const getRecentSyncTasks = (limit: number = 10) => {
  return GET(`/api/v1/serve_skill_service/recent_sync_tasks?limit=${limit}`);
};

export const uploadSkillFromZip = (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return POST('/api/v1/serve_skill_service/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

export const uploadSkillFromFolder = (skill_name: string, skill_path: string) => {
  const formData = new FormData();
  formData.append('skill_name', skill_name);
  formData.append('skill_path', skill_path);
  return POST(`/api/v1/serve_skill_service/upload_folder?skill_name=${encodeURIComponent(skill_name)}&skill_path=${encodeURIComponent(skill_path)}`, formData);
};

export const getSkillDetail = (data: any) => {
  return POST('/api/v1/serve_skill_service/query', data);
};

// File operation APIs
export const listSkillFiles = (skill_code: string) => {
  return GET(`/api/v1/serve_skill_service/file/list/${skill_code}`);
};

export const readSkillFile = (skill_code: string, file_path: string) => {
  return POST('/api/v1/serve_skill_service/file/read', {
    skill_code,
    file_path,
  });
};

export const writeSkillFile = (skill_code: string, file_path: string, content: string) => {
  return POST('/api/v1/serve_skill_service/file/write', {
    skill_code,
    file_path,
    content,
  });
};

export const createSkillFile = (skill_code: string, file_path: string, content: string = '') => {
  return POST('/api/v1/serve_skill_service/file/create', {
    skill_code,
    file_path,
    content,
  });
};

export const deleteSkillFile = (skill_code: string, file_path: string) => {
  return POST('/api/v1/serve_skill_service/file/delete', {
    skill_code,
    file_path,
  });
};

export const renameSkillFile = (skill_code: string, old_path: string, new_path: string) => {
  return POST('/api/v1/serve_skill_service/file/rename', {
    skill_code,
    old_path,
    new_path,
  });
};

export const batchUploadSkillFiles = (skill_code: string, files: { file_path: string; content: string; is_base64?: boolean }[], overwrite?: boolean) => {
  return POST('/api/v1/serve_skill_service/file/upload_batch', {
    skill_code,
    files,
    overwrite,
  });
};
