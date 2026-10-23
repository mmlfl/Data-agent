import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

interface RowDetailModalProps {
  row: Record<string, unknown> | null;
  columns: string[];
  onClose: () => void;
}

export function RowDetailModal({ row, columns, onClose }: RowDetailModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (!row) return;
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
    };
  }, [row]);

  if (!row) return null;

  const formatValue = (value: unknown): string => {
    if (value === null || value === undefined) return "—";
    if (typeof value === "object") return JSON.stringify(value, null, 2);
    return String(value);
  };

  return createPortal(
    <dialog
      ref={dialogRef}
      className="modal"
      aria-modal="true"
      aria-labelledby="row-detail-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target !== e.currentTarget) return;
        const bounds = e.currentTarget.getBoundingClientRect();
        if (
          e.clientX < bounds.left ||
          e.clientX > bounds.right ||
          e.clientY < bounds.top ||
          e.clientY > bounds.bottom
        )
          onClose();
      }}
    >
      <div className="modal__header">
        <h3 id="row-detail-title" className="modal__title">
          行详情
        </h3>
        <button
          type="button"
          className="modal__close"
          onClick={onClose}
          aria-label="关闭"
        >
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
    </dialog>,
    document.body,
  );
}
