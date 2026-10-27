import { useMemo, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import type { ColumnDataType, DataFrameComponent } from "../types";
import { defaultCsvFilename, exportToCsv, exportJson } from "../utils/exportCsv";
import { RowDetailModal } from "./RowDetailModal";
import { compareNumericText } from "../utils/numeric";

const PAGE_SIZE = 25;

function formatCell(value: unknown, type: ColumnDataType): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  if (type === "number" && typeof value === "number") {
    return String(value);
  }
  if (type === "boolean") return value ? "是" : "否";
  if (type === "datetime" && typeof value === "string") {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) return date.toLocaleString("zh-CN");
  }
  return String(value);
}

interface QueryResultTableProps {
  data: DataFrameComponent;
}

export function QueryResultTable({ data }: QueryResultTableProps) {
  const [globalFilter, setGlobalFilter] = useState("");
  const [sorting, setSorting] = useState<SortingState>([]);
  const [exportScope, setExportScope] = useState("filtered");
  const [exportFormat, setExportFormat] = useState("csv");
  const [exportNotice, setExportNotice] = useState("");
  const [selectedRow, setSelectedRow] = useState<Record<
    string,
    unknown
  > | null>(null);

  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      data.columns.map((column) => ({
        id: column.name,
        accessorFn: (row) => row[column.name],
        sortingFn: column.numeric_encoding === "exact_string" ? (a, b) => compareNumericText(a.original[column.name], b.original[column.name]) : "auto",
        header: () => (
          <span className="result-table__column">
            <span title={column.source_name ?? column.name}>{column.name}</span>
            <small>{column.data_type}</small>
          </span>
        ),
        cell: (info) => {
          const value = info.getValue();
          const formatted = formatCell(value, column.data_type);
          return (
            <span
              className={`result-table__cell result-table__cell--${column.data_type}${
                value == null ? " result-table__cell--null" : ""
              }`}
              title={formatted}
            >
              {formatted}
            </span>
          );
        },
      })),
    [data.columns],
  );

  const table = useReactTable({
    data: data.rows,
    columns,
    state: { globalFilter, sorting },
    onGlobalFilterChange: setGlobalFilter,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: PAGE_SIZE } },
    globalFilterFn: (row, columnId, filter: string) => {
      const value = row.getValue(columnId);
      const text =
        value == null
          ? "null"
          : typeof value === "object"
            ? JSON.stringify(value)
            : String(value);
      return text.toLocaleLowerCase().includes(filter.toLocaleLowerCase());
    },
  });

  const handleExport = () => {
    const filtered = exportScope === "loaded" ? data.rows :
      (exportScope === "page" ? table.getRowModel() : table.getSortedRowModel()).rows.map((r) => r.original);
    if (exportFormat === "json") exportJson({ columns: data.columns, rows: filtered, sql: data.sql,
      exported_rows: filtered.length, loaded_rows: data.displayed_row_count, truncated: data.truncated,
      row_count_is_exact: data.row_count_is_exact, exported_at: new Date().toISOString() }, defaultCsvFilename().replace(/csv$/, "json"));
    else exportToCsv(
      data.columns.map((column) => column.name),
      filtered,
      defaultCsvFilename(),
    );
    setExportNotice(`已导出 ${filtered.length} 行${data.truncated ? "；仅含已加载数据，查询结果未完整取回" : ""}。${exportFormat === "csv" ? "CSV 已防护公式和长数字；需要原始值时请选择 JSON。" : ""}`);
  };

  return (
    <div className="result-table">
      <div className="result-table__toolbar">
        <input
          type="search"
          className="result-table__search"
          placeholder="搜索所有列…"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          aria-label="搜索表格"
        />
        <div className="result-table__meta">
          {data.row_count_is_exact ? "共" : "已取回至少"} {data.row_count} 行
          {data.truncated && ` · 当前展示前 ${data.displayed_row_count} 行`}
          {globalFilter &&
            ` · 筛选后 ${table.getFilteredRowModel().rows.length} 行`}
        </div>
        <select aria-label="导出范围" value={exportScope} onChange={e => setExportScope(e.target.value)}>
          <option value="filtered">筛选和排序后</option><option value="loaded">全部已加载数据</option><option value="page">当前页</option>
        </select>
        <select aria-label="导出格式" value={exportFormat} onChange={e => setExportFormat(e.target.value)}><option value="csv">CSV</option><option value="json">JSON 原始数据</option></select>
        <button disabled={!data.rows.length}
          type="button"
          className="result-table__export"
          onClick={handleExport}
        >
          导出数据
        </button>
      </div>
      {(exportNotice || data.truncated) && <p className="chart-panel__note" role="status">{exportNotice || "当前是受限结果集，筛选、排序与导出仅覆盖已加载数据。"}</p>}

      {data.rows.length === 0 ? (
        <p className="result-table__empty">查询未返回任何行。</p>
      ) : (
        <>
          <div className="result-table__scroll">
            <table className="result-table__table">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id}>
                    {hg.headers.map((header) => (
                      <th
                        key={header.id}
                        aria-sort={
                          header.column.getIsSorted() === "asc"
                            ? "ascending"
                            : header.column.getIsSorted() === "desc"
                              ? "descending"
                              : "none"
                        }
                        className={
                          header.column.getCanSort()
                            ? "result-table__th--sortable"
                            : ""
                        }
                      >
                        <button
                          type="button"
                          className="result-table__sort"
                          onClick={header.column.getToggleSortingHandler()}
                          disabled={!header.column.getCanSort()}
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          <span aria-hidden="true">
                            {{ asc: "↑", desc: "↓" }[
                              header.column.getIsSorted() as string
                            ] ?? "↕"}
                          </span>
                        </button>
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {table.getRowModel().rows.length === 0 && (
                  <tr>
                    <td
                      colSpan={data.columns.length}
                      className="result-table__no-match"
                    >
                      没有匹配的记录，请尝试其他搜索词。
                    </td>
                  </tr>
                )}
                {table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className="result-table__row"
                    onClick={() => setSelectedRow(row.original)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedRow(row.original);
                      }
                    }}
                    aria-label="查看行详情"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="result-table__pagination">
            <button
              type="button"
              disabled={!table.getCanPreviousPage()}
              onClick={() => table.previousPage()}
            >
              上一页
            </button>
            <span>
              第 {table.getState().pagination.pageIndex + 1} /{" "}
              {Math.max(1, table.getPageCount())} 页
            </span>
            <button
              type="button"
              disabled={!table.getCanNextPage()}
              onClick={() => table.nextPage()}
            >
              下一页
            </button>
          </div>
        </>
      )}

      <RowDetailModal
        row={selectedRow}
        columns={data.columns.map((column) => column.name)}
        onClose={() => setSelectedRow(null)}
      />
    </div>
  );
}
