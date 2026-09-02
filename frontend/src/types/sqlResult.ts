export interface SqlResultData {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  sql?: string;
  truncated?: boolean;
}
