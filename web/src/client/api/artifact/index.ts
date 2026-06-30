import { POST, GET } from '..';

export const createArtifact = (data: any) => POST('/api/v1/serve_artifact_service/artifacts/create', data);
export const listArtifacts = (data: any) => POST('/api/v1/serve_artifact_service/artifacts/list', data);
export const getArtifactInfo = (artifact_id: number) => GET(`/api/v1/serve_artifact_service/artifacts/info?artifact_id=${artifact_id}`);
export const updateArtifact = (data: any) => POST('/api/v1/serve_artifact_service/artifacts/update', data);
export const listArtifactVersions = (artifact_id: number) => GET(`/api/v1/serve_artifact_service/artifacts/${artifact_id}/versions`);
