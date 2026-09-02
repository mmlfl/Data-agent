import { lazy, Suspense, useEffect, useState } from "react";
import type { ResultArtifact, TurnPhase } from "../../types";
import { QueryResultTable } from "../QueryResultTable";
import { ResultSummary } from "./ResultSummary";
import { SqlDisclosure } from "./SqlDisclosure";

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
  const hasChart = Boolean(
    active?.finalResult && active.finalResult.chart.type !== "none",
  );
  const [view, setView] = useState<"chart" | "table">("table");

  useEffect(() => {
    setView(hasChart ? "chart" : "table");
  }, [active?.id, active?.finalResult?.chart.type, hasChart]);

  return (
    <section className="result-pane" aria-label="查询洞察画布">
      <header className="pane-heading pane-heading--result">
        <div>
          <span className="pane-heading__eyebrow">Evidence canvas</span>
          <h2>洞察画布</h2>
        </div>
        {active && (
          <span className="pane-heading__meta">
            {active.data.row_count} 行 · {active.data.columns.length} 列
          </span>
        )}
      </header>

      {!active ? (
        <div className="result-empty">
          <div className="result-empty__frame" aria-hidden="true">
            <span /><span /><span /><span />
            <i />
          </div>
          <span className="result-empty__eyebrow">No evidence yet</span>
          <h3>结果将在这里保持可见</h3>
          <p>
            左侧完成 SQL 查询后，这里会固定显示结论、图表、数据表和实际执行语句，方便你边看结果边继续追问。
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
                  {artifact.finalResult?.title || `${artifact.data.row_count} 行结果`}
                </button>
              ))}
            </nav>
          )}

          <ResultSummary
            artifact={active}
            loading={phase === "streaming" || phase === "summarizing"}
          />

          <div className="result-view">
            <header className="result-view__toolbar">
              <div className="result-view__tabs" role="tablist" aria-label="结果视图">
                <button
                  type="button"
                  role="tab"
                  aria-selected={view === "chart"}
                  className={view === "chart" ? "is-active" : ""}
                  disabled={!hasChart}
                  onClick={() => setView("chart")}
                >
                  图表
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={view === "table"}
                  className={view === "table" ? "is-active" : ""}
                  onClick={() => setView("table")}
                >
                  数据
                </button>
              </div>
              <div className="result-view__facts">
                <span>{active.data.displayed_row_count} 行已加载</span>
                {active.data.truncated && <strong>结果已截断</strong>}
              </div>
            </header>

            <div className="result-view__body">
              {view === "chart" && active.finalResult ? (
                <Suspense
                  fallback={
                    <div className="chart-empty">
                      <strong>正在加载图表组件…</strong>
                    </div>
                  }
                >
                  <ChartPanel
                    data={active.data}
                    spec={active.finalResult.chart}
                  />
                </Suspense>
              ) : (
                <QueryResultTable data={active.data} />
              )}
            </div>
          </div>

          <SqlDisclosure sql={active.data.sql} />
        </div>
      )}
    </section>
  );
}
