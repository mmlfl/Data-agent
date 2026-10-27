import type { ChartSpec, ChartType, DataFrameComponent } from "../../types";

const identifier = (name: string) => /(^|_)(id|code|uuid|phone|mobile|no)$|编号|编码|证件|电话|手机/i.test(name);
export const measureFields = (data: DataFrameComponent) => data.columns.filter(column => column.data_type === "number" && !identifier(column.name));
export const numericFields = (data: DataFrameComponent) => measureFields(data).filter(column => column.numeric_encoding !== "exact_string");
export function availableChartTypes(data: DataFrameComponent, spec: ChartSpec): Exclude<ChartType, "none">[] {
  if (data.rows.length < 2 || !spec.x_field || !spec.y_fields.length) return [];
  const x = data.columns.find(column => column.name === spec.x_field);
  if (!x || x.numeric_encoding === "exact_string" || !spec.y_fields.every(field => numericFields(data).some(column => column.name === field))) return [];
  if (x.data_type === "number") return spec.y_fields.some(field => field !== x.name) ? ["scatter"] : [];
  const dimension = new Set(data.rows.map(row => String(row[x.name])));
  if (dimension.size < 2 && (!spec.series_field || new Set(data.rows.map(row => String(row[spec.series_field!]))).size < 2)) return [];
  const temporal = x.data_type === "datetime" || data.rows.every(row => /^\d{4}[-/]\d{1,2}([-/]\d{1,2})?/.test(String(row[x.name])));
  const result: Exclude<ChartType, "none">[] = temporal ? ["line", "bar", "area"] : ["bar"];
  const nonnegative = data.rows.every(row => spec.y_fields.every(field => row[field] != null && Number(row[field]) >= 0));
  if (!temporal && dimension.size <= 8 && spec.y_fields.length === 1 && !spec.series_field && nonnegative && data.rows.some(row => Number(row[spec.y_fields[0]]) > 0)) result.push("pie");
  return result;
}

export function recommendChart(data: DataFrameComponent): ChartSpec {
  if (data.rows.length < 2) return { type: "none", y_fields: [], reason: data.rows.length ? "单条结果优先以指标和表格展示。" : "没有返回数据，无需绘图。" };
  const numeric = numericFields(data);
  const dimensions = data.columns.filter(column => ["datetime", "string", "boolean"].includes(column.data_type) && !identifier(column.name));
  for (const x of dimensions) {
    const categories = new Set(data.rows.map(row => String(row[x.name])));
    if (categories.size !== data.rows.length || categories.size > 30) continue;
    const spec: ChartSpec = { type: "bar", x_field: x.name, y_fields: numeric.slice(0, 1).map(column => column.name), aggregation: "none", reason: "按当前结果的维度和数值推荐，可手动调整。" };
    const available = availableChartTypes(data, spec);
    if (available.length) return { ...spec, type: available[0] };
  }
  return { type: "none", y_fields: [], reason: "当前是明细或分组口径尚未明确，优先查看数据表；需要时可手动选择字段和聚合方式。" };
}
