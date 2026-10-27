import type { ChartAggregation, ChartSpec, DataFrameComponent } from "../../types";
import { numericFields } from "./chartPolicy";

export function ChartControls({ data, spec, onChange }: { data: DataFrameComponent; spec: ChartSpec; onChange: (spec: ChartSpec) => void }) {
  const change = (patch: Partial<ChartSpec>) => onChange({ ...spec, ...patch });
  return <div className="chart-controls" aria-label="图表字段设置">
    <label>维度<select aria-label="图表维度" value={spec.x_field ?? ""} onChange={e => change({ x_field: e.target.value })}>
      {data.columns.map(column => <option key={column.name}>{column.name}</option>)}
    </select></label>
    <label>数值<select aria-label="图表指标" value={spec.y_fields[0] ?? ""} onChange={e => change({ y_fields: [e.target.value] })}>
      {numericFields(data).map(column => <option key={column.name}>{column.name}</option>)}
    </select></label>
    <label>系列<select aria-label="图表系列" value={spec.series_field ?? ""} onChange={e => change({ series_field: e.target.value || null })}>
      <option value="">不分系列</option>{data.columns.filter(column => column.name !== spec.x_field).map(column => <option key={column.name}>{column.name}</option>)}
    </select></label>
    <label>聚合<select aria-label="图表聚合方式" value={spec.aggregation ?? "none"} onChange={e => change({ aggregation: e.target.value as ChartAggregation })}>
      <option value="none">不聚合</option><option value="sum">求和</option><option value="avg">平均值</option><option value="min">最小值</option><option value="max">最大值</option><option value="count">非空计数</option>
    </select></label>
    <small>聚合仅作用于已加载数据；占比、加权平均等请先在 SQL 中按业务口径计算。</small>
  </div>;
}
