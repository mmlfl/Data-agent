import { describe, expect, it } from "vitest";
import type { ChartSpec, DataFrameComponent } from "../../types";
import { availableChartTypes } from "./ChartPanel";
import { prepareSeries } from "./chartPrepare";

const data: DataFrameComponent = {
  type: "dataframe",
  title: "查询结果",
  columns: [
    { name: "month", data_type: "string" },
    { name: "amount", data_type: "number" },
  ],
  rows: [{ month: "2026-01", amount: 12 }],
  row_count: 1,
  row_count_is_exact: true,
  displayed_row_count: 1,
  truncated: false,
  sql: "SELECT month, amount FROM orders",
};

describe("availableChartTypes", () => {
  it("rejects a chart that references unknown result fields", () => {
    const spec: ChartSpec = {
      type: "line",
      x_field: "unknown",
      y_fields: ["amount"],
    };
    expect(availableChartTypes(data, spec)).toEqual([]);
  });

  it("only enables scatter when the x field is numeric", () => {
    const categorical: ChartSpec = {
      type: "bar",
      x_field: "month",
      y_fields: ["amount"],
    };
    const numeric: ChartSpec = {
      type: "scatter",
      x_field: "amount",
      y_fields: ["amount"],
    };
    expect(availableChartTypes(data, categorical)).not.toContain("scatter");
    expect(availableChartTypes(data, numeric)).toContain("scatter");
  });
});

describe("prepareSeries", () => {
  it("sums duplicate x values instead of silently overwriting", () => {
    const rows = [
      { month: "2026-01", amount: 10 },
      { month: "2026-01", amount: 5 },
      { month: "2026-02", amount: 7 },
    ];
    const prepared = prepareSeries(
      rows,
      {
        type: "bar",
        x_field: "month",
        y_fields: ["amount"],
        aggregation: "none",
      },
      "bar",
    );

    expect(prepared.aggregated).toBe(true);
    expect(prepared.rows).toEqual([
      { month: "2026-01", amount: 15 },
      { month: "2026-02", amount: 7 },
    ]);
  });

  it("respects explicit avg aggregation across series", () => {
    const rows = [
      { month: "2026-01", region: "东", amount: 10 },
      { month: "2026-01", region: "东", amount: 20 },
      { month: "2026-01", region: "西", amount: 8 },
    ];
    const prepared = prepareSeries(
      rows,
      {
        type: "bar",
        x_field: "month",
        y_fields: ["amount"],
        series_field: "region",
        aggregation: "avg",
      },
      "bar",
    );

    expect(prepared.rows[0]["amount::东"]).toBe(15);
    expect(prepared.rows[0]["amount::西"]).toBe(8);
  });
});
