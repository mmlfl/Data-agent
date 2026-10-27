import { useState } from "react";
import type { SyncTarget } from "../api/metadata";
import type { SyncExecution } from "../hooks/useMetadataSync";
import type { HealthResponse } from "../types";
import { Icon } from "./Icon";
import { MetadataCacheBrowser } from "./MetadataCacheBrowser";
import { MetadataMilvusBrowser } from "./MetadataMilvusBrowser";

const LABELS = { sqlite: "SQLite 缓存", milvus: "Milvus collection" };
const STATUS_LABELS = { running: "同步中", success: "已完成", error: "未完成" };

function formatTime(value: number) {
  return new Date(value).toLocaleTimeString("zh-CN", { hour12: false });
}

interface MetadataManagerProps {
  active?: boolean;
  health: HealthResponse | null;
  healthError: string | null;
  executions: SyncExecution[];
  activeTarget: SyncTarget | null;
  onSync: (target: SyncTarget) => void;
}

export function MetadataManager({
  active = true,
  health,
  healthError,
  executions,
  activeTarget,
  onSync,
}: MetadataManagerProps) {
  const [inspectionTab, setInspectionTab] = useState<SyncTarget>("sqlite");
  const busy = activeTarget !== null;
  const canSyncCache = Boolean(health?.with_db && !healthError);
  const latest = (target: SyncTarget) =>
    executions.find((item) => item.target === target);
  const latestSuccess = (target: SyncTarget) =>
    executions.find(
      (item) => item.target === target && item.status === "success",
    );

  return (
    <div className="metadata-page">
      <div className="page-intro">
        <span className="page-eyebrow">METADATA STUDIO</span>
        <h1>
          让每一次分析，都有据可依<span>。</span>
        </h1>
        <p>在一个地方管理单表元数据，让结构缓存与检索索引保持更新。</p>
      </div>
      <section className="metadata-pipeline" aria-label="元数据同步路径">
        <div className="metadata-pipeline__heading">
          <Icon name="layers" size={16} />
          <strong>元数据流转</strong>
          <span>建议按顺序执行同步</span>
        </div>
        <div className="pipeline-nodes">
          <div className="pipeline-node">
            <span className="pipeline-node__icon">
              <Icon name="database" size={21} />
            </span>
            <div>
              <strong>业务数据库</strong>
              <span>表、字段与注释</span>
            </div>
            <small>01</small>
          </div>
          <span className="pipeline-link">
            <Icon name="arrow" size={20} />
          </span>
          <div className="pipeline-node">
            <span className="pipeline-node__icon tone-green">
              <Icon name="table" size={21} />
            </span>
            <div>
              <strong>SQLite 元数据缓存</strong>
              <span>单表结构的本地快照</span>
            </div>
            <small>02</small>
          </div>
          <span className="pipeline-link">
            <Icon name="arrow" size={20} />
          </span>
          <div className="pipeline-node">
            <span className="pipeline-node__icon tone-purple">
              <Icon name="layers" size={21} />
            </span>
            <div>
              <strong>Milvus collection</strong>
              <span>单表元数据检索索引</span>
            </div>
            <small>03</small>
          </div>
        </div>
      </section>
      <div className="metadata-inspection-tabs" role="tablist" aria-label="选择检查与浏览的数据源">
        <button type="button" role="tab" id="sqlite-inspection-tab" aria-controls="sqlite-inspection-panel" aria-selected={inspectionTab === "sqlite"} onClick={() => setInspectionTab("sqlite")}><Icon name="database" size={16} />SQLite 缓存</button>
        <button type="button" role="tab" id="milvus-inspection-tab" aria-controls="milvus-inspection-panel" aria-selected={inspectionTab === "milvus"} onClick={() => setInspectionTab("milvus")}><Icon name="layers" size={16} />Milvus 文档</button>
      </div>
      <div id="sqlite-inspection-panel" role="tabpanel" aria-labelledby="sqlite-inspection-tab" hidden={inspectionTab !== "sqlite"}>
        <MetadataCacheBrowser enabled={active && inspectionTab === "sqlite"} refreshKey={latestSuccess("sqlite")?.finishedAt} />
      </div>
      <div id="milvus-inspection-panel" role="tabpanel" aria-labelledby="milvus-inspection-tab" hidden={inspectionTab !== "milvus"}>
        <MetadataMilvusBrowser enabled={active && inspectionTab === "milvus"} refreshKey={latestSuccess("milvus")?.finishedAt} />
      </div>
      <div className="sync-grid">
        {(["sqlite", "milvus"] as const).map((target) => {
          const last = latest(target);
          const success = latestSuccess(target);
          const running = activeTarget === target;
          return (
            <section
              className={`sync-card sync-card--${target}`}
              key={target}
              aria-labelledby={`sync-title-${target}`}
            >
              <div className="sync-card__top">
                <span
                  className={`sync-card__icon ${target === "sqlite" ? "tone-green" : "tone-purple"}`}
                >
                  <Icon
                    name={target === "sqlite" ? "database" : "layers"}
                    size={25}
                  />
                </span>
                <span
                  className={`sync-badge ${last ? `sync-badge--${last.status}` : ""}`}
                >
                  <span className="status-dot" />
                  {last
                    ? STATUS_LABELS[last.status]
                    : target === "sqlite" && canSyncCache
                      ? "已连接"
                      : "尚未执行"}
                </span>
              </div>
              <h2 id={`sync-title-${target}`}>{LABELS[target]}</h2>
              <p>
                {target === "sqlite"
                  ? "从业务数据库重新读取单表元数据，更新本地结构缓存，为分析提供最新的字段与注释。"
                  : "将单表元数据重新同步至 Milvus collection，更新用于表结构检索的索引。"}
              </p>
              <dl className="sync-card__facts">
                <div>
                  <dt>{target === "sqlite" ? "缓存表数量" : "最近同步写入"}</dt>
                  <dd>
                    {target === "sqlite"
                      ? health?.with_db
                        ? `${health.cache_table_count ?? 0} 张表`
                        : "待连接"
                      : success?.report?.written !== undefined
                        ? `${success.report.written} 条`
                        : "—"}
                  </dd>
                </div>
                <div>
                  <dt>本次最近成功</dt>
                  <dd>
                    {success?.finishedAt
                      ? formatTime(success.finishedAt)
                      : "尚无记录"}
                  </dd>
                </div>
                {target === "milvus" && success?.report?.collection && (
                  <div>
                    <dt>Collection</dt>
                    <dd title={success.report.collection}>
                      {success.report.collection}
                    </dd>
                  </div>
                )}
              </dl>
              {last && (
                <div
                  className={`sync-feedback sync-feedback--${last.status}`}
                  role={last.status === "error" ? "alert" : "status"}
                >
                  <Icon
                    name={
                      last.status === "running"
                        ? "refresh"
                        : last.status === "success"
                          ? "check"
                          : "alert"
                    }
                    size={15}
                    className={running ? "is-spinning" : ""}
                  />
                  <span>
                    {last.message}
                    {last.status === "success" &&
                    last.report?.skipped !== undefined
                      ? `（跳过 ${last.report.skipped} 条未变更记录）`
                      : ""}
                  </span>
                </div>
              )}
              <div className="sync-card__action">
                <button
                  type="button"
                  className={`action-button ${target === "sqlite" ? "action-button--primary" : ""}`}
                  disabled={
                    busy ||
                    (target === "sqlite" && !canSyncCache) ||
                    (target === "milvus" && Boolean(healthError))
                  }
                  onClick={() => onSync(target)}
                >
                  <Icon
                    name="refresh"
                    size={16}
                    className={running ? "is-spinning" : ""}
                  />
                  {running ? "正在重新同步…" : `重新同步 ${LABELS[target]}`}
                </button>
                <small>
                  {busy
                    ? "请等待当前同步完成"
                    : target === "sqlite" && !canSyncCache
                      ? "连接并启用数据库后可执行"
                      : target === "sqlite"
                        ? "更新表结构时，建议先执行此操作"
                        : "请先确认 SQLite 缓存已更新"}
                </small>
              </div>
            </section>
          );
        })}
      </div>
      <section className="sync-history">
        <div className="section-caption">
          <span>
            <Icon name="clock" size={16} />
            同步记录
          </span>
          <small>最近 30 次任务，刷新后可恢复</small>
        </div>
        {executions.length === 0 ? (
          <div className="sync-history__empty">
            <span>
              <Icon name="clock" size={23} />
            </span>
            <strong>还没有同步记录</strong>
            <p>执行同步后，在这里查看每次操作的状态、耗时和结果。</p>
          </div>
        ) : (
          <ol className="sync-history__list">
            {executions.map((item) => (
              <li key={item.id}>
                <span
                  className={`execution-icon execution-icon--${item.status}`}
                >
                  <Icon
                    name={
                      item.status === "running"
                        ? "refresh"
                        : item.status === "success"
                          ? "check"
                          : "alert"
                    }
                    size={16}
                    className={item.status === "running" ? "is-spinning" : ""}
                  />
                </span>
                <div>
                  <strong>
                    {LABELS[item.target]}
                    <span
                      className={`execution-label execution-label--${item.status}`}
                    >
                      {STATUS_LABELS[item.status]}
                    </span>
                  </strong>
                  <p>{item.message}</p>
                </div>
                <time dateTime={new Date(item.startedAt).toISOString()}>
                  {formatTime(item.startedAt)}
                  <small>
                    {item.finishedAt
                      ? `${((item.finishedAt - item.startedAt) / 1000).toFixed(1)} 秒`
                      : "执行中"}
                  </small>
                </time>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
