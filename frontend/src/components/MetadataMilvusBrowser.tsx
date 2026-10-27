import { useEffect, useRef, useState } from "react";
import {
  checkMilvus, getMilvusDocument, getMilvusDocuments,
  type MilvusInspection, type MilvusComparison, type StoredMilvusDocument,
} from "../api/inspection";
import { MetadataInspectionReport } from "./MetadataInspectionReport";
import { Icon } from "./Icon";
import "../styles/metadata-cache.css";

const comparisons: Record<string, string> = {
  current: "与 SQLite 一致", stale: "内容需要更新", sqlite_missing: "仅存在于 Milvus",
  sqlite_unavailable: "SQLite 暂不可读", sqlite_incomplete: "SQLite 字段不完整",
  identity_mismatch: "文档标识不一致", invalid_hash: "文档指纹异常",
};
const count = (value?: number | null) => value == null ? "—" : value.toLocaleString("zh-CN");
const date = (value: string | null | undefined) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚无记录";

function comparisonChecks(value: MilvusComparison) {
  return [
    { label: "内容一致", ok: true, detail: `${value.matching} 张表` },
    { label: "Milvus 缺少", ok: value.milvus_missing === 0, detail: value.milvus_missing == null ? "检查范围不足，尚不能确定" : `${value.milvus_missing} 张表` },
    { label: "内容需要更新", ok: value.stale === 0, detail: `${value.stale} 张表` },
    { label: "仅存在于 Milvus", ok: value.sqlite_missing === 0, detail: `${value.sqlite_missing} 张表` },
    { label: "本地字段不完整", ok: value.sqlite_incomplete === 0, detail: `${value.sqlite_incomplete} 张表` },
    { label: "标识 / 重复记录", ok: value.identity_mismatch === 0 && value.duplicate_tables === 0, detail: `${value.identity_mismatch} / ${value.duplicate_tables} 条` },
  ];
}

export function MetadataMilvusBrowser({ enabled, refreshKey }: { enabled: boolean; refreshKey?: number }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [data, setData] = useState<MilvusInspection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<{ value: StoredMilvusDocument; source: MilvusInspection } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [checking, setChecking] = useState(false);
  const [check, setCheck] = useState<Awaited<ReturnType<typeof checkMilvus>> | null>(null);
  const [checkError, setCheckError] = useState("");
  const checkRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => { setSearch(query.trim()); setOffset(0); }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    checkRequest.current?.abort();
    setChecking(false); setCheck(null); setCheckError("");
    return () => checkRequest.current?.abort();
  }, [enabled, reload, refreshKey]);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setLoading(true); setError("");
    getMilvusDocuments(search, offset, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      if (offset > 0 && offset >= result.browse_total) { setOffset(0); return; }
      setData(result);
      setSelected((previous) => result.documents.some((item) => item.record_id === previous)
        ? previous : result.documents[0]?.record_id ?? "");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "无法读取 Milvus。");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [enabled, search, offset, reload, refreshKey]);

  useEffect(() => {
    if (!enabled || loading || error || !data || !selected) return;
    const controller = new AbortController();
    setDetail(null); setDetailLoading(true); setDetailError("");
    getMilvusDocument(selected, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      if (result.document) setDetail({ value: result.document, source: data });
      else setDetailError(result.message);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setDetailError(reason instanceof Error ? reason.message : "无法读取文档。");
    }).finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [enabled, loading, error, data, selected]);

  async function inspect() {
    const controller = new AbortController();
    checkRequest.current = controller;
    setChecking(true); setCheck(null); setCheckError("");
    try {
      const result = await checkMilvus(controller.signal);
      if (!controller.signal.aborted) setCheck(result);
    } catch (reason) {
      if (!controller.signal.aborted) setCheckError(reason instanceof Error ? reason.message : "检查未完成。");
    } finally {
      if (!controller.signal.aborted) setChecking(false);
    }
  }

  const current = detail?.source === data && detail.value.record_id === selected ? detail.value : null;
  const selectedDocument = data?.documents.find((item) => item.record_id === selected);
  const comparison = check?.comparison;

  return <section className="cache-browser milvus-browser" aria-labelledby="milvus-browser-title">
    <header className="cache-browser__header">
      <div>
        <div className="cache-browser__eyebrow"><Icon name="layers" size={14} /> MILVUS INSPECTION</div>
        <h2 id="milvus-browser-title">已存储的单表文档</h2>
        <p>读取当前数据源的远程索引，核对实际文档与本地缓存。</p>
      </div>
      <div className="metadata-inspection-actions">
        <button type="button" className="action-button" disabled={loading || checking} onClick={() => void inspect()}>
          <Icon name={checking ? "refresh" : "shield"} size={15} className={checking ? "is-spinning" : ""} />
          {checking ? "正在核对…" : "检查一致性"}
        </button>
        <button type="button" className="action-button" disabled={loading} onClick={() => setReload((value) => value + 1)}>
          <Icon name="refresh" size={15} className={loading ? "is-spinning" : ""} />刷新列表
        </button>
      </div>
    </header>

    <div className="cache-browser__overview">
      <div className="cache-browser__stats">
        <span><strong>{count(data?.document_count)}</strong>条文档</span>
        <span><strong>{count(data?.active_count)}</strong>条有效</span>
        <span><strong>{count(data?.vector_dimensions)}</strong>维向量</span>
      </div>
      <div className="cache-browser__source"><code>{data?.collection ?? "正在读取 Collection…"}</code><span>{data ? `${data.milvus_database} / ${data.database_id}` : ""}</span></div>
    </div>
    {data && <div className="milvus-browser__configuration">
      <span><i className={data.connected ? "inspection-dot inspection-dot--ok" : "inspection-dot"} />{data.connected ? "连接已建立" : "尚未连接"}</span>
      <span>BM25：{data.bm25 ? "已配置" : data.collection_exists ? "待核对" : "未知"}</span>
      <span>已存模型：<code>{data.embedding_profile ?? "未知"}</code></span>
      <span>当前配置：<code>{data.configured_embedding_profile}</code></span>
    </div>}
    {data && !loading && (data.issues.length > 0 || !data.can_browse) && <div className="metadata-inspection-notice metadata-inspection-notice--warning" role="status">
      <Icon name="alert" size={16} /><div>{data.message}{data.issues.map((issue) => <p key={issue}>{issue}</p>)}</div>
    </div>}
    {data && !data.rag_enabled && <div className="metadata-inspection-notice">Agent 向量检索开关当前关闭，仍可只读检查已有索引。</div>}
    {comparison && <MetadataInspectionReport
      message={comparison.consistent ? "当前数据源的有效文档与 SQLite 缓存一致。" : comparison.complete ? "核对完成，存在待处理的内容或配置项。" : `本次仅检查 ${comparison.scanned} 条，未完成全量核对。`}
      checks={comparisonChecks(comparison)}
    />}
    {check && !comparison && <div className="metadata-inspection-notice metadata-inspection-notice--warning" role="status">{check.message}</div>}
    {check?.issues.length ? <div className="metadata-inspection-notice metadata-inspection-notice--warning">{check.issues.join("；")}</div> : null}
    {checkError && <div className="metadata-inspection-notice metadata-inspection-notice--warning" role="alert">{checkError}</div>}

    <div className="cache-browser__toolbar">
      <label className="cache-search"><Icon name="search" size={16} /><input aria-label="搜索 Milvus 文档" maxLength={200} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="按表名或 Schema 搜索索引文档" /></label>
      <span className="milvus-browser__read-label"><Icon name="shield" size={13} />只读检查</span>
    </div>
    {data?.truncated && <div className="metadata-inspection-notice">匹配 {count(data.matched_total)} 条，本次浏览上限为 {count(data.scan_limit)} 条，请缩小搜索范围。</div>}
    {error ? <div className="cache-browser__empty cache-browser__error" role="alert"><Icon name="alert" size={24} /><strong>Milvus 暂时无法读取</strong><p>{error}</p></div>
      : <div className="cache-browser__body" aria-busy={loading}>
        <aside className="cache-browser__tables" aria-label="Milvus 文档列表">
          <div className="cache-browser__list-heading"><span>索引文档</span><span>{loading ? "读取中…" : data?.can_browse ? `${count(data.matched_total)} 条匹配` : "尚未读取"}</span></div>
          <div className="cache-browser__table-list">
            {loading ? <div className="cache-browser__empty"><Icon name="refresh" className="is-spinning" size={22} /><span>正在连接并读取 Milvus…</span></div>
              : data?.documents.length ? data.documents.map((document) => <button type="button" className={`cache-table-item ${selected === document.record_id ? "is-selected" : ""}`} key={document.record_id} aria-pressed={selected === document.record_id} onClick={() => setSelected(document.record_id)}>
                <Icon name="table" size={17} /><span><strong title={document.table_name}>{document.table_name}</strong><small>{document.schema_name || "默认 Schema"} · {document.column_count} 个字段</small><em>{document.active ? "有效" : "已停用"} · {comparisons[document.comparison] ?? "待核对"}</em></span><Icon name="chevron" size={12} />
              </button>) : <div className="cache-browser__empty"><Icon name="layers" size={28} /><strong>{data?.can_browse ? "当前范围没有文档" : "文档暂不可浏览"}</strong><p>{data?.can_browse ? "调整关键词，或将 SQLite 元数据同步至当前 Collection。" : data?.message}</p></div>}
          </div>
          <div className="cache-browser__pagination"><span>{data?.can_browse ? data.browse_total ? `${offset + 1}–${Math.min(offset + 30, data.browse_total)}` : "0" : "—"}</span><div>
            <button type="button" aria-label="上一页 Milvus 文档" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}><Icon name="chevron" className="cache-chevron-back" size={14} /></button>
            <button type="button" aria-label="下一页 Milvus 文档" disabled={loading || offset + 30 >= (data?.browse_total ?? 0)} onClick={() => setOffset(offset + 30)}><Icon name="chevron" size={14} /></button>
          </div></div>
        </aside>
        <div className="cache-browser__detail" aria-label="Milvus 文档详情" aria-busy={detailLoading || loading}>
          {loading || (selectedDocument && !current && !detailError) ? <div className="cache-browser__empty"><Icon name="refresh" className="is-spinning" size={24} /><span>正在读取索引内容…</span></div>
            : !selectedDocument ? <div className="cache-browser__empty"><Icon name="layers" size={34} /><strong>从左侧选择一条文档</strong><p>在这里查看 Milvus 实际存储的完整表结构文本。</p></div>
              : detailError ? <div className="cache-browser__empty cache-browser__error" role="alert"><Icon name="alert" size={24} /><p>{detailError}</p><button type="button" className="action-button" onClick={() => setReload((value) => value + 1)}>刷新重试</button></div>
                : current && <>
                  <div className="cache-detail__heading"><span className="cache-detail__icon"><Icon name="layers" size={21} /></span><div><span>{current.schema_name}</span><h3>{current.table_name}</h3><p>{comparisons[current.comparison] ?? "待核对"} · {current.active ? "有效文档" : "已停用"}</p></div><small>{current.column_count} 个字段</small></div>
                  <div className="cache-detail__tools"><span><Icon name="clock" size={13} />写入时间 {date(current.updated_at)}</span><span><Icon name={current.content_hash_valid ? "check" : "alert"} size={13} />文档指纹{current.content_hash_valid ? "有效" : "异常"}</span></div>
                  <pre className="milvus-document-text">{current.document_text}</pre>
                  <details className="milvus-document-identifiers"><summary>查看文档标识与内容指纹</summary><dl><dt>文档 ID</dt><dd>{current.record_id}</dd><dt>内容指纹</dt><dd>{current.content_hash}</dd></dl></details>
                </>}
        </div>
      </div>}
  </section>;
}
