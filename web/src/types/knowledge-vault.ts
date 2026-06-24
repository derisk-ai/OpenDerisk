/**
 * Types for the new knowledge-vault frontend (three-layer model: L0/L1/L2).
 *
 * Backend: derisk_serve.knowledge HTTP API at /api/v1/serve/knowledge.
 */

export interface SpaceInfo {
  slug: string;
  root: string;
  backend?: 'local' | 'distributed' | null;
  // v2 ingest pipeline config (RFC 004 §6). All optional.
  default_agent_id?: string | null;
  llm_model?: string | null;
  multimodal_model?: string | null;
  embedder_model?: string | null;
}

export interface UpdateSpaceRequest {
  default_agent_id?: string | null;
  llm_model?: string | null;
  multimodal_model?: string | null;
  embedder_model?: string | null;
}

export interface CreateSpaceRequest {
  slug: string;
  backend?: 'local' | 'distributed' | null;
  default_agent_id?: string | null;
  llm_model?: string | null;
  multimodal_model?: string | null;
  embedder_model?: string | null;
}

export interface IngestJob {
  id: string;
  space_slug: string;
  source_file: string;
  verbat_ids: string[];
  wiki_doc_ids: string[];
  status: 'pending' | 'extracting' | 'embedding' | 'generating_wiki' | 'done' | 'failed';
  error?: string | null;
  started_at: string;
  finished_at?: string | null;
}

export interface IngestJobListResponse {
  items: IngestJob[];
}

export interface UploadResponse {
  job_id: string;
  verbat_ids: string[];
  wiki_doc_ids: string[];
}

export interface LintIssue {
  rule: 'orphan_doc' | 'broken_wikilink' | 'verbat_without_wiki' | string;
  severity: 'info' | 'warning' | 'error';
  path?: string | null;
  verbat_id?: string | null;
  edge_id?: string | null;
  message: string;
}

export interface LintResponse {
  issues: LintIssue[];
}

export interface TreeNode {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number | null;
  children?: TreeNode[] | null;
}

export interface DocMeta {
  id: string;
  path: string;
  type: string;
  title: string;
  status: string;
}

export interface DocRead {
  id: string;
  path: string;
  type: string;
  title: string;
  frontmatter: Record<string, unknown>;
  content: string;
  version: number;
}

export interface EdgeOut {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  valid_from?: string | null;
  valid_to?: string | null;
  source_document_id?: string | null;
  weight: number;
}

export interface Subgraph {
  nodes: string[];
  edges: EdgeOut[];
  root?: string | null;
}

export type ExtractMode = 'mine' | 'clip' | 'upload' | 'convo' | 'legacy_chunk';

export interface VerbatOut {
  id: string;
  source_file: string;
  extract_mode: ExtractMode;
  deprecated: boolean;
  content_preview?: string | null;
  content_date?: string | null;
  filed_at?: string | null;
}

export interface VerbatFull {
  id: string;
  source_file: string;
  extract_mode: ExtractMode;
  content: string;
  deprecated: boolean;
  filed_at?: string | null;
}

export interface VerbatListResponse {
  items: VerbatOut[];
}

export interface SchemaMdResponse {
  schema_md: string;
}

export interface RawFileCreateRequest {
  path: string;
  content: string;
}

export interface RawFileEditRequest {
  content: string;
}

export type DocSearchMode = 'documents' | 'semantic' | 'hybrid' | 'references';

export interface DocHit {
  document_id: string;
  path: string;
  title: string;
  type: string;
  score: number;
  snippet: string;
  verbats: string[];
}

export interface SearchRequest {
  query: string;
  mode: DocSearchMode;
  limit?: number;
}

export interface SearchResponse {
  hits: DocHit[];
  mode: DocSearchMode;
  total: number;
}
