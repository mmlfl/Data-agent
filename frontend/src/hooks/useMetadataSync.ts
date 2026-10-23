import { useRef, useState } from "react";
import {
  runMetadataSync,
  type SyncReport,
  type SyncTarget,
} from "../api/metadata";

export interface SyncExecution {
  id: string;
  target: SyncTarget;
  status: "running" | "success" | "error";
  startedAt: number;
  finishedAt?: number;
  message: string;
  report?: SyncReport;
}

export function useMetadataSync(onCacheSynced: () => Promise<unknown>) {
  const [executions, setExecutions] = useState<SyncExecution[]>([]);
  const [activeTarget, setActiveTarget] = useState<SyncTarget | null>(null);
  const lock = useRef(false);

  const sync = async (target: SyncTarget, path: string, token: string) => {
    if (lock.current) return;
    lock.current = true;
    setActiveTarget(target);
    const id = crypto.randomUUID();
    const execution: SyncExecution = {
      id,
      target,
      status: "running",
      startedAt: Date.now(),
      message: "正在重新同步单表元数据，请保持页面打开…",
    };
    setExecutions((current) => [execution, ...current].slice(0, 30));
    try {
      const report = await runMetadataSync(target, path, token);
      setExecutions((current) =>
        current.map((item) =>
          item.id === id
            ? {
                ...item,
                status: "success",
                finishedAt: Date.now(),
                message: report.message,
                report,
              }
            : item,
        ),
      );
      // Health failure after a successful sync must not turn it into a failed sync.
      if (target === "sqlite") await onCacheSynced().catch(() => {});
    } catch (error) {
      setExecutions((current) =>
        current.map((item) =>
          item.id === id
            ? {
                ...item,
                status: "error",
                finishedAt: Date.now(),
                message:
                  error instanceof Error
                    ? error.message
                    : "同步失败，请稍后重试。",
              }
            : item,
        ),
      );
    } finally {
      lock.current = false;
      setActiveTarget(null);
    }
  };

  return { executions, activeTarget, sync };
}
