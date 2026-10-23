import { useEffect, useState } from "react";
import { queryFeedback, type FeedbackVerdict } from "../api/feedback";

export function QueryFeedback({
  queryId,
  question,
}: {
  queryId: string;
  question?: string;
}) {
  const [verdict, setVerdict] = useState<FeedbackVerdict | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [eligible, setEligible] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setVerdict(null);
    setError(null);
    queryFeedback(queryId)
      .then((status) => {
        if (!cancelled) {
          setVerdict(status.verdict);
          setEligible(status.eligible !== false);
        }
      })
      .catch(() => {
        // The POST still validates ownership and eligibility if the initial read failed.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [queryId]);

  const submit = async (next: FeedbackVerdict) => {
    setBusy(true);
    setError(null);
    try {
      const result = await queryFeedback(queryId, next);
      setVerdict(result.verdict);
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "反馈暂未保存，请重试",
      );
    } finally {
      setBusy(false);
    }
  };

  if (!eligible) return null;
  return (
    <section className="query-feedback" aria-label="查询结果反馈">
      <span>这次查询符合要求吗？</span>
      {question && (
        <details>
          <summary>查看本次查询的问题</summary>
          <p>{question}</p>
        </details>
      )}
      <div className="query-feedback__actions">
        <button
          type="button"
          disabled={loading || busy || verdict === "satisfied"}
          aria-pressed={verdict === "satisfied"}
          onClick={() => void submit("satisfied")}
        >
          符合要求
        </button>
        <button
          type="button"
          disabled={loading || busy || verdict === "unsatisfied"}
          aria-pressed={verdict === "unsatisfied"}
          onClick={() => void submit("unsatisfied")}
        >
          不符合要求
        </button>
      </div>
      <small role="status">
        {busy
          ? "正在保存…"
          : verdict === "satisfied"
            ? "已确认，将作为后续查询的参考。"
            : verdict === "unsatisfied"
              ? "已记录，这次查询不会作为后续参考。"
              : "确认后，可帮助后续查询参考已认可的 SQL 和连接关系。"}
      </small>
      {error && <small role="alert">{error}</small>}
    </section>
  );
}
