import { useEffect, useRef, useState } from "react";
import { getCachedTable, getCachedTables, type CachedTable, type CacheTable, type CacheTables } from "../api/metadata";
import { Icon } from "./Icon";
import { checkSqlite, type CacheCheck } from "../api/inspection";
import { MetadataInspectionReport } from "./MetadataInspectionReport";
import "../styles/metadata-cache.css";

const tableKey = (table: Pick<CachedTable, "schema_name" | "table_name">) => JSON.stringify([table.schema_name, table.table_name]);
const number = (value: number) => value.toLocaleString("zh-CN");

function date(value?: string | null) {
  if (!value) return "尚无记录";
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? value : time.toLocaleString("zh-CN", { hour12: false });
}

function nullable(value: string | null) {
  if (!value) return "—";
  if (["N", "NO", "0", "FALSE"].includes(value.toUpperCase())) return "否";
  if (["Y", "YES", "1", "TRUE"].includes(value.toUpperCase())) return "是";
  return value;
}

export function MetadataCacheBrowser({ enabled, refreshKey }: { enabled: boolean; refreshKey?: number }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [schema, setSchema] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [data, setData] = useState<CacheTables | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<CacheTable | null>(null);
  const [detailSource, setDetailSource] = useState<CacheTables | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [fieldQuery, setFieldQuery] = useState("");
  const [check, setCheck] = useState<CacheCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState("");
  const checkRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    checkRequest.current?.abort();
    setChecking(false); setCheck(null); setCheckError("");
    return () => checkRequest.current?.abort();
  }, [enabled, reload, refreshKey]);

  async function inspectCache() {
    const controller = new AbortController();
    checkRequest.current = controller;
    setChecking(true); setCheck(null); setCheckError("");
    try {
      const result = await checkSqlite(controller.signal);
      if (!controller.signal.aborted) setCheck(result);
    } catch (reason) {
      if (!controller.signal.aborted) setCheckError(reason instanceof Error ? reason.message : "检查未完成。");
    } finally {
      if (!controller.signal.aborted) setChecking(false);
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => { setSearch(query.trim()); setOffset(0); }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    getCachedTables({ q: search, schema, offset }, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      if (offset > 0 && offset >= result.matched_tables) { setOffset(0); return; }
      setData(result);
      setSelected((previous) => result.tables.some((table) => tableKey(table) === previous)
        ? previous : result.tables[0] ? tableKey(result.tables[0]) : "");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "暂时无法读取缓存。");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [enabled, search, schema, offset, reload, refreshKey]);

  useEffect(() => {
    if (!enabled || loading || error) return;
    const table = data?.tables.find((item) => tableKey(item) === selected);
    setDetail(null);
    setDetailError("");
    setFieldQuery("");
    if (!table) return;
    const controller = new AbortController();
    setDetailLoading(true);
    getCachedTable(table, controller.signal).then((result) => {
      if (!controller.signal.aborted) { setDetail(result); setDetailSource(data); }
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) setDetailError(reason instanceof Error ? reason.message : "无法读取字段。");
    }).finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [enabled, data, selected, loading, error]);

  const currentDetail = detail && detailSource === data && tableKey(detail) === selected ? detail : null;
  const waitingForDetail = detailLoading || (!currentDetail && !detailError);
  const visibleColumns = currentDetail?.columns.filter((column) =>
    `${column.column_name} ${column.column_comment ?? ""}`.toLocaleLowerCase().includes(fieldQuery.trim().toLocaleLowerCase())) ?? [];
  const selectedTable = data?.tables.find((table) => tableKey(table) === selected);
  const stats = data && [
    [number(data.total_tables), "张表"],
    [number(data.total_columns), "个字段"],
    [number(data.schemas.length), "个 Schema"],
  ];

  return <section className="cache-browser" aria-labelledby="cache-browser-title">
    <header className="cache-browser__header">
      <div>
        <div className="cache-browser__eyebrow"><Icon name="database" size={14} /> SQLITE SNAPSHOT</div>
        <h2 id="cache-browser-title">已缓存的表结构</h2>
        <p>直接查看本地缓存中的表、字段与注释。</p>
      </div>
      <div className="metadata-inspection-actions"><button type="button" className="action-button" disabled={loading || checking} onClick={() => void inspectCache()}>
        <Icon name={checking ? "refresh" : "shield"} size={15} className={checking ? "is-spinning" : ""} />{checking ? "检查中…" : "检查 SQLite"}
      </button><button type="button" className="action-button" disabled={loading} onClick={() => setReload((value) => value + 1)}>
        <Icon name="refresh" size={15} className={loading ? "is-spinning" : ""} />刷新列表
      </button></div>
    </header>
    <div className="cache-browser__overview" aria-live="polite">
      <div className="cache-browser__stats">{stats ? stats.map(([value, label]) => <span key={label}><strong>{value}</strong>{label}</span>) : <span>正在读取缓存概况…</span>}</div>
      <div className="cache-browser__source">{data?.cache_file && <code title={data.cache_file}>{data.cache_file}</code>}<span>最近更新 {date(data?.last_synced_at)}</span></div>
    </div>
    {check && <MetadataInspectionReport message={check.message} checks={check.checks} />}
    {checkError && <div className="metadata-inspection-notice metadata-inspection-notice--warning" role="alert">{checkError}</div>}
    <div className="cache-browser__toolbar">
      <label className="cache-search"><Icon name="search" size={16} /><input aria-label="搜索缓存表" value={query} maxLength={200} onChange={(event) => setQuery(event.target.value)} placeholder="搜索表名、表注释或字段" /><kbd>搜索</kbd></label>
      <select aria-label="筛选 Schema" value={schema === null ? "all" : JSON.stringify(schema)} onChange={(event) => { setSchema(event.target.value === "all" ? null : JSON.parse(event.target.value)); setOffset(0); }}>
        <option value="all">全部 Schema</option>
        {data?.schemas.map((name) => <option key={name} value={JSON.stringify(name)}>{name || "默认 Schema"}</option>)}
      </select>
    </div>
    {error ? <div className="cache-browser__empty cache-browser__error" role="alert"><Icon name="alert" size={24} /><strong>缓存暂时无法读取</strong><p>{error}</p><button type="button" className="action-button" onClick={() => setReload((value) => value + 1)}>重新加载</button></div>
      : <div className="cache-browser__body" aria-busy={loading}>
        <aside className="cache-browser__tables" aria-label="缓存表列表">
          <div className="cache-browser__list-heading"><span>表目录</span><span>{loading ? "读取中…" : `${number(data?.matched_tables ?? 0)} 张${search || schema !== null ? "匹配" : "表"}`}</span></div>
          <div className="cache-browser__table-list">
            {loading ? <div className="cache-browser__empty"><Icon name="refresh" className="is-spinning" size={22} /><span>正在读取本地表目录…</span></div>
              : data?.tables.length ? data.tables.map((table) => <button type="button" className={`cache-table-item ${selected === tableKey(table) ? "is-selected" : ""}`} key={tableKey(table)} aria-pressed={selected === tableKey(table)} onClick={() => setSelected(tableKey(table))}>
                <Icon name="table" size={17} /><span><strong title={table.table_name}>{table.table_name}</strong><small title={table.table_comment}>{table.table_comment || "暂无表注释"}</small><em>{table.schema_name || "默认 Schema"} · {table.column_count} 个字段</em></span><Icon name="chevron" size={12} />
              </button>) : <div className="cache-browser__empty"><Icon name="search" size={25} /><strong>{data?.total_tables ? "没有匹配的表" : "还没有缓存表结构"}</strong><p>{data?.total_tables ? "试试表名、业务注释或字段名称。" : "先同步 SQLite 缓存，再查看表与字段。"}</p></div>}
          </div>
          <div className="cache-browser__pagination"><span>{data?.matched_tables ? `${offset + 1}–${Math.min(offset + 30, data.matched_tables)}` : "0"}</span><div><button type="button" aria-label="上一页缓存表" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}><Icon name="chevron" className="cache-chevron-back" size={14} /></button><button type="button" aria-label="下一页缓存表" disabled={loading || offset + 30 >= (data?.matched_tables ?? 0)} onClick={() => setOffset(offset + 30)}><Icon name="chevron" size={14} /></button></div></div>
        </aside>
        <div className="cache-browser__detail" aria-label="缓存字段详情" aria-busy={detailLoading || loading}>
          {loading ? <div className="cache-browser__empty"><Icon name="refresh" className="is-spinning" size={24} /><span>正在更新缓存视图…</span></div>
            : !selectedTable ? <div className="cache-browser__empty"><Icon name="table" size={34} /><strong>从左侧选择一张表</strong><p>在这里查看缓存中的完整字段结构。</p></div>
              : <>
                <div className="cache-detail__heading"><span className="cache-detail__icon"><Icon name="table" size={21} /></span><div><span>{selectedTable.schema_name || "默认 Schema"}</span><h3>{selectedTable.table_name}</h3><p>{selectedTable.table_comment || "该表暂无注释"}</p></div><small>{selectedTable.column_count} 个字段</small></div>
                <div className="cache-detail__tools"><span><Icon name="clock" size={13} />{date(currentDetail?.synced_at ?? selectedTable.synced_at)}</span><label><Icon name="search" size={14} /><input aria-label="筛选当前表字段" value={fieldQuery} onChange={(event) => setFieldQuery(event.target.value)} placeholder="筛选字段或注释" /></label></div>
                {waitingForDetail ? <div className="cache-browser__empty"><Icon name="refresh" size={22} className="is-spinning" /><span>正在读取字段…</span></div>
                  : detailError ? <div className="cache-browser__empty cache-browser__error" role="alert"><Icon name="alert" size={23} /><p>{detailError}</p><button className="action-button" type="button" onClick={() => setReload((value) => value + 1)}>刷新重试</button></div>
                    : <div className="cache-detail__fields"><table><thead><tr><th>字段名</th><th>数据类型</th><th>长度</th><th>可空</th><th>字段注释</th></tr></thead><tbody>{visibleColumns.map((column, index) => <tr key={`${column.column_name}-${index}`}><td><code>{column.column_name}</code></td><td>{column.data_type || "—"}</td><td>{column.data_length || "—"}</td><td>{nullable(column.is_nullable)}</td><td>{column.column_comment || <span className="cache-detail__muted">暂无注释</span>}</td></tr>)}</tbody></table>{!visibleColumns.length && <div className="cache-browser__empty"><span>{currentDetail?.columns.length ? "没有匹配的字段" : "该表尚未缓存字段信息，请重新同步 SQLite 缓存。"}</span></div>}</div>}
              </>}
        </div>
      </div>}
  </section>;
}
