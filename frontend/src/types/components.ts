export type ColumnDataType =
  | "number"
  | "datetime"
  | "boolean"
  | "string"
  | "unknown";

export interface DataColumn {
  name: string;
  data_type: ColumnDataType;
}

export interface DataFrameComponent {
  type: "dataframe";
  title: string;
  columns: DataColumn[];
  rows: Record<string, unknown>[];
  row_count: number;
  row_count_is_exact: boolean;
  displayed_row_count: number;
  truncated: boolean;
  sql: string;
}

export interface TableInfo {
  table_name: string;
  schema_name?: string | null;
  table_comment?: string | null;
}

export interface TableListComponent {
  type: "table_list";
  title: string;
  keyword: string;
  tables: TableInfo[];
}

export interface SchemaColumn {
  column_name: string;
  data_type?: string | null;
  is_nullable?: string | null;
  data_length?: number | null;
  column_comment?: string | null;
}

export interface TableSchemaComponent {
  type: "table_schema";
  title: string;
  table_name: string;
  columns: SchemaColumn[];
}

export type ChartType = "bar" | "line" | "area" | "pie" | "scatter" | "none";
export type ChartAggregation = "none" | "sum" | "avg" | "min" | "max" | "count";

export interface ChartSpec {
  type: ChartType;
  title?: string | null;
  x_field?: string | null;
  y_fields: string[];
  series_field?: string | null;
  aggregation?: ChartAggregation;
  reason?: string | null;
}

export interface FinalResultComponent {
  type: "final_result";
  source_tool_call_id: string;
  title: string;
  summary: string;
  insights: string[];
  chart: ChartSpec;
  warnings: string[];
}

export type UiComponent =
  | DataFrameComponent
  | TableListComponent
  | TableSchemaComponent
  | FinalResultComponent;
