import { useEffect, useMemo, useRef, useState } from "react";
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
import type { ChartSpec, ChartType, DataFrameComponent } from "../../types";
import { prepareSeries } from "./chartPrepare";
import { availableChartTypes } from "./chartPolicy";
import { exportChart } from "../../utils/exportChart";
export { availableChartTypes } from "./chartPolicy";

const CHART_COLORS = ["#448574", "#6d8bc6", "#c69b55", "#9b85bd", "#7a9c6b"];
const MAX_CHART_ROWS = 100;

const CHART_LABELS: Record<Exclude<ChartType, "none">, string> = {
  bar: "柱状",
  line: "折线",
  area: "面积",
  pie: "饼图",
  scatter: "散点",
};

export function ChartPanel({
  data,
  spec,
}: {
  data: DataFrameComponent;
  spec: ChartSpec;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [exportError, setExportError] = useState("");
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

  const sourceRows = useMemo(() => {
    const rows = [...data.rows];
    if ((chartType === "line" || chartType === "area") && spec.x_field)
      rows.sort((a, b) => String(a[spec.x_field!]).localeCompare(String(b[spec.x_field!]), undefined, { numeric: true }));
    return rows.slice(0, MAX_CHART_ROWS);
  }, [data.rows, chartType, spec.x_field]);
  const prepared = useMemo(
    () => prepareSeries(sourceRows, spec, chartType),
    [sourceRows, spec, chartType],
  );

  if (!chartType || !spec.x_field || prepared.rows.length === 0) {
    return (
      <div className="chart-empty">
        <span className="chart-empty__glyph" aria-hidden="true">
          ⌁
        </span>
        <strong>当前结果更适合表格查看</strong>
        <p>{prepared.issue || spec.reason || "缺少可用于稳定绘图的分类、时间或数值字段。"}</p>
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
      <div className="result-export-actions">
        {(["png", "svg"] as const).map(format => <button type="button" key={format} onClick={async () => {
          setExportError(""); try { if (container.current) await exportChart(container.current, format, "query-chart"); }
          catch (error) { setExportError(error instanceof Error ? error.message : "图片导出失败"); }
        }}>导出 {format.toUpperCase()}</button>)}
        {exportError && <span role="alert">{exportError}</span>}
      </div>

      <div
        className="chart-panel__canvas"
        ref={container}
        role="img"
        aria-label={spec.title || "查询结果图表"}
        data-export-note={`基于已加载 ${sourceRows.length} 行${data.truncated ? "，查询结果已截断" : ""} · ${prepared.keys.map(key => key.label).join(" / ")}`}
      >
        <ResponsiveContainer width="100%" height="100%">
          {chartType === "bar" ? (
            <BarChart
              data={prepared.rows}
              margin={{ top: 12, right: 18, left: 0, bottom: 8 }}
            >
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
            <LineChart
              data={prepared.rows}
              margin={{ top: 12, right: 18, left: 0, bottom: 8 }}
            >
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
            <AreaChart
              data={prepared.rows}
              margin={{ top: 12, right: 18, left: 0, bottom: 8 }}
            >
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
      {prepared.omittedSeries ? <p className="chart-panel__note">系列过多，当前仅展示前 8 个系列，另 {prepared.omittedSeries} 个未绘制；请缩小范围。</p> : null}

      {(data.rows.length > MAX_CHART_ROWS ||
        data.truncated ||
        prepared.aggregated) && (
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
