import { useEffect, useRef } from "react";

interface RowDetailModalProps {
  row: Record<string, unknown> | null;
  columns: string[];
  onClose: () => void;
}

export function RowDetailModal({ row, columns, onClose }: RowDetailModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!row) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [row, onClose]);

  if (!row) return null;

  const formatValue = (value: unknown): string => {
    if (value === null || value === undefined) return "—";
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  };

  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="row-detail-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal__header">
          <h3 id="row-detail-title" className="modal__title">
            行详情
          </h3>
          <button type="button" className="modal__close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <dl className="modal__fields">
          {columns.map((col) => (
            <div key={col} className="modal__field">
              <dt className="modal__label">{col}</dt>
              <dd className="modal__value">{formatValue(row[col])}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
