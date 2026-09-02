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
import { defaultCsvFilename, exportToCsv } from "../utils/exportCsv";
import { RowDetailModal } from "./RowDetailModal";

const PAGE_SIZE = 25;

function formatCell(value: unknown, type: ColumnDataType): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  if (type === "number" && typeof value === "number") {
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 6 }).format(value);
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
  const [selectedRow, setSelectedRow] = useState<Record<string, unknown> | null>(null);

  const columns = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      data.columns.map((column) => ({
        accessorKey: column.name,
        header: () => (
          <span className="result-table__column">
            <span>{column.name}</span>
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
    globalFilterFn: "includesString",
  });

  const handleExport = () => {
    const filtered = table.getFilteredRowModel().rows.map((r) => r.original);
    exportToCsv(
      data.columns.map((column) => column.name),
      filtered,
      defaultCsvFilename(),
    );
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
          共 {data.row_count} 行
          {data.truncated && ` · 当前展示前 ${data.displayed_row_count} 行`}
          {globalFilter && ` · 筛选后 ${table.getFilteredRowModel().rows.length} 行`}
        </div>
        <button type="button" className="result-table__export" onClick={handleExport}>
          导出当前展示
        </button>
      </div>

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
                        onClick={header.column.getToggleSortingHandler()}
                        className={header.column.getCanSort() ? "result-table__th--sortable" : ""}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {{
                          asc: " ↑",
                          desc: " ↓",
                        }[header.column.getIsSorted() as string] ?? null}
                      </th>
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
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
                    role="button"
                    aria-label="查看行详情"
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
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
              第 {table.getState().pagination.pageIndex + 1} / {table.getPageCount()} 页
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
