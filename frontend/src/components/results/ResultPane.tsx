import { lazy, Suspense, useEffect, useState } from "react";
import type { ChartSpec, ResultArtifact, TurnPhase } from "../../types";
import { QueryResultTable } from "../QueryResultTable";
import { ResultSummary } from "./ResultSummary";
import { SqlDisclosure } from "./SqlDisclosure";
import { Icon } from "../Icon";
import { availableChartTypes, measureFields, numericFields, recommendChart } from "./chartPolicy";
import { ChartControls } from "./ChartControls";
import { downloadBlob, exportJson } from "../../utils/exportCsv";
import "../../styles/results-enhanced.css";

const ChartPanel = lazy(() =>
  import("./ChartPanel").then((module) => ({ default: module.ChartPanel })),
);

interface ResultPaneProps {
  artifacts: ResultArtifact[];
  activeResultId: string | null;
  phase: TurnPhase;
  onSelectResult: (resultId: string) => void;
}

export function ResultPane({
  artifacts,
  activeResultId,
  phase,
  onSelectResult,
}: ResultPaneProps) {
  const active =
    artifacts.find((artifact) => artifact.id === activeResultId) ??
    artifacts[artifacts.length - 1] ??
    null;
  const [choice, setChoice] = useState<{ id: string; spec: ChartSpec } | null>(null);
  const spec = active ? choice?.id === active.id ? choice.spec : active.finalResult?.chart ?? recommendChart(active.data) : null;
  const hasChart = Boolean(active && spec && spec.type !== "none" && availableChartTypes(active.data, spec).length);
  const canConfigureChart = Boolean(active && active.data.rows.length >= 2 && numericFields(active.data).length);
  const [view, setView] = useState<"chart" | "table">("table");

  useEffect(() => {
    setView(hasChart ? "chart" : "table");
  }, [active?.id, active?.finalResult?.chart.type]);

  return (
    <section className="result-pane" aria-label="查询洞察画布">
      <header className="pane-heading pane-heading--result">
        <div>
          <span className="pane-heading__eyebrow">INSIGHTS & DATA</span>
          <h2>查询结果</h2>
        </div>
        {active && (
          <span className="pane-heading__meta">
            {active.data.row_count_is_exact ? "" : "至少 "}{active.data.row_count} 行 · {active.data.columns.length} 列
          </span>
        )}
      </header>

      {!active ? (
        <div className="result-empty">
          <div className="result-empty__frame" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
            <i />
          </div>
          <span className="result-empty__eyebrow">A SPACE FOR DISCOVERY</span>
          <h3>
            {phase === "streaming" || phase === "summarizing"
              ? "正在寻找数据中的答案"
              : "下一份洞察，在这里呈现"}
          </h3>
          <p>
            查询完成后，在这里查看分析结论、交互图表与原始数据。继续追问时，结果依然保持可见。
          </p>
        </div>
      ) : (
        <div className="result-pane__content">
          {artifacts.length > 1 && (
            <nav className="result-history" aria-label="本次会话的查询结果">
              {artifacts.map((artifact, index) => (
                <button
                  key={artifact.id}
                  type="button"
                  className={artifact.id === active.id ? "is-active" : ""}
                  onClick={() => onSelectResult(artifact.id)}
                >
                  <span>Q{String(index + 1).padStart(2, "0")}</span>
                  {artifact.finalResult?.title ||
                    `${artifact.data.row_count} 行结果`}
                </button>
              ))}
            </nav>
          )}

          <ResultSummary
            artifact={active}
            loading={phase === "streaming" || phase === "summarizing"}
          />
          {active.data.rows.length === 1 && measureFields(active.data).length > 0 && <div className="result-metrics">{measureFields(active.data).map(column => <div key={column.name}><span>{column.name}</span><strong>{String(active.data.rows[0][column.name] ?? "—")}</strong></div>)}</div>}
          <div className="result-export-actions">
            <button type="button" onClick={() => downloadBlob(new Blob([active.data.sql], { type: "text/plain;charset=utf-8" }), "query.sql")}>导出 SQL</button>
            <button type="button" onClick={() => exportJson({ result: active.data, conclusion: active.finalResult, exported_at: new Date().toISOString() }, "query-analysis.json")}>导出分析记录</button>
          </div>

          <div className="result-view">
            <header className="result-view__toolbar">
              <div
                className="result-view__tabs"
                role="tablist"
                aria-label="结果视图"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={view === "chart"}
                  className={view === "chart" ? "is-active" : ""}
                  disabled={!canConfigureChart}
                  onClick={() => {
                    if (active && (!spec?.x_field || !spec.y_fields.length)) {
                      const x = active.data.columns.find(column => column.data_type !== "number") ?? active.data.columns[0];
                      setChoice({ id: active.id, spec: { type: "bar", x_field: x.name, y_fields: [numericFields(active.data)[0].name], aggregation: "none" } });
                    }
                    setView("chart");
                  }}
                >
                  <Icon name="chart" size={14} />
                  图表
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={view === "table"}
                  className={view === "table" ? "is-active" : ""}
                  onClick={() => setView("table")}
                >
                  <Icon name="table" size={14} />
                  数据
                </button>
              </div>
              <div className="result-view__facts">
                <span>{active.data.displayed_row_count} 行已加载</span>
                {active.data.truncated && <strong>结果已截断</strong>}
              </div>
            </header>

            <div className="result-view__body">
              {view === "chart" && spec ? (<>
                <ChartControls data={active.data} spec={spec} onChange={next => setChoice({ id: active.id, spec: next })} />
                <Suspense
                  fallback={
                    <div className="chart-empty">
                      <strong>正在加载图表组件…</strong>
                    </div>
                  }
                >
                  <ChartPanel
                    data={active.data}
                    spec={spec}
                  />
                </Suspense></>
              ) : (
                <QueryResultTable key={active.id} data={active.data} />
              )}
            </div>
          </div>
          {!hasChart && view === "table" && <p className="chart-panel__note">{spec?.reason || "当前结果以数据表展示，需要时可手动配置图表。"}</p>}

          <SqlDisclosure sql={active.data.sql} />
        </div>
      )}
    </section>
  );
}
