import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  ChartSpec,
  ChartType,
  DataFrameComponent,
} from "../../types";
import { prepareSeries } from "./chartPrepare";

const CHART_COLORS = ["#137c7e", "#315fca", "#d08a2e", "#7956a8", "#4c8f5c"];
const MAX_CHART_ROWS = 100;

const CHART_LABELS: Record<Exclude<ChartType, "none">, string> = {
  bar: "柱状",
  line: "折线",
  area: "面积",
  pie: "饼图",
  scatter: "散点",
};

export function availableChartTypes(
  data: DataFrameComponent,
  spec: ChartSpec,
): Exclude<ChartType, "none">[] {
  if (!spec.x_field || spec.y_fields.length === 0) return [];
  const typeByName = new Map(
    data.columns.map((column) => [column.name, column.data_type]),
  );
  if (!typeByName.has(spec.x_field)) return [];
  const hasNumericY = spec.y_fields.some(
    (field) => typeByName.get(field) === "number",
  );
  if (!hasNumericY) return [];
  const result: Exclude<ChartType, "none">[] = ["bar", "line", "area"];
  if (data.rows.length <= 12) result.push("pie");
  if (typeByName.get(spec.x_field) === "number") result.push("scatter");
  return result;
}

export function ChartPanel({
  data,
  spec,
}: {
  data: DataFrameComponent;
  spec: ChartSpec;
}) {
  const available = useMemo(
    () => availableChartTypes(data, spec),
    [data, spec],
  );
  const defaultType =
    spec.type !== "none" && available.includes(spec.type)
      ? spec.type
      : available[0];
  const [chartType, setChartType] = useState<
    Exclude<ChartType, "none"> | undefined
  >(defaultType);

  useEffect(() => {
    setChartType(defaultType);
  }, [defaultType, data.sql]);

  const sourceRows = data.rows.slice(0, MAX_CHART_ROWS);
  const prepared = useMemo(
    () => prepareSeries(sourceRows, spec, chartType),
    [sourceRows, spec, chartType],
  );

  if (!chartType || !spec.x_field || prepared.rows.length === 0) {
    return (
      <div className="chart-empty">
        <span className="chart-empty__glyph" aria-hidden="true">⌁</span>
        <strong>当前结果更适合表格查看</strong>
        <p>{spec.reason || "缺少可用于稳定绘图的分类、时间或数值字段。"}</p>
      </div>
    );
  }

  const commonAxes = (
    <>
      <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
      <XAxis
        dataKey={spec.x_field}
        tick={{ fill: "var(--color-muted)", fontSize: 11 }}
        axisLine={{ stroke: "var(--color-line)" }}
        tickLine={false}
        minTickGap={18}
      />
      <YAxis
        tick={{ fill: "var(--color-muted)", fontSize: 11 }}
        axisLine={false}
        tickLine={false}
        width={52}
      />
      <Tooltip
        contentStyle={{
          background: "var(--color-panel)",
          border: "1px solid var(--color-line)",
          borderRadius: 8,
          color: "var(--color-ink)",
          fontSize: 12,
        }}
      />
      {prepared.keys.length > 1 && <Legend />}
    </>
  );

  const aggregationLabel =
    (spec.aggregation && spec.aggregation !== "none"
      ? spec.aggregation
      : prepared.aggregated
        ? "sum"
        : null) ?? null;

  return (
    <section className="chart-panel">
      <header className="chart-panel__header">
        <div>
          <span>Visualization</span>
          <h3>{spec.title || "查询结果图表"}</h3>
        </div>
        <div className="chart-panel__switcher" aria-label="切换图表类型">
          {available.map((type) => (
            <button
              key={type}
              type="button"
              className={chartType === type ? "is-active" : ""}
              onClick={() => setChartType(type)}
              aria-pressed={chartType === type}
            >
              {CHART_LABELS[type]}
            </button>
          ))}
        </div>
      </header>

      <div
        className="chart-panel__canvas"
        role="img"
        aria-label={spec.title || "查询结果图表"}
      >
        <ResponsiveContainer width="100%" height="100%">
          {chartType === "bar" ? (
            <BarChart data={prepared.rows} margin={{ top: 12, right: 18, left: 0, bottom: 8 }}>
              {commonAxes}
              {prepared.keys.map((series, index) => (
                <Bar
                  key={series.key}
                  dataKey={series.key}
                  name={series.label}
                  fill={CHART_COLORS[index % CHART_COLORS.length]}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={54}
                />
              ))}
            </BarChart>
          ) : chartType === "line" ? (
            <LineChart data={prepared.rows} margin={{ top: 12, right: 18, left: 0, bottom: 8 }}>
              {commonAxes}
              {prepared.keys.map((series, index) => (
                <Line
                  key={series.key}
                  type="monotone"
                  dataKey={series.key}
                  name={series.label}
                  stroke={CHART_COLORS[index % CHART_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  activeDot={{ r: 4 }}
                />
              ))}
            </LineChart>
          ) : chartType === "area" ? (
            <AreaChart data={prepared.rows} margin={{ top: 12, right: 18, left: 0, bottom: 8 }}>
              {commonAxes}
              {prepared.keys.map((series, index) => (
                <Area
                  key={series.key}
                  type="monotone"
                  dataKey={series.key}
                  name={series.label}
                  stroke={CHART_COLORS[index % CHART_COLORS.length]}
                  fill={CHART_COLORS[index % CHART_COLORS.length]}
                  fillOpacity={0.14}
                  strokeWidth={2}
                />
              ))}
            </AreaChart>
          ) : chartType === "pie" ? (
            <PieChart>
              <Tooltip
                contentStyle={{
                  background: "var(--color-panel)",
                  border: "1px solid var(--color-line)",
                  borderRadius: 8,
                }}
              />
              <Legend />
              <Pie
                data={prepared.rows}
                dataKey={spec.y_fields[0]}
                nameKey={spec.x_field}
                innerRadius="48%"
                outerRadius="76%"
                paddingAngle={2}
              >
                {prepared.rows.map((_, index) => (
                  <Cell
                    key={index}
                    fill={CHART_COLORS[index % CHART_COLORS.length]}
                  />
                ))}
              </Pie>
            </PieChart>
          ) : (
            <ScatterChart margin={{ top: 12, right: 18, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="var(--chart-grid)" />
              <XAxis
                type="number"
                dataKey={spec.x_field}
                name={spec.x_field}
                tick={{ fill: "var(--color-muted)", fontSize: 11 }}
              />
              <YAxis
                type="number"
                dataKey={spec.y_fields[0]}
                name={spec.y_fields[0]}
                tick={{ fill: "var(--color-muted)", fontSize: 11 }}
              />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              <Scatter
                data={prepared.rows}
                fill={CHART_COLORS[0]}
                name={spec.y_fields[0]}
              />
            </ScatterChart>
          )}
        </ResponsiveContainer>
      </div>

      {(data.rows.length > MAX_CHART_ROWS || data.truncated || prepared.aggregated) && (
        <p className="chart-panel__note">
          {prepared.aggregated && aggregationLabel
            ? `相同横轴存在重复记录，已按 ${aggregationLabel} 聚合后再绘图。`
            : null}
          {data.rows.length > MAX_CHART_ROWS || data.truncated
            ? ` 图表基于当前展示数据的前 ${Math.min(data.rows.length, MAX_CHART_ROWS)} 行。`
            : null}
        </p>
      )}
    </section>
  );
}
