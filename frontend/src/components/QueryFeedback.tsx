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
  const [indexStatus, setIndexStatus] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setVerdict(null);
    setError(null);
    setEligible(true); setIndexStatus("");
    queryFeedback(queryId)
      .then((status) => {
        if (!cancelled) {
          setVerdict(status.verdict);
          setEligible(status.eligible !== false);
          setIndexStatus(status.index_status ?? "");
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
      setIndexStatus(result.index_status ?? "");
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "反馈暂未保存，请重试",
      );
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (verdict !== "satisfied" || indexStatus !== "pending") return;
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const status = await queryFeedback(queryId); if (!stopped) setIndexStatus(status.index_status ?? "pending"); }
      catch { /* Keep the persisted confirmation visible during a temporary outage. */ }
      finally { if (!stopped) timer = setTimeout(() => void poll(), 4000); }
    };
    timer = setTimeout(() => void poll(), 1500);
    return () => { stopped = true; clearTimeout(timer); };
  }, [queryId, verdict, indexStatus]);

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
      {verdict === "satisfied" && <small role="status">{({ indexed: "向量索引已就绪，可供后续检索。", pending: "已保存确认，等待向量索引；检索关闭时保持待处理。", failed: "已保存确认，但向量索引失败。" } as Record<string, string>)[indexStatus] ?? "确认记录已保存。"}</small>}
      {verdict === "satisfied" && indexStatus === "failed" && <button type="button" disabled={busy} onClick={async () => {
        setBusy(true); try {
          const response = await fetch("/api/knowledge/reindex", { method: "POST", headers: { "X-Requested-With": "SQL-Insight-Workbench" } });
          if (!response.ok) throw new Error("重试未提交，请稍后再试"); setIndexStatus("pending");
        } catch (failure) { setError(String(failure)); } finally { setBusy(false); }
      }}>重试索引</button>}
      {error && <small role="alert">{error}</small>}
    </section>
  );
}
