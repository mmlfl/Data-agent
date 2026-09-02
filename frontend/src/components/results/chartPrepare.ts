import type {
  ChartAggregation,
  ChartSpec,
  ChartType,
} from "../../types";

export interface PreparedSeries {
  rows: Record<string, unknown>[];
  keys: { key: string; label: string }[];
  aggregated: boolean;
  duplicateGroups: number;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function aggregateValues(
  values: number[],
  aggregation: ChartAggregation,
): number | null {
  if (aggregation === "count") return values.length;
  if (values.length === 0) return null;
  switch (aggregation) {
    case "sum":
      return values.reduce((sum, value) => sum + value, 0);
    case "avg":
      return values.reduce((sum, value) => sum + value, 0) / values.length;
    case "min":
      return Math.min(...values);
    case "max":
      return Math.max(...values);
    default:
      return values[values.length - 1] ?? null;
  }
}

function resolveAggregation(
  spec: ChartSpec,
  hasDuplicates: boolean,
): ChartAggregation {
  const requested = spec.aggregation ?? "none";
  if (requested !== "none") return requested;
  return hasDuplicates ? "sum" : "none";
}

function aggregateByX(
  rows: Record<string, unknown>[],
  spec: ChartSpec,
): PreparedSeries {
  const xField = spec.x_field!;
  const buckets = new Map<
    string,
    { xValue: unknown; values: Record<string, number[]> }
  >();
  let duplicateGroups = 0;

  for (const row of rows) {
    const mapKey = String(row[xField]);
    const existing = buckets.get(mapKey);
    if (existing) duplicateGroups += 1;
    const bucket = existing ?? {
      xValue: row[xField],
      values: Object.fromEntries(spec.y_fields.map((field) => [field, []] as const)),
    };
    for (const yField of spec.y_fields) {
      const numeric = toNumber(row[yField]);
      if (numeric != null) bucket.values[yField].push(numeric);
    }
    buckets.set(mapKey, bucket);
  }

  const aggregation = resolveAggregation(spec, duplicateGroups > 0);
  const aggregatedRows = Array.from(buckets.values()).map((bucket) => {
    const next: Record<string, unknown> = { [xField]: bucket.xValue };
    for (const yField of spec.y_fields) {
      next[yField] = aggregateValues(bucket.values[yField], aggregation);
    }
    return next;
  });

  return {
    rows: aggregatedRows,
    keys: spec.y_fields.map((field) => ({ key: field, label: field })),
    aggregated: aggregation !== "none" && duplicateGroups > 0,
    duplicateGroups,
  };
}

export function prepareSeries(
  rows: Record<string, unknown>[],
  spec: ChartSpec,
  chartType?: Exclude<ChartType, "none">,
): PreparedSeries {
  if (!spec.x_field) {
    return {
      rows,
      keys: spec.y_fields.map((field) => ({ key: field, label: field })),
      aggregated: false,
      duplicateGroups: 0,
    };
  }

  if (chartType === "scatter") {
    return {
      rows,
      keys: spec.y_fields.map((field) => ({ key: field, label: field })),
      aggregated: false,
      duplicateGroups: 0,
    };
  }

  if (!spec.series_field || chartType === "pie") {
    return aggregateByX(rows, spec);
  }

  const xField = spec.x_field;
  const seriesField = spec.series_field;
  const seriesValues = Array.from(
    new Set(rows.map((row) => String(row[seriesField] ?? "未分类"))),
  ).slice(0, 8);

  type Bucket = {
    xValue: unknown;
    values: Record<string, number[]>;
  };
  const byX = new Map<string, Bucket>();
  let duplicateGroups = 0;

  for (const row of rows) {
    const mapKey = String(row[xField]);
    const series = String(row[seriesField] ?? "未分类");
    if (!seriesValues.includes(series)) continue;

    const bucket = byX.get(mapKey) ?? {
      xValue: row[xField],
      values: {},
    };
    for (const yField of spec.y_fields) {
      const cellKey = `${yField}::${series}`;
      const numeric = toNumber(row[yField]);
      const list = bucket.values[cellKey] ?? [];
      if (list.length > 0) duplicateGroups += 1;
      if (numeric != null) list.push(numeric);
      bucket.values[cellKey] = list;
    }
    byX.set(mapKey, bucket);
  }

  const aggregation = resolveAggregation(spec, duplicateGroups > 0);
  const preparedRows = Array.from(byX.values()).map((bucket) => {
    const next: Record<string, unknown> = { [xField]: bucket.xValue };
    for (const [key, values] of Object.entries(bucket.values)) {
      next[key] = aggregateValues(values, aggregation);
    }
    return next;
  });

  return {
    rows: preparedRows,
    keys: spec.y_fields.flatMap((field) =>
      seriesValues.map((series) => ({
        key: `${field}::${series}`,
        label: spec.y_fields.length === 1 ? series : `${field} · ${series}`,
      })),
    ),
    aggregated: aggregation !== "none" && duplicateGroups > 0,
    duplicateGroups,
  };
}
