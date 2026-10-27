function escapeCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  let s = typeof value === "object" ? JSON.stringify(value) : String(value);
  // Spreadsheet applications interpret these strings as formulas or rounded numbers.
  if (typeof value === "string" && (/^[\s]*[=+@\t\r]/.test(s) || /^\s*-/.test(s) || /^\d+(\.\d+)?([eE][+-]?\d+)?$/.test(s))) s = "'" + s;
  if (
    s.includes(",") ||
    s.includes('"') ||
    s.includes("\n") ||
    s.includes("\r")
  ) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function exportToCsv(
  columns: string[],
  rows: Record<string, unknown>[],
  filename = "query-result.csv",
): void {
  downloadBlob(new Blob([buildCsv(columns, rows)], { type: "text/csv;charset=utf-8;" }), filename);
}

export function buildCsv(columns: string[], rows: Record<string, unknown>[]): string {
  const header = columns.map(escapeCell).join(",");
  const body = rows
    .map((row) => columns.map((col) => escapeCell(row[col])).join(","))
    .join("\n");
  const bom = "\uFEFF";
  return bom + header + "\r\n" + body;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function exportJson(value: unknown, filename = "query-result.json"): void {
  downloadBlob(new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" }), filename);
}

function formatExportTimestamp(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
}

export function defaultCsvFilename(): string {
  return `query-result-${formatExportTimestamp()}.csv`;
}
