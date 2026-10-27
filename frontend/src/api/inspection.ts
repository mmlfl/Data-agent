import { readCache } from "./metadata";

export interface InspectionCheck {
  label: string;
  ok: boolean;
  detail: string;
}

export interface CacheCheck {
  status: string;
  message: string;
  cache_file: string;
  checks: InspectionCheck[];
}

export interface MilvusDocument {
  record_id: string;
  schema_name: string;
  table_name: string;
  column_count: number;
  content_hash: string;
  active: boolean;
  updated_at: string | null;
  comparison: string;
}

export interface StoredMilvusDocument extends MilvusDocument {
  document_text: string;
  database_name: string;
  dialect: string;
  content_hash_valid: boolean;
}

export interface MilvusInspection {
  status: string;
  message: string;
  connected: boolean;
  rag_enabled: boolean;
  collection: string;
  milvus_database: string;
  database_id: string;
  tenant_id: string;
  collection_exists: boolean | null;
  load_state: string;
  can_browse: boolean;
  document_count: number | null;
  active_count: number | null;
  vector_dimensions: number | null;
  embedding_profile: string | null;
  configured_embedding_profile: string;
  bm25: boolean;
  issues: string[];
  indexes: { name: string; field: string; metric: string; type: string }[];
  matched_total: number;
  browse_total: number;
  truncated: boolean;
  scan_limit: number;
  offset: number;
  limit: number;
  documents: MilvusDocument[];
  checked_at: string;
}

export interface MilvusComparison {
  complete: boolean;
  consistent: boolean;
  scanned: number;
  sqlite_tables: number;
  matching: number;
  stale: number;
  sqlite_missing: number;
  sqlite_incomplete: number;
  inactive: number;
  identity_mismatch: number;
  duplicate_tables: number;
  milvus_missing: number | null;
}

export function checkSqlite(signal?: AbortSignal) {
  return readCache<CacheCheck>("/api/cache/check", signal);
}

export function getMilvusDocuments(q: string, offset: number, signal?: AbortSignal) {
  const query = new URLSearchParams({ q, offset: String(offset), limit: "30" });
  return readCache<MilvusInspection>(`/api/milvus/documents?${query}`, signal);
}

export function getMilvusDocument(recordId: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ record_id: recordId });
  return readCache<MilvusInspection & { document: StoredMilvusDocument | null }>(`/api/milvus/document?${query}`, signal);
}

export function checkMilvus(signal?: AbortSignal) {
  return readCache<MilvusInspection & { comparison: MilvusComparison | null }>("/api/milvus/check", signal);
}
