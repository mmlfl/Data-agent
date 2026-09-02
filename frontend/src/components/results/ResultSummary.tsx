import type { ResultArtifact } from "../../types";

export function ResultSummary({
  artifact,
  loading,
}: {
  artifact: ResultArtifact;
  loading: boolean;
}) {
  const result = artifact.finalResult;

  if (!result) {
    return (
      <section className="result-summary result-summary--pending">
        <span className="result-summary__kicker">Query complete</span>
        <h3>已取得 {artifact.data.row_count} 行结果</h3>
        <p>
          {loading
            ? "正在核对字段与数值，并整理最终分析结论。"
            : "结果可在下方数据表中查看。"}
        </p>
        {loading && <span className="result-summary__loader" aria-hidden="true" />}
      </section>
    );
  }

  return (
    <section className="result-summary">
      <span className="result-summary__kicker">Final insight</span>
      <h3>{result.title}</h3>
      <p className="result-summary__lead">{result.summary}</p>

      {result.insights.length > 0 && (
        <div className="result-summary__insights">
          <span>关键发现</span>
          <ul>
            {result.insights.map((insight) => (
              <li key={insight}>{insight}</li>
            ))}
          </ul>
        </div>
      )}

      {result.warnings.length > 0 && (
        <div className="result-summary__warnings">
          {result.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
    </section>
  );
}
