export type FeedbackVerdict = "satisfied" | "unsatisfied";

export interface FeedbackStatus {
  query_id: string;
  verdict: FeedbackVerdict | null;
  question?: string;
  eligible?: boolean;
  index_status?: string;
  relations?: number;
}

export async function queryFeedback(
  queryId: string,
  verdict?: FeedbackVerdict,
): Promise<FeedbackStatus> {
  const response = await fetch(
    `/api/queries/${encodeURIComponent(queryId)}/feedback`,
    verdict
      ? {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "SQL-Insight-Workbench",
          },
          body: JSON.stringify({ verdict }),
        }
      : undefined,
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(body.detail || "反馈暂未保存，请重试");
  }
  return response.json();
}
