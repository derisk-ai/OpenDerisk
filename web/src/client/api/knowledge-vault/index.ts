/**
 * API client for the new knowledge-vault backend.
 * Backend module: derisk_serve.knowledge (mounted at /api/v1/serve/knowledge).
 */

import { DELETE, GET, PATCH, POST, PUT } from '../index';
import type {
  CreateSpaceRequest,
  DocHit,
  DocMeta,
  DocRead,
  EdgeOut,
  IngestJobListResponse,
  LintResponse,
  RawFileCreateRequest,
  RawFileEditRequest,
  SchemaMdResponse,
  SearchRequest,
  SearchResponse,
  SpaceInfo,
  Subgraph,
  TreeNode,
  UpdateSpaceRequest,
  UploadResponse,
  VerbatFull,
  VerbatListResponse,
} from '@/types/knowledge-vault';

const BASE = '/api/v1/serve/knowledge';

// ----- spaces -----

export const listSpaces = () => GET<null, SpaceInfo[]>(`${BASE}/spaces`);

export const getSpace = (slug: string) =>
  GET<null, SpaceInfo>(`${BASE}/spaces/${slug}`);

export const createSpace = (req: CreateSpaceRequest) =>
  POST<CreateSpaceRequest, SpaceInfo>(`${BASE}/spaces`, req);

export const patchSpace = (slug: string, req: UpdateSpaceRequest) =>
  PATCH<UpdateSpaceRequest, SpaceInfo>(`${BASE}/spaces/${slug}`, req);

// ----- raw (L0) -----

export const getRawTree = (slug: string) =>
  GET<null, TreeNode[]>(`${BASE}/spaces/${slug}/raw/tree`);

export const readRawFile = (slug: string, path: string) =>
  GET<{ path: string }, { content: string }>(
    `${BASE}/spaces/${slug}/raw/files/read`,
    { path },
  );

export const createRawFile = (slug: string, req: RawFileCreateRequest) =>
  POST<RawFileCreateRequest, UploadResponse>(
    `${BASE}/spaces/${slug}/raw/files`,
    req,
  );

export const editRawFile = (slug: string, path: string, req: RawFileEditRequest) =>
  PUT<RawFileEditRequest, UploadResponse>(
    `${BASE}/spaces/${slug}/raw/files?path=${encodeURIComponent(path)}`,
    req,
  );

export const deleteRawFile = (slug: string, path: string) =>
  DELETE<null, { ok: boolean }>(
    `${BASE}/spaces/${slug}/raw/files?path=${encodeURIComponent(path)}`,
  );

export const listVerbats = (slug: string, limit = 100, offset = 0) =>
  GET<{ limit: number; offset: number }, VerbatListResponse>(
    `${BASE}/spaces/${slug}/verbats`,
    { limit, offset },
  );

export const getVerbat = (slug: string, verbatId: string) =>
  GET<null, VerbatFull>(`${BASE}/spaces/${slug}/verbats/${verbatId}`);

export const deleteVerbat = (slug: string, verbatId: string) =>
  DELETE<null, { ok: boolean }>(`${BASE}/spaces/${slug}/verbats/${verbatId}`);

// ----- file upload + ingest pipeline -----

export interface UploadFileParams {
  slug: string;
  file: File;
  extract_mode?: string;
  model_override?: string;
  agent_id_override?: string;
  llm_model_override?: string;
}

export const uploadFile = (params: UploadFileParams) => {
  const {
    slug,
    file,
    extract_mode = 'upload',
    model_override,
    agent_id_override,
    llm_model_override,
  } = params;
  const search = new URLSearchParams({ extract_mode });
  if (model_override) search.set('model_override', model_override);
  if (agent_id_override) search.set('agent_id_override', agent_id_override);
  if (llm_model_override) search.set('llm_model_override', llm_model_override);
  const formData = new FormData();
  formData.append('file', file);
  return POST<FormData, UploadResponse>(
    `${BASE}/spaces/${slug}/files?${search.toString()}`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
};

export const rebuildVerbatWiki = (slug: string, verbatId: string, llmModel?: string) => {
  const search = new URLSearchParams();
  if (llmModel) search.set('llm_model', llmModel);
  const q = search.toString();
  return POST<null, UploadResponse>(
    `${BASE}/spaces/${slug}/verbats/${verbatId}/rebuild-wiki${q ? `?${q}` : ''}`,
    null as any,
  );
};

export const rebuildAllWiki = (slug: string, llmModel?: string) => {
  const search = new URLSearchParams();
  if (llmModel) search.set('llm_model', llmModel);
  const q = search.toString();
  return POST<null, UploadResponse[]>(
    `${BASE}/spaces/${slug}/rebuild-wiki${q ? `?${q}` : ''}`,
    null as any,
  );
};

export const listIngestJobs = (slug: string, limit = 50) =>
  GET<{ limit: number }, IngestJobListResponse>(
    `${BASE}/spaces/${slug}/ingest-jobs`,
    { limit },
  );

// ----- wiki (L1) -----

export const getWikiTree = (slug: string) =>
  GET<null, TreeNode[]>(`${BASE}/spaces/${slug}/wiki/tree`);

export const listDocs = (slug: string, limit = 100, offset = 0) =>
  GET<{ limit: number; offset: number }, DocMeta[]>(
    `${BASE}/spaces/${slug}/docs`,
    { limit, offset },
  );

export const readDoc = (slug: string, path: string) =>
  GET<{ path: string }, DocRead>(`${BASE}/spaces/${slug}/docs/read`, { path });

export const searchSpace = (slug: string, req: SearchRequest) =>
  POST<SearchRequest, SearchResponse>(`${BASE}/spaces/${slug}/search`, req);

export const createDoc = (slug: string, path: string, content: string) =>
  POST<{ path: string; content: string }, { doc_id: string }>(
    `${BASE}/spaces/${slug}/docs`,
    { path, content },
  );

export const editDoc = (slug: string, path: string, content: string) =>
  PUT<{ content: string }, { path: string }>(
    `${BASE}/spaces/${slug}/docs?path=${encodeURIComponent(path)}`,
    { content },
  );

// ----- graph (L2) -----

export const getSpaceFullGraph = (slug: string, includeInvalid = false) =>
  GET<{ include_invalid: boolean }, Subgraph>(
    `${BASE}/spaces/${slug}/graph/full`,
    { include_invalid: includeInvalid },
  );

export const queryGraph = (
  slug: string,
  entity: string,
  predicate?: string,
  includeInvalid = false,
) =>
  GET<
    { entity: string; predicate?: string; include_invalid: boolean },
    Subgraph
  >(`${BASE}/spaces/${slug}/graph`, {
    entity,
    predicate,
    include_invalid: includeInvalid,
  });

export const traverseGraph = (slug: string, entity: string, hop = 2, mode = 'bfs') =>
  GET<{ entity: string; hop: number; mode: string }, Subgraph>(
    `${BASE}/spaces/${slug}/graph/traverse`,
    { entity, hop, mode },
  );

export const graphBacklinks = (slug: string, entity: string) =>
  GET<{ entity: string }, EdgeOut[]>(`${BASE}/spaces/${slug}/graph/backlinks`, {
    entity,
  });

// ----- schema.md -----

export const readSchemaMd = (slug: string) =>
  GET<null, SchemaMdResponse>(`${BASE}/spaces/${slug}/schema`);

export const writeSchemaMd = (slug: string, content: string) =>
  PUT<{ content: string }, { ok: boolean }>(
    `${BASE}/spaces/${slug}/schema`,
    { content },
  );

// ----- lint -----

export const lintSpace = (slug: string) =>
  GET<null, LintResponse>(`${BASE}/spaces/${slug}/lint`);

// ----- embedder identity -----

export const setEmbedderIdentity = (
  slug: string,
  body: { model_name: string; dimension: number; force_swap?: boolean },
) =>
  POST<{ model_name: string; dimension: number; force_swap?: boolean }, { ok: boolean }>(
    `${BASE}/spaces/${slug}/embedder-identity`,
    body,
  );
