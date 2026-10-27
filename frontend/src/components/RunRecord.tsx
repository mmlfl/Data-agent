import { useState } from "react";
import { getRun } from "../api/runs";
import { exportJson } from "../utils/exportCsv";

export function RunRecord({ runId }: { runId: string }) {
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  return <details className="tool-detail" onToggle={async event => {
    if (!event.currentTarget.open) return;
    try {
      const run = await getRun(runId);
      const labels: Record<string,string> = { success: "完成", partial: "部分完成", error: "失败", cancelled: "已取消", interrupted: "中断", running: "执行中", queued: "待执行", cancelling: "取消收尾中" };
      setSummary(labels[run.status] ?? run.status);
    } catch { setSummary("状态暂不可读，请稍后重试"); }
  }}><summary>本轮运行记录 · {runId.slice(0, 8)}</summary><p>{summary}</p><button type="button" disabled={busy} onClick={async () => {
    setBusy(true);
    try {
      let after = 0; const events = []; let page;
      do { page = await getRun(runId, after); events.push(...page.events); after = Number(page.events.at(-1)?.metadata?.sequence ?? after); } while (page.events.length === 200);
      exportJson({ run_id: runId, status: page.status, events }, `run-${runId}.json`);
    } catch { setSummary("运行记录导出失败，请重试"); } finally { setBusy(false); }
  }}>导出执行记录</button></details>;
}
