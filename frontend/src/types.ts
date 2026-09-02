export * from "./types/chat";
export * from "./types/components";
export * from "./types/events";

export interface HealthResponse {
  status: string;
  service: string;
  protocol_version: "1";
  with_db: boolean;
  db_dialect: string;
  tools: string[];
  cache_status?: string | null;
  cache_table_count?: number;
}

export interface CacheSyncResponse {
  status: string;
  dialect: string;
  table_count: number;
  message: string;
}
